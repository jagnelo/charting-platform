from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.strategy_lab_v2.etf_pit import freeze_etf_pit_membership


def _records(*, known_at=None, complete="complete", row_type="security"):
    decision = datetime(2025, 3, 4, 15, tzinfo=UTC)
    etf = NS(
        id=1,
        domain_key="US:ETF:SPY",
        identity_status="resolved",
        is_active=True,
        is_synthetic=False,
    )
    profile = NS(id=2, instrument_id=1)
    snapshot = NS(
        id=3,
        etf_profile_id=2,
        composition_date=date(2025, 3, 3),
        known_at=known_at if known_at is not None else decision - timedelta(hours=1),
        published_at=decision - timedelta(hours=2),
        source_artifact_id=4,
        provenance="issuer",
        source_provider="local",
        source_quality="verified",
        completeness_status=complete,
        row_count=1,
        resolved_count=1,
        unresolved_count=0,
        snapshot_hash="snapshot-hash",
    )
    instrument = NS(
        id=5, domain_key="US:EQ:ABC", identity_status="resolved", is_active=True, is_synthetic=False
    )
    holding = NS(
        id=6,
        snapshot_id=3,
        row_type=row_type,
        holding_type="equity",
        is_resolved=True,
        constituent_instrument_id=5,
        source_row_hash="row-hash",
        position=1,
        weight=Decimal("0.25"),
    )
    return decision, etf, profile, snapshot, ((holding, instrument),)


def test_freezes_exact_pit_membership_and_canonical_digest():
    decision, etf, profile, snapshot, rows = _records()
    evidence = freeze_etf_pit_membership(
        etf_instrument=etf,
        profile=profile,
        snapshot=snapshot,
        rows=rows,
        decision_time=decision,
    )
    assert evidence.snapshot_id == 3
    assert evidence.constituents[0].domain_key == "US:EQ:ABC"
    assert evidence.content_digest.startswith("sha256:")
    assert len(evidence.content_digest.removeprefix("sha256:")) == 64


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"known_at": None}, "known_at"),
        ({"known_at": datetime(2025, 3, 4, 16, tzinfo=UTC)}, "not known"),
        ({"complete": "partial"}, "not complete"),
        ({"row_type": "cash"}, "row evidence"),
    ],
)
def test_rejects_missing_late_or_partial_historical_membership(change, message):
    decision, etf, profile, snapshot, rows = _records()
    if "known_at" in change:
        snapshot.known_at = change["known_at"]
    if "complete" in change:
        snapshot.completeness_status = change["complete"]
    if "row_type" in change:
        rows[0][0].row_type = change["row_type"]
    with pytest.raises(ValueError, match=message):
        freeze_etf_pit_membership(
            etf_instrument=etf,
            profile=profile,
            snapshot=snapshot,
            rows=rows,
            decision_time=decision,
        )
