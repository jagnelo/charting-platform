from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.services.etf_holdings_capability import (
    CURRENT,
    DEGRADED,
    SEC_FILING,
    STALE,
    UNKNOWN,
    evaluate_capability,
    freshness_deadline,
    infer_expected_cadence,
    symbol_audit_for_profile,
)
from app.services.etf_holdings_refresh import _canary_failure_class

NOW = datetime(2026, 9, 4, 12, tzinfo=UTC)


def profile(adapter_key: str | None = "issuer"):
    return SimpleNamespace(adapter_key=adapter_key)


def profile_with_symbol(symbol: str, adapter_key: str = "issuer"):
    return SimpleNamespace(
        adapter_key=adapter_key,
        instrument=SimpleNamespace(symbol=symbol),
    )


def snapshot(
    *,
    composition_date: date = date(2026, 9, 3),
    provenance: str = "issuer_current_holdings",
    source_provider: str = "issuer",
    completeness_status: str = "complete",
    extra_data: dict | None = None,
    source_url: str = "https://issuer.example/holdings.csv",
):
    return SimpleNamespace(
        composition_date=composition_date,
        published_at=NOW,
        provenance=provenance,
        source_provider=source_provider,
        completeness_status=completeness_status,
        row_count=25,
        resolved_count=24,
        unresolved_count=1,
        extra_data={
            "artifact_identity_validation": {"status": "matched"},
            **(extra_data or {}),
        },
        source_url=source_url,
    )


def state(
    *,
    status: str = "success",
    checked: datetime | None = NOW,
    success: datetime | None = NOW,
    failure: datetime | None = None,
    reason: str | None = None,
    extra_data: dict | None = None,
):
    return SimpleNamespace(
        status=status,
        last_checked_at=checked,
        last_success_at=success,
        last_failure_at=failure,
        failure_reason=reason,
        row_count=25,
        resolved_count=24,
        unresolved_count=1,
        completeness_status="complete",
        extra_data=extra_data,
    )


def test_current_requires_complete_snapshot_and_successful_check():
    result = evaluate_capability(profile(), snapshot(), state(), now=NOW)

    assert result.availability == CURRENT
    assert result.usable_for_current_analysis is True
    assert result.displayable_last_known is True
    assert result.source_tier == "issuer_native"
    assert result.transport_kind == "file_export"


def test_sec_reconstruction_is_degraded_even_when_the_fetch_succeeded():
    result = evaluate_capability(
        profile(),
        snapshot(
            provenance="sec_edgar_filing_fallback",
            source_provider="sec",
            completeness_status="filing_reconstructed",
        ),
        state(),
        now=NOW,
    )

    assert result.availability == DEGRADED
    assert result.source_tier == SEC_FILING
    assert result.usable_for_current_analysis is False
    assert "SEC" in result.reason


def test_failed_current_route_keeps_last_known_snapshot_degraded():
    result = evaluate_capability(
        profile(),
        snapshot(),
        state(status="failure", reason="HTTP 403", failure=NOW),
        now=NOW,
    )

    assert result.availability == DEGRADED
    assert result.usable_for_current_analysis is False
    assert result.displayable_last_known is True
    assert result.failure_reason == "HTTP 403"


def test_unspecified_cadence_expires_after_conservative_window():
    result = evaluate_capability(
        profile(),
        snapshot(composition_date=NOW.date() - timedelta(days=8)),
        state(),
        now=NOW,
    )

    assert result.availability == STALE
    assert result.usable_for_current_analysis is False
    assert result.freshness_deadline == NOW.date() - timedelta(days=1)


def test_missing_snapshot_is_unknown_until_a_route_check_records_outcome():
    result = evaluate_capability(profile(), None, None, now=NOW)

    assert result.availability == UNKNOWN
    assert result.usable_for_current_analysis is False
    assert result.displayable_last_known is False


