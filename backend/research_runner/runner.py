"""Dedicated, no-network research execution process.

This process is intended to run only in the locked-down `research-runner`
container. It receives pre-materialised JSON inputs and never imports platform
configuration, connects to a provider, or receives credentials.
"""

from __future__ import annotations

import json
import math
import os
import resource
import signal
import time
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

import numpy as _numpy
import pandas as _pandas

from research_runner.curated import SCIPY, STATSMODELS
from research_runner.validation import validate_workstation_python

try:  # The isolated image receives this file through Dockerfile.research-runner.
    from research_runner.canonical_indicators import (
        OHLCVSeries as _CanonicalOHLCVSeries,
        compute_indicator as _compute_canonical_indicator,
        normalize_indicator_params as _normalize_canonical_indicator_params,
    )
except ImportError:  # Local unit tests run from the application source tree.
    from app.services.indicators import (
        OHLCVSeries as _CanonicalOHLCVSeries,
        compute_indicator as _compute_canonical_indicator,
        normalize_indicator_params as _normalize_canonical_indicator_params,
    )

JOB_DIR = Path(os.environ.get("RESEARCH_JOB_DIR", "/jobs"))
RESULT_DIR = Path(os.environ.get("RESEARCH_RESULT_DIR", "/results"))
MAX_SECONDS = int(os.environ.get("RESEARCH_MAX_SECONDS", "15"))
MAX_MEMORY_BYTES = int(os.environ.get("RESEARCH_MAX_MEMORY_BYTES", str(512 * 1024 * 1024)))
MAX_OUTPUT_BYTES = int(os.environ.get("RESEARCH_MAX_OUTPUT_BYTES", str(8 * 1024 * 1024)))
MAX_OUTPUT_ROWS = int(os.environ.get("RESEARCH_MAX_OUTPUT_ROWS", "10000"))
MAX_OUTPUT_ARTIFACTS = int(os.environ.get("RESEARCH_MAX_OUTPUT_ARTIFACTS", "128"))
MAX_JOB_BYTES = int(os.environ.get("RESEARCH_MAX_JOB_BYTES", str(64 * 1024 * 1024)))

_SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


def _materialize(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_materialize(item) for item in value]
    if isinstance(value, _DataFrame):
        return _materialize(value.to_dict())
    if isinstance(value, _Series):
        return _materialize(value.tolist())
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if hasattr(value, "tolist") and callable(value.tolist):
        try:
            return _materialize(value.tolist())
        except (TypeError, ValueError):
            pass
    return value


def _limit_resources() -> dict[int, tuple[int, int]]:
    # macOS does not implement every rlimit enforced by the Linux deployment
    # container. Failure here is tolerated only for local unit execution; the
    # compose service independently supplies cgroup/read-only/no-network limits.
    previous: dict[int, tuple[int, int]] = {}
    for limit, value in (
        (resource.RLIMIT_CPU, (MAX_SECONDS, MAX_SECONDS + 1)),
        (resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES)),
    ):
        try:
            current = resource.getrlimit(limit)
            previous[limit] = current
            hard_limit = current[1]
            soft_limit = value[0]
            if limit == resource.RLIMIT_CPU:
                cpu_used = resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime
                # RLIMIT_CPU is an absolute process CPU-time limit, not a
                # duration. Offset it from already-consumed CPU time so local
                # test callers cannot inherit an immediately-expired limit.
                soft_limit = math.ceil(cpu_used + value[0])
            if hard_limit != resource.RLIM_INFINITY:
                soft_limit = min(soft_limit, hard_limit)
            # Keep the existing hard boundary. Lowering a process hard limit would
            # make restoration impossible for an unprivileged worker/test process.
            resource.setrlimit(limit, (soft_limit, hard_limit))
        except (OSError, ValueError):
            continue
    return previous


def _restore_resources(previous: dict[int, tuple[int, int]]) -> None:
    for limit, value in previous.items():
        try:
            resource.setrlimit(limit, value)
        except (OSError, ValueError):
            # The deployment container owns the hard cgroup boundary. Local test
            # environments may refuse restoration of an unsupported limit.
            continue


def _timeout(_signal, _frame) -> None:
    raise TimeoutError("research execution wall-time limit exceeded")


def _dashboard_reference_error(outputs: dict[str, object]) -> str | None:
    """Return a diagnostic for a dashboard that references an unavailable artifact."""
    for dashboard_name, artifact in outputs.items():
        if not isinstance(artifact, dict) or artifact.get("type") != "dashboard":
            continue
        value = artifact.get("value")
        panels = value.get("panels") if isinstance(value, dict) else None
        if not isinstance(panels, list):
            return f"dashboard {dashboard_name!r} has an invalid panel list"
        for panel in panels:
            reference = panel.get("artifact") if isinstance(panel, dict) else None
            if not isinstance(reference, str) or reference not in outputs:
                return f"dashboard {dashboard_name!r} references unavailable artifact {reference!r}"
            if reference == dashboard_name:
                return f"dashboard {dashboard_name!r} cannot reference itself"
    return None


def execute_job(
    job: dict,
    *,
    progress_callback: Callable[[dict], None] | None = None,
    cancellation_check: Callable[[], bool] | None = None,
) -> dict:
    source = str(job["source"])
    validation = validate_workstation_python(source)
    if not validation.valid:
        return {
            "status": "failed",
            "diagnostics": [item.__dict__ for item in validation.diagnostics],
        }
    datasets = job.get("dataset", {}).get("datasets")
    if isinstance(datasets, list):
        if str(job.get("output_contract") or "") == "study":
            return _execute_single(source, job.get("dataset", {}), job)
        return _execute_batch(
            source,
            datasets,
            str(job.get("output_contract") or ""),
            job,
            output_name=str(job.get("output_name") or "") or None,
            progress_callback=progress_callback,
            cancellation_check=cancellation_check,
        )
    return _execute_single(source, job.get("dataset", {}), job)


