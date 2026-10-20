from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    preflight_capabilities,
)
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    DataSeriesManifest,
    DataSnapshot,
    EventGranularity,
    ProductClass,
)
from app.strategy_lab_v2.data_acquisition import (
    DataAcquisitionReceipt,
    DataAcquisitionRequest,
    verify_data_acquisition,
)
from app.strategy_lab_v2.provider_series_contract import (
    ProviderFreshness,
    assess_provider_freshness,
    provider_coverage_evidence_digest,
    resolve_provider_coverage,
    verify_provider_series_binding,
)
from app.strategy_lab_v2.snapshot_coverage import verify_snapshot_coverage

NOW = datetime(2026, 10, 20, 20, tzinfo=UTC)


def _manifest(**changes: object) -> DataSeriesManifest:
    values: dict[str, object] = {
        "instrument_id": "figi:BBG000B9XRY4",
        "event_type": "ohlcv",
        "event_granularity": EventGranularity.BAR,
        "timeframe": "D1",
        "session": "regular",
        "feed": "provider_native",
        "start": NOW - timedelta(days=30),
        "end": NOW,
        "adjustment": AdjustmentMode.RAW,
        "corporate_action_semantics": "raw_unadjusted",
        "coverage_evidence_digest": content_digest("provider-coverage-evidence"),
        "content_digest": content_digest("local-bar-content"),
        "row_count": 22,
    }
    values.update(changes)
    return DataSeriesManifest(**values)  # type: ignore[arg-type]


def _provider_inputs(*, resolved: bool = True, provenance: dict | None = None):
    instrument = SimpleNamespace(
        id=7,
        domain_key="figi:BBG000B9XRY4" if resolved else None,
        identity_status="resolved" if resolved else "quarantined",
    )
    series = SimpleNamespace(
        id=31,
        instrument_id=7,
        data_source_id=4,
        is_active=True,
        timeframe="D1",
        session_code="regular",
        feed_scope="provider_native",
        adjustment_basis="raw",
        source_series_key="provider-symbol:D1:provider_native:regular:raw:v1",
        provenance={
            "provider": "published-local-provider",
            **(provenance or {}),
        },
    )
    return instrument, series


def test_provider_resolved_identity_and_exact_local_series_scope_bind_manifest():
    instrument, series = _provider_inputs()

    first = verify_provider_series_binding(instrument, series, _manifest())
    second = verify_provider_series_binding(instrument, series, _manifest())

    assert first.verified
    assert first.instrument_key == "figi:BBG000B9XRY4"
    assert first.market_series_id == 31
    assert first.series_scope_fingerprint == second.series_scope_fingerprint
    assert first.mismatches == ()


def test_adjustment_version_is_part_of_provider_series_lineage():
    instrument, series = _provider_inputs()
    series.adjustment_version = "v1"
    first = verify_provider_series_binding(instrument, series, _manifest())
    series.adjustment_version = "v2"
    second = verify_provider_series_binding(instrument, series, _manifest())

    assert first.verified and second.verified
    assert first.series_scope_fingerprint != second.series_scope_fingerprint


def test_provider_binding_rejects_quarantined_identity_and_manifest_drift():
    instrument, series = _provider_inputs(resolved=False)

    rejected = verify_provider_series_binding(
        instrument,
        series,
        _manifest(instrument_id="AAPL", feed="guessed-feed"),
    )

    assert not rejected.verified
    assert rejected.mismatches == (
        "provider_feed_mismatch",
        "provider_identity_unresolved",
        "strategy_instrument_key_mismatch",
    )


def test_provider_binding_rejects_provider_adjustment_without_strategy_semantics():
    instrument, series = _provider_inputs()
    series.adjustment_basis = "provider_adjusted"

    rejected = verify_provider_series_binding(instrument, series, _manifest())

    assert not rejected.verified
    assert "provider_adjustment_semantics_unsupported" in rejected.mismatches
    assert "provider_corporate_action_semantics_unbound" in rejected.mismatches


