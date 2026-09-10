from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.services import watchlist_history as history


def test_watchlist_history_normalizers_dedupe_sources_and_timeframes():
    assert history.normalize_source_ids(["watchlist:1", " market-group:sp500 ", "watchlist:1"]) == [
        "watchlist:1",
        "market-group:sp500",
    ]
    assert history.normalize_history_timeframes(["d1", "W1", "D1"]) == ["D1", "W1"]

    with pytest.raises(ValueError, match="At least one watchlist source"):
        history.normalize_source_ids([])
    with pytest.raises(ValueError, match="Unsupported history timeframe"):
        history.normalize_history_timeframes(["TICK"])


def test_state_factor_evidence_does_not_project_future_state_into_historical_views():
    lineage = [
        {
            "instrument_id": 10,
            "provider_bar_count": 252,
            "derived_bar_count": 0,
            "provider_source_ids": {7},
        }
    ]
    future_state = [
        (
            10,
            7,
            "D1:adj",
            {
                "adjustment_provenance": {
                    "factor_status": "rebuildable_split_factors",
                    "factor_version": "afv1-future",
                }
            },
            datetime(2025, 2, 1, tzinfo=UTC),
            datetime(2025, 2, 2, tzinfo=UTC),
        )
    ]

    assert (
        history.state_factor_evidence(
            lineage,
            future_state,
            "D1",
            as_of=datetime(2025, 1, 31, tzinfo=UTC),
        )
        is None
    )

    evidence = history.state_factor_evidence(
        lineage,
        future_state,
        "D1",
        as_of=datetime(2025, 2, 2, tzinfo=UTC),
    )
    assert evidence is not None
    assert evidence["factor_version"] == "afv1-future"