def test_unverified_identity_never_becomes_current_even_with_complete_rows():
    result = evaluate_capability(
        profile(),
        snapshot(extra_data={"artifact_identity_validation": {"status": "unverified"}}),
        state(),
        now=NOW,
    )

    assert result.availability == DEGRADED
    assert result.identity_verified is False
    assert result.usable_for_current_analysis is False
    assert "identity verification" in result.reason


def test_successor_metadata_is_preserved_as_a_distinct_source_tier():
    result = evaluate_capability(
        profile(),
        snapshot(
            extra_data={"source_tier": "successor_native", "transport_kind": "structured_api"}
        ),
        state(),
        now=NOW,
    )

    assert result.source_tier == "successor_native"
    assert result.transport_kind == "structured_api"
    assert result.usable_for_current_analysis is True


def test_cadence_inference_prefers_explicit_metadata_and_source_access():
    assert infer_expected_cadence(metadata={"expected_cadence": "monthly"}) == "monthly"
    assert infer_expected_cadence(source_access="issuer_public_daily_holdings_csv") == "daily"
    assert freshness_deadline(date(2026, 9, 1), "monthly") == date(2026, 10, 16)


def test_canary_failure_classification_keeps_provider_edges_explicit():
    assert (
        _canary_failure_class(ValueError("Fetched artifact identity mismatch"))
        == "identity_mismatch"
    )
    assert (
        _canary_failure_class(ValueError("Issuer holdings route returned no parseable rows."))
        == "empty_or_partial_source"
    )
    assert _canary_failure_class(TimeoutError("timed out")) == "transport_error"


def test_tier_zero_symbol_audit_preserves_unavailable_evidence_and_next_action():
    result = symbol_audit_for_profile(profile_with_symbol("DXJ", "wisdomtree"))

    assert result.tier == 0
    assert result.outcome == "unavailable"
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "wisdomtree"
    assert result.investigated_at == date(2026, 9, 4)
    assert "identity-verified" in result.next_action


def test_tier_zero_symbol_audit_rejects_a_mismatched_provider_identity():
    result = symbol_audit_for_profile(profile_with_symbol("DXJ", "other_provider"))

    assert result.tier == 0
    assert result.outcome == UNKNOWN
    assert result.evidence_state == "profile_provider_identity_mismatch"
    assert result.provider_identity == "other_provider"
    assert "Reconcile" in result.next_action


def test_tier_zero_symbol_audit_accepts_reconciled_provider_aliases():
    result = symbol_audit_for_profile(profile_with_symbol("UTWO", "us_benchmark_series"))

    assert result.tier == 0
    assert result.outcome == "unavailable"
    assert result.provider_identity == "fm_investments"


def test_identity_only_fallback_symbols_remain_unknown_until_symbol_route_evidence():
    result = symbol_audit_for_profile(profile_with_symbol("TALV", "aegon"))

    assert result.tier == 1
    assert result.outcome == "unknown"
    assert result.evidence_state == "identity_level_only"
    assert result.provider_identity == "aegon"
    assert result.investigated_at == date(2026, 7, 26)


def test_unreviewed_fallback_symbol_cannot_be_marked_current_from_a_snapshot_alone():
    result = evaluate_capability(
        profile_with_symbol("TALV", "aegon"),
        snapshot(),
        state(),
        now=NOW,
    )

    assert result.availability == UNKNOWN
    assert result.usable_for_current_analysis is False
    assert result.displayable_last_known is True
    assert "symbol-level source audit" in result.reason


def test_unavailable_tier_zero_audit_blocks_current_analysis_even_with_a_snapshot():
    result = evaluate_capability(
        profile_with_symbol("DXJ", "wisdomtree"),
        snapshot(),
        state(),
        now=NOW,
    )

    assert result.availability == "unavailable"
    assert result.usable_for_current_analysis is False
    assert result.symbol_audit.outcome == "unavailable"


def test_terminal_non_publisher_identity_is_not_applicable_at_symbol_boundary():
    result = symbol_audit_for_profile(profile_with_symbol("ABEQ", "epiris"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "identity_level_terminal_disposition"
