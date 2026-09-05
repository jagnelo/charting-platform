from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.config import settings
from app.services.etf_holdings_capability import (
    CONTROLLED_FIXTURE,
    CURRENT,
    DEGRADED,
    NO_SOURCE,
    SEC_FILING,
    STALE,
    UNAVAILABLE,
    UNKNOWN,
    evaluate_capability,
    evaluate_tier0_shadow_gate,
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


def test_known_adapter_provider_remains_visible_before_first_snapshot():
    result = evaluate_capability(
        profile("wisdomtree"),
        None,
        state(status="failure", reason="HTTP 403"),
        now=NOW,
    )

    assert result.source_provider == "wisdomtree"
    assert result.availability == UNAVAILABLE
    assert result.usable_for_current_analysis is False


def test_malformed_failure_streak_does_not_crash_capability_evaluation():
    result = evaluate_capability(
        profile("wisdomtree"),
        snapshot(),
        state(
            status="failure",
            reason="HTTP 403",
            failure=NOW,
            extra_data={"consecutive_failures": "bad"},
        ),
        now=NOW,
    )

    assert result.availability == DEGRADED
    assert result.consecutive_failures == 1


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


def test_unrecognized_source_tier_never_becomes_current_even_with_complete_rows():
    result = evaluate_capability(
        profile(),
        snapshot(
            provenance="stored_holdings_snapshot",
            source_provider="unclassified_provider",
        ),
        state(),
        now=NOW,
    )

    assert result.source_tier == NO_SOURCE
    assert result.availability == DEGRADED
    assert result.usable_for_current_analysis is False
    assert "recognized current-data source tier" in result.reason


def test_controlled_fixture_is_current_only_in_explicit_e2e_mode(monkeypatch):
    fixture = snapshot(
        provenance="controlled_fixture",
        source_provider="e2e_reference",
        extra_data={"source_tier": CONTROLLED_FIXTURE},
    )

    monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", True)
    enabled = evaluate_capability(profile(None), fixture, None, now=NOW)
    assert enabled.source_tier == CONTROLLED_FIXTURE
    assert enabled.availability == CURRENT
    assert enabled.usable_for_current_analysis is True

    monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", False)
    disabled = evaluate_capability(profile(None), fixture, None, now=NOW)
    assert disabled.source_tier == CONTROLLED_FIXTURE
    assert disabled.usable_for_current_analysis is False


def test_unqualified_vendor_text_does_not_become_a_licensed_current_source():
    result = evaluate_capability(
        profile(),
        snapshot(
            provenance="aggregator_snapshot",
            source_provider="market_vendor",
        ),
        state(),
        now=NOW,
    )

    assert result.source_tier == NO_SOURCE
    assert result.availability == DEGRADED
    assert result.usable_for_current_analysis is False


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
    assert result.investigated_at == date(2026, 9, 5)
    assert "identity-verified" in result.next_action


def test_tier_zero_symbol_audit_records_pimco_authentication_boundary():
    for symbol, evidence_ref in (
        ("MINT", "live:pimco-mint-fund-detail-api-2026-09-05-unauthorized"),
        ("BOND", "live:pimco-bond-fund-detail-api-2026-09-05-unauthorized"),
    ):
        result = symbol_audit_for_profile(profile_with_symbol(symbol, "pacific_investments"))

        assert result.tier == 0
        assert result.outcome == UNAVAILABLE
        assert result.evidence_state == "no_complete_executable_public_artifact"
        assert result.investigated_at == date(2026, 9, 5)
        assert evidence_ref in result.evidence_refs
        assert "requires authentication" in result.next_action


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
    assert result.outcome == CURRENT
    assert result.evidence_state == "issuer_current_canary_verified"
    assert result.provider_identity == "fm_investments"
    assert result.investigated_at == date(2026, 9, 5)


def test_tier_zero_geme_uses_pacific_asset_management_current_route_evidence():
    result = symbol_audit_for_profile(profile_with_symbol("GEME", "pacific_investments"))

    assert result.tier == 0
    assert result.outcome == CURRENT
    assert result.evidence_state == "issuer_current_canary_verified"
    assert result.provider_identity == "pacific_investments"
    assert result.investigated_at == date(2026, 9, 5)
    assert "live:pacific-asset-management-geme-holdings-2026-09-05" in result.evidence_refs


def test_ranked_fallback_non_executable_symbols_remain_unavailable():
    result = symbol_audit_for_profile(profile_with_symbol("BGGG", "baillie_gifford"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "baillie_gifford"
    assert result.investigated_at == date(2026, 9, 2)
    assert result.evidence_refs == ("web:baillie-gifford-top-ten-only-2026-09-02",)


def test_ranked_fallback_symbol_audit_uses_explicit_issuer_evidence():
    result = symbol_audit_for_profile(profile_with_symbol("TALV", "aegon"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "aegon"
    assert result.investigated_at == date(2026, 9, 3)
    assert result.evidence_refs == ("web:aegonam-us-asset-management-capabilities-2026-09-03",)


def test_ranked_fallback_symbol_audit_rejects_provider_identity_mismatch():
    result = symbol_audit_for_profile(profile_with_symbol("TALV", "other_provider"))

    assert result.tier == 1
    assert result.outcome == UNKNOWN
    assert result.evidence_state == "profile_provider_identity_mismatch"
    assert result.provider_identity == "other_provider"
    assert result.evidence_refs == ("web:aegonam-us-asset-management-capabilities-2026-09-03",)


def test_ranked_fallback_terminal_symbol_is_not_applicable():
    result = symbol_audit_for_profile(profile_with_symbol("ADFI", "anfield"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"


def test_follow_on_ranked_fallback_terminal_symbol_preserves_successor_evidence():
    result = symbol_audit_for_profile(profile_with_symbol("ALFA", "alphaclone"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"
    assert result.provider_identity == "alphaclone"
    assert result.investigated_at == date(2026, 9, 2)
    assert result.evidence_refs == ("web:alphaclone-domain-unrelated-content-2026-09-02",)


def test_follow_on_ranked_fallback_blocked_symbol_remains_unavailable():
    result = symbol_audit_for_profile(profile_with_symbol("AAAA", "amplius"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "amplius"
    assert result.evidence_refs == ("web:amplius-aaaa-holdings-cloudflare-2026-09-02",)


def test_follow_on_ranked_fallback_non_executable_symbol_is_not_current():
    result = evaluate_capability(
        profile_with_symbol("NDOW", "anydrus"),
        snapshot(),
        state(),
        now=NOW,
    )

    assert result.availability == UNAVAILABLE
    assert result.usable_for_current_analysis is False
    assert result.symbol_audit.outcome == UNAVAILABLE
    assert result.symbol_audit.evidence_state == "non_executable_public_source"


def test_follow_on_ranked_fallback_avos_symbol_preserves_blocked_route_evidence():
    result = symbol_audit_for_profile(profile_with_symbol("AVOS", "avos"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "avos"
    assert result.investigated_at == date(2026, 9, 4)
    assert result.evidence_refs == (
        "web:avos-current-holdings-page-2026-09-04",
        "live:avos-current-holdings-page-2026-09-04-blocked",
    )


def test_third_ranked_fallback_terminal_symbol_preserves_liquidation_evidence():
    result = symbol_audit_for_profile(profile_with_symbol("CHRG", "elements"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"
    assert result.provider_identity == "elements"
    assert result.evidence_refs == (
        "web:elements-chrg-liquidation-2026-09-02",
        "web:elements-successor-no-etf-route-2026-09-02",
    )


def test_third_ranked_fallback_non_publisher_symbol_is_not_applicable():
    result = symbol_audit_for_profile(profile_with_symbol("USSE", "emirate_abu_dhabi"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "identity_not_portfolio_publisher"
    assert result.provider_identity == "emirate_abu_dhabi"


def test_third_ranked_fallback_successor_symbols_preserve_etfmg_evidence():
    result = symbol_audit_for_profile(profile_with_symbol("AIEQ", "etf_managers_group"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"
    assert result.provider_identity == "etf_managers_group"
    assert result.evidence_refs == (
        "web:amplify-etfmg-acquisition-complete-2026-09-02",
        "web:etfmg-domain-unreachable-successor-amplify-2026-09-02",
    )


def test_fifth_ranked_fallback_first_manhattan_symbols_remain_unavailable():
    result = symbol_audit_for_profile(profile_with_symbol("FMCX", "first_manhattan"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "first_manhattan"
    assert result.evidence_refs == (
        "web:first-manhattan-official-etf-catalogue-2026-09-02",
        "web:first-manhattan-daily-holdings-disclosure-2026-09-02",
        "web:first-manhattan-fmcx-prospectus-2026-09-02",
    )


def test_fifth_ranked_fallback_successor_alias_preserves_fcf_evidence():
    result = symbol_audit_for_profile(profile_with_symbol("ABFL", "fcf_advisors"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"
    assert result.provider_identity == "fcf_advisors"
    assert result.evidence_refs == (
        "web:abacus-fcf-rebrand-2026-09-02",
        "web:abacus-fcf-catalogue-2026-09-02",
        "web:abacus-fcf-current-holdings-2026-09-02",
    )


def test_fifth_ranked_fallback_formula_folio_is_not_applicable():
    result = symbol_audit_for_profile(profile_with_symbol("FFHG", "formula_folio"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"


def test_fifth_ranked_fallback_fpa_alias_requires_identity_reconciliation():
    result = symbol_audit_for_profile(profile_with_symbol("FPAG", "fpa"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "identity_requires_reconciliation"
    assert result.provider_identity == "fpa"


def test_sixth_ranked_fallback_parent_identity_is_not_a_publisher():
    result = symbol_audit_for_profile(profile_with_symbol("FEGE", "gc_ferry_parent"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "identity_not_portfolio_publisher"
    assert result.provider_identity == "gc_ferry_parent"


def test_sixth_ranked_fallback_highland_symbol_remains_unavailable_without_mapping():
    result = symbol_audit_for_profile(profile_with_symbol("AQLG", "highland_capital"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "highland_capital"
    assert result.evidence_refs == (
        "web:highland-aqlg-page-and-csv-2026-09-03",
        "web:highland-sec-prospectus-2026-09-03",
    )


def test_sixth_ranked_fallback_successor_identity_is_not_applicable():
    result = symbol_audit_for_profile(profile_with_symbol("QYLD", "horizons"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"
    assert result.provider_identity == "horizons"


def test_sixth_ranked_fallback_hoya_alias_requires_identity_reconciliation():
    result = symbol_audit_for_profile(profile_with_symbol("HOMZ", "hoya"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "identity_requires_reconciliation"
    assert result.provider_identity == "hoya"


def test_seventh_ranked_fallback_m2_adviser_is_not_a_publisher():
    result = symbol_audit_for_profile(profile_with_symbol("FFTY", "m2_financial"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "identity_not_portfolio_publisher"
    assert result.provider_identity == "m2_financial"


def test_seventh_ranked_fallback_m_d_sass_placeholder_remains_unavailable():
    result = symbol_audit_for_profile(profile_with_symbol("SASS", "m_d_sass"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "m_d_sass"


def test_seventh_ranked_fallback_madison_alias_is_not_a_publisher():
    result = symbol_audit_for_profile(profile_with_symbol("SIXH", "madison_avenue"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "identity_not_portfolio_publisher"
    assert result.provider_identity == "madison_avenue"


def test_seventh_ranked_fallback_matrix_remains_unavailable_when_cloudflare_blocked():
    result = symbol_audit_for_profile(profile_with_symbol("MAVF", "matrix"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "matrix"
    assert result.evidence_refs == (
        "web:matrix-mavf-official-page-2026-09-03",
        "live:matrix-mavf-cloudflare-block-2026-09-03",
    )


def test_eighth_ranked_fallback_merk_liquidation_is_not_applicable():
    result = symbol_audit_for_profile(profile_with_symbol("STGF", "merk"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"
    assert result.provider_identity == "merk"
    assert result.evidence_refs == (
        "web:merk-stgf-liquidation-2026-09-03",
        "web:merk-stgf-sec-fund-identity-2026-09-03",
    )


def test_eighth_ranked_fallback_merk_vaneck_successor_is_not_applicable():
    result = symbol_audit_for_profile(profile_with_symbol("OUNZ", "merk"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"
    assert result.provider_identity == "merk"


def test_eighth_ranked_fallback_merlyn_liquidated_series_are_not_applicable():
    result = symbol_audit_for_profile(profile_with_symbol("WIZ", "merlyn_ai"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"
    assert result.provider_identity == "merlyn_ai"
    assert result.evidence_refs == (
        "web:merlyn-ai-liquidation-2026-09-03",
        "web:merlyn-ai-sec-fund-series-2026-09-03",
    )


def test_ninth_ranked_fallback_nicholas_wealth_route_is_blocked():
    result = symbol_audit_for_profile(profile_with_symbol("DRMY", "nicholas_wealth"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "nicholas_wealth"
    assert result.evidence_refs == (
        "web:nicholas-wealth-official-xfunds-2026-09-03",
        "web:nicholas-wealth-sec-series-identities-2026-09-03",
        "web:nicholas-wealth-access-blocked-2026-09-03",
    )


def test_ninth_ranked_fallback_north_square_disclosure_is_non_executable():
    result = symbol_audit_for_profile(profile_with_symbol("NSIV", "north_square"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "north_square"


def test_ninth_ranked_fallback_pabrai_periodic_report_is_non_executable():
    result = symbol_audit_for_profile(profile_with_symbol("WAGN", "pabrai"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "pabrai"


def test_tenth_ranked_fallback_panagram_symbols_resolve_to_eldridge():
    result = symbol_audit_for_profile(profile_with_symbol("CLOX", "panagram"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"
    assert result.provider_identity == "panagram"


def test_tenth_ranked_fallback_parnassus_routes_are_blocked():
    result = symbol_audit_for_profile(profile_with_symbol("PRCS", "parnassus_investments"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "parnassus_investments"


def test_tenth_ranked_fallback_performance_trust_pdf_is_not_current():
    result = symbol_audit_for_profile(profile_with_symbol("STBF", "performance_trust"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "performance_trust"


def test_tenth_ranked_fallback_premise_route_is_unreachable():
    result = symbol_audit_for_profile(profile_with_symbol("TCTL", "premise_capital"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "premise_capital"


def test_tenth_ranked_fallback_putnam_successor_snapshots_are_not_current():
    result = symbol_audit_for_profile(profile_with_symbol("PFRX", "putnam"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "putnam"


def test_tenth_ranked_fallback_pzena_pages_are_blocked():
    result = symbol_audit_for_profile(profile_with_symbol("PZIV", "pzena"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "pzena"


def test_eleventh_ranked_fallback_riverfront_subadviser_resolves_to_first_trust():
    result = symbol_audit_for_profile(profile_with_symbol("RFDI", "riverfront"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "identity_not_portfolio_publisher"
    assert result.provider_identity == "riverfront"


def test_eleventh_ranked_fallback_roc_liquidation_is_not_applicable():
    result = symbol_audit_for_profile(profile_with_symbol("ROCI", "roc"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "inactive_or_successor_disposition"
    assert result.provider_identity == "roc"


def test_eleventh_ranked_fallback_saturna_routes_are_blocked():
    result = symbol_audit_for_profile(profile_with_symbol("AMEI", "saturna"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "saturna"


def test_eleventh_ranked_fallback_sophus_routes_are_blocked():
    result = symbol_audit_for_profile(profile_with_symbol("EMEM", "sophus"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "sophus"


def test_eleventh_ranked_fallback_strategy_shares_is_top_ten_only():
    result = symbol_audit_for_profile(profile_with_symbol("GOLY", "strategy_shares"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "strategy_shares"


def test_twelfth_ranked_fallback_subversive_routes_are_blocked():
    result = symbol_audit_for_profile(profile_with_symbol("GOP", "subversive"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "subversive"


def test_twelfth_ranked_fallback_suncoast_route_is_blocked():
    result = symbol_audit_for_profile(profile_with_symbol("SEMG", "suncoast"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "suncoast"


def test_twelfth_ranked_fallback_towle_route_is_blocked():
    result = symbol_audit_for_profile(profile_with_symbol("TCV", "towle"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "towle"


def test_twelfth_ranked_fallback_tweedy_browne_artifact_is_stale():
    result = symbol_audit_for_profile(profile_with_symbol("COPY", "tweedy_browne"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "tweedy_browne"


def test_final_ranked_fallback_rareview_artifacts_are_stale():
    result = symbol_audit_for_profile(profile_with_symbol("RMME", "rareview_funds"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "rareview_funds"


def test_final_ranked_fallback_vega_shares_is_top_ten_only():
    result = symbol_audit_for_profile(profile_with_symbol("ODTE", "vega_financial"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "vega_financial"


def test_final_ranked_fallback_vistashares_download_is_unresolved():
    result = symbol_audit_for_profile(profile_with_symbol("RTOO", "vistashares"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "vistashares"


def test_final_ranked_fallback_wellesley_is_not_a_publisher():
    result = symbol_audit_for_profile(profile_with_symbol("MCRT", "wellesley_asset_management"))

    assert result.tier == 1
    assert result.outcome == "not_applicable"
    assert result.evidence_state == "identity_not_portfolio_publisher"
    assert result.provider_identity == "wellesley_asset_management"


def test_final_ranked_fallback_worth_route_is_blocked():
    result = symbol_audit_for_profile(profile_with_symbol("WRTH", "worth_charting"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "worth_charting"


def test_final_ranked_fallback_yoke_route_is_blocked():
    result = symbol_audit_for_profile(profile_with_symbol("YOKE", "yoke"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "issuer_route_access_blocked"
    assert result.provider_identity == "yoke"


def test_final_ranked_fallback_epwa_route_is_non_executable():
    result = symbol_audit_for_profile(profile_with_symbol("FUNL", "epwa"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "epwa"


def test_final_ranked_fallback_planrock_download_is_non_executable():
    result = symbol_audit_for_profile(profile_with_symbol("PRAE", "planrock"))

    assert result.tier == 1
    assert result.outcome == UNAVAILABLE
    assert result.evidence_state == "non_executable_public_source"
    assert result.provider_identity == "planrock"


def test_unreviewed_fallback_symbol_cannot_be_marked_current_from_a_snapshot_alone():
    result = evaluate_capability(
        profile_with_symbol("UNREVIEWED", "matrix"),
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


def _shadow_observation(
    observed_at: str,
    *,
    status: str = "success",
    availability: str = CURRENT,
    identity_verified: bool = True,
    completeness_status: str = "complete",
    source_tier: str = "issuer_native",
    usable_for_current_analysis: bool = True,
    freshness_deadline: str = "2026-10-01",
    symbol_audit_outcome: str = CURRENT,
):
    return {
        "observed_at": observed_at,
        "status": status,
        "availability": availability,
        "identity_verified": identity_verified,
        "completeness_status": completeness_status,
        "source_tier": source_tier,
        "usable_for_current_analysis": usable_for_current_analysis,
        "freshness_deadline": freshness_deadline,
        "symbol_audit_outcome": symbol_audit_outcome,
    }


def test_tier_zero_shadow_gate_requires_a_current_usable_observation():
    observations = [
        _shadow_observation(f"2026-09-{day:02d}T12:00:00+00:00") for day in range(1, 19)
    ]
    observations.extend(
        [
            _shadow_observation(
                "2026-09-19T12:00:00+00:00",
                availability=UNAVAILABLE,
                usable_for_current_analysis=False,
                symbol_audit_outcome=UNAVAILABLE,
            ),
            _shadow_observation(
                "2026-09-20T12:00:00+00:00",
                availability=UNAVAILABLE,
                usable_for_current_analysis=False,
                symbol_audit_outcome=UNAVAILABLE,
            ),
        ]
    )

    result = evaluate_tier0_shadow_gate(
        {"DXJ": observations},
        now=date(2026, 9, 20),
        eligible_symbols=["DXJ"],
    )

    assert result["status"] == "fail"
    assert result["eligible_checks"] == 20
    assert result["passing_checks"] == 18
    assert result["success_rate"] == 0.9
    assert result["silent_violation_count"] == 0


def test_tier_zero_shadow_gate_rejects_silent_violations_and_two_freshness_misses():
    observations = [
        _shadow_observation(
            "2026-09-18T12:00:00+00:00",
            availability=STALE,
            usable_for_current_analysis=False,
            freshness_deadline="2026-09-17",
        ),
        _shadow_observation(
            "2026-09-19T12:00:00+00:00",
            availability=STALE,
            usable_for_current_analysis=False,
            freshness_deadline="2026-09-17",
        ),
        _shadow_observation(
            "2026-09-20T12:00:00+00:00",
            identity_verified=False,
        ),
    ]

    result = evaluate_tier0_shadow_gate(
        {"DXJ": observations},
        now=date(2026, 9, 20),
        eligible_symbols=["DXJ"],
    )

    assert result["status"] == "fail"
    assert result["max_consecutive_missed_freshness_deadlines"] == 2
    assert result["silent_violation_count"] == 1
    assert any("silent" in reason for reason in result["failure_reasons"])


def test_tier_zero_shadow_gate_rejects_unclassified_current_source_tier():
    result = evaluate_tier0_shadow_gate(
        {
            "GEME": [
                _shadow_observation(
                    "2026-09-20T12:00:00+00:00",
                    source_tier=NO_SOURCE,
                )
            ]
        },
        now=date(2026, 9, 20),
        eligible_symbols=["GEME"],
    )

    assert result["status"] == "fail"
    assert result["passing_checks"] == 0
    assert result["silent_violation_count"] == 1
    assert any("identity/schema/completeness" in reason for reason in result["failure_reasons"])


def test_tier_zero_shadow_gate_requires_observations_in_the_window():
    result = evaluate_tier0_shadow_gate(
        {
            "DXJ": [
                _shadow_observation(
                    "2026-08-01T12:00:00+00:00",
                )
            ]
        },
        now=date(2026, 9, 20),
        eligible_symbols=["DXJ"],
    )

    assert result["status"] == "fail"
    assert result["eligible_checks"] == 0
    assert result["passing_checks"] == 0
    assert any("no eligible Tier 0 observations" in reason for reason in result["failure_reasons"])


def test_tier_zero_shadow_gate_rejects_missing_eligible_symbol_coverage():
    result = evaluate_tier0_shadow_gate(
        {
            "DXJ": [_shadow_observation("2026-09-20T12:00:00+00:00")],
            "NTSX": [],
        },
        now=date(2026, 9, 20),
        eligible_symbols=["DXJ", "NTSX"],
    )

    assert result["status"] == "fail"
    assert result["missing_symbols"] == ["NTSX"]
    assert any(
        "missing eligible Tier 0 observations" in reason for reason in result["failure_reasons"]
    )


def test_tier_zero_shadow_gate_normalizes_observation_symbol_keys():
    result = evaluate_tier0_shadow_gate(
        {"dxj": [_shadow_observation("2026-09-20T12:00:00+00:00")]},
        now=date(2026, 9, 20),
        eligible_symbols=["DXJ"],
    )

    assert result["status"] == "pass"
    assert result["missing_symbols"] == []
    assert result["eligible_checks"] == 1
    assert result["passing_checks"] == 1