def _execute_single(
    source: str,
    dataset: dict,
    hash_input: dict,
    *,
    manage_timeout: bool = True,
) -> dict:
    # The SDK is injected as immutable data/callables by the future materialiser.
    # No Python builtins, imports, filesystem APIs, sockets, or process APIs are exposed.
    parameters = hash_input.get("parameters", {})
    if not isinstance(parameters, dict):
        return {"status": "failed", "diagnostics": [{"code": "invalid_parameters", "message": "research parameters must be a JSON object"}]}
    outputs: dict[str, object] = {}
    safe_globals = {
        "__builtins__": _SAFE_BUILTINS,
        "output": _Output(outputs, dataset),
        "dataset": dataset,
        "parameters": parameters,
        "benchmark": dataset.get("benchmark_dataset"),
        "market": _Market(dataset),
        "ta": _Ta(dataset),
        "stats": _Stats(),
        "research": _Research(),
        "np": _NumpyFacade(),
        "pd": _PandasFacade(),
        "scipy": SCIPY,
        "statsmodels": STATSMODELS,
    }
    previous_limits: dict[int, tuple[int, int]] = {}
    previous_alarm_handler = None
    if manage_timeout:
        previous_limits = _limit_resources()
        previous_alarm_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _timeout)
        signal.alarm(MAX_SECONDS)
    started = time.monotonic()
    try:
        exec(compile(source, "<research>", "exec"), safe_globals, {})  # noqa: S102 - locked runner only
    except TimeoutError:
        # A batch owns one wall-clock budget. Do not turn its alarm into a
        # per-cell failure and then continue running the remaining universe.
        if not manage_timeout:
            raise
        return {"status": "failed", "diagnostics": [{"code": "wall_time_limit", "message": "research execution wall-time limit exceeded"}]}
    except MemoryError:
        return {"status": "failed", "diagnostics": [{"code": "memory_limit", "message": "research execution exceeded the configured memory limit"}]}
    except Exception as exc:
        return {"status": "failed", "diagnostics": [{"code": "runtime_error", "message": str(exc)}]}
    finally:
        if manage_timeout:
            signal.alarm(0)
            if previous_alarm_handler is not None:
                signal.signal(signal.SIGALRM, previous_alarm_handler)
            _restore_resources(previous_limits)
    dashboard_error = _dashboard_reference_error(outputs)
    if dashboard_error:
        return {"status": "failed", "diagnostics": [{"code": "dashboard_reference_error", "message": dashboard_error}]}
    try:
        serialized_artifacts = json.dumps(outputs, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        return {"status": "failed", "diagnostics": [{"code": "output_serialization_error", "message": str(exc)}]}
    if len(serialized_artifacts.encode()) > MAX_OUTPUT_BYTES:
        return {
            "status": "failed",
            "diagnostics": [{"code": "output_size_limit", "message": "research output exceeds the configured byte limit"}],
        }
    return {
        "status": "completed",
        "artifacts": outputs,
        "resource_usage": {"wall_ms": round((time.monotonic() - started) * 1000, 3)},
        "reproducibility_hash": sha256(json.dumps(hash_input, sort_keys=True).encode()).hexdigest(),
    }


def _execute_batch(
    source: str,
    datasets: list[object],
    output_contract: str,
    hash_input: dict,
    output_name: str | None = None,
    *,
    progress_callback: Callable[[dict], None] | None = None,
    cancellation_check: Callable[[], bool] | None = None,
) -> dict:
    if output_contract not in {"scalar", "boolean", "events"}:
        return {"status": "failed", "diagnostics": [{"code": "batch_output_contract_unsupported", "message": "Batch execution requires scalar, boolean, or events output."}]}
    cells: list[dict] = []
    started = time.monotonic()
    total = len(datasets)
    if progress_callback:
        progress_callback({"completed_cells": 0, "total_cells": total, "status": "running"})
    previous_limits = _limit_resources()
    previous_alarm_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(MAX_SECONDS)
    try:
        for candidate in datasets:
            if cancellation_check and cancellation_check():
                return {
                    "status": "canceled",
                    "diagnostics": [{"code": "batch_canceled", "message": "prepared-universe batch canceled"}],
                    "artifacts": {"batch_cells": {"type": "batch", "value": {"cells": cells}}},
                    "resource_usage": {"cell_count": len(cells), "wall_ms": round((time.monotonic() - started) * 1000, 3)},
                }
            if not isinstance(candidate, dict):
                continue
            instrument_id = candidate.get("instrument_id")
            symbol = str(candidate.get("symbol") or "").upper()
            if not isinstance(instrument_id, int) or not symbol:
                continue
            result = _execute_single(
                source,
                candidate,
                {"source": source, "dataset": candidate, "output_contract": output_contract, "parameters": hash_input.get("parameters", {})},
                manage_timeout=False,
            )
            if result.get("status") != "completed":
                diagnostics = result.get("diagnostics", [])
                message = diagnostics[0].get("message") if diagnostics and isinstance(diagnostics[0], dict) else "Batch cell failed"
                cells.append({"instrument_id": instrument_id, "symbol": symbol, "status": "failed", "error": message})
                continue
            matches = [
                artifact for name, artifact in result.get("artifacts", {}).items()
                if isinstance(artifact, dict)
                and artifact.get("type") == output_contract
                and (output_name is None or name == output_name)
            ]
            if len(matches) != 1:
                cells.append({"instrument_id": instrument_id, "symbol": symbol, "status": "failed", "error": f"Expected exactly one {output_contract} output."})
                continue
            value = matches[0].get("value")
            if output_contract == "scalar" and (not isinstance(value, int | float) or isinstance(value, bool)):
                cells.append({"instrument_id": instrument_id, "symbol": symbol, "status": "failed", "error": "Scalar output must be numeric."})
                continue
            cells.append({"instrument_id": instrument_id, "symbol": symbol, "status": "completed", "value": value})
            if progress_callback and (len(cells) == total or len(cells) % 50 == 0):
                progress_callback({"completed_cells": len(cells), "total_cells": total, "status": "running"})
    except TimeoutError:
        return {
            "status": "failed",
            "diagnostics": [{"code": "batch_wall_time_limit", "message": "prepared-universe batch wall-time limit exceeded"}],
            "artifacts": {"batch_cells": {"type": "batch", "value": {"cells": cells}}},
            "resource_usage": {"cell_count": len(cells), "wall_ms": round((time.monotonic() - started) * 1000, 3)},
        }
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_alarm_handler)
        _restore_resources(previous_limits)
    return {
        "status": "completed",
        "artifacts": {"batch_cells": {"type": "batch", "value": {"cells": cells}}},
        "resource_usage": {"cell_count": len(cells), "wall_ms": round((time.monotonic() - started) * 1000, 3)},
        "reproducibility_hash": sha256(json.dumps(hash_input, sort_keys=True).encode()).hexdigest(),
    }


