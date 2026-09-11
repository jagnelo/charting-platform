from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.services import benchmark_family_history as history


def test_history_end_for_date_is_inclusive_utc_end_of_day():
    assert history.history_end_for_date(date(2024, 1, 2)) == datetime(
        2024, 1, 2, 23, 59, 59, 999999, tzinfo=UTC
    )


def test_history_end_iso_normalizes_naive_and_offset_aware_bounds():
    assert history.history_end_iso(datetime(2024, 1, 2)) == "2024-01-02T00:00:00Z"
    assert history.history_end_iso(datetime(2024, 1, 2, tzinfo=UTC)) == ("2024-01-02T00:00:00Z")
    assert history.history_end_iso(None) is None


def test_canonical_history_job_id_separates_historical_end_bounds():
    assert history.canonical_history_job_id(7, ["D1"]) == "watchlist-source-history:7:D1"
    assert history.canonical_history_job_id(7, ["W1", "D1", "W1"]) == (
        "watchlist-source-history:7:D1,W1"
    )
    assert (
        history.canonical_history_job_id(7, ["D1"], history.datetime(2024, 1, 2))
        == "watchlist-source-history:7:D1:end=2024-01-02T00:00:00Z"
    )


def test_family_history_normalizers_reject_unknown_values_and_dedupe_timeframes():
    assert history.normalize_family_roles(["growth", "cap_weight", "growth"]) == [
        "cap_weight",
        "growth",
    ]
    assert history.normalize_history_timeframes(["d1", "W1", "D1"]) == ["D1", "W1"]

    with pytest.raises(ValueError, match="Unknown benchmark family"):
        history.normalize_family_keys(["not-a-family"])
    with pytest.raises(ValueError, match="Unsupported benchmark family role"):
        history.normalize_family_roles(["momentum"])
    with pytest.raises(ValueError, match="Unsupported history timeframe"):
        history.normalize_history_timeframes(["TICK"])


@pytest.mark.asyncio
async def test_family_history_plan_deduplicates_members_and_preserves_pending_legs(monkeypatch):
    async def fake_resolve(_db, _user_id, source_id, *, as_of):
        assert _user_id == 0
        assert as_of is None
        if source_id.endswith(":cap_weight"):
            return SimpleNamespace(
                descriptor=SimpleNamespace(
                    membership_version="cap-v1",
                    provenance={"availability": "available"},
                ),
                members=(
                    SimpleNamespace(instrument_id=10),
                    SimpleNamespace(instrument_id=20),
                ),
                exclusions=({"reason": "unresolved_holding"},),
            )
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="empty-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(),
        family_keys=[history.normalize_family_keys(None)[0]],
        roles=["cap_weight", "equal_weight"],
        max_instruments=1,
        timeframes=["D1", "D1"],
    )

    assert plan["instrument_ids"] == [10]
    assert plan["available_instrument_count"] == 2
    assert plan["selected_instrument_count"] == 1
    assert plan["limited"] is True
    assert plan["timeframes"] == ["D1"]
    assert plan["legs"][0]["selected_count"] == 2
    assert plan["legs"][0]["member_disposition"] == {
        "canonical": 2,
        "placeholder": 0,
        "unresolved": 1,
        "excluded": 0,
    }
    assert plan["legs"][1]["status"] == "pending"
    assert plan["legs"][1]["message"] == "holdings_snapshot_not_loaded"
    assert plan["legs"][1]["member_disposition"] == {
        "canonical": 0,
        "placeholder": 0,
        "unresolved": 0,
        "excluded": 0,
    }


@pytest.mark.asyncio
async def test_family_history_plan_reports_placeholder_and_excluded_dispositions(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="sp500-v1",
                provenance={"availability": "available", "placeholder_member_count": 2},
            ),
            members=(SimpleNamespace(instrument_id=10), SimpleNamespace(instrument_id=10)),
            exclusions=(
                {"reason": "unresolved_holding"},
                {"reason": "unresolved_holding"},
                {"reason": "unresolved_holding"},
                {"reason": "cash_holding"},
                {"reason": "non_equity_holding"},
            ),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(), family_keys=[history.normalize_family_keys(None)[0]], roles=["cap_weight"]
    )

    assert plan["legs"][0]["member_disposition"] == {
        "canonical": 1,
        "placeholder": 2,
        "unresolved": 1,
        "excluded": 2,
    }


