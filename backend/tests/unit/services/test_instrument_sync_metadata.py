from datetime import UTC, datetime

from app.services.instrument_sync import _listing_evidence


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
