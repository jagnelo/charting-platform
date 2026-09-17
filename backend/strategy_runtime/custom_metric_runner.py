"""Mounted-file CLI for isolated custom-metric execution.

The command is deliberately separate from the strategy CLI so worker images
can grant only the operation they were scheduled to perform.  It never starts
Docker itself; the host worker must launch it inside the validated sandbox.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from app.strategy_lab_v2.custom_metrics import (
    CustomMetricStatus,
    run_custom_metric,
    run_custom_metrics,
)
from strategy_runtime.custom_metric_protocol import (
    deserialize_custom_metric_invocation,
    deserialize_custom_metric_invocation_batch,
    serialize_custom_metric_result,
    serialize_custom_metric_result_batch,
)
from strategy_runtime.runner import _absolute_path, _atomic_write


def main(argv: Sequence[str] | None = None) -> int:
    """Run one mounted custom-metric request and atomically publish its result.

    Exit status ``0`` means a successful metric value, ``2`` means typed
    rejection/failure, and ``1`` means malformed input/output setup.  The
    latter never includes exception text in the output file.
    """

    parser = argparse.ArgumentParser(description="run Strategy Lab custom metric input")
    parser.add_argument("--request", required=True, help="absolute mounted invocation JSON")
    parser.add_argument("--result", required=True, help="absolute result JSON destination")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="interpret the request and result as deterministic custom-metric batches",
    )
    args = parser.parse_args(argv)
    try:
        request_path = _absolute_path(args.request, "request path")
        result_path = _absolute_path(args.result, "result path")
        request_payload = Path(request_path).read_text(encoding="utf-8")
        if args.batch:
            invocations = deserialize_custom_metric_invocation_batch(request_payload)
            results = run_custom_metrics(invocations)
            _atomic_write(result_path, serialize_custom_metric_result_batch(results))
            return 0 if all(item.status is CustomMetricStatus.SUCCEEDED for item in results) else 2
        source, definition, observations, parameters = deserialize_custom_metric_invocation(
            request_payload
        )
        result = run_custom_metric(
            source,
            definition=definition,
            observations=observations,
            parameters=parameters,
        )
        _atomic_write(result_path, serialize_custom_metric_result(result))
        return 0 if result.status is CustomMetricStatus.SUCCEEDED else 2
    except (OSError, TypeError, UnicodeError, ValueError):
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI gate
    raise SystemExit(main())


__all__ = ["main"]
