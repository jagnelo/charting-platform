"""Dedicated, no-network research execution process.

This process is intended to run only in the locked-down `research-runner`
container. It receives pre-materialised JSON inputs and never imports platform
configuration, connects to a provider, or receives credentials.
"""

from __future__ import annotations

import json
import os
import resource
import signal
import time
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from research_runner.validation import validate_workstation_python

JOB_DIR = Path(os.environ.get("RESEARCH_JOB_DIR", "/jobs"))
RESULT_DIR = Path(os.environ.get("RESEARCH_RESULT_DIR", "/results"))
MAX_SECONDS = int(os.environ.get("RESEARCH_MAX_SECONDS", "15"))
MAX_MEMORY_BYTES = int(os.environ.get("RESEARCH_MAX_MEMORY_BYTES", str(512 * 1024 * 1024)))


def _limit_resources() -> None:
    # macOS does not implement every rlimit enforced by the Linux deployment
    # container. Failure here is tolerated only for local unit execution; the
    # compose service independently supplies cgroup/read-only/no-network limits.
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (MAX_SECONDS, MAX_SECONDS + 1))
        resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES))
    except (OSError, ValueError):
        pass


def _timeout(_signal, _frame) -> None:
    raise TimeoutError("research execution wall-time limit exceeded")


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
        return _execute_batch(
            source,
            datasets,
            str(job.get("output_contract") or ""),
            job,
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
    outputs: dict[str, object] = {}
    safe_globals = {
        "__builtins__": {},
        "output": _Output(outputs, dataset),
        "dataset": dataset,
        "market": _Market(dataset),
        "ta": _Ta(),
        "stats": _Stats(),
    }
    if manage_timeout:
        _limit_resources()
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
    except Exception as exc:
        return {"status": "failed", "diagnostics": [{"code": "runtime_error", "message": str(exc)}]}
    finally:
        if manage_timeout:
            signal.alarm(0)
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
    *,
    progress_callback: Callable[[dict], None] | None = None,
    cancellation_check: Callable[[], bool] | None = None,
) -> dict:
    if output_contract not in {"scalar", "boolean"}:
        return {"status": "failed", "diagnostics": [{"code": "batch_output_contract_unsupported", "message": "Batch execution requires scalar or boolean output."}]}
    cells: list[dict] = []
    started = time.monotonic()
    total = len(datasets)
    if progress_callback:
        progress_callback({"completed_cells": 0, "total_cells": total, "status": "running"})
    _limit_resources()
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
                {"source": source, "dataset": candidate, "output_contract": output_contract},
                manage_timeout=False,
            )
            if result.get("status") != "completed":
                diagnostics = result.get("diagnostics", [])
                message = diagnostics[0].get("message") if diagnostics and isinstance(diagnostics[0], dict) else "Batch cell failed"
                cells.append({"instrument_id": instrument_id, "symbol": symbol, "status": "failed", "error": message})
                continue
            matches = [artifact for artifact in result.get("artifacts", {}).values() if isinstance(artifact, dict) and artifact.get("type") == output_contract]
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

    def scalar(self, name: str, value: object) -> None:
        self.values[name] = {"type": "scalar", "value": value}

    def series(self, name: str, value: object) -> None:
        values = list(value) if isinstance(value, list | tuple) else value
        timestamps = self.dataset.get("timestamps", [])
        if (
            isinstance(values, list)
            and isinstance(timestamps, list)
            and len(timestamps) == len(values)
        ):
            self.values[name] = {
                "type": "series",
                "value": {"timestamps": timestamps, "values": values},
            }
        else:
            self.values[name] = {"type": "series", "value": values}

    def boolean(self, name: str, value: object) -> None:
        if not isinstance(value, bool):
            raise ValueError("boolean output must be true or false")
        self.values[name] = {"type": "boolean", "value": value}

    def table(self, name: str, value: object) -> None:
        self.values[name] = {"type": "table", "value": value}

    def events(self, name: str, value: object) -> None:
        if not isinstance(value, list) or not all(isinstance(event, dict) for event in value):
            raise ValueError("events output must be a list of event objects")
        declared_symbol = str(self.dataset.get("symbol") or "").upper()
        normalized: list[dict] = []
        for event in value:
            timestamp = event.get("timestamp")
            if not isinstance(timestamp, str) or not timestamp:
                raise ValueError("each event must contain a timestamp")
            symbol = str(event.get("symbol") or declared_symbol).upper()
            if not declared_symbol or symbol != declared_symbol:
                raise ValueError(
                    f"event symbol {symbol or '<missing>'} is not declared in this run dataset"
                )
            normalized.append({**event, "symbol": symbol, "timestamp": timestamp})
        self.values[name] = {"type": "events", "value": normalized}


class _Stats:
    """Small deterministic SDK seed; it has no I/O or host references."""

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
        }


class _Market:
    """Prepared-dataset market namespace; it can never retrieve undeclared data."""

    def __init__(self, dataset: dict) -> None:
        self._dataset = dataset

    def close(self, symbol: str | None = None) -> list[float]:
        declared = str(self._dataset.get("symbol") or "").upper()
        requested = str(symbol or declared).upper()
        if not declared or requested != declared:
            raise ValueError(f"{requested} is not declared in this run dataset")
        closes = self._dataset.get("closes", [])
        if not isinstance(closes, list):
            raise ValueError("Declared dataset has no close series")
        return [float(value) for value in closes]


class _Ta:
    """Small vector-only technical-analysis subset for the isolated SDK."""

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
    payload = json.loads(running_path.read_text())
    progress_path = RESULT_DIR / f"{path.stem}.progress.json"
    cancel_path = JOB_DIR / f"{path.stem}.cancel"
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    def write_progress(progress: dict) -> None:
        temporary = progress_path.with_suffix(".progress.tmp")
        temporary.write_text(json.dumps(progress, separators=(",", ":")))
        temporary.replace(progress_path)

    result = execute_job(
        payload,
        progress_callback=write_progress,
        cancellation_check=cancel_path.exists,
    )
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    destination = RESULT_DIR / f"{path.stem}.json"
    destination.write_text(json.dumps(result, separators=(",", ":")))
    progress_path.unlink(missing_ok=True)
    cancel_path.unlink(missing_ok=True)
    running_path.rename(path.with_suffix(".processed"))


def main() -> None:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        for path in JOB_DIR.glob("*.json"):
            run_once(path)
        time.sleep(0.25)


if __name__ == "__main__":
    main()