@pytest.mark.asyncio
async def test_watchlist_history_plan_uses_user_scope_and_deduplicates_members(monkeypatch):
    calls = []

    async def fake_resolve(_db, user_id, source_id, *, as_of):
        calls.append((user_id, source_id, as_of))
        if source_id == "watchlist:private":
            return SimpleNamespace(
                descriptor=SimpleNamespace(
                    source_id=source_id,
                    source_kind="personal",
                    name="Private",
                    locked=False,
                    membership_version="private-v1",
                    effective_at=datetime(2026, 1, 1, tzinfo=UTC),
                    known_at=datetime(2026, 1, 2, tzinfo=UTC),
                    provenance={
                        "timing_provenance": {
                            "effective_at": "provider_reported",
                            "known_at": "provider_reported",
                        },
                        "snapshot_published_at": "2026-01-03T00:00:00+00:00",
                        "snapshot_cadence": "month_end",
                        "snapshot_parser_version": "sec-v2",
                        "snapshot_source_identifier": "issuer-feed",
                    },
                ),
                members=(SimpleNamespace(instrument_id=10), SimpleNamespace(instrument_id=20)),
                exclusions=(),
            )
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                source_id=source_id,
                source_kind="index_membership",
                name="Managed",
                locked=True,
                membership_version="managed-v1",
            ),
            members=(SimpleNamespace(instrument_id=20), SimpleNamespace(instrument_id=30)),
            exclusions=({"reason": "unresolved_holding"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    as_of = SimpleNamespace()
    plan = await history.plan_watchlist_source_history_refresh(
        object(),
        42,
        source_ids=["watchlist:private", "market-group:managed"],
        as_of=as_of,
        max_instruments=2,
        timeframes=["D1", "D1"],
    )

    assert calls == [(42, "watchlist:private", as_of), (42, "market-group:managed", as_of)]
    assert plan["instrument_ids"] == [10, 20]
    assert plan["available_instrument_count"] == 3
    assert plan["selected_instrument_count"] == 2
    assert plan["limited"] is True
    assert plan["sources"][0]["selected_count"] == 2
    assert plan["sources"][0]["effective_at"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert plan["sources"][0]["known_at"] == datetime(2026, 1, 2, tzinfo=UTC)
    assert plan["sources"][0]["timing_provenance"] == {
        "effective_at": "provider_reported",
        "known_at": "provider_reported",
    }
    assert plan["sources"][0]["published_at"] == "2026-01-03T00:00:00+00:00"
    assert plan["sources"][0]["cadence"] == "month_end"
    assert plan["sources"][0]["parser_version"] == "sec-v2"
    assert plan["sources"][0]["source_identifier"] == "issuer-feed"
    assert plan["sources"][1]["deduplicated_count"] == 1
    assert plan["sources"][1]["locked"] is True
    assert plan["sources"][1]["member_disposition"] == {
        "canonical": 2,
        "placeholder": 0,
        "unresolved": 1,
        "excluded": 0,
    }


@pytest.mark.asyncio
async def test_watchlist_history_plan_reports_all_member_dispositions(monkeypatch):
    async def fake_resolve(_db, _user_id, source_id, *, as_of):
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                source_id=source_id,
                source_kind="index_membership",
                name="Mixed",
                locked=True,
                membership_version="mixed-v1",
                provenance={"placeholder_member_count": 2},
            ),
            members=(
                SimpleNamespace(instrument_id=10),
                SimpleNamespace(instrument_id=10),
                SimpleNamespace(instrument_id=20),
            ),
            exclusions=(
                {"reason": "unresolved_holding"},
                {"reason": "unresolved_holding"},
                {"reason": "unresolved_holding"},
                {"reason": "cash_holding"},
                {"reason": "non_equity_holding"},
            ),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_watchlist_source_history_refresh(
        object(), 7, source_ids=["market-group:mixed"], timeframes=["D1"]
    )

    assert plan["sources"][0]["member_disposition"] == {
        "canonical": 2,
        "placeholder": 2,
        "unresolved": 1,
        "excluded": 2,
    }


@pytest.mark.asyncio
async def test_watchlist_history_plan_retains_unavailable_source(monkeypatch):
    async def fake_resolve(_db, _user_id, source_id, *, as_of):
        raise LookupError(f"{source_id} is not visible")

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_watchlist_source_history_refresh(
        object(),
        7,
        source_ids=["watchlist:missing"],
    )

    assert plan["instrument_ids"] == []
    assert plan["sources"] == [
        {
            "source_id": "watchlist:missing",
            "source_kind": None,
            "name": "watchlist:missing",
            "locked": False,
            "status": "unavailable",
            "member_count": 0,
            "selected_count": 0,
            "deduplicated_count": 0,
            "excluded_count": 0,
            "member_disposition": {
                "canonical": 0,
                "placeholder": 0,
                "unresolved": 0,
                "excluded": 0,
            },
            "membership_version": None,
            "effective_at": None,
            "known_at": None,
            "timing_provenance": {},
            "published_at": None,
            "cadence": None,
            "parser_version": None,
            "source_identifier": None,
            "message": "watchlist:missing is not visible",
        }
    ]


@pytest.mark.asyncio
async def test_watchlist_history_plan_and_status_preserve_pending_locked_source(monkeypatch):
    async def fake_resolve(_db, _user_id, source_id, *, as_of):
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                source_id=source_id,
                source_kind="etf_holdings",
                name="Unhydrated ETF holdings",
                locked=True,
                membership_version="etf-v1",
                provenance={"availability": "profile_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "etf_profile_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_watchlist_source_history_refresh(
        object(),
        7,
        source_ids=["etf-holdings:UNHYDRATED"],
        timeframes=["D1"],
    )

    assert plan["sources"][0]["status"] == "pending"
    assert plan["sources"][0]["message"] == "etf_profile_not_loaded"

    class FakeDB:
        async def execute(self, _statement):
            raise AssertionError("pending source with no members must not query bars")

    status = await history.build_watchlist_source_history_status(
        FakeDB(),
        7,
        source_id="etf-holdings:UNHYDRATED",
        timeframes=["D1"],
    )
    assert status["overall_status"] == "pending"
    assert status["selected_instrument_count"] == 0


@pytest.mark.asyncio
async def test_watchlist_history_status_uses_local_coverage_and_worker_progress(monkeypatch):
    async def fake_plan(*_args, **_kwargs):
        return {
            "source_ids": ["benchmark-family:sp500:cap_weight"],
            "timeframes": ["D1"],
            "as_of": None,
            "max_instruments": 5000,
            "instrument_ids": [10, 20],
            "available_instrument_count": 2,
            "selected_instrument_count": 2,
            "limited": False,
            "sources": [
                {
                    "source_id": "benchmark-family:sp500:cap_weight",
                    "source_kind": "index_membership",
                    "name": "S&P 500 — Cap weight",
                    "locked": True,
                    "excluded_count": 1,
                    "member_disposition": {
                        "canonical": 2,
                        "placeholder": 0,
                        "unresolved": 1,
                        "excluded": 0,
                    },
                    "membership_version": "sp500-v1",
                    "message": None,
                }
            ],
        }

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1

            class FakeResult:
                def all(self_inner):
                    if self.calls == 1:
                        return [
                            SimpleNamespace(
                                timeframe=SimpleNamespace(value="D1"),
                                covered_count=1,
                                bar_count=250,
                                oldest=datetime(2024, 1, 2, tzinfo=UTC),
                                newest=datetime(2025, 1, 2, tzinfo=UTC),
                            )
                        ]
                    return [(10, SimpleNamespace(value="D1"), 250)]

            return FakeResult()

    monkeypatch.setattr(history, "plan_watchlist_source_history_refresh", fake_plan)
    status = await history.build_watchlist_source_history_status(
        FakeDB(),
        42,
        source_id="benchmark-family:sp500:cap_weight",
        progress_by_instrument={20: {"status": "in_progress", "results": {}}},
    )

    assert status["locked"] is True
    assert status["overall_status"] == "fetching"
    assert status["analysis_ready"] is False
    assert status["analysis_ready_status"] == "pending"
    assert status["selected_instrument_count"] == 2
    assert status["excluded_count"] == 1
    assert status["member_disposition"] == {
        "canonical": 2,
        "placeholder": 0,
        "unresolved": 1,
        "excluded": 0,
    }
    assert status["timeframes"] == [
        {
            "timeframe": "D1",
            "member_count": 2,
            "covered_member_count": 1,
            "coverage_percent": 50.0,
            "analysis_ready_member_count": 0,
            "analysis_ready_percent": 0.0,
            "required_bar_count": 252,
            "bar_count": 250,
            "provider_member_count": 1,
            "derived_member_count": 0,
            "provider_only_member_count": 1,
            "derived_only_member_count": 0,
            "mixed_member_count": 0,
            "provider_bar_count": 250,
            "derived_bar_count": 0,
            "source_lineage": "provider_only",
            "adjustment_provenance": {
                "mode": "split_adjusted",
                "source_kind": "provider_observation",
                "factor_status": "provider_native_opaque",
                "factor_version": None,
                "contract_version": 1,
            },
            "oldest": datetime(2024, 1, 2, tzinfo=UTC),
            "newest": datetime(2025, 1, 2, tzinfo=UTC),
            "in_progress_count": 1,
            "complete_count": 0,
            "failed_count": 0,
            "pending_count": 0,
        }
    ]


@pytest.mark.asyncio
async def test_watchlist_history_status_separates_covered_from_analysis_ready(monkeypatch):
    async def fake_plan(*_args, **_kwargs):
        return {
            "source_ids": ["market-group:sp500"],
            "timeframes": ["D1", "W1"],
            "as_of": None,
            "max_instruments": 5000,
            "instrument_ids": [10],
            "available_instrument_count": 1,
            "selected_instrument_count": 1,
            "limited": False,
            "sources": [
                {
                    "source_id": "market-group:sp500",
                    "source_kind": "index_membership",
                    "name": "S&P 500",
                    "locked": True,
                    "status": "ready",
                    "excluded_count": 0,
                    "membership_version": "v1",
                    "message": None,
                }
            ],
        }

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1

            class FakeResult:
                def __init__(self, call_number):
                    self.call_number = call_number

                def all(self_inner):
                    if self_inner.call_number == 1:
                        return [
                            SimpleNamespace(
                                timeframe=SimpleNamespace(value="D1"),
                                covered_count=1,
                                bar_count=252,
                                oldest=None,
                                newest=None,
                            ),
                            SimpleNamespace(
                                timeframe=SimpleNamespace(value="W1"),
                                covered_count=1,
                                bar_count=10,
                                oldest=None,
                                newest=None,
                            ),
                        ]
                    return [
                        (10, SimpleNamespace(value="D1"), 250, False),
                        (10, SimpleNamespace(value="D1"), 2, True),
                        (10, SimpleNamespace(value="W1"), 10, True),
                    ]

            return FakeResult(self.calls)

    monkeypatch.setattr(history, "plan_watchlist_source_history_refresh", fake_plan)
    status = await history.build_watchlist_source_history_status(
        FakeDB(), 42, source_id="market-group:sp500", timeframes=["D1", "W1"]
    )

    assert status["overall_status"] == "ready"
    assert status["analysis_ready"] is False
    assert status["analysis_ready_status"] == "partial"
    d1 = next(item for item in status["timeframes"] if item["timeframe"] == "D1")
    assert d1["analysis_ready_member_count"] == 1
    assert d1["provider_member_count"] == 1
    assert d1["derived_member_count"] == 1
    assert d1["provider_only_member_count"] == 0
    assert d1["derived_only_member_count"] == 0
    assert d1["mixed_member_count"] == 1
    assert d1["provider_bar_count"] == 250
    assert d1["derived_bar_count"] == 2
    assert d1["source_lineage"] == "provider_and_derived"
    assert d1["adjustment_provenance"] == {
        "mode": "split_adjusted",
        "source_kind": "mixed_provider_and_derived",
        "factor_status": "mixed_provider_native_opaque_and_inherited_from_canonical_d1",
        "factor_version": None,
        "contract_version": 1,
    }
    w1 = next(item for item in status["timeframes"] if item["timeframe"] == "W1")
    assert w1["source_lineage"] == "derived_only"
    assert w1["derived_only_member_count"] == 1
    assert w1["adjustment_provenance"]["factor_status"] == "inherited_from_canonical_d1"


@pytest.mark.asyncio
async def test_watchlist_history_status_exposes_consistent_factor_version(monkeypatch):
    async def fake_plan(*_args, **_kwargs):
        return {
            "source_ids": ["market-group:sp500"],
            "timeframes": ["D1"],
            "as_of": None,
            "max_instruments": 5000,
            "instrument_ids": [10, 20],
            "available_instrument_count": 2,
            "selected_instrument_count": 2,
            "limited": False,
            "sources": [
                {
                    "source_id": "market-group:sp500",
                    "source_kind": "index_membership",
                    "name": "S&P 500",
                    "locked": True,
                    "status": "ready",
                    "excluded_count": 0,
                    "membership_version": "v1",
                    "message": None,
                }
            ],
        }

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1

            class FakeResult:
                def __init__(self, call_number):
                    self.call_number = call_number

                def all(self_inner):
                    if self_inner.call_number == 1:
                        return [
                            SimpleNamespace(
                                timeframe=SimpleNamespace(value="D1"),
                                covered_count=2,
                                bar_count=504,
                                oldest=None,
                                newest=None,
                            )
                        ]
                    if self_inner.call_number == 2:
                        return [
                            (10, SimpleNamespace(value="D1"), 252, False, 7),
                            (20, SimpleNamespace(value="D1"), 252, False, 7),
                        ]
                    return [
                        (
                            10,
                            7,
                            "D1:adj",
                            {
                                "adjustment_provenance": {
                                    "factor_status": "rebuildable_split_factors",
                                    "factor_version": "afv1-stable",
                                }
                            },
                        ),
                        (
                            20,
                            7,
                            "D1:adj",
                            {
                                "adjustment_provenance": {
                                    "factor_status": "rebuildable_split_factors",
                                    "factor_version": "afv1-stable",
                                }
                            },
                        ),
                    ]

            return FakeResult(self.calls)

    monkeypatch.setattr(history, "plan_watchlist_source_history_refresh", fake_plan)
    status = await history.build_watchlist_source_history_status(
        FakeDB(), 42, source_id="market-group:sp500", timeframes=["D1"]
    )

    provenance = status["timeframes"][0]["adjustment_provenance"]
    assert provenance == {
        "mode": "split_adjusted",
        "source_kind": "provider_observation",
        "factor_status": "rebuildable_split_factors",
        "factor_version": "afv1-stable",
        "contract_version": 1,
        "factor_versioned_member_count": 2,
        "factor_opaque_member_count": 0,
        "factor_unavailable_member_count": 0,
    }


@pytest.mark.asyncio
async def test_watchlist_history_status_reads_local_provider_factor_state(monkeypatch):
    async def fake_plan(*_args, **_kwargs):
        return {
            "source_ids": ["watchlist:derived"],
            "timeframes": ["D1"],
            "as_of": None,
            "max_instruments": 5000,
            "instrument_ids": [10],
            "available_instrument_count": 1,
            "selected_instrument_count": 1,
            "limited": False,
            "sources": [
                {
                    "source_id": "watchlist:derived",
                    "source_kind": "personal",
                    "name": "Derived",
                    "locked": False,
                    "status": "ready",
                    "excluded_count": 0,
                    "member_disposition": {
                        "canonical": 1,
                        "placeholder": 0,
                        "unresolved": 0,
                        "excluded": 0,
                    },
                    "membership_version": "v1",
                    "message": None,
                }
            ],
        }

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1

            class FakeResult:
                def __init__(self, call_number):
                    self.call_number = call_number

                def all(self_inner):
                    if self_inner.call_number == 1:
                        return [
                            SimpleNamespace(
                                timeframe=SimpleNamespace(value="D1"),
                                covered_count=1,
                                bar_count=252,
                                oldest=datetime(2025, 1, 2, tzinfo=UTC),
                                newest=datetime(2025, 12, 31, tzinfo=UTC),
                            )
                        ]
                    if self_inner.call_number == 2:
                        return [
                            (
                                10,
                                SimpleNamespace(value="D1"),
                                252,
                                True,
                                None,
                                "provider_adjustment_factor",
                            )
                        ]
                    return [
                        (
                            10,
                            None,
                            "D1:adj:provider_adjustment_factor",
                            {
                                "adjustment_provenance": {
                                    "factor_status": "rebuildable_provider_factors",
                                    "factor_version": "afv1-provider-local",
                                }
                            },
                        )
                    ]

            return FakeResult(self.calls)

    monkeypatch.setattr(history, "plan_watchlist_source_history_refresh", fake_plan)
    status = await history.build_watchlist_source_history_status(
        FakeDB(), 42, source_id="watchlist:derived", timeframes=["D1"]
    )

    provenance = status["timeframes"][0]["adjustment_provenance"]
    assert provenance["factor_version"] == "afv1-provider-local"
    assert provenance["factor_status"] == "rebuildable_provider_factors"
    assert provenance["factor_versioned_member_count"] == 1
    assert provenance["factor_opaque_member_count"] == 0
    assert provenance["factor_unavailable_member_count"] == 0
