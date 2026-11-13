"""ETF dataset preparation for the shared durable request worker.

The callable consumes Provider-owned ``DatasetPreparationContext`` and
``DatasetPreparationResult`` DTOs. Cache eligibility stays ETF-specific and
allows a source skip only for the exact selected fund's verified current
snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument

if TYPE_CHECKING:
    from app.services.data_preparation_contracts import (
        DatasetPreparationContext,
        DatasetPreparationResult,
    )


def _coverage_for_composition_date(
    value: date | datetime | None,
) -> tuple[datetime | None, datetime | None]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return None, None
        start = value.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    elif isinstance(value, date):
        start = datetime.combine(value, time.min, tzinfo=UTC)
    else:
        return None, None
    return start, start + timedelta(days=1)


def _known_retry_at(*values: Any) -> datetime | None:
    for value in values:
        if (
            isinstance(value, datetime)
            and value.tzinfo is not None
            and value.utcoffset() is not None
        ):
            return value.astimezone(UTC)
    return None


def is_reusable_current_holdings_snapshot(
    instrument: Any,
    profile: Any,
    snapshot: Any | None,
    capability: Mapping[str, Any] | None,
) -> bool:
    """Return true only for a current, verified snapshot bound to this fund.

    Callers load the snapshot through the normal visibility filter and evaluate
    capability against that same ORM row.  These local bindings make the
    selected instrument/profile relationship explicit and prevent a late or
    stale snapshot from another selection from satisfying this dataset.
    """

    instrument_id = getattr(instrument, "id", None)
    profile_id = getattr(profile, "id", None)
    if (
        isinstance(instrument_id, bool)
        or not isinstance(instrument_id, int)
        or instrument_id <= 0
        or isinstance(profile_id, bool)
        or not isinstance(profile_id, int)
        or profile_id <= 0
        or getattr(instrument, "is_active", False) is not True
        or getattr(instrument, "is_synthetic", False) is True
        or getattr(instrument, "identity_status", None) != "resolved"
        or getattr(profile, "instrument_id", None) != instrument_id
        or snapshot is None
        or getattr(snapshot, "etf_profile_id", None) != profile_id
        or not isinstance(capability, Mapping)
    ):
        return False

    return (
        capability.get("availability") == "current"
        and capability.get("identity_verified") is True
        and capability.get("usable_for_current_analysis") is True
    )


def _preparation_result(
    *,
    status: str,
    snapshot: Any | None,
    reason_code: str | None = None,
    retry_at: datetime | None = None,
):
    # Provider owns this result DTO. Import lazily so this ETF worktree remains
    # importable before the released Provider dependency is adopted.
    from app.services.data_preparation_contracts import DatasetPreparationResult

    covered_start, covered_end = _coverage_for_composition_date(
        getattr(snapshot, "composition_date", None)
    )
    return DatasetPreparationResult(
        status=status,
        covered_start=covered_start,
        covered_end=covered_end,
        reason_code=reason_code,
        retry_at=retry_at,
        acquired_version=getattr(snapshot, "id", None),
    )


async def prepare_etf_holdings(
    db: AsyncSession,
    instrument: Instrument,
    *,
    context: DatasetPreparationContext,
) -> DatasetPreparationResult:
    """Prepare the selected canonical fund's latest issuer holdings dataset.

    The shared durable request is the user's acquisition intent. This callable
    never discovers identities or bypasses the existing ETF route/admission
    service. It returns ready only when the same visible, persisted ORM snapshot
    is both current and verified by the normal capability evaluator.
    """

    from app.services.data_preparation_contracts import PreparationDataset
    from app.services.etf_holdings import (
        _latest_snapshot_record_for_profile,
        get_etf_profile_for_instrument,
        holdings_capability_for_profile,
    )
    from app.services.etf_holdings_refresh import acquire_etf_holdings_profile

    instrument_id = getattr(instrument, "id", None)
    if context.dataset != PreparationDataset.HOLDINGS:
        return _preparation_result(
            status="unavailable",
            snapshot=None,
            reason_code="holdings_dataset_required",
        )
    if (
        isinstance(instrument_id, bool)
        or not isinstance(instrument_id, int)
        or instrument_id <= 0
        or getattr(instrument, "is_active", False) is not True
        or getattr(instrument, "is_synthetic", False) is True
        or getattr(instrument, "identity_status", None) != "resolved"
    ):
        return _preparation_result(
            status="unavailable",
            snapshot=None,
            reason_code="canonical_etf_instrument_required",
        )

    profile = await get_etf_profile_for_instrument(db, instrument_id)
    snapshot = None
    capability = None
    if profile is not None:
        snapshot = await _latest_snapshot_record_for_profile(
            db,
            profile.id,
            include_holdings=False,
            include_controlled_fixture=False,
        )
        capability = await holdings_capability_for_profile(db, profile, snapshot=snapshot)
        if is_reusable_current_holdings_snapshot(instrument, profile, snapshot, capability):
            return _preparation_result(status="ready", snapshot=snapshot)

    deadline = context.deadline
    if not isinstance(deadline, datetime) or deadline.tzinfo is None:
        return _preparation_result(
            status="waiting",
            snapshot=snapshot,
            reason_code="preparation_deadline_unavailable",
        )
    if deadline.astimezone(UTC) <= datetime.now(UTC):
        return _preparation_result(
            status="waiting",
            snapshot=snapshot,
            reason_code="preparation_deadline_elapsed",
        )

    acquisition = await acquire_etf_holdings_profile(
        db,
        symbol=instrument.symbol,
        request_id=context.request_id,
        refresh=True,
        instrument_id=instrument_id,
    )
    if acquisition is None:
        return _preparation_result(
            status="unavailable",
            snapshot=None,
            reason_code="canonical_etf_instrument_unavailable",
        )

    # Re-read from storage after the issuer service returns. An adapter return
    # or queued request alone does not prove that a current snapshot exists.
    profile = await get_etf_profile_for_instrument(db, instrument_id)
    snapshot = None
    capability = None
    if profile is not None:
        snapshot = await _latest_snapshot_record_for_profile(
            db,
            profile.id,
            include_holdings=False,
            include_controlled_fixture=False,
        )
        capability = await holdings_capability_for_profile(db, profile, snapshot=snapshot)
        if is_reusable_current_holdings_snapshot(instrument, profile, snapshot, capability):
            return _preparation_result(status="ready", snapshot=snapshot)

    outcome = acquisition.outcome
    retry_at = _known_retry_at(
        getattr(acquisition, "retry_at", None),
        capability.get("circuit_open_until") if isinstance(capability, Mapping) else None,
    )
    acquisition_reason = getattr(acquisition, "reason_code", None)
    if outcome == "unavailable":
        status, reason_code = "unavailable", acquisition_reason or "issuer_route_unavailable"
        retry_at = None
    elif outcome == "failed":
        status, reason_code = "failed", acquisition_reason or "issuer_acquisition_failed"
    elif outcome == "held":
        unavailable_reasons = {
            "issuer_route_mismatch",
            "issuer_adapter_unavailable",
            "issuer_source_identity_mismatch",
            "issuer_route_incomplete",
            "issuer_adapter_not_ready",
            "issuer_provider_identity_missing",
        }
        status = "unavailable" if acquisition_reason in unavailable_reasons else "waiting"
        reason_code = acquisition_reason or "issuer_acquisition_held"
    elif outcome == "no_data":
        status, reason_code = "waiting", "issuer_snapshot_unavailable"
    else:
        status, reason_code = "waiting", "issuer_snapshot_not_current"
    return _preparation_result(
        status=status,
        snapshot=snapshot,
        reason_code=reason_code,
        retry_at=retry_at,
    )