def test_adjusted_provider_series_requires_explicit_corporate_action_provenance():
    instrument, series = _provider_inputs()
    series.adjustment_basis = "split_adjusted"
    series.provenance["adjustment_basis"] = "split_adjusted"

    rejected = verify_provider_series_binding(
        instrument,
        series,
        _manifest(
            adjustment=AdjustmentMode.SPLIT_ADJUSTED,
            corporate_action_semantics="split_only",
        ),
    )

    assert not rejected.verified
    assert "provider_corporate_action_semantics_unbound" in rejected.mismatches


def _coverage_assessment(**changes: object):
    values: dict[str, object] = {
        "status": "ready",
        "covered_start": NOW - timedelta(days=29),
        "covered_end": NOW - timedelta(days=1),
        "bar_count": 22,
        "missing_slices": (),
        "explanation": "Local series covers the requested historical range.",
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _provider_manifest(instrument, series, assessment, *, calendar_digest: str):
    evidence_digest = provider_coverage_evidence_digest(
        instrument,
        series,
        assessment,
        calendar_digest=calendar_digest,
    )
    return _manifest(coverage_evidence_digest=evidence_digest)


def test_ready_local_provider_coverage_becomes_existing_strategy_attestation():
    instrument, series = _provider_inputs()
    assessment = _coverage_assessment()
    calendar_digest = content_digest("XNYS-calendar-v1")
    manifest = _provider_manifest(instrument, series, assessment, calendar_digest=calendar_digest)

    resolved = resolve_provider_coverage(
        instrument,
        series,
        manifest,
        assessment,
        calendar_digest=calendar_digest,
        attested_at=NOW,
    )

    assert resolved.verified
    assert resolved.attestation is not None
    assert resolved.attestation.series_content_digest == manifest.content_digest
    assert resolved.attestation.evidence_digest == manifest.coverage_evidence_digest


def test_partial_or_stale_provider_coverage_cannot_publish_strategy_attestation():
    instrument, series = _provider_inputs()
    calendar_digest = content_digest("XNYS-calendar-v1")
    partial = _coverage_assessment(
        status="partial",
        missing_slices=((NOW - timedelta(days=10), NOW - timedelta(days=9)),),
    )
    manifest = _provider_manifest(instrument, series, partial, calendar_digest=calendar_digest)

    partial_result = resolve_provider_coverage(
        instrument,
        series,
        manifest,
        partial,
        calendar_digest=calendar_digest,
        attested_at=NOW,
    )
    stale = _coverage_assessment(status="stale")
    stale_manifest = _provider_manifest(instrument, series, stale, calendar_digest=calendar_digest)
    stale_result = resolve_provider_coverage(
        instrument,
        series,
        stale_manifest,
        stale,
        calendar_digest=calendar_digest,
        attested_at=NOW,
    )

    assert not partial_result.verified
    assert partial_result.attestation is None
    assert "provider_coverage_contains_gaps" in partial_result.mismatches
    assert not stale_result.verified
    assert stale_result.attestation is None
    assert "provider_coverage_not_ready" in stale_result.mismatches


def test_provider_local_series_contract_flows_through_strategy_snapshot_acquisition_gate():
    instrument, series = _provider_inputs()
    assessment = _coverage_assessment()
    calendar_digest = content_digest("XNYS-calendar-v1")
    manifest = _provider_manifest(instrument, series, assessment, calendar_digest=calendar_digest)
    provider_coverage = resolve_provider_coverage(
        instrument,
        series,
        manifest,
        assessment,
        calendar_digest=calendar_digest,
        attested_at=NOW,
    )
    assert provider_coverage.attestation is not None

    requirement = CapabilityRequirement(
        instrument_id=manifest.instrument_id,
        product_class=ProductClass.EQUITY,
        event_granularity=manifest.event_granularity,
        event_type=manifest.event_type,
        timeframe=manifest.timeframe,
        start=manifest.start,
        end=manifest.end,
        adjustment=manifest.adjustment,
        session=manifest.session,
        feed=manifest.feed,
        execution_model="close_on_close",
        account_model="cash",
        corporate_action_semantics=manifest.corporate_action_semantics,
    )
    cell = CapabilityCell(
        instrument_id=manifest.instrument_id,
        product_class=ProductClass.EQUITY,
        event_granularities=frozenset({manifest.event_granularity}),
        event_types=frozenset({manifest.event_type}),
        timeframes=frozenset({manifest.timeframe}),
        adjustments=frozenset({manifest.adjustment}),
        sessions=frozenset({manifest.session}),
        feeds=frozenset({manifest.feed}),
        execution_models=frozenset({"close_on_close"}),
        account_models=frozenset({"cash"}),
        corporate_action_semantics=frozenset({manifest.corporate_action_semantics}),
        history_start=manifest.start,
        history_end=manifest.end,
        evidence_digest=content_digest("published-provider-capability"),
    )
    preflight = preflight_capabilities((requirement,), (cell,))
    snapshot = DataSnapshot(
        "provider-snapshot",
        "provider-market-series-snapshot",
        preflight,
        (manifest,),
        NOW,
    )
    request = DataAcquisitionRequest("provider-bound-request", preflight, NOW)
    coverage = verify_snapshot_coverage(snapshot, (provider_coverage.attestation,))
    receipt = DataAcquisitionReceipt(
        request.fingerprint,
        snapshot.fingerprint,
        snapshot.snapshot_id,
        snapshot.provider_snapshot_id,
        coverage.fingerprint,
        content_digest("provider-local-series-receipt"),
        NOW + timedelta(minutes=1),
    )

    verification = verify_data_acquisition(request, snapshot, coverage, receipt)

    assert coverage.verified
    assert verification.verified


def _dataset_state(**changes: object):
    values: dict[str, object] = {
        "instrument_id": 7,
        "data_source_id": 4,
        "dataset_type": "ohlcv",
        "dataset_key": "D1:raw",
        "status": "fresh",
        "fetched_at": NOW - timedelta(minutes=5),
        "stale_after": NOW + timedelta(hours=1),
        "coverage_start": NOW - timedelta(days=30),
        "coverage_end": NOW - timedelta(days=1),
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_provider_freshness_is_scoped_and_uses_explicit_stale_after():
    instrument, series = _provider_inputs()
    current = assess_provider_freshness(
        _dataset_state(),
        instrument=instrument,
        series=series,
        evaluated_at=NOW,
    )
    stale = assess_provider_freshness(
        _dataset_state(stale_after=NOW),
        instrument=instrument,
        series=series,
        evaluated_at=NOW,
    )
    mismatched = assess_provider_freshness(
        _dataset_state(data_source_id=9),
        instrument=instrument,
        series=series,
        evaluated_at=NOW,
    )

    assert current.status is ProviderFreshness.CURRENT
    assert stale.status is ProviderFreshness.STALE
    assert mismatched.status is ProviderFreshness.UNKNOWN


def test_missing_or_incomplete_freshness_never_becomes_current():
    instrument, series = _provider_inputs()
    missing = assess_provider_freshness(
        None,
        instrument=instrument,
        series=series,
        evaluated_at=NOW,
    )
    incomplete = assess_provider_freshness(
        _dataset_state(stale_after=None, coverage_end=None),
        instrument=instrument,
        series=series,
        evaluated_at=NOW,
    )
    unavailable = assess_provider_freshness(
        _dataset_state(status="pending"),
        instrument=instrument,
        series=series,
        evaluated_at=NOW,
    )

    assert missing.status is ProviderFreshness.UNKNOWN
    assert incomplete.status is ProviderFreshness.UNKNOWN
    assert unavailable.status is ProviderFreshness.UNAVAILABLE


def test_provider_freshness_derives_adjusted_dataset_scope_from_the_series():
    instrument, series = _provider_inputs()
    series.adjustment_basis = "split_adjusted"
    raw_state = assess_provider_freshness(
        _dataset_state(),
        instrument=instrument,
        series=series,
        evaluated_at=NOW,
    )
    adjusted_state = assess_provider_freshness(
        _dataset_state(dataset_key="D1:adj"),
        instrument=instrument,
        series=series,
        evaluated_at=NOW,
    )

    assert raw_state.status is ProviderFreshness.UNKNOWN
    assert raw_state.reason == "provider_dataset_state_scope_mismatch"
    assert adjusted_state.status is ProviderFreshness.CURRENT