@pytest.mark.asyncio
async def test_family_history_plan_keeps_unmapped_roles_unavailable(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert _user_id == 0
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="missing-v1",
                provenance={"availability": "unavailable"},
            ),
            members=(),
            exclusions=({"reason": "benchmark_family_role_unavailable"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(),
        family_keys=[history.normalize_family_keys(None)[0]],
        roles=["value"],
    )

    assert plan["legs"][0]["status"] == "unavailable"
    assert plan["legs"][0]["message"] == "benchmark_family_role_unavailable"


@pytest.mark.asyncio
async def test_family_history_plan_preserves_nasdaq_historical_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, source_id, *, as_of):
        assert _user_id == 0
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version=f"{source_id}-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(),
        family_keys=["nasdaq100"],
        roles=["cap_weight", "equal_weight"],
    )

    legs = {leg["role"]: leg for leg in plan["legs"]}
    assert legs["cap_weight"]["status"] == "pending"
    assert legs["cap_weight"]["history_route_status"] == "sec_filing_reconstruction"
    assert legs["cap_weight"]["history_route_provider"] == "sec"
    assert legs["cap_weight"]["history_route_policy"] == (
        "latest_sec_filing_report_on_or_before_requested_date"
    )
    assert legs["cap_weight"]["history_route_source_url"].endswith("CIK0001067839.json")
    assert legs["equal_weight"]["history_route_source_url"].endswith("CIK0001424958.json")


@pytest.mark.asyncio
async def test_family_history_plan_preserves_ishares_as_of_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(),
        family_keys=["russell1000"],
        roles=["cap_weight", "value", "growth"],
    )

    expected_source = (
        "https://www.blackrock.com/varnish-api/blk-one01-product-data/"
        "product-data/api/v2/get-product-data"
    )
    legs = {leg["role"]: leg for leg in plan["legs"]}
    assert {leg["history_route_status"] for leg in legs.values()} == {"issuer_as_of_date"}
    assert {leg["history_route_provider"] for leg in legs.values()} == {"ishares"}
    assert {leg["history_route_policy"] for leg in legs.values()} == {
        "issuer_public_json_api_as_of_date"
    }
    assert {leg["history_route_source_url"] for leg in legs.values()} == {expected_source}


@pytest.mark.asyncio
async def test_family_history_plan_has_no_spdr_current_only_routes_after_sec_identity(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(),
        family_keys=["sp500", "sp400", "sp600", "sp1500"],
        roles=["cap_weight", "value", "growth"],
    )

    mapped_legs = [leg for leg in plan["legs"] if leg["history_route_provider"] == "spdr"]
    assert mapped_legs == []


@pytest.mark.asyncio
async def test_family_history_plan_preserves_spy_sec_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(), family_keys=["sp500"], roles=["cap_weight"]
    )

    leg = plan["legs"][0]
    assert leg["history_route_status"] == "sec_filing_reconstruction"
    assert leg["history_route_provider"] == "sec"
    assert leg["history_route_policy"] == ("latest_sec_filing_report_on_or_before_requested_date")
    assert leg["history_route_source_url"] == (
        "https://data.sec.gov/submissions/CIK0000884394.json"
    )


@pytest.mark.asyncio
async def test_family_history_plan_preserves_slyv_sec_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(), family_keys=["sp600"], roles=["value"]
    )

    leg = plan["legs"][0]
    assert leg["history_route_status"] == "sec_filing_reconstruction"
    assert leg["history_route_provider"] == "sec"
    assert leg["history_route_policy"] == ("latest_sec_filing_report_on_or_before_requested_date")
    assert leg["history_route_source_url"] == (
        "https://data.sec.gov/submissions/CIK0001064642.json"
    )


@pytest.mark.asyncio
async def test_family_history_plan_preserves_slyg_sec_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(), family_keys=["sp600"], roles=["growth"]
    )

    leg = plan["legs"][0]
    assert leg["history_route_status"] == "sec_filing_reconstruction"
    assert leg["history_route_provider"] == "sec"
    assert leg["history_route_policy"] == ("latest_sec_filing_report_on_or_before_requested_date")
    assert leg["history_route_source_url"] == (
        "https://data.sec.gov/submissions/CIK0001064642.json"
    )


@pytest.mark.asyncio
async def test_family_history_plan_preserves_sptm_sec_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(), family_keys=["sp1500"], roles=["cap_weight"]
    )

    leg = plan["legs"][0]
    assert leg["history_route_status"] == "sec_filing_reconstruction"
    assert leg["history_route_provider"] == "sec"
    assert leg["history_route_policy"] == ("latest_sec_filing_report_on_or_before_requested_date")
    assert leg["history_route_source_url"] == (
        "https://data.sec.gov/submissions/CIK0001064642.json"
    )


