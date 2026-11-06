from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.etf_holdings_preparation import (
    _coverage_for_composition_date,
    is_reusable_current_holdings_snapshot,
)


def _fund_context():
    instrument = SimpleNamespace(
        id=41,
        is_active=True,
        is_synthetic=False,
        identity_status="resolved",
    )
    profile = SimpleNamespace(id=52, instrument_id=41)
    snapshot = SimpleNamespace(id=73, etf_profile_id=52)
    capability = {
        "availability": "current",
        "identity_verified": True,
        "usable_for_current_analysis": True,
        "completeness_status": "complete",
    }
    return instrument, profile, snapshot, capability


def test_reuses_only_current_verified_snapshot_bound_to_selected_fund():
    instrument, profile, snapshot, capability = _fund_context()

    assert is_reusable_current_holdings_snapshot(
        instrument,
        profile,
        snapshot,
        capability,
    )


@pytest.mark.parametrize(
    "completeness_status",
    ["complete", "issuer_current", "issuer_reported", "self_snapshotted"],
)
def test_reuses_all_current_completeness_states_when_capability_confirms_usability(
    completeness_status,
):
    instrument, profile, snapshot, capability = _fund_context()
    capability["completeness_status"] = completeness_status

    assert is_reusable_current_holdings_snapshot(
        instrument,
        profile,
        snapshot,
        capability,
    )


@pytest.mark.parametrize(
    "capability_patch",
    [
        {"availability": "stale"},
        {"identity_verified": False},
        {"usable_for_current_analysis": False},
    ],
)
def test_stale_or_unverified_snapshot_does_not_satisfy_holdings_dataset(capability_patch):
    instrument, profile, snapshot, capability = _fund_context()
    capability.update(capability_patch)

    assert not is_reusable_current_holdings_snapshot(
        instrument,
        profile,
        snapshot,
        capability,
    )


@pytest.mark.parametrize(
    ("instrument_patch", "profile_patch", "snapshot_patch"),
    [
        ({}, {"instrument_id": 42}, {}),  # another canonical fund's profile
        ({}, {}, {"etf_profile_id": 54}),  # another profile's snapshot
        ({"identity_status": "provisional"}, {}, {}),
        ({"is_active": False}, {}, {}),
        ({"is_synthetic": True}, {}, {}),
    ],
)
def test_does_not_reuse_snapshot_from_another_or_ineligible_fund(
    instrument_patch,
    profile_patch,
    snapshot_patch,
):
    instrument, profile, snapshot, capability = _fund_context()
    instrument = SimpleNamespace(**(vars(instrument) | instrument_patch))
    profile = SimpleNamespace(**(vars(profile) | profile_patch))
    snapshot = SimpleNamespace(**(vars(snapshot) | snapshot_patch))

    assert not is_reusable_current_holdings_snapshot(
        instrument,
        profile,
        snapshot,
        capability,
    )


def test_missing_snapshot_or_capability_never_counts_as_a_cache_hit():
    instrument, profile, snapshot, capability = _fund_context()

    assert not is_reusable_current_holdings_snapshot(instrument, profile, None, capability)
    assert not is_reusable_current_holdings_snapshot(instrument, profile, snapshot, None)


def test_holdings_coverage_uses_composition_day_not_requested_price_range():
    start, end = _coverage_for_composition_date(date(2026, 11, 6))

    assert start == datetime(2026, 11, 6, tzinfo=UTC)
    assert end == datetime(2026, 11, 7, tzinfo=UTC)


def test_naive_composition_datetime_is_not_reported_as_verified_coverage():
    assert _coverage_for_composition_date(datetime(2026, 11, 6)) == (None, None)


def test_timezone_aware_composition_datetime_is_normalized_to_utc_day():
    start, end = _coverage_for_composition_date(
        datetime(2026, 11, 6, 14, tzinfo=UTC) - timedelta(hours=4)
    )

    assert start == datetime(2026, 11, 6, tzinfo=UTC)
    assert end == datetime(2026, 11, 7, tzinfo=UTC)
