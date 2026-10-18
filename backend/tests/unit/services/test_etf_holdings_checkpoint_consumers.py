"""Persisted ETF consumer contracts for the staged Provider integration.

These exercise the real capability/API/basket consumers over stored outcomes.
They do not establish Provider transport, quota, or budget admission evidence;
those tests must run against the shared runtime after its staging release.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

import app.routers.etf_holdings as etf_holdings_router
from app.models.basket import Basket
from app.models.etf_holdings import (
    ETFHolding,
    ETFHoldingsAdapterState,
    ETFHoldingsRawArtifact,
    ETFHoldingsSnapshot,
    ETFProfile,
)
from app.models.instrument import Instrument
from app.models.provider_runtime import ProviderRequestLog
from app.services.baskets import materialize_etf_holdings_basket
from tests.unit.conftest import AsyncSessionAdapter


@pytest.fixture(autouse=True)
def reject_external_holdings_operations(monkeypatch, db):
    """Keep cached, historical, and PIT consumer contracts network-free."""

    def unexpected_external_operation(*args, **kwargs):
        raise AssertionError("persisted ETF consumer dispatched an external holdings operation")

    for operation in (
        "backfill_all_sec_legacy_holdings",
        "backfill_all_sec_nport_holdings",
        "backfill_sec_legacy_holdings",
        "backfill_sec_nport_holdings",
        "bootstrap_etf_holdings_profile",
        "discover_etf_profiles_from_issuer_feed",
        "discover_etf_profiles_from_sec_fund_tickers",
        "probe_etf_holdings_adapter_route",
        "refresh_all_benchmark_family_holdings_for_date",
        "refresh_all_benchmark_family_holdings_for_dates",
        "refresh_all_known_etf_holdings",
        "refresh_benchmark_family_holdings_for_date",
        "refresh_benchmark_family_holdings_for_dates",
        "refresh_etf_holdings_for_date",
    ):
        monkeypatch.setattr(
            etf_holdings_router,
            operation,
            unexpected_external_operation,
        )

    yield

    assert db.scalar(select(func.count()).select_from(ProviderRequestLog)) == 0


@pytest.fixture
def lineage(db, instrument, instrument_type):
    now = datetime.now(UTC)
    fund = Instrument(
        symbol="ARKK",
        name="ARK Innovation ETF",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    profile = ETFProfile(instrument=fund, adapter_key="ark", adapter_status="success")
    db.add(profile)
    db.flush()
    artifact = ETFHoldingsRawArtifact(
        etf_profile_id=profile.id,
        source_kind="issuer_current_holdings",
        source_url="https://issuer.example/holdings.csv",
        content_hash="checkpoint-original-artifact",
        fetched_at=now - timedelta(days=1),
        payload_text="Ticker,Weight\nAAPL,100%\n",
    )
    db.add(artifact)
    db.flush()
    snapshot = ETFHoldingsSnapshot(
        etf_profile_id=profile.id,
        source_artifact_id=artifact.id,
        composition_date=(now - timedelta(days=1)).date(),
        known_at=now - timedelta(days=1),
        published_at=now - timedelta(days=1),
        provenance="issuer_current_holdings",
        source_provider="ark",
        source_quality="issuer_current",
        completeness_status="complete",
        snapshot_hash="checkpoint-original-snapshot",
        row_count=1,
        resolved_count=1,
        unresolved_count=0,
        extra_data={"artifact_identity_validation": {"status": "matched"}},
    )
    snapshot.rows.append(
        ETFHolding(
            constituent_instrument_id=instrument.id,
            reported_symbol=instrument.symbol,
            row_type="security",
            weight=Decimal("1"),
            is_resolved=True,
            source_row_hash="checkpoint-original-row",
        )
    )
    state = ETFHoldingsAdapterState(
        etf_profile_id=profile.id,
        adapter_key="ark",
        status="success",
        last_checked_at=now,
        last_success_at=now,
        composition_date=snapshot.composition_date,
        completeness_status="complete",
        extra_data={"expected_cadence": "daily"},
    )
    db.add_all([snapshot, state])
    db.flush()
    return profile, snapshot, state, artifact, now


def test_current_consumer_exposes_native_identity_and_snapshot_lineage(
    client, auth_headers, db, lineage
):
    _, snapshot, _, _, _ = lineage
    capability = client.get("/api/v1/etf-holdings/ARKK/capability", headers=auth_headers)
    assert capability.status_code == 200
    assert capability.json()["availability"] == "current"
    assert capability.json()["identity_verified"] is True
    assert capability.json()["usable_for_current_analysis"] is True
    response = client.get("/api/v1/etf-holdings/ARKK/basket", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_snapshot_id"] == snapshot.id
    assert body["metadata"]["source_provider"] == "ark"
    assert body["metadata"]["provenance"] == "issuer_current_holdings"
    assert body["members"][0]["symbol"] == "AAPL"
    assert db.scalar(select(func.count()).select_from(ProviderRequestLog)) == 0


@pytest.mark.parametrize(
    "failure_class",
    [
        "entitlement_exclusion",
        "quota_unknown",
        "quota_rate_limited",
        "budget_exhausted",
        "identity_mismatch",
        "circuit_open",
    ],
)
def test_denied_refresh_preserves_history_and_rejects_current_analysis(
    client, auth_headers, db, lineage, failure_class
):
    _, snapshot, state, artifact, now = lineage
    original_payload = artifact.payload_text
    original_hash = snapshot.snapshot_hash
    state.status = "failure"
    state.last_failure_at = now
    state.failure_reason = f"Shared provider admission: {failure_class}"
    state.extra_data = {
        "expected_cadence": "daily",
        "last_failure_class": failure_class,
    }
    db.flush()

    capability = client.get("/api/v1/etf-holdings/ARKK/capability", headers=auth_headers)
    assert capability.status_code == 200
    body = capability.json()
    assert body["availability"] == "degraded"
    assert body["usable_for_current_analysis"] is False
    assert body["displayable_last_known"] is True
    assert body["failure_class"] == failure_class
    assert body["source_provider"] == "ark"

    response = client.get("/api/v1/etf-holdings/ARKK/basket", headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["failure_class"] == failure_class
    assert db.scalar(select(func.count()).select_from(Basket)) == 0

    historical = client.get(
        f"/api/v1/etf-holdings/ARKK/basket?snapshot_id={snapshot.id}",
        headers=auth_headers,
    )
    assert historical.status_code == 200, historical.text
    assert historical.json()["source_snapshot_id"] == snapshot.id
    assert historical.json()["metadata"]["provenance"] == "issuer_current_holdings"
    db.refresh(snapshot)
    db.refresh(artifact)
    assert snapshot.snapshot_hash == original_hash
    assert artifact.payload_text == original_payload
    assert db.scalar(select(func.count()).select_from(ProviderRequestLog)) == 0


def test_no_snapshot_stays_explicitly_unavailable_after_admission_denial(
    client, auth_headers, db, lineage
):
    _, snapshot, state, _, now = lineage
    db.delete(snapshot)
    state.status = "failure"
    state.last_failure_at = now
    state.failure_reason = "Shared provider entitlement excludes this environment."
    state.extra_data = {"last_failure_class": "entitlement_exclusion"}
    db.flush()
    response = client.get("/api/v1/etf-holdings/ARKK/capability", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["availability"] == "unavailable"
    assert response.json()["usable_for_current_analysis"] is False
    assert response.json()["displayable_last_known"] is False
    assert response.json()["failure_class"] == "entitlement_exclusion"


def test_successful_health_does_not_make_expired_holdings_current(
    client, auth_headers, db, lineage
):
    _, snapshot, state, _, now = lineage
    snapshot.composition_date = (now - timedelta(days=40)).date()
    state.status = "success"
    state.last_success_at = now
    db.flush()
    response = client.get("/api/v1/etf-holdings/ARKK/capability", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["availability"] == "stale"
    assert response.json()["usable_for_current_analysis"] is False
    basket = client.get("/api/v1/etf-holdings/ARKK/basket", headers=auth_headers)
    assert basket.status_code == 409
    assert basket.json()["detail"]["availability"] == "stale"


@pytest.mark.asyncio
async def test_historical_basket_excludes_corrections_not_yet_known(db, lineage):
    profile, original, _, _, now = lineage
    target_date = (now - timedelta(days=10)).date()
    composition_date = target_date - timedelta(days=1)
    original.composition_date = composition_date
    original.known_at = datetime.combine(target_date, datetime.min.time(), tzinfo=UTC)
    correction = ETFHoldingsSnapshot(
        etf_profile_id=profile.id,
        composition_date=composition_date,
        known_at=original.known_at + timedelta(days=2),
        provenance="issuer_current_holdings",
        source_provider="ark",
        source_quality="issuer_current",
        completeness_status="complete",
        snapshot_hash="checkpoint-late-correction",
    )
    db.add(correction)
    db.flush()
    basket = await materialize_etf_holdings_basket(
        AsyncSessionAdapter(db), "ARKK", snapshot_date=target_date
    )
    assert basket is not None
    assert basket.source_snapshot_id == original.id
    assert basket.members[0].instrument_id == original.rows[0].constituent_instrument_id
    # An explicit snapshot selection remains an inspectable historical artifact.
    selected = await materialize_etf_holdings_basket(
        AsyncSessionAdapter(db), "ARKK", snapshot_id=correction.id
    )
    assert selected is not None
    assert selected.source_snapshot_id == correction.id


@pytest.mark.asyncio
async def test_historical_basket_does_not_borrow_another_etfs_snapshot(db, lineage, instrument):
    _, snapshot, _, _, _ = lineage
    # The requested instrument has its own profile, so this exercises the
    # profile/snapshot identity predicate rather than a missing-profile exit.
    db.add(ETFProfile(instrument_id=instrument.id, adapter_key="ark"))
    db.flush()
    result = await materialize_etf_holdings_basket(
        AsyncSessionAdapter(db), "AAPL", snapshot_id=snapshot.id
    )
    assert result is None


@pytest.mark.asyncio
async def test_historical_basket_is_unavailable_before_any_snapshot_was_known(db, lineage):
    _, original, _, _, now = lineage
    target_date = (now - timedelta(days=10)).date()
    original.composition_date = target_date - timedelta(days=1)
    original.known_at = datetime.combine(
        target_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC
    )
    db.flush()
    result = await materialize_etf_holdings_basket(
        AsyncSessionAdapter(db), "ARKK", snapshot_date=target_date
    )
    assert result is None
    assert db.scalar(select(func.count()).select_from(Basket)) == 0


@pytest.mark.asyncio
async def test_historical_basket_includes_knowledge_through_end_of_requested_utc_day(db, lineage):
    _, original, _, _, now = lineage
    target_date = (now - timedelta(days=10)).date()
    original.composition_date = target_date
    original.known_at = datetime.combine(target_date, datetime.max.time(), tzinfo=UTC)
    db.flush()
    result = await materialize_etf_holdings_basket(
        AsyncSessionAdapter(db), "ARKK", snapshot_date=target_date
    )
    assert result is not None
    assert result.source_snapshot_id == original.id


@pytest.mark.asyncio
async def test_historical_basket_prefers_newer_knowledge_over_later_insert_id(db, lineage):
    profile, original, _, _, now = lineage
    target_date = (now - timedelta(days=10)).date()
    original.composition_date = target_date - timedelta(days=1)
    original.known_at = datetime.combine(target_date, datetime.min.time(), tzinfo=UTC)
    older_knowledge = ETFHoldingsSnapshot(
        etf_profile_id=profile.id,
        composition_date=original.composition_date,
        known_at=original.known_at - timedelta(hours=1),
        provenance="issuer_current_holdings",
        source_provider="ark",
        source_quality="issuer_current",
        completeness_status="complete",
        snapshot_hash="checkpoint-late-insert-old-knowledge",
    )
    db.add(older_knowledge)
    db.flush()
    assert older_knowledge.id > original.id
    result = await materialize_etf_holdings_basket(
        AsyncSessionAdapter(db), "ARKK", snapshot_date=target_date
    )
    assert result is not None
    assert result.source_snapshot_id == original.id