@pytest.mark.asyncio
async def test_family_history_plan_preserves_mdy_sec_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(), family_keys=["sp400"], roles=["cap_weight"]
    )

    leg = plan["legs"][0]
    assert leg["family_key"] == "sp400"
    assert leg["role"] == "cap_weight"
    assert leg["history_route_status"] == "sec_filing_reconstruction"
    assert leg["history_route_provider"] == "sec"
    assert leg["history_route_source_url"] == (
        "https://data.sec.gov/submissions/CIK0000936958.json"
    )


@pytest.mark.asyncio
async def test_family_history_plan_preserves_spyv_sec_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(), family_keys=["sp500"], roles=["value"]
    )

    leg = plan["legs"][0]
    assert leg["history_route_status"] == "sec_filing_reconstruction"
    assert leg["history_route_provider"] == "sec"
    assert leg["history_route_source_url"] == (
        "https://data.sec.gov/submissions/CIK0001064642.json"
    )


@pytest.mark.asyncio
async def test_family_history_plan_preserves_spyg_sec_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(), family_keys=["sp500"], roles=["growth"]
    )

    leg = plan["legs"][0]
    assert leg["history_route_status"] == "sec_filing_reconstruction"
    assert leg["history_route_provider"] == "sec"
    assert leg["history_route_policy"] == ("latest_sec_filing_report_on_or_before_requested_date")
    assert leg["history_route_source_url"] == (
        "https://data.sec.gov/submissions/CIK0001064642.json"
    )


@pytest.mark.asyncio
async def test_family_history_plan_preserves_mdyg_sec_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(), family_keys=["sp400"], roles=["growth"]
    )

    leg = plan["legs"][0]
    assert leg["history_route_status"] == "sec_filing_reconstruction"
    assert leg["history_route_provider"] == "sec"
    assert leg["history_route_policy"] == ("latest_sec_filing_report_on_or_before_requested_date")
    assert leg["history_route_source_url"] == (
        "https://data.sec.gov/submissions/CIK0001064642.json"
    )


@pytest.mark.asyncio
async def test_family_history_plan_preserves_mdyv_sec_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(), family_keys=["sp400"], roles=["value"]
    )

    leg = plan["legs"][0]
    assert leg["history_route_status"] == "sec_filing_reconstruction"
    assert leg["history_route_provider"] == "sec"


@pytest.mark.asyncio
async def test_family_history_plan_preserves_invesco_sec_route_evidence(monkeypatch):
    async def fake_resolve(_db, _user_id, _source_id, *, as_of):
        assert as_of is None
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                membership_version="pending-v1",
                provenance={"availability": "holdings_snapshot_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(),
        family_keys=["sp500"],
        roles=["equal_weight"],
    )

    leg = plan["legs"][0]
    assert leg["history_route_status"] == "sec_filing_reconstruction"
    assert leg["history_route_provider"] == "sec"
    assert leg["history_route_policy"] == "latest_sec_filing_report_on_or_before_requested_date"
    assert leg["history_route_source_url"] == (
        "https://data.sec.gov/submissions/CIK0001209466.json"
    )


