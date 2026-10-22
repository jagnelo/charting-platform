"""Fail-closed immutable ETF membership evidence for a single decision time.

This is a consumer-side contract over already persisted ETF rows. It performs
no acquisition and deliberately does not call the ETF "current capability"
gate: historical visibility is decided only by the snapshot's known_at.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ETFMembershipReference

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


async def resolve_etf_pit_membership(
    session: Any,
    *,
    etf_instrument_id: str,
    decision_time: datetime,
    snapshot_id: int | None = None,
) -> ETFPointInTimeMembership:
    """Read the exact persisted ETF snapshot locally; never refresh or fallback."""

    from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
    from app.models.instrument import Instrument

    if not isinstance(etf_instrument_id, str) or not etf_instrument_id.strip():
        raise ValueError("etf_instrument_id must be a canonical domain key")
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("ETF decision_time must be timezone-aware")
    instruments = (
        (
            await session.execute(
                select(Instrument).where(Instrument.domain_key == etf_instrument_id)
            )
        )
        .scalars()
        .all()
    )
    if len(instruments) != 1:
        raise ValueError("ETF canonical identity is missing or ambiguous")
    instrument = instruments[0]
    profiles = (
        (await session.execute(select(ETFProfile).where(ETFProfile.instrument_id == instrument.id)))
        .scalars()
        .all()
    )
    if len(profiles) != 1:
        raise ValueError("ETF profile is missing or ambiguous")
    profile = profiles[0]
    snapshot_query = select(ETFHoldingsSnapshot).where(
        ETFHoldingsSnapshot.etf_profile_id == profile.id,
        ETFHoldingsSnapshot.known_at.is_not(None),
        ETFHoldingsSnapshot.known_at <= decision_time,
    )
    if snapshot_id is None:
        snapshot_query = snapshot_query.where(
            ETFHoldingsSnapshot.composition_date <= decision_time.date()
        )
    else:
        if not isinstance(snapshot_id, int) or isinstance(snapshot_id, bool) or snapshot_id <= 0:
            raise ValueError("pinned ETF snapshot_id must be a positive integer")
        snapshot_query = snapshot_query.where(ETFHoldingsSnapshot.id == snapshot_id)
    snapshots = (await session.execute(snapshot_query)).scalars().all()
    if not snapshots:
        raise ValueError("pinned ETF snapshot is missing or was not known at decision time")
    if snapshot_id is not None and len(snapshots) != 1:
        raise ValueError("pinned ETF snapshot identity is ambiguous")
    snapshots.sort(key=lambda item: (item.composition_date, item.known_at), reverse=True)
    latest_key = (snapshots[0].composition_date, snapshots[0].known_at)
    latest = [item for item in snapshots if (item.composition_date, item.known_at) == latest_key]
    if len(latest) != 1:
        raise ValueError("latest ETF point-in-time snapshot is ambiguous")
    snapshot = latest[0]
    rows = (
        await session.execute(
            select(ETFHolding, Instrument)
            .outerjoin(Instrument, Instrument.id == ETFHolding.constituent_instrument_id)
            .where(ETFHolding.snapshot_id == snapshot.id)
            .order_by(ETFHolding.position, ETFHolding.id)
        )
    ).all()
    return freeze_etf_pit_membership(
        etf_instrument=instrument,
        profile=profile,
        snapshot=snapshot,
        rows=tuple(rows),
        decision_time=decision_time,
    )


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
    # Match the released producer's durable artifact-identity field/status.
    # Current availability/canary state is intentionally excluded: it cannot
    # prove historical visibility at this decision timestamp.
    metadata = snapshot.extra_data if isinstance(snapshot.extra_data, dict) else {}
    legal_metadata = metadata.get("legal_metadata")
    legal_metadata = legal_metadata if isinstance(legal_metadata, dict) else {}
    validation = metadata.get("artifact_identity_validation")
    if not validation:
        validation = legal_metadata.get("artifact_identity_validation")
    validation = validation if isinstance(validation, dict) else {}
    if validation.get("status") not in {"matched", "matched_inferred"}:
        raise ValueError("ETF snapshot lacks producer-verified artifact identity")
    # The producer can infer source tier from several metadata fields. Strategy
    # intentionally requires an explicit persisted tier and never repeats that
    # inference, so absent provenance stays unavailable.
    source_tier = metadata.get("source_tier") or legal_metadata.get("source_tier")
    if source_tier not in {"issuer_native", "successor_native", "licensed_vendor"}:
        raise ValueError("ETF snapshot source tier is denied for Strategy inputs")
    quality = str(snapshot.source_quality or "").strip().lower()
    if not quality.startswith(("issuer_", "successor_", "licensed_", "self_snapshotted_")):
        raise ValueError("ETF snapshot source quality is unknown or denied")
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
            or not weight.is_finite()
            or weight < 0
            or weight > 1
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


def membership_reference(
    membership: ETFPointInTimeMembership, *, decision_time: datetime
) -> ETFMembershipReference:
    """Create the small immutable selector persisted by a DataSnapshot."""

    if not isinstance(membership, ETFPointInTimeMembership):
        raise TypeError("membership must be verified ETFPointInTimeMembership evidence")
    return ETFMembershipReference(
        etf_instrument_id=membership.etf_instrument_id,
        decision_time=decision_time,
        snapshot_id=membership.snapshot_id,
        content_digest=membership.content_digest,
    )


class LocalETFMembershipReader:
    """Worker-side persisted membership reader used only for restart checks."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory

    async def resolve_pinned_etf_membership(
        self, reference: ETFMembershipReference
    ) -> ETFPointInTimeMembership:
        if not isinstance(reference, ETFMembershipReference):
            raise TypeError("reference must be ETFMembershipReference")
        async with self._session_factory() as session:
            return await resolve_etf_pit_membership(
                session,
                etf_instrument_id=reference.etf_instrument_id,
                decision_time=reference.decision_time,
                snapshot_id=reference.snapshot_id,
            )