class _Output:
    def __init__(self, values: dict[str, object], dataset: dict) -> None:
        self.values = values
        self.dataset = dataset

    @staticmethod
    def _validate_name(name: str) -> str:
        if not isinstance(name, str) or not name or len(name) > 128:
            raise ValueError("output names must be non-empty strings of at most 128 characters")
        return name

    @staticmethod
    def _row_count(value: object) -> int:
        if isinstance(value, list | tuple):
            return len(value)
        if isinstance(value, dict):
            return sum(_Output._row_count(item) for item in value.values())
        return 0

    def _store(self, name: str, artifact: dict[str, object]) -> None:
        key = self._validate_name(name)
        if len(self.values) >= MAX_OUTPUT_ARTIFACTS and key not in self.values:
            raise ValueError("research output artifact limit exceeded")
        if self._row_count(artifact.get("value")) > MAX_OUTPUT_ROWS:
            raise ValueError("research output row limit exceeded")
        self.values[key] = artifact

    def scalar(self, name: str, value: object) -> None:
        self._store(name, {"type": "scalar", "value": _materialize(value)})

    def series(self, name: str, value: object) -> None:
        materialized = _materialize(value)
        values = list(materialized) if isinstance(materialized, list | tuple) else materialized
        timestamps = self.dataset.get("timestamps", [])
        if (
            isinstance(values, list)
            and isinstance(timestamps, list)
            and len(timestamps) == len(values)
        ):
            self._store(name, {
                "type": "series",
                "value": {"timestamps": timestamps, "values": values},
            })
        else:
            self._store(name, {"type": "series", "value": values})

    def boolean(self, name: str, value: object) -> None:
        value = _materialize(value)
        if not isinstance(value, bool):
            raise ValueError("boolean output must be true or false")
        self._store(name, {"type": "boolean", "value": value})

    def table(self, name: str, value: object) -> None:
        self._store(name, {"type": "table", "value": _materialize(value)})

    def bar(self, name: str, labels: object, values: object) -> None:
        """Emit a bounded categorical/numeric bar series for Study Lab renderers."""
        raw_labels = _materialize(labels)
        raw_values = _materialize(values)
        if not isinstance(raw_labels, list | tuple) or not isinstance(raw_values, list | tuple):
            raise ValueError("bar labels and values must be lists")
        if len(raw_labels) != len(raw_values) or not raw_labels:
            raise ValueError("bar labels and values must be non-empty and have the same length")
        normalized_values = [
            float(value)
            for value in raw_values
            if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(float(value))
        ]
        if len(normalized_values) != len(raw_values):
            raise ValueError("bar values must be finite numbers")
        normalized_labels = [str(label) for label in raw_labels]
        if any(not label or len(label) > 128 for label in normalized_labels):
            raise ValueError("bar labels must be non-empty strings of at most 128 characters")
        self._store(name, {"type": "bar", "value": {"labels": normalized_labels, "values": normalized_values}})

    def histogram(self, name: str, value: object, bins: int = 8, current: object = None) -> None:
        """Emit a deterministic numeric distribution for Study Lab renderers."""
        value = _materialize(value)
        if not isinstance(value, list | tuple):
            raise ValueError("histogram values must be a list")
        if not isinstance(bins, int) or isinstance(bins, bool) or not 1 <= bins <= 64:
            raise ValueError("histogram bins must be an integer between 1 and 64")
        if current is not None and (not isinstance(current, int | float) or isinstance(current, bool) or not math.isfinite(float(current))):
            raise ValueError("histogram current value must be numeric")
        numeric = [float(item) for item in value if isinstance(item, int | float) and not isinstance(item, bool) and math.isfinite(float(item))]
        if not numeric:
            self._store(name, {"type": "histogram", "value": {"bins": [], "sample_size": 0, "current": current}})
            return
        minimum = min(numeric)
        maximum = max(numeric)
        if minimum == maximum:
            bucket_rows = [{"start": minimum, "end": maximum, "count": len(numeric)}]
        else:
            width = (maximum - minimum) / bins
            counts = [0] * bins
            for item in numeric:
                index = min(bins - 1, int((item - minimum) / width))
                counts[index] += 1
            bucket_rows = [
                {
                    "start": minimum + (index * width),
                    "end": maximum if index == bins - 1 else minimum + ((index + 1) * width),
                    "count": count,
                }
                for index, count in enumerate(counts)
            ]
        self._store(name, {
            "type": "histogram",
            "value": {"bins": bucket_rows, "sample_size": len(numeric), "min": minimum, "max": maximum, "current": current},
        })

    def range(self, name: str, lower: object, upper: object, center: object = None) -> None:
        """Emit aligned lower/upper bands with an optional center series."""
        lower_values = _materialize(lower)
        upper_values = _materialize(upper)
        center_values = _materialize(center) if center is not None else None
        if not isinstance(lower_values, list | tuple) or not isinstance(upper_values, list | tuple):
            raise ValueError("range bounds must be lists")
        if len(lower_values) == 0 or len(lower_values) != len(upper_values):
            raise ValueError("range bounds must be non-empty and have the same length")
        if center_values is not None and (not isinstance(center_values, list | tuple) or len(center_values) != len(lower_values)):
            raise ValueError("range center must match the bound length")
        def finite_values(values: list | tuple) -> list[float]:
            if not all(isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(float(value)) for value in values):
                raise ValueError("range values must be finite numbers")
            return [float(value) for value in values]
        normalized_lower = finite_values(lower_values)
        normalized_upper = finite_values(upper_values)
        normalized_center = finite_values(center_values) if center_values is not None else None
        timestamps = self.dataset.get("timestamps")
        if not isinstance(timestamps, list) or len(timestamps) != len(normalized_lower):
            timestamps = [str(index) for index in range(len(normalized_lower))]
        self._store(name, {"type": "range", "value": {
            "timestamps": [str(timestamp) for timestamp in timestamps],
            "lower": normalized_lower,
            "upper": normalized_upper,
            "center": normalized_center,
        }})

    def scatter(self, name: str, x: object, y: object) -> None:
        """Emit a bounded numeric x/y point cloud for uPlot rendering."""
        x_values = _materialize(x)
        y_values = _materialize(y)
        if not isinstance(x_values, list | tuple) or not isinstance(y_values, list | tuple):
            raise ValueError("scatter x and y values must be lists")
        if len(x_values) != len(y_values):
            raise ValueError("scatter x and y values must have the same length")
        points = [
            (float(left), float(right))
            for left, right in zip(x_values, y_values, strict=True)
            if isinstance(left, int | float) and not isinstance(left, bool)
            and isinstance(right, int | float) and not isinstance(right, bool)
            and math.isfinite(float(left)) and math.isfinite(float(right))
        ]
        self._store(name, {
            "type": "scatter",
            "value": {"x": [point[0] for point in points], "y": [point[1] for point in points]},
        })

    def heatmap(self, name: str, values: object, rows: object = None, columns: object = None) -> None:
        """Emit a bounded rectangular numeric matrix for the native Study Lab renderer."""
        matrix = _materialize(values)
        if not isinstance(matrix, list | tuple) or not matrix or not all(isinstance(row, list | tuple) for row in matrix):
            raise ValueError("heatmap values must be a non-empty matrix")
        width = len(matrix[0])
        if width == 0 or any(len(row) != width for row in matrix):
            raise ValueError("heatmap values must be rectangular")
        normalized = [[float(value) for value in row] for row in matrix]
        if not all(math.isfinite(value) for row in normalized for value in row):
            raise ValueError("heatmap values must be finite numbers")
        raw_rows = _materialize(rows)
        raw_columns = _materialize(columns)
        row_labels = [str(value) for value in raw_rows] if isinstance(raw_rows, list | tuple) else [str(index + 1) for index in range(len(normalized))]
        column_labels = [str(value) for value in raw_columns] if isinstance(raw_columns, list | tuple) else [str(index + 1) for index in range(width)]
        if len(row_labels) != len(normalized) or len(column_labels) != width:
            raise ValueError("heatmap labels must match matrix dimensions")
        self._store(name, {"type": "heatmap", "value": {"rows": row_labels, "columns": column_labels, "values": normalized}})

    def dashboard(self, name: str, panels: object) -> None:
        """Compose named artifacts into a typed, non-HTML dashboard."""
        panels = _materialize(panels)
        if not isinstance(panels, list) or not panels:
            raise ValueError("dashboard panels must be a non-empty list")
        if len(panels) > 64:
            raise ValueError("dashboard panel limit exceeded")
        normalized: list[dict[str, object]] = []
        for panel in panels:
            if not isinstance(panel, dict):
                raise ValueError("dashboard panels must be objects")
            artifact = panel.get("artifact")
            title = panel.get("title") or artifact
            span = panel.get("span", 1)
            if not isinstance(artifact, str) or not artifact or len(artifact) > 128:
                raise ValueError("dashboard panels require an artifact name")
            if not isinstance(title, str) or not title or len(title) > 128:
                raise ValueError("dashboard panel titles must be non-empty strings")
            if not isinstance(span, int) or isinstance(span, bool) or not 1 <= span <= 12:
                raise ValueError("dashboard panel span must be an integer between 1 and 12")
            normalized.append({"artifact": artifact, "title": title, "span": span})
        self._store(name, {"type": "dashboard", "value": {"panels": normalized}})

    def events(self, name: str, value: object) -> None:
        if not isinstance(value, list) or not all(isinstance(event, dict) for event in value):
            raise ValueError("events output must be a list of event objects")
        declared_symbol = str(self.dataset.get("symbol") or "").upper()
        prepared_datasets = self.dataset.get("datasets")
        if not isinstance(prepared_datasets, list):
            prepared_datasets = []
        universe_symbols = {
            str(item.get("symbol") or "").upper()
            for item in prepared_datasets
            if isinstance(item, dict) and str(item.get("symbol") or "").strip()
        }
        normalized: list[dict] = []
        for event in value:
            timestamp = event.get("timestamp")
            if not isinstance(timestamp, str) or not timestamp:
                raise ValueError("each event must contain a timestamp")
            symbol = str(event.get("symbol") or declared_symbol).upper()
            allowed = {declared_symbol} if declared_symbol else universe_symbols
            if not symbol or symbol not in allowed:
                raise ValueError(
                    f"event symbol {symbol or '<missing>'} is not declared in this run dataset"
                )
            normalized.append({**event, "symbol": symbol, "timestamp": timestamp})
        self._store(name, {"type": "events", "value": normalized})


