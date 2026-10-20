from types import SimpleNamespace

from app.services.watchlist_sources import current_analysis_source_error_detail


def _source(source_kind: str, provenance: dict):
    return SimpleNamespace(source_kind=source_kind, provenance=provenance)


def test_non_current_etf_source_returns_stable_current_analysis_detail():
    detail = current_analysis_source_error_detail(
        _source(
            "etf_holdings",
            {
                "availability": "unknown",
                "source_tier": "issuer_native",
                "usable_for_current_analysis": False,
                "failure_class": "issuer_access_blocked",
                "capability_reason": "Issuer route is blocked.",
            },
        )
    )

    assert detail == {
        "code": "etf_holdings_not_current",
        "availability": "unknown",
        "source_tier": "issuer_native",
        "usable_for_current_analysis": False,
        "displayable_last_known": False,
        "identity_verified": None,
        "adapter_key": None,
        "source_provider": None,
        "transport_kind": None,
        "snapshot_id": None,
        "snapshot_hash": None,
        "composition_date": None,
        "published_at": None,
        "known_at": None,
        "freshness_deadline": None,
        "last_checked_at": None,
        "last_success_at": None,
        "last_failure_at": None,
        "completeness_status": None,
        "row_count": None,
        "resolved_count": None,
        "unresolved_count": None,
        "failure_class": "issuer_access_blocked",
        "reason": "Issuer route is blocked.",
    }


def test_non_current_etf_source_preserves_cached_snapshot_lineage():
    detail = current_analysis_source_error_detail(
        _source(
            "etf_holdings",
            {
                "availability": "degraded",
                "source_tier": "issuer_native",
                "usable_for_current_analysis": False,
                "displayable_last_known": True,
                "identity_verified": True,
                "adapter_key": "ark",
                "source_provider": "ark",
                "transport_kind": "csv_download",
                "snapshot_id": 42,
                "snapshot_hash": "snapshot-sha256",
                "composition_date": "2026-10-19",
                "snapshot_published_at": "2026-10-19T08:00:00+00:00",
                "known_at": "2026-10-19T08:05:00+00:00",
                "freshness_deadline": "2026-10-20",
                "last_checked_at": "2026-10-20T08:00:00+00:00",
                "last_success_at": "2026-10-19T08:00:00+00:00",
                "last_failure_at": "2026-10-20T08:00:00+00:00",
                "completeness_status": "complete",
                "snapshot_row_count": 10,
                "snapshot_resolved_count": 9,
                "snapshot_unresolved_count": 1,
                "failure_class": "quota_unknown",
                "capability_reason": "Shared provider admission is unknown.",
            },
        )
    )

    assert detail is not None
    assert detail["availability"] == "degraded"
    assert detail["displayable_last_known"] is True
    assert detail["identity_verified"] is True
    assert detail["adapter_key"] == "ark"
    assert detail["source_provider"] == "ark"
    assert detail["transport_kind"] == "csv_download"
    assert detail["snapshot_id"] == 42
    assert detail["snapshot_hash"] == "snapshot-sha256"
    assert detail["composition_date"] == "2026-10-19"
    assert detail["published_at"] == "2026-10-19T08:00:00+00:00"
    assert detail["known_at"] == "2026-10-19T08:05:00+00:00"
    assert detail["freshness_deadline"] == "2026-10-20"
    assert detail["last_checked_at"] == "2026-10-20T08:00:00+00:00"
    assert detail["last_success_at"] == "2026-10-19T08:00:00+00:00"
    assert detail["last_failure_at"] == "2026-10-20T08:00:00+00:00"
    assert detail["completeness_status"] == "complete"
    assert detail["row_count"] == 10
    assert detail["resolved_count"] == 9
    assert detail["unresolved_count"] == 1
    assert detail["failure_class"] == "quota_unknown"
    assert detail["reason"] == "Shared provider admission is unknown."


def test_pending_etf_source_remains_available_for_hydration():
    assert (
        current_analysis_source_error_detail(
            _source("etf_holdings", {"availability": "profile_not_loaded"})
        )
        is None
    )


def test_personal_sources_and_explicit_historical_etf_sources_are_not_rejected():
    assert (
        current_analysis_source_error_detail(
            _source("personal", {"availability": "unknown", "usable_for_current_analysis": False})
        )
        is None
    )
    assert (
        current_analysis_source_error_detail(
            _source(
                "etf_holdings", {"availability": "stale", "usable_for_current_analysis": False}
            ),
            historical=True,
        )
        is None
    )
