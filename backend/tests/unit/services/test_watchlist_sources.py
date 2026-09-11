from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import watchlist_history as history
from app.services import watchlist_sources as sources


def test_watchlist_membership_cutoffs_normalize_persisted_timestamps_to_utc():
    item = SimpleNamespace(
        instrument_id=17,
        added_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
        left_screener_at=datetime(2024, 2, 1, 0, 0, tzinfo=UTC),
    )

    assert sources._watchlist_item_active_at(item, datetime(2024, 1, 15))
    assert sources._watchlist_item_active_at(
        item,
        datetime(2024, 2, 1, 1, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    assert not sources._watchlist_item_active_at(
        item,
        datetime(2024, 2, 1, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    assert sources._watchlist_item_as_of_exclusion(
        item,
        datetime(2024, 2, 1, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    ) == {
        "instrument_id": 17,
        "reason": "membership_not_active_at_as_of",
        "left_screener_at": "2024-02-01T00:00:00Z",
    }


def test_saved_explicit_source_known_at_cutoff_normalizes_to_utc():
    item = SimpleNamespace(
        updated_at=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        created_at=None,
    )

    before_known_at = datetime(2024, 1, 1, 1, 0, tzinfo=timezone(timedelta(hours=2)))
    at_known_at = datetime(2024, 1, 1, 2, 0, tzinfo=timezone(timedelta(hours=2)))

    assert sources._saved_explicit_known_at_exclusions(item, [17, 23], before_known_at) == (
        {
            "instrument_id": 17,
            "reason": "membership_not_known_at_as_of",
            "known_at": "2024-01-01T00:00:00Z",
        },
        {
            "instrument_id": 23,
            "reason": "membership_not_known_at_as_of",
            "known_at": "2024-01-01T00:00:00Z",
        },
    )
    assert sources._saved_explicit_known_at_exclusions(item, [17, 23], at_known_at) == ()


def test_holdings_route_provenance_serializes_published_at_as_canonical_utc():
    profile = SimpleNamespace(
        adapter_key="demo",
        adapter_status="verified",
        adapter_confidence=0.9,
    )
    snapshot = SimpleNamespace(
        source_quality="provider",
        completeness_status="complete",
        row_count=2,
        resolved_count=2,
        unresolved_count=0,
        total_weight=1.0,
        published_at=datetime(2024, 1, 1, 2, 0, tzinfo=timezone(timedelta(hours=2))),
        parser_version="v1",
        source_identifier="demo:2024-01-01",
        source_provider="demo",
        extra_data={},
    )

    provenance = sources._holdings_route_provenance(profile, snapshot)

    assert provenance["snapshot_published_at"] == "2024-01-01T00:00:00Z"


@pytest.mark.asyncio
async def test_market_group_resolver_normalizes_membership_cutoff():
    item = SimpleNamespace(
        id=1,
        instrument_id=17,
        position=1,
        weight=None,
        relationship_type="member",
        source="provider",
        verification_state="verified",
        added_at=None,
        left_screener_at=None,
        effective_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
        known_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
    )
    group = SimpleNamespace(
        stable_key="demo",
        group_type="market_group",
        name="Demo",
        members=[item],
        source="provider",
        provenance={},
        effective_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
        known_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
    )

    class Result:
        def scalar_one_or_none(self):
            return group

    class FakeDB:
        async def execute(self, _statement):
            return Result()

    before_known_at = datetime(2024, 1, 1, 13, 0, tzinfo=timezone(timedelta(hours=2)))
    at_known_at = datetime(2024, 1, 1, 14, 0, tzinfo=timezone(timedelta(hours=2)))

    before = await sources.resolve_watchlist_source(
        FakeDB(), 1, "market-group:demo", as_of=before_known_at
    )
    at = await sources.resolve_watchlist_source(FakeDB(), 1, "market-group:demo", as_of=at_known_at)

    assert before.members == ()
    assert before.exclusions == ({"instrument_id": 17, "reason": "membership_not_known_at_as_of"},)
    assert [member.instrument_id for member in at.members] == [17]


@pytest.mark.asyncio
async def test_watchlist_history_bars_bind_normalized_cutoff(monkeypatch):
    as_of = datetime(2024, 1, 1, 14, 0, tzinfo=timezone(timedelta(hours=2)))

    async def fake_plan(*_args, **_kwargs):
        return {
            "source_ids": ["watchlist:one"],
            "timeframes": ["D1"],
            "as_of": as_of,
            "max_instruments": 5000,
            "instrument_ids": [17],
            "available_instrument_count": 1,
            "selected_instrument_count": 1,
            "limited": False,
            "sources": [
                {
                    "source_id": "watchlist:one",
                    "source_kind": "personal",
                    "name": "One",
                    "locked": False,
                    "status": "ready",
                    "excluded_count": 0,
                    "member_disposition": {
                        "canonical": 1,
                        "placeholder": 0,
                        "unresolved": 0,
                        "excluded": 0,
                    },
                }
            ],
        }

    class FakeResult:
        def all(self):
            return []

    class FakeDB:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            return FakeResult()

    monkeypatch.setattr(history, "plan_watchlist_source_history_refresh", fake_plan)
    db = FakeDB()
    await history.build_watchlist_source_history_status(
        db, 1, source_id="watchlist:one", as_of=as_of, timeframes=["D1"]
    )

    expected = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    bound_values = [
        value
        for statement in db.statements
        for value in statement.compile().params.values()
        if isinstance(value, datetime)
    ]
    assert expected in bound_values
