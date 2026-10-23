"""Typed, fail-closed consumer contract for persisted TC Study output payloads.

The producer's isolated ``research_runner`` validates these shapes before
publication. Strategy Lab revalidates them when pinning or reconstructing a
payload so a digest-bound but malformed row cannot enter an immutable runtime
context. This is payload integrity only, not proof of native execution.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TypeAlias, cast

FrozenStudyArtifactValue: TypeAlias = (  # noqa: UP040 - CI pins mypy 1.10, before PEP 695 aliases.
    str
    | int
    | float
    | bool
    | None
    | tuple["FrozenStudyArtifactValue", ...]
    | Mapping[str, "FrozenStudyArtifactValue"]
)

SUPPORTED_STUDY_ARTIFACT_TYPES = frozenset(
    {
        "scalar",
        "series",
        "boolean",
        "table",
        "bar",
        "histogram",
        "range",
        "scatter",
        "heatmap",
        "dashboard",
        "events",
    }
)


def _sequence(value: object) -> tuple[object, ...] | None:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return None


def _finite_number(value: object) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _nonempty_label(value: object, *, maximum: int = 128) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= maximum


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _has_exact_fields(value: Mapping[str, object], fields: set[str]) -> bool:
    return set(value) == fields


def validate_study_artifact_payload(payload: Mapping[str, object], *, expected_type: str) -> None:
    """Validate the actual accepted TC output adapter schema for one payload."""

    if expected_type not in SUPPORTED_STUDY_ARTIFACT_TYPES:
        raise ValueError("unsupported Study artifact type")
    if payload.get("type") != expected_type or "value" not in payload:
        raise ValueError("Study artifact type/value does not match its declared contract")
    allowed_fields = (
        {"type", "value", "metric", "exclusion"}
        if expected_type == "boolean"
        else {"type", "value"}
    )
    if set(payload) - allowed_fields:
        raise ValueError("Study artifact contains fields outside its producer contract")
    value = payload["value"]

    # The producer intentionally leaves scalar, series, and table values as
    # finite JSON; their downstream Research SDK access is defined by the type
    # discriminant and immutable payload, not an inferred numeric cast.
    if expected_type in {"scalar", "series", "table"}:
        return

    if expected_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("boolean Study output must contain a boolean value")
        metric = payload.get("metric")
        if "metric" in payload and not _finite_number(metric):
            raise ValueError("boolean Study metric must be finite")
        exclusion = payload.get("exclusion")
        if "exclusion" in payload and not _nonempty_text(exclusion):
            raise ValueError("boolean Study exclusion must be a non-empty string")
        return

    if expected_type == "events":
        events = _sequence(value)
        if events is None:
            raise ValueError("events Study output requires timestamped, symbol-bound objects")
        for event in events:
            if not isinstance(event, Mapping):
                raise ValueError("events Study output requires timestamped, symbol-bound objects")
            timestamp, symbol = event.get("timestamp"), event.get("symbol")
            if (
                not _nonempty_text(timestamp)
                or not isinstance(symbol, str)
                or not symbol
                or symbol != symbol.upper()
            ):
                raise ValueError(
                    "events Study output requires timestamped, normalized symbol-bound objects"
                )
        return

    if not isinstance(value, Mapping):
        raise ValueError(f"{expected_type} Study output value must be an object")

    if expected_type == "bar":
        if not _has_exact_fields(value, {"labels", "values"}):
            raise ValueError("bar Study output contains fields outside its producer contract")
        labels = _sequence(value.get("labels"))
        values = _sequence(value.get("values"))
        if (
            labels is None
            or values is None
            or not labels
            or len(labels) != len(values)
            or not all(_nonempty_label(label) for label in labels)
            or not all(_finite_number(item) for item in values)
        ):
            raise ValueError("bar Study output requires aligned labels and finite values")
        return

    if expected_type == "histogram":
        bins = _sequence(value.get("bins"))
        sample_size = value.get("sample_size")
        if (
            bins is None
            or len(bins) > 64
            or not isinstance(sample_size, int)
            or isinstance(sample_size, bool)
            or sample_size < 0
        ):
            raise ValueError("histogram Study output has invalid bins or sample size")
        current = value.get("current")
        if current is not None and not _finite_number(current):
            raise ValueError("histogram Study current value must be finite")
        if sample_size == 0:
            if bins or not _has_exact_fields(value, {"bins", "sample_size", "current"}):
                raise ValueError("empty histogram Study output cannot contain bins")
            return
        minimum = value.get("min")
        maximum = value.get("max")
        if (
            not bins
            or not _has_exact_fields(value, {"bins", "sample_size", "min", "max", "current"})
            or not _finite_number(minimum)
            or not _finite_number(maximum)
        ):
            raise ValueError("non-empty histogram Study output requires finite bounds and bins")
        counts: list[int] = []
        for item in bins:
            if not isinstance(item, Mapping) or not _has_exact_fields(
                item, {"start", "end", "count"}
            ):
                raise ValueError("histogram Study bins must be objects")
            start, end, count = item.get("start"), item.get("end"), item.get("count")
            if (
                not _finite_number(start)
                or not _finite_number(end)
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count < 0
            ):
                raise ValueError("histogram Study bin is malformed")
            counts.append(count)
        if sum(counts) != sample_size or float(cast(int | float, minimum)) > float(
            cast(int | float, maximum)
        ):
            raise ValueError("histogram Study counts or bounds are inconsistent")
        return

    if expected_type == "range":
        if not _has_exact_fields(value, {"timestamps", "lower", "upper", "center"}):
            raise ValueError("range Study output contains fields outside its producer contract")
        timestamps = _sequence(value.get("timestamps"))
        lower = _sequence(value.get("lower"))
        upper = _sequence(value.get("upper"))
        center = value.get("center")
        if (
            timestamps is None
            or lower is None
            or upper is None
            or not lower
            or len(timestamps) != len(lower)
            or len(upper) != len(lower)
            or not all(isinstance(item, str) for item in timestamps)
            or not all(_finite_number(item) for item in (*lower, *upper))
        ):
            raise ValueError("range Study output requires aligned timestamps and finite bounds")
        if center is not None:
            center_values = _sequence(center)
            if (
                center_values is None
                or len(center_values) != len(lower)
                or not all(_finite_number(item) for item in center_values)
            ):
                raise ValueError("range Study center must align with its bounds")
        return

    if expected_type == "scatter":
        if not _has_exact_fields(value, {"x", "y"}):
            raise ValueError("scatter Study output contains fields outside its producer contract")
        x_values = _sequence(value.get("x"))
        y_values = _sequence(value.get("y"))
        if (
            x_values is None
            or y_values is None
            or len(x_values) != len(y_values)
            or not all(_finite_number(item) for item in (*x_values, *y_values))
        ):
            raise ValueError("scatter Study output requires aligned finite coordinates")
        return

    if expected_type == "heatmap":
        if not _has_exact_fields(value, {"rows", "columns", "values"}):
            raise ValueError("heatmap Study output contains fields outside its producer contract")
        rows = _sequence(value.get("rows"))
        columns = _sequence(value.get("columns"))
        matrix = _sequence(value.get("values"))
        if (
            rows is None
            or columns is None
            or matrix is None
            or not matrix
            or not columns
            or len(rows) != len(matrix)
            or not all(isinstance(label, str) for label in (*rows, *columns))
        ):
            raise ValueError("heatmap Study output has invalid labels or matrix dimensions")
        matrix_rows = tuple(_sequence(row) for row in matrix)
        if (
            any(row is None for row in matrix_rows)
            or any(len(row or ()) != len(columns) for row in matrix_rows)
            or not all(_finite_number(item) for row in matrix_rows if row for item in row)
        ):
            raise ValueError("heatmap Study output must be rectangular and finite")
        return

    if expected_type == "dashboard":
        if not _has_exact_fields(value, {"panels"}):
            raise ValueError("dashboard Study output contains fields outside its producer contract")
        panels = _sequence(value.get("panels"))
        if panels is None or not panels or len(panels) > 64:
            raise ValueError("dashboard Study output requires one to 64 panels")
        for panel in panels:
            if not isinstance(panel, Mapping) or not _has_exact_fields(
                panel, {"artifact", "title", "span"}
            ):
                raise ValueError("dashboard Study panels must be objects")
            title, artifact, span = panel.get("title"), panel.get("artifact"), panel.get("span")
            if (
                not _nonempty_label(title)
                or not _nonempty_label(artifact)
                or not isinstance(span, int)
                or isinstance(span, bool)
                or not 1 <= span <= 12
            ):
                raise ValueError("dashboard Study panel is malformed")
        return

    raise ValueError("unsupported Study artifact type")
