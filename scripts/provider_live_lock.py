"""Cross-worktree lock for quota-consuming provider live validation.

The live matrix intentionally performs real requests.  Separate Git worktrees
on one host otherwise have no way to know that another checkout is spending
the same provider key.  This lock is local-only coordination; it does not
claim visibility into provider usage from CI, deployments, or other hosts.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4


DEFAULT_LOCK_PATH = Path.home() / ".config" / "charting-platform" / "provider-live.lock"


class ProviderLiveRunAlreadyActive(RuntimeError):
    """Raised when another local live matrix owns the provider-key lock."""


def _lock_path(path: str | os.PathLike[str] | None = None) -> Path:
    return Path(
        path
        or os.getenv("PROVIDER_LIVE_LOCK_FILE", str(DEFAULT_LOCK_PATH))
    ).expanduser()


@contextmanager
def provider_live_run_lock(
    path: str | os.PathLike[str] | None = None,
) -> Iterator[Path]:
    """Hold an exclusive local lock for one quota-consuming live run.

    The lock metadata contains no credentials.  It is overwritten while the
    lock is held and cleared before release, so stale metadata cannot be
    mistaken for an active run after a process crash.
    """

    lock_path = _lock_path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    acquired = False
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            metadata = handle.read().strip()
            detail = f" ({metadata})" if metadata else ""
            raise ProviderLiveRunAlreadyActive(
                f"another provider live run already holds {lock_path}{detail}"
            ) from exc
        acquired = True

        payload = {
            "run_id": str(uuid4()),
            "pid": os.getpid(),
            "started_at": datetime.now(UTC).isoformat(),
            "cwd": os.getcwd(),
        }
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(payload, sort_keys=True))
        handle.flush()
        yield lock_path
    finally:
        if acquired:
            try:
                handle.seek(0)
                handle.truncate()
                handle.flush()
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
        else:
            handle.close()
