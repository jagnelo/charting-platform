from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, screener):
        self.screener = screener

    async def execute(self, _statement):
        return _Result(self.screener)


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _ScheduledSession:
    def __init__(self, screener, latest_run):
        self.screener = screener
        self.latest_run = latest_run
        self.calls = 0

    async def execute(self, _statement):
        self.calls += 1
        return _Rows([self.screener]) if self.calls == 1 else _Scalar(self.latest_run)


@pytest.mark.asyncio
async def test_scheduled_python_screener_uses_isolated_queue(monkeypatch):
    from app.tasks import screener_tasks

    screener = SimpleNamespace(
        id=7,
        user_id=3,
        conditions={"type": "python_condition", "code_version_id": 42},
    )
    result = SimpleNamespace(
        id=9,
        matched_ids=[11],
        result_data={"_coverage": {"universe_count": 2}},
        duration_ms=None,
    )
    queue = AsyncMock(return_value=result)
    legacy = AsyncMock(side_effect=AssertionError("Python source reached legacy evaluator"))
    monkeypatch.setattr(screener_tasks, "queue_python_screener_run", queue)
    monkeypatch.setattr(screener_tasks, "run_screener", legacy)
    monkeypatch.setattr(
        screener_tasks,
        "AsyncSessionLocal",
        lambda: _SessionFactory(_Session(screener)),
    )

    summary = await screener_tasks.run_screener_task({}, screener.id, screener.user_id)

    assert summary == {
        "screener_id": 7,
        "matched": 1,
        "total_scanned": 2,
        "duration_ms": None,
        "result_id": 9,
    }
    queue.assert_awaited_once()
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_uses_persisted_result_time_not_removed_last_run_field(monkeypatch):
    from app.tasks import screener_tasks

    screener = SimpleNamespace(
        id=8,
        user_id=3,
        schedule="* * * * *",
        is_active=True,
        conditions={},
    )
    session = _ScheduledSession(screener, datetime.now(UTC) - timedelta(minutes=2))
    queued = AsyncMock()
    monkeypatch.setattr(screener_tasks, "_run_screener_or_queue", queued)
    monkeypatch.setattr(screener_tasks, "_collect_pending_python_results", AsyncMock())
    monkeypatch.setattr(screener_tasks, "AsyncSessionLocal", lambda: _SessionFactory(session))

    summary = await screener_tasks.run_all_scheduled_screeners({})

    assert summary == {"ran": 1}
    queued.assert_awaited_once_with(session, screener)