class _Stats:
    """Small deterministic SDK seed; it has no I/O or host references."""

    @staticmethod
    def _finite_values(value: object) -> list[float]:
        materialized = _materialize(value)
        if not isinstance(materialized, list | tuple):
            raise ValueError("stats values must be a list")
        values = [
            float(item)
            for item in materialized
            if isinstance(item, int | float)
            and not isinstance(item, bool)
            and math.isfinite(float(item))
        ]
        if len(values) != len(materialized):
            raise ValueError("stats values must contain only finite numbers")
        return values

    @staticmethod
    def mean(values: object) -> float | None:
        numeric = _Stats._finite_values(values)
        return sum(numeric) / len(numeric) if numeric else None

    @staticmethod
    def median(values: object) -> float | None:
        numeric = sorted(_Stats._finite_values(values))
        if not numeric:
            return None
        middle = len(numeric) // 2
        return numeric[middle] if len(numeric) % 2 else (numeric[middle - 1] + numeric[middle]) / 2

    @staticmethod
    def std(values: object) -> float | None:
        numeric = _Stats._finite_values(values)
        if not numeric:
            return None
        average = sum(numeric) / len(numeric)
        return math.sqrt(sum((item - average) ** 2 for item in numeric) / len(numeric))

    @staticmethod
    def percentile(values: object, probability: float) -> float | None:
        numeric = sorted(_Stats._finite_values(values))
        if not isinstance(probability, int | float) or isinstance(probability, bool) or not math.isfinite(float(probability)) or not 0 <= float(probability) <= 1:
            raise ValueError("stats percentile probability must be between 0 and 1")
        if not numeric:
            return None
        position = float(probability) * (len(numeric) - 1)
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return numeric[lower]
        fraction = position - lower
        return numeric[lower] + ((numeric[upper] - numeric[lower]) * fraction)

    @staticmethod
    def ranks(values: object, descending: bool = True) -> list[int]:
        numeric = _Stats._finite_values(values)
        order = sorted(range(len(numeric)), key=lambda index: (-numeric[index], index) if descending else (numeric[index], index))
        ranks = [0] * len(numeric)
        for rank, index in enumerate(order, start=1):
            ranks[index] = rank
        return ranks

    @staticmethod
    def rolling(values: object, period: int, function: str = "mean") -> list[float | None]:
        numeric = _Stats._finite_values(values)
        if not isinstance(period, int) or isinstance(period, bool) or period <= 0:
            raise ValueError("stats rolling period must be a positive integer")
        if function not in {"mean", "median", "std"}:
            raise ValueError("stats rolling function must be mean, median, or std")
        result: list[float | None] = []
        for index in range(len(numeric)):
            if index + 1 < period:
                result.append(None)
                continue
            window = numeric[index - period + 1 : index + 1]
            if function == "mean":
                result.append(sum(window) / period)
            elif function == "median":
                result.append(_Stats.median(window))
            else:
                result.append(_Stats.std(window))
        return result

    @staticmethod
    def correlation(left: object, right: object) -> float | None:
        x = _Stats._finite_values(left)
        y = _Stats._finite_values(right)
        if len(x) != len(y):
            raise ValueError("stats correlation inputs must have the same length")
        if len(x) < 2:
            return None
        x_mean, y_mean = sum(x) / len(x), sum(y) / len(y)
        numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y, strict=True))
        x_variance = sum((a - x_mean) ** 2 for a in x)
        y_variance = sum((b - y_mean) ** 2 for b in y)
        denominator = math.sqrt(x_variance * y_variance)
        return numerator / denominator if denominator else None

    @staticmethod
    def regression(x_values: object, y_values: object) -> dict[str, float | int | None]:
        x = _Stats._finite_values(x_values)
        y = _Stats._finite_values(y_values)
        if len(x) != len(y):
            raise ValueError("stats regression inputs must have the same length")
        if len(x) < 2:
            return {"slope": None, "intercept": None, "r_squared": None, "sample_size": len(x)}
        x_mean, y_mean = sum(x) / len(x), sum(y) / len(y)
        denominator = sum((item - x_mean) ** 2 for item in x)
        if denominator == 0:
            return {"slope": None, "intercept": None, "r_squared": None, "sample_size": len(x)}
        slope = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y, strict=True)) / denominator
        intercept = y_mean - (slope * x_mean)
        residual = sum((actual - (slope * predicted + intercept)) ** 2 for predicted, actual in zip(x, y, strict=True))
        total = sum((actual - y_mean) ** 2 for actual in y)
        r_squared = 1.0 - residual / total if total else 1.0
        return {"slope": slope, "intercept": intercept, "r_squared": r_squared, "sample_size": len(x)}

    @staticmethod
    def distribution(values: object, bins: int = 8, current: object = None) -> dict[str, object]:
        numeric = _Stats._finite_values(values)
        if not isinstance(bins, int) or isinstance(bins, bool) or not 1 <= bins <= 64:
            raise ValueError("stats distribution bins must be an integer between 1 and 64")
        if current is not None and (not isinstance(current, int | float) or isinstance(current, bool) or not math.isfinite(float(current))):
            raise ValueError("stats distribution current value must be numeric")
        if not numeric:
            return {"bins": [], "sample_size": 0, "current": current}
        minimum, maximum = min(numeric), max(numeric)
        if minimum == maximum:
            bucket_rows = [{"start": minimum, "end": maximum, "count": len(numeric)}]
        else:
            width = (maximum - minimum) / bins
            counts = [0] * bins
            for item in numeric:
                counts[min(bins - 1, int((item - minimum) / width))] += 1
            bucket_rows = [
                {
                    "start": minimum + (index * width),
                    "end": maximum if index == bins - 1 else minimum + ((index + 1) * width),
                    "count": count,
                }
                for index, count in enumerate(counts)
            ]
        return {"bins": bucket_rows, "sample_size": len(numeric), "min": minimum, "max": maximum, "current": current}

    def positive_close_streaks(self, dataset: dict) -> dict:
        closes = dataset.get("closes", [])
        timestamps = dataset.get("timestamps", [])
        records: list[dict] = []
        current = 0
        for index in range(1, len(closes)):
            if closes[index] > closes[index - 1]:
                current += 1
            else:
                if current:
                    records.append(
                        {
                            "end_index": index - 1,
                            "end_timestamp": timestamps[index - 1]
                            if index - 1 < len(timestamps)
                            else None,
                            "length": current,
                        }
                    )
                current = 0
        completed = [record["length"] for record in records]
        all_lengths = completed + ([current] if current else [])
        return {
            "current": current,
            "longest": max(all_lengths) if all_lengths else 0,
            "shortest": min(all_lengths) if all_lengths else 0,
            "average": sum(all_lengths) / len(all_lengths) if all_lengths else 0,
            "records": records,
            "lengths": completed,
        }


