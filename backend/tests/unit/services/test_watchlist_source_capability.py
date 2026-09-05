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
        "failure_class": "issuer_access_blocked",
        "reason": "Issuer route is blocked.",
    }


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
