"""Host-side metric-set construction from a verified native OOS equity trace."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import MetricSet
from app.strategy_lab_v2.metrics import (
    METRIC_DEFINITION_VERSION,
    calculate_event_aligned_equity_metrics,
)
from app.strategy_lab_v2.nautilus_equity_trace import NautilusAccountEquityTraceReference


def build_nautilus_oos_equity_metric_set(
    reference: NautilusAccountEquityTraceReference,
    equity_marks: Iterable[Decimal],
    *,
    created_at: datetime,
) -> MetricSet:
    """Build reproducible official OOS equity metrics for one native attempt.

    ``equity_marks`` must be streamed from the byte-verified Parquet artifact
    identified by ``reference``. Its opening row is the first scoring-window
    account mark and the receipt count is enforced during metric calculation.
    Other native reports (fills, positions, and costs) can be added as further
    metric families without changing this equity-only evidence binding.
    """

    if not isinstance(reference, NautilusAccountEquityTraceReference):
        raise TypeError("reference must be a NautilusAccountEquityTraceReference")
    if reference.evaluation_window_fingerprint is None:
        raise ValueError("official Nautilus metrics require an OOS evaluation window")
    values = calculate_event_aligned_equity_metrics(
        equity_marks,
        base_currency=reference.base_currency,
        evidence_digest=reference.artifact.content_digest,
        expected_mark_count=reference.observation_count,
    )
    metric_set_identity = content_digest(
        {
            "attempt_id": reference.attempt_id,
            "definition_version": METRIC_DEFINITION_VERSION,
            "equity_trace_digest": reference.artifact.content_digest,
            "trial_id": reference.trial_id,
        }
    )
    return MetricSet(
        metric_set_id=f"metrics-{metric_set_identity.removeprefix('sha256:')}",
        trial_id=reference.trial_id,
        attempt_id=reference.attempt_id,
        definition_version=METRIC_DEFINITION_VERSION,
        values=values,
        created_at=created_at,
    )


__all__ = ["build_nautilus_oos_equity_metric_set"]