class _NumpyFacade:
    """Numerical helpers with no filesystem, process, or network surface."""

    @staticmethod
    def array(value: object) -> object:
        return _numpy.asarray(value)

    @staticmethod
    def mean(value: object) -> float:
        return float(_numpy.mean(value))

    @staticmethod
    def median(value: object) -> float:
        return float(_numpy.median(value))

    @staticmethod
    def std(value: object) -> float:
        return float(_numpy.std(value))

    @staticmethod
    def percentile(value: object, percentile: float) -> float:
        return float(_numpy.percentile(value, percentile))

    @staticmethod
    def isfinite(value: object) -> object:
        return _numpy.isfinite(value)

    @staticmethod
    def isnan(value: object) -> object:
        return _numpy.isnan(value)

    @staticmethod
    def where(condition: object, left: object, right: object) -> object:
        return _numpy.where(condition, left, right)

    @staticmethod
    def clip(value: object, minimum: float, maximum: float) -> object:
        return _numpy.clip(value, minimum, maximum)

    @staticmethod
    def diff(value: object) -> object:
        return _numpy.diff(value)

    @staticmethod
    def cumsum(value: object) -> object:
        return _numpy.cumsum(value)


class _Rolling:
    def __init__(self, value: object, period: int) -> None:
        self._value = value.rolling(period)

    def __getattribute__(self, name: str) -> object:
        if name.startswith("_"):
            raise AttributeError("private wrapper attributes are unavailable")
        return object.__getattribute__(self, name)

    def mean(self) -> _Series:
        return _Series(object.__getattribute__(self, "_value").mean())

    def sum(self) -> _Series:
        return _Series(object.__getattribute__(self, "_value").sum())

    def std(self) -> _Series:
        return _Series(object.__getattribute__(self, "_value").std())


class _Series:
    def __init__(self, value: object) -> None:
        self._value = _pandas.Series(value)

    def __getattribute__(self, name: str) -> object:
        if name.startswith("_"):
            raise AttributeError("private wrapper attributes are unavailable")
        return object.__getattribute__(self, name)

    def mean(self) -> float:
        return float(object.__getattribute__(self, "_value").mean())

    def median(self) -> float:
        return float(object.__getattribute__(self, "_value").median())

    def std(self) -> float:
        return float(object.__getattribute__(self, "_value").std())

    def quantile(self, percentile: float) -> float:
        return float(object.__getattribute__(self, "_value").quantile(percentile))

    def rolling(self, period: int) -> _Rolling:
        if not isinstance(period, int) or period <= 0:
            raise ValueError("rolling period must be a positive integer")
        return _Rolling(object.__getattribute__(self, "_value"), period)

    def tolist(self) -> list[object]:
        return object.__getattribute__(self, "_value").tolist()


class _DataFrame:
    def __init__(self, value: object) -> None:
        self._value = _pandas.DataFrame(value)

    def __getattribute__(self, name: str) -> object:
        if name.startswith("_"):
            raise AttributeError("private wrapper attributes are unavailable")
        return object.__getattribute__(self, name)

    def mean(self) -> _Series:
        return _Series(object.__getattribute__(self, "_value").mean(numeric_only=True))

    def median(self) -> _Series:
        return _Series(object.__getattribute__(self, "_value").median(numeric_only=True))

    def to_dict(self) -> list[dict]:
        return object.__getattribute__(self, "_value").to_dict(orient="records")


