from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.models.instrument_sync_run import InstrumentSyncRun
from app.services import instrument_sync
from app.services.instrument_sync import _listing_evidence, _seed_quote_type, sync_instruments
from tests.unit.conftest import AsyncSessionAdapter


def test_listing_evidence_preserves_provider_dates_and_provenance():
    observed_at = datetime(2026, 8, 11, 12, 30, tzinfo=UTC)

    evidence = _listing_evidence(
        {
            "status": "delisted",
            "ipo_date": "2010-01-04",
            "delisting_date": "2026-07-31",
        },
        provider_name="alpha_vantage",
        observed_at=observed_at,
    )

    assert evidence == {
        "status": "delisted",
        "ipo_date": "2010-01-04",
        "delisting_date": "2026-07-31",
        "source": "alpha_vantage",
        "observed_at": "2026-08-11T12:30:00+00:00",
        "evidence_role": "provider_listing_observation",
    }


def test_listing_evidence_does_not_create_empty_lifecycle_claims():
    assert (
        _listing_evidence(
            {"status": "", "ipo_date": None, "delisting_date": None},
            provider_name="alpha_vantage",
            observed_at=datetime(2026, 8, 11, tzinfo=UTC),
        )
        is None
    )


@pytest.mark.parametrize(
    ("row", "fallback", "expected"),
    [
        ({"instrument_type": "ETF"}, "EQUITY", "ETF"),
        ({"instrument_type": "Common Stock"}, "ETF", "EQUITY"),
        ({"instrument_type": "unrecognized provider label"}, "EQUITY", "UNCLASSIFIED"),
        ({"instrument_type": "ETV"}, "EQUITY", "ETV"),
        ({"instrument_type": "ETN"}, "EQUITY", "ETN"),
        ({}, "CRYPTOCURRENCY", "CRYPTOCURRENCY"),
    ],
)
def test_seed_uses_recognized_row_type_without_losing_provider_fallback(row, fallback, expected):
    assert _seed_quote_type(row, fallback) == expected


@pytest.mark.asyncio
async def test_tracked_sync_redacts_failure_error(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(instrument_sync, "_provider_chain_label", AsyncMock(return_value="fixture"))

    async def failing_seed(*_args, **_kwargs):
        raise RuntimeError("GET https://provider.test/data?api_key=sync-secret")

    monkeypatch.setattr(instrument_sync, "seed_universe", failing_seed)

    with pytest.raises(RuntimeError, match="sync-secret"):
        await instrument_sync.run_tracked_sync(async_db, "seed-universe")

    run = db.query(InstrumentSyncRun).one()
    assert "sync-secret" not in (run.error or "")
    assert "<redacted>" in (run.error or "")


@pytest.mark.asyncio
async def test_metadata_sync_uses_canonical_profile_operation(db, instrument, monkeypatch):
    """The workload must charge the same operation used by provider contracts."""

    async_db = AsyncSessionAdapter(db)
    captured: dict[str, object] = {}

    async def _fail_closed(*args, **kwargs):
        captured["operation"] = args[2]
        raise RuntimeError("fixture provider unavailable")

    monkeypatch.setattr(instrument_sync, "execute_provider_call", _fail_closed)
    monkeypatch.setattr(instrument_sync.settings, "INSTRUMENT_METADATA_DELAY_SECONDS", 0)

    result = await sync_instruments(async_db, limit=1)

    assert captured["operation"] == "get_instrument_profile"
    assert result == {
        "updated": 0,
        "deactivated": 0,
        "total": 1,
        "processed": 1,
        "truncated": False,
    }


@pytest.mark.asyncio
async def test_metadata_sync_stops_at_its_deadline_and_keeps_committed_progress(
    db, instrument, monkeypatch
):
    """Production regression: the capped daily pass hit the 600s job timeout.

    It committed only at the end, so cancellation discarded every profile it
    had already spent provider quota on.
    """

    from app.models.instrument import Instrument

    for index in range(29):
        db.add(
            Instrument(
                symbol=f"MS{index:02d}",
                name=f"Meta {index}",
                currency="USD",
                instrument_type_id=instrument.instrument_type_id,
            )
        )
    db.commit()
    async_db = AsyncSessionAdapter(db)
    clock = [100.0]
    calls = []
    commits = []
    real_commit = async_db.commit

    async def counting_commit():
        commits.append(len(calls))
        await real_commit()

    async def slow_provider(*args, **kwargs):
        calls.append(args[2])
        clock[0] += 10.0
        raise RuntimeError("fixture provider unavailable")

    monkeypatch.setattr(async_db, "commit", counting_commit)
    monkeypatch.setattr(instrument_sync, "execute_provider_call", slow_provider)
    monkeypatch.setattr(instrument_sync.settings, "INSTRUMENT_METADATA_DELAY_SECONDS", 0)
    monkeypatch.setattr(instrument_sync, "time", type("T", (), {"monotonic": lambda: clock[0]}))

    result = await sync_instruments(async_db, limit=30, deadline=100.0 + 275.0)

    assert result["truncated"] is True
    assert result["processed"] == 28
    assert len(calls) == 28
    # Progress was committed mid-pass (after 25 instruments), not only at the end.
    assert commits[0] == 25
    assert commits[-1] == 28


@pytest.mark.asyncio
async def test_daily_metadata_task_bounds_the_pass_inside_the_job_timeout(monkeypatch):
    from app.tasks import instrument_sync_tasks

    captured = {}

    class _Session:
        async def __aenter__(self):
            return "db"

        async def __aexit__(self, *_args):
            return False

    async def fake_run(db, operation, *, limit, deadline):
        captured.update(operation=operation, limit=limit, deadline=deadline)
        return {"run_id": 1}

    monkeypatch.setattr(instrument_sync_tasks, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(instrument_sync_tasks, "run_tracked_sync", fake_run)
    monkeypatch.setattr(
        instrument_sync_tasks.settings, "INSTRUMENT_DAILY_METADATA_MAX_SECONDS", 10_000
    )
    before = instrument_sync_tasks.time.monotonic()

    await instrument_sync_tasks.sync_instruments_task({}, limit=5)

    assert captured["operation"] == "sync-instruments"
    assert captured["limit"] == 5
    assert before + 540.0 <= captured["deadline"] <= instrument_sync_tasks.time.monotonic() + 540.0
