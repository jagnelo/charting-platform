from datetime import UTC, datetime, timedelta

import pytest

from app.config import (
    provider_rate_limit_seed,
    settings,
    tiingo_persistent_storage_authority_missing,
)

PLAN_SCOPE = "written_single_user_automated_internal_display_perpetual_archive"


def _authorize_tiingo_storage(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORIZED", True)
    monkeypatch.setattr(
        settings, "TIINGO_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "owner-2026-10-04"
    )
    monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORITY_SCOPE", PLAN_SCOPE)
    monkeypatch.setattr(
        settings,
        "TIINGO_PERSISTENT_STORAGE_REVIEWED_AT",
        datetime.now(UTC) - timedelta(minutes=1),
    )
    monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_EXPIRES_AT", None)


def test_tiingo_storage_is_missing_by_default(monkeypatch):
    monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORIZED", False)
    monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
    monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
    monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_REVIEWED_AT", None)
    monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_EXPIRES_AT", None)
    missing = tiingo_persistent_storage_authority_missing()
    assert "TIINGO_PERSISTENT_STORAGE_AUTHORIZED" in missing
    assert "TIINGO_PERSISTENT_STORAGE_AUTHORITY_REFERENCE" in missing
    assert "TIINGO_PERSISTENT_STORAGE_AUTHORITY_SCOPE" in missing
    assert "TIINGO_PERSISTENT_STORAGE_REVIEWED_AT" in missing


def test_tiingo_storage_authorized_with_complete_authority(monkeypatch):
    _authorize_tiingo_storage(monkeypatch)
    assert tiingo_persistent_storage_authority_missing() == []


def test_tiingo_storage_rejects_unknown_scope_future_review_and_expiry(monkeypatch):
    _authorize_tiingo_storage(monkeypatch)
    monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "plan_only")
    assert tiingo_persistent_storage_authority_missing() == [
        "TIINGO_PERSISTENT_STORAGE_AUTHORITY_SCOPE"
    ]

    _authorize_tiingo_storage(monkeypatch)
    monkeypatch.setattr(
        settings,
        "TIINGO_PERSISTENT_STORAGE_REVIEWED_AT",
        datetime.now(UTC) + timedelta(days=1),
    )
    assert tiingo_persistent_storage_authority_missing() == [
        "TIINGO_PERSISTENT_STORAGE_REVIEWED_AT"
    ]

    _authorize_tiingo_storage(monkeypatch)
    monkeypatch.setattr(
        settings,
        "TIINGO_PERSISTENT_STORAGE_EXPIRES_AT",
        datetime.now(UTC) - timedelta(seconds=1),
    )
    assert tiingo_persistent_storage_authority_missing() == ["TIINGO_PERSISTENT_STORAGE_EXPIRES_AT"]


def _set_custom(monkeypatch, *, values, evidence):
    unique, hourly, daily, bandwidth = values
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_UNIQUE_SYMBOLS_PER_MONTH", unique)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_REQUESTS_PER_HOUR", hourly)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_REQUESTS_PER_DAY", daily)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_BANDWIDTH_BYTES_PER_MONTH", bandwidth)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_QUOTA_EVIDENCE", evidence)


FULL_CUSTOM = (2_000, 500, 10_000, 5_000_000_000)


def test_tiingo_custom_limits_with_evidence_classify_as_reviewed_custom(monkeypatch):
    monkeypatch.setattr(settings, "TIINGO_REVIEWED_PLAN", "starter")
    _set_custom(monkeypatch, values=FULL_CUSTOM, evidence="account plan readout")
    contract = provider_rate_limit_seed("tiingo")["quota_contract"]
    dimensions = {item["name"]: item for item in contract["dimensions"]}
    assert dimensions["unique_symbols_per_month"]["limit"] == 2_000
    assert dimensions["requests_per_hour"]["limit"] == 500
    assert dimensions["requests_per_day"]["limit"] == 10_000
    assert contract["account_plan"] == "custom"
    assert contract["plan_evidence"] == "account plan readout"


@pytest.mark.parametrize(
    ("values", "evidence"),
    [
        ((2_000, 500, 10_000, 0), "account plan readout"),
        ((2_000, 500, 0, 5_000_000_000), "account plan readout"),
        ((2_000, 500, 10_000, 5_000_000_000), ""),
        ((2_000, 500, 10_000, 5_000_000_000), "   "),
    ],
)
def test_tiingo_partial_custom_values_keep_published_starter_profile(monkeypatch, values, evidence):
    monkeypatch.setattr(settings, "TIINGO_REVIEWED_PLAN", "starter")
    _set_custom(monkeypatch, values=values, evidence=evidence)
    contract = provider_rate_limit_seed("tiingo")["quota_contract"]
    dimensions = {item["name"]: item for item in contract["dimensions"]}
    assert dimensions["unique_symbols_per_month"]["limit"] == 500
    assert dimensions["requests_per_hour"]["limit"] == 50
    assert contract["account_plan"] == "starter"


def test_tiingo_explicit_custom_plan_with_partial_values_stays_non_routable(monkeypatch):
    monkeypatch.setattr(settings, "TIINGO_REVIEWED_PLAN", "custom")
    _set_custom(monkeypatch, values=(2_000, 0, 0, 0), evidence="")
    contract = provider_rate_limit_seed("tiingo")["quota_contract"]
    assert contract["dimensions"] == []
    assert contract["unknown_dimensions"] == ["custom_account_quota_values_or_evidence"]