@pytest.mark.asyncio
async def test_queue_snapshot_member_history_deduplicates_canonical_members_and_reports_queue_state():
    class Result:
        def all(self):
            return [
                (101, 10, "security", "equity", True),
                (101, 20, "security", "equity", True),
                (102, 20, "security", "equity", True),
                (102, 30, "security", "equity", True),
            ]

    class Session:
        async def execute(self, _statement):
            return Result()

    class Redis:
        def __init__(self):
            self.calls = []

        async def enqueue_job(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return object()

    redis = Redis()
    result = await history.queue_snapshot_member_history(
        Session(),
        redis,
        [102, 101, 102],
        timeframes=["D1", "W1", "D1"],
        max_instruments=2,
    )

    assert result == {
        "status": "queued",
        "snapshot_ids": [102, 101],
        "available_instrument_count": 3,
        "selected_instrument_count": 2,
        "limited": True,
        "queued": 2,
        "already_queued": 0,
        "queue_errors": [],
        "queue_error_count": 0,
        "unresolved_count": 0,
        "timeframes": ["D1", "W1"],
        "history_end": None,
    }
    assert redis.calls == [
        (
            ("task_bulk_fetch_instrument", 10, ["D1", "W1"]),
            {"_job_id": "watchlist-source-history:10:D1,W1"},
        ),
        (
            ("task_bulk_fetch_instrument", 20, ["D1", "W1"]),
            {"_job_id": "watchlist-source-history:20:D1,W1"},
        ),
    ]

    historical = await history.queue_snapshot_member_history(
        Session(),
        redis,
        [101],
        timeframes=["D1"],
        max_instruments=2,
        end=history.datetime(2024, 1, 2),
    )
    assert historical["queued"] == 2
    assert historical["history_end"] == "2024-01-02T00:00:00Z"
    assert redis.calls[-2][0] == (
        "task_bulk_fetch_instrument",
        10,
        ["D1"],
        None,
        "2024-01-02T00:00:00Z",
    )
    assert "end=2024-01-02T00:00:00Z" in redis.calls[-2][1]["_job_id"]


@pytest.mark.asyncio
async def test_queue_snapshot_member_history_accepts_issuer_equity_label_variants():
    class Result:
        def all(self):
            return [
                (101, 10, "security", "common stock", True),
                (101, 20, "security", "real estate investment trust", True),
                (101, 30, "security", "money market fund, taxable", True),
            ]

    class Session:
        async def execute(self, _statement):
            return Result()

    class Redis:
        def __init__(self):
            self.calls = []

        async def enqueue_job(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return object()

    redis = Redis()
    result = await history.queue_snapshot_member_history(Session(), redis, [101])

    assert result["available_instrument_count"] == 2
    assert result["selected_instrument_count"] == 2
    assert result["unresolved_count"] == 1
    assert [call[0][1] for call in redis.calls] == [10, 20]


@pytest.mark.asyncio
async def test_queue_snapshot_member_history_skips_internal_placeholder_instruments():
    class Result:
        def all(self):
            return [
                (101, 10, "security", "equity", True, "AAPL"),
                (101, 20, "security", "equity", True, "HOLDING-ABC123"),
            ]

    class Session:
        async def execute(self, _statement):
            return Result()

    class Redis:
        def __init__(self):
            self.calls = []

        async def enqueue_job(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return object()

    redis = Redis()
    result = await history.queue_snapshot_member_history(Session(), redis, [101])

    assert result["available_instrument_count"] == 1
    assert result["selected_instrument_count"] == 1
    assert result["unresolved_count"] == 1
    assert [call[0][1] for call in redis.calls] == [10]


@pytest.mark.asyncio
async def test_queue_snapshot_member_history_retains_member_queue_errors_and_continues():
    class Result:
        def all(self):
            return [
                (101, 10, "security", "equity", True),
                (101, 20, "security", "equity", True),
                (101, 30, "security", "equity", True),
            ]

    class Session:
        async def execute(self, _statement):
            return Result()

    class Redis:
        def __init__(self):
            self.calls = []

        async def enqueue_job(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            if args[1] == 20:
                raise RuntimeError("transient history queue failure")
            return object()

    redis = Redis()
    result = await history.queue_snapshot_member_history(Session(), redis, [101])

    assert result["status"] == "queue_error"
    assert result["available_instrument_count"] == 3
    assert result["selected_instrument_count"] == 3
    assert result["queued"] == 2
    assert result["already_queued"] == 0
    assert result["queue_error_count"] == 1
    assert result["queue_errors"] == [
        {
            "status": "queue_error",
            "instrument_id": 20,
            "error": "transient history queue failure",
        }
    ]
    assert [call[0][1] for call in redis.calls] == [10, 20, 30]


@pytest.mark.asyncio
async def test_snapshot_history_plan_is_bounded_and_excludes_fixture_rows(monkeypatch):
    monkeypatch.setattr(
        history,
        "BENCHMARK_FAMILY_REGISTRY",
        (
            {
                "logical_key": "sp500",
                "cap_weight": {"symbol": "SPY"},
                "equal_weight": {"symbol": None},
                "value": {"symbol": "SPYV"},
                "growth": {"symbol": "SPYG"},
            },
        ),
    )

    class Result:
        def all(self):
            return [
                (101, date(2026, 7, 31), 500, "SPY"),
                (102, date(2026, 6, 30), 400, "SPYV"),
                (103, date(2026, 5, 31), 300, "SPYG"),
            ]

    class Session:
        async def execute(self, _statement):
            return Result()

    plan = await history.plan_benchmark_family_snapshot_history_refresh(
        Session(),
        family_keys=["sp500"],
        roles=["cap_weight", "value", "growth"],
        max_snapshots=2,
    )

    assert plan["available_snapshot_count"] == 3
    assert plan["selected_snapshot_count"] == 2
    assert plan["limited"] is True
    assert [item["snapshot_id"] for item in plan["snapshots"]] == [101, 102]
    assert plan["snapshots"][0]["legs"] == [{"family_key": "sp500", "role": "cap_weight"}]
