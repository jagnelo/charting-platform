"""Fail-closed immutable ETF membership evidence for a single decision time.

This is a consumer-side contract over already persisted ETF rows. It performs
no acquisition and deliberately does not call the ETF "current capability"
gate: historical visibility is decided only by the snapshot's known_at.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.strategy_lab_v2.canonical import content_digest

_COMPLETE = {"complete", "issuer_current", "issuer_reported", "self_snapshotted"}


@dataclass(frozen=True, slots=True)
class ETFConstituentIdentity:
    instrument_id: int
    domain_key: str
    source_row_hash: str
    position: int
    weight: Decimal


@dataclass(frozen=True, slots=True)
class ETFPointInTimeMembership:
    etf_instrument_id: str
    etf_database_id: int
    profile_id: int
    snapshot_id: int
    composition_date: date
    known_at: datetime
    published_at: datetime | None
    source_artifact_id: int | None
    provenance: str
    source_provider: str
    source_quality: str
    completeness_status: str
    snapshot_hash: str
    constituents: tuple[ETFConstituentIdentity, ...]
    content_digest: str


def freeze_etf_pit_membership(
    *,
    etf_instrument: Any,
    profile: Any,
    snapshot: Any,
    rows: tuple[tuple[Any, Any], ...],
    decision_time: datetime,
) -> ETFPointInTimeMembership:
    """Validate persisted producer records and freeze their exact lineage.

    ``rows`` pairs each ETF holding with its joined canonical Instrument. Any
    identity ambiguity, unsupported row kind, missing timing, or partial
    membership rejects the entire snapshot; callers must not fall back.
    """

    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("ETF decision_time must be timezone-aware")
    decision_time = decision_time.astimezone(UTC)
    if (
        etf_instrument is None
        or etf_instrument.id is None
        or not etf_instrument.domain_key
        or etf_instrument.identity_status != "resolved"
        or not etf_instrument.is_active
        or etf_instrument.is_synthetic
    ):
        raise ValueError("ETF identity is not canonical and active")
    if profile is None or profile.instrument_id != etf_instrument.id:
        raise ValueError("ETF profile does not match canonical identity")
    if snapshot is None or snapshot.etf_profile_id != profile.id:
        raise ValueError("snapshot does not match ETF profile")
    if snapshot.composition_date > decision_time.date():
        raise ValueError("ETF composition is later than decision time")
    known_at = snapshot.known_at
    if known_at is None or known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("ETF snapshot known_at is required for point-in-time use")
    known_at = known_at.astimezone(UTC)
    if known_at > decision_time:
        raise ValueError("ETF snapshot was not known at decision time")
    if snapshot.completeness_status not in _COMPLETE:
        raise ValueError("ETF snapshot is not complete")
    if not snapshot.provenance or not snapshot.source_provider or not snapshot.snapshot_hash:
        raise ValueError("ETF snapshot provenance is incomplete")
    if snapshot.row_count <= 0 or len(rows) != snapshot.row_count:
        raise ValueError("ETF membership row count is partial")
    if snapshot.unresolved_count != 0 or snapshot.resolved_count != snapshot.row_count:
        raise ValueError("ETF membership contains unresolved rows")

    constituents: list[ETFConstituentIdentity] = []
    seen_ids: set[int] = set()
    seen_keys: set[str] = set()
    seen_hashes: set[str] = set()
    for holding, instrument in rows:
        domain_key = getattr(instrument, "domain_key", None)
        weight = holding.weight
        if (
            holding.snapshot_id != snapshot.id
            or holding.row_type != "security"
            or holding.holding_type != "equity"
            or not holding.is_resolved
            or holding.constituent_instrument_id != getattr(instrument, "id", None)
            or not domain_key
            or instrument.identity_status != "resolved"
            or not instrument.is_active
            or instrument.is_synthetic
            or not holding.source_row_hash
            or not isinstance(weight, Decimal)
            or weight < 0
        ):
            raise ValueError("ETF constituent identity or row evidence is invalid")
        if (
            instrument.id in seen_ids
            or domain_key in seen_keys
            or holding.source_row_hash in seen_hashes
        ):
            raise ValueError("ETF membership contains ambiguous duplicate constituents")
        seen_ids.add(instrument.id)
        seen_keys.add(domain_key)
        seen_hashes.add(holding.source_row_hash)
        constituents.append(
            ETFConstituentIdentity(
                instrument_id=instrument.id,
                domain_key=domain_key,
                source_row_hash=holding.source_row_hash,
                position=holding.position,
                weight=weight,
            )
        )
    constituents.sort(key=lambda item: (item.position, item.domain_key))
    published_at = snapshot.published_at
    if published_at is not None:
        if published_at.tzinfo is None or published_at.utcoffset() is None:
            raise ValueError("ETF published_at must be timezone-aware when present")
        published_at = published_at.astimezone(UTC)
        if published_at > decision_time:
            raise ValueError("ETF snapshot publication is later than decision time")
    lineage = {
        "etf_instrument_id": etf_instrument.domain_key,
        "etf_database_id": etf_instrument.id,
        "profile_id": profile.id,
        "snapshot_id": snapshot.id,
        "composition_date": snapshot.composition_date,
        "known_at": known_at,
        "published_at": published_at,
        "source_artifact_id": snapshot.source_artifact_id,
        "provenance": snapshot.provenance,
        "source_provider": snapshot.source_provider,
        "source_quality": snapshot.source_quality,
        "completeness_status": snapshot.completeness_status,
        "snapshot_hash": snapshot.snapshot_hash,
        "constituents": tuple(constituents),
    }
    return ETFPointInTimeMembership(**lineage, content_digest=content_digest(lineage))