class _PandasFacade:
    Series = _Series
    DataFrame = _DataFrame


class _Research:
    """Deterministic, point-in-time study helpers over the prepared dataset."""

    def cross_sectional_rank(self, dataset: dict, lookback: int = 20) -> list[dict]:
        """Rank a declared universe by trailing price return without external access."""
        if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback <= 0:
            raise ValueError("cross-sectional lookback must be a positive integer")
        datasets = dataset.get("datasets")
        if not isinstance(datasets, list):
            raise ValueError("Declared prepared universe is unavailable")
        rows: list[dict] = []
        for item in datasets:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper()
            closes = item.get("closes")
            if not symbol or not isinstance(closes, list) or len(closes) <= lookback:
                continue
            latest = closes[-1]
            base = closes[-lookback - 1]
            if not isinstance(latest, int | float) or isinstance(latest, bool) or not isinstance(base, int | float) or isinstance(base, bool) or base == 0:
                continue
            rows.append({
                "symbol": symbol,
                "instrument_id": item.get("instrument_id"),
                "return": (float(latest) / float(base)) - 1,
                "lookback": lookback,
            })
        rows.sort(key=lambda row: (row["return"], row["symbol"]), reverse=True)
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        return rows

    def breadth_snapshot(self, dataset: dict, period: int = 20) -> dict:
        """Summarize declared-universe participation above a simple moving average."""
        if not isinstance(period, int) or isinstance(period, bool) or period <= 0:
            raise ValueError("breadth period must be a positive integer")
        datasets = dataset.get("datasets")
        if not isinstance(datasets, list):
            raise ValueError("Declared prepared universe is unavailable")
        rows: list[dict] = []
        for item in datasets:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper()
            closes = item.get("closes")
            if not symbol or not isinstance(closes, list) or len(closes) < period:
                continue
            latest = closes[-1]
            window = closes[-period:]
            if not isinstance(latest, int | float) or isinstance(latest, bool) or not all(isinstance(value, int | float) and not isinstance(value, bool) for value in window):
                continue
            average = sum(float(value) for value in window) / period
            rows.append({"symbol": symbol, "moving_average": average, "close": float(latest), "above": float(latest) >= average})
        above = sum(1 for row in rows if row["above"])
        coverage = len(rows)
        return {
            "period": period,
            "coverage": coverage,
            "above_count": above,
            "below_count": coverage - above,
            "percent_above": (above / coverage) * 100 if coverage else None,
            "rows": rows,
        }

    def forward_returns(self, dataset: dict, event_indices: object, horizons: object = (1, 5, 20)) -> list[dict]:
        closes = dataset.get("closes", [])
        timestamps = dataset.get("timestamps", [])
        if not isinstance(closes, list) or not isinstance(event_indices, list | tuple) or not isinstance(horizons, list | tuple):
            raise ValueError("forward_returns requires event indices and horizons lists")
        parsed_horizons = []
        for horizon in horizons:
            if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon <= 0:
                raise ValueError("forward horizons must be positive integers")
            parsed_horizons.append(horizon)
        rows: list[dict] = []
        for index in event_indices:
            if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= len(closes):
                continue
            base = float(closes[index])
            if base == 0:
                continue
            for horizon in parsed_horizons:
                target = index + horizon
                if target >= len(closes):
                    continue
                rows.append({
                    "event_index": index,
                    "event_timestamp": timestamps[index] if index < len(timestamps) else None,
                    "horizon": horizon,
                    "outcome_timestamp": timestamps[target] if target < len(timestamps) else None,
                    "forward_return": (float(closes[target]) / base) - 1,
                })
        return rows

    def occurrences(self, dataset: dict, event_indices: object, kind: str = "occurrence") -> list[dict]:
        timestamps = dataset.get("timestamps", [])
        symbol = str(dataset.get("symbol") or "").upper()
        if not symbol or not isinstance(timestamps, list) or not isinstance(event_indices, list | tuple):
            raise ValueError("occurrences requires a declared symbol, timestamps, and event indices")
        label = str(kind or "occurrence")
        return [
            {"symbol": symbol, "timestamp": timestamps[index], "kind": label, "event_index": index}
            for index in event_indices
            if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(timestamps) and isinstance(timestamps[index], str) and timestamps[index]
        ]


