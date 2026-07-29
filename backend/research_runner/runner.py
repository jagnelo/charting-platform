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


def execute_job(job: dict) -> dict:
    source = str(job["source"])
    validation = validate_workstation_python(source)
    if not validation.valid:
        return {
            "status": "failed",
            "diagnostics": [item.__dict__ for item in validation.diagnostics],
        }
    # The SDK is injected as immutable data/callables by the future materialiser.
    # No Python builtins, imports, filesystem APIs, sockets, or process APIs are exposed.
    outputs: dict[str, object] = {}
    safe_globals = {
        "__builtins__": {},
        "output": _Output(outputs),
        "dataset": job.get("dataset", {}),
        "stats": _Stats(),
    }
    _limit_resources()
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(MAX_SECONDS)
    started = time.monotonic()
    try:
        exec(compile(source, "<research>", "exec"), safe_globals, {})  # noqa: S102 - locked runner only
    except Exception as exc:
        return {"status": "failed", "diagnostics": [{"code": "runtime_error", "message": str(exc)}]}
    finally:
        signal.alarm(0)
    return {
        "status": "completed",
        "artifacts": outputs,
        "resource_usage": {"wall_ms": round((time.monotonic() - started) * 1000, 3)},
        "reproducibility_hash": sha256(json.dumps(job, sort_keys=True).encode()).hexdigest(),
    }


class _Output:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def scalar(self, name: str, value: object) -> None:
        self.values[name] = {"type": "scalar", "value": value}

    def series(self, name: str, value: object) -> None:
        self.values[name] = {"type": "series", "value": value}

    def table(self, name: str, value: object) -> None:
        self.values[name] = {"type": "table", "value": value}

    def events(self, name: str, value: object) -> None:
        self.values[name] = {"type": "events", "value": value}


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


def run_once(path: Path) -> None:
    payload = json.loads(path.read_text())
    result = execute_job(payload)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    destination = RESULT_DIR / f"{path.stem}.json"
    destination.write_text(json.dumps(result, separators=(",", ":")))
    path.rename(path.with_suffix(".processed"))


def main() -> None:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        for path in JOB_DIR.glob("*.json"):
            run_once(path)
        time.sleep(0.25)


if __name__ == "__main__":
    main()