class _Market:
    """Prepared-dataset market namespace; it can never retrieve undeclared data."""

    def __init__(self, dataset: dict) -> None:
        self._dataset = dataset
        benchmark = dataset.get("benchmark_dataset")
        self._benchmark = benchmark if isinstance(benchmark, dict) and benchmark.get("status", "ready") == "ready" else None

    def close(self, symbol: str | None = None) -> list[float]:
        return self._series("closes", symbol)

    def open(self, symbol: str | None = None) -> list[float]:
        return self._series("opens", symbol)

    def high(self, symbol: str | None = None) -> list[float]:
        return self._series("highs", symbol)

    def low(self, symbol: str | None = None) -> list[float]:
        return self._series("lows", symbol)

    def volume(self, symbol: str | None = None) -> list[float | None]:
        return self._series("volumes", symbol, allow_none=True)

    def vwap(self, symbol: str | None = None) -> list[float | None]:
        return self._series("vwaps", symbol, allow_none=True)

    def ohlcv(self, symbol: str | None = None) -> list[dict[str, object]]:
        """Return aligned, read-only OHLCV rows from the declared dataset."""
        requested = self._series_fields(symbol)
        timestamps = self._dataset.get("timestamps", [])
        if not isinstance(timestamps, list):
            raise ValueError("Declared dataset has no timestamp series")
        lengths = {len(values) for values in requested.values()}
        if len(lengths) != 1 or next(iter(lengths), 0) != len(timestamps):
            raise ValueError("Declared OHLCV fields are not aligned")
        return [
            {"timestamp": timestamps[index], "session": self._sessions()[index], **{name: values[index] for name, values in requested.items()}}
            for index in range(len(timestamps))
        ]

    def timestamps(self, symbol: str | None = None) -> list[str]:
        self._check_declared(symbol)
        values = self._dataset.get("timestamps")
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise ValueError("Declared dataset has no valid timestamp series")
        return list(values)

    def sessions(self, symbol: str | None = None) -> list[str]:
        self._check_declared(symbol)
        return self._sessions()

    def metadata(self, symbol: str | None = None) -> dict[str, object]:
        self._check_declared(symbol)
        value = self._dataset.get("metadata")
        if not isinstance(value, dict):
            raise ValueError("Declared dataset has no instrument metadata")
        return dict(value)

    def percent_change(self, lookback_or_period: int | str) -> float | None:
        """Return the latest percentage change over bars or a named period.

        The visual condition compiler uses this public helper so calendar and
        bar-change conditions execute through the same isolated Python SDK.
        The prepared dataset is the only source; no provider or hidden history
        access is possible.
        """
        closes = self._series("closes")
        timestamps = self.timestamps()
        if len(closes) < 2:
            return None
        if isinstance(lookback_or_period, int) and not isinstance(lookback_or_period, bool):
            index = len(closes) - 1 - lookback_or_period
        else:
            period = str(lookback_or_period)
            if period == "1D":
                seconds = 86_400
            elif period == "1W":
                seconds = 7 * 86_400
            elif period == "1M":
                seconds = 30 * 86_400
            elif period == "3M":
                seconds = 90 * 86_400
            elif period == "6M":
                seconds = 180 * 86_400
            elif period == "1Y":
                seconds = 365 * 86_400
            elif period in {"MTD", "QTD", "YTD"}:
                # The dataset timestamps are ISO strings; use the first bar in
                # the relevant UTC calendar bucket without importing datetime
                # into user code.
                latest = timestamps[-1][:10]
                year, month = (int(latest[:4]), int(latest[5:7]))
                if period == "YTD":
                    prefix = f"{year:04d}-01-"
                elif period == "QTD":
                    prefix = f"{year:04d}-{((month - 1) // 3) * 3 + 1:02d}-"
                else:
                    prefix = f"{year:04d}-{month:02d}-"
                index = next((i for i, stamp in enumerate(timestamps) if str(stamp).startswith(prefix)), len(closes) - 1)
            else:
                return None
            if "index" not in locals():
                latest_timestamp = timestamps[-1]
                # Parse only the epoch-independent ISO date portion in the
                # host SDK; users never receive datetime or import access.
                import datetime as _datetime
                target = _datetime.datetime.fromisoformat(str(latest_timestamp).replace("Z", "+00:00")).timestamp() - seconds
                index = next((i for i, stamp in enumerate(timestamps) if _datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp() >= target), len(closes) - 1)
        if index < 0 or index >= len(closes) or closes[index] == 0:
            return None
        return (float(closes[-1]) - float(closes[index])) / float(closes[index])

    def week52_new_high(self) -> bool:
        closes = self._series("closes")
        if len(closes) < 2:
            return False
        window = closes[-253:-1] if len(closes) > 253 else closes[:-1]
        return bool(window) and closes[-1] > max(window)

    def week52_new_low(self) -> bool:
        closes = self._series("closes")
        if len(closes) < 2:
            return False
        window = closes[-253:-1] if len(closes) > 253 else closes[:-1]
        return bool(window) and closes[-1] < min(window)

    def pct_from_52w_high(self) -> float | None:
        closes = self._series("closes")
        if not closes:
            return None
        window = closes[-252:]
        high = max(window)
        return (float(closes[-1]) - float(high)) / float(high) if high else None

    def pct_from_52w_low(self) -> float | None:
        closes = self._series("closes")
        if not closes:
            return None
        window = closes[-252:]
        low = min(window)
        return (float(closes[-1]) - float(low)) / float(low) if low else None

    def benchmark_close(self) -> list[float]:
        return self._benchmark_market().close()

    def benchmark_open(self) -> list[float]:
        return self._benchmark_market().open()

    def benchmark_high(self) -> list[float]:
        return self._benchmark_market().high()

    def benchmark_low(self) -> list[float]:
        return self._benchmark_market().low()

    def benchmark_volume(self) -> list[float | None]:
        return self._benchmark_market().volume()

    def benchmark_vwap(self) -> list[float | None]:
        return self._benchmark_market().vwap()

    def benchmark_ohlcv(self) -> list[dict[str, object]]:
        return self._benchmark_market().ohlcv()

    def benchmark_timestamps(self) -> list[str]:
        return self._benchmark_market().timestamps()

    def benchmark_sessions(self) -> list[str]:
        return self._benchmark_market().sessions()

    def benchmark_metadata(self) -> dict[str, object]:
        return self._benchmark_market().metadata()

    def universe(self) -> list[dict[str, object]]:
        """Return the prepared, provider-free universe for aggregate studies."""
        datasets = self._dataset.get("datasets")
        if not isinstance(datasets, list):
            raise ValueError("Declared prepared universe is unavailable")
        return [dict(item) for item in datasets if isinstance(item, dict)]

    def _benchmark_market(self) -> _Market:
        if self._benchmark is None:
            raise ValueError("Declared benchmark dataset is unavailable")
        return _Market(self._benchmark)

    def _sessions(self) -> list[str]:
        timestamps = self._dataset.get("timestamps")
        sessions = self._dataset.get("sessions")
        if not isinstance(timestamps, list):
            raise ValueError("Declared dataset has no timestamp series")
        if sessions is None:
            return ["regular"] * len(timestamps)
        if not isinstance(sessions, list) or len(sessions) != len(timestamps) or not all(isinstance(value, str) for value in sessions):
            raise ValueError("Declared session fields are not aligned")
        return list(sessions)

    def _series_fields(self, symbol: str | None = None) -> dict[str, list[object]]:
        self._check_declared(symbol)
        fields = {
            "open": self._dataset.get("opens"),
            "high": self._dataset.get("highs"),
            "low": self._dataset.get("lows"),
            "close": self._dataset.get("closes"),
            "volume": self._dataset.get("volumes"),
            "vwap": self._dataset.get("vwaps"),
        }
        if any(not isinstance(values, list) for values in fields.values()):
            raise ValueError("Declared dataset is missing one or more OHLCV fields")
        return fields

    def _series(self, field: str, symbol: str | None = None, *, allow_none: bool = False) -> list[float | None]:
        self._check_declared(symbol)
        values = self._dataset.get(field)
        if not isinstance(values, list):
            raise ValueError(f"Declared dataset has no {field.removesuffix('s')} series")
        if allow_none:
            return [float(value) if value is not None else None for value in values]
        if any(value is None for value in values):
            raise ValueError(f"Declared dataset has missing {field} values")
        return [float(value) for value in values]

    def _check_declared(self, symbol: str | None = None) -> None:
        declared = str(self._dataset.get("symbol") or "").upper()
        requested = str(symbol or declared).upper()
        if not declared or requested != declared:
            raise ValueError(f"{requested} is not declared in this run dataset")


class _Ta:
    """Canonical indicator facade used by all Python programmable surfaces."""

    def __init__(self, dataset: dict | None = None) -> None:
        self._dataset = dataset or {}

    def indicator(
        self,
        indicator_type: str,
        params: dict | None = None,
        output: str | None = None,
    ) -> list[float | None]:
        """Compute one named output using the canonical backend indicator registry."""
        if not isinstance(indicator_type, str) or not indicator_type:
            raise ValueError("indicator type must be a non-empty string")
        opens = self._dataset.get("opens", [])
        highs = self._dataset.get("highs", [])
        lows = self._dataset.get("lows", [])
        closes = self._dataset.get("closes", [])
        volumes = self._dataset.get("volumes", [])
        timestamps = self._dataset.get("timestamps", [])
        if not all(isinstance(values, list) for values in (opens, highs, lows, closes, volumes, timestamps)):
            raise ValueError("declared OHLCV data is incomplete")
        if not (len(opens) == len(highs) == len(lows) == len(closes) == len(volumes) == len(timestamps)):
            raise ValueError("declared OHLCV data is not aligned")
        import datetime as _datetime
        epoch = []
        for stamp in timestamps:
            epoch.append(int(_datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()))
        data = _CanonicalOHLCVSeries(
            timestamps=_numpy.asarray(epoch, dtype=_numpy.int64),
            opens=_numpy.asarray(opens, dtype=float),
            highs=_numpy.asarray(highs, dtype=float),
            lows=_numpy.asarray(lows, dtype=float),
            closes=_numpy.asarray(closes, dtype=float),
            volumes=_numpy.asarray([0 if value is None else value for value in volumes], dtype=float),
        )
        normalized = _normalize_canonical_indicator_params(indicator_type, params or {})
        values = _compute_canonical_indicator(indicator_type, data, normalized)
        if not isinstance(values, dict) or not values:
            raise ValueError(f"indicator {indicator_type!r} returned no outputs")
        selected = output if isinstance(output, str) and output in values else next(iter(values))
        raw = values[selected]
        return [float(value) if _numpy.isfinite(value) else float("nan") for value in raw]

    @staticmethod
    def _period(period: int) -> int:
        if not isinstance(period, int) or period <= 0:
            raise ValueError("period must be a positive integer")
        return period

    def sma(self, values: list[float], period: int) -> list[float | None]:
        period = self._period(period)
        series = [float(value) for value in values]
        output: list[float | None] = []
        rolling_sum = 0.0
        for index, value in enumerate(series):
            rolling_sum += value
            if index >= period:
                rolling_sum -= series[index - period]
            output.append(rolling_sum / period if index >= period - 1 else None)
        return output

    def ema(self, values: list[float], period: int) -> list[float | None]:
        period = self._period(period)
        series = [float(value) for value in values]
        output: list[float | None] = []
        multiplier = 2 / (period + 1)
        current: float | None = None
        for index, value in enumerate(series):
            if index < period - 1:
                output.append(None)
                continue
            if current is None:
                current = sum(series[index - period + 1 : index + 1]) / period
            else:
                current = (value - current) * multiplier + current
            output.append(current)
        return output

    def rsi(self, values: list[float], period: int = 14) -> list[float | None]:
        period = self._period(period)
        series = [float(value) for value in values]
        output: list[float | None] = [None] * len(series)
        if len(series) <= period:
            return output
        gains = [max(series[index] - series[index - 1], 0.0) for index in range(1, len(series))]
        losses = [max(series[index - 1] - series[index], 0.0) for index in range(1, len(series))]
        average_gain = sum(gains[:period]) / period
        average_loss = sum(losses[:period]) / period
        output[period] = (
            100.0 if average_loss == 0 else 100 - (100 / (1 + average_gain / average_loss))
        )
        for index in range(period, len(gains)):
            average_gain = ((average_gain * (period - 1)) + gains[index]) / period
            average_loss = ((average_loss * (period - 1)) + losses[index]) / period
            output[index + 1] = (
                100.0 if average_loss == 0 else 100 - (100 / (1 + average_gain / average_loss))
            )
        return output


def run_once(path: Path) -> None:
    running_path = path.with_suffix(".running")
    try:
        path.replace(running_path)
    except FileNotFoundError:
        return
    result_path = RESULT_DIR / f"{path.stem}.json"
    progress_path = RESULT_DIR / f"{path.stem}.progress.json"
    cancel_path = JOB_DIR / f"{path.stem}.cancel"
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    def write_result(result: dict) -> None:
        encoded = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
        if len(encoded) > MAX_OUTPUT_BYTES:
            result = {
                "status": "failed",
                "diagnostics": [{"code": "output_size_limit", "message": "research result exceeds the configured byte limit"}],
            }
            encoded = json.dumps(result, separators=(",", ":")).encode()
        temporary = result_path.with_suffix(".tmp")
        temporary.write_bytes(encoded)
        temporary.replace(result_path)

    try:
        if running_path.stat().st_size > MAX_JOB_BYTES:
            raise ValueError("research job exceeds the configured input byte limit")
        payload = json.loads(running_path.read_text())
        if not isinstance(payload, dict) or not isinstance(payload.get("source"), str):
            raise ValueError("research job payload must contain a source string")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        write_result({"status": "failed", "diagnostics": [{"code": "job_payload_invalid", "message": str(exc)}]})
        cancel_path.unlink(missing_ok=True)
        progress_path.unlink(missing_ok=True)
        running_path.rename(path.with_suffix(".processed"))
        return

    def write_progress(progress: dict) -> None:
        temporary = progress_path.with_suffix(".progress.tmp")
        temporary.write_text(json.dumps(progress, separators=(",", ":")))
        temporary.replace(progress_path)

    write_progress({"status": "running"})
    try:
        result = execute_job(
            payload,
            progress_callback=write_progress,
            cancellation_check=cancel_path.exists,
        )
    except Exception as exc:  # the worker must survive one malformed/crashing job
        result = {"status": "failed", "diagnostics": [{"code": "runner_error", "message": str(exc)}]}
    write_result(result)
    progress_path.unlink(missing_ok=True)
    cancel_path.unlink(missing_ok=True)
    running_path.rename(path.with_suffix(".processed"))


def recover_orphaned_jobs() -> None:
    """Return jobs left in claimed state by a terminated worker to the queue."""
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    for path in JOB_DIR.glob("*.running"):
        job_id = path.stem
        # A worker can terminate after creating these sentinels but before its
        # normal cleanup path. They belong to the previous execution and must
        # not cancel or masquerade as progress for the requeued job.
        (JOB_DIR / f"{job_id}.cancel").unlink(missing_ok=True)
        (RESULT_DIR / f"{job_id}.progress.json").unlink(missing_ok=True)
        destination = path.with_suffix(".json")
        if destination.exists():
            path.unlink(missing_ok=True)
        else:
            path.rename(destination)


def main() -> None:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    recover_orphaned_jobs()
    while True:
        for path in JOB_DIR.glob("*.json"):
            run_once(path)
        time.sleep(0.25)


if __name__ == "__main__":
    main()
