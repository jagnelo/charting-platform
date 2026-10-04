from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.metrics import METRIC_DEFINITION_VERSION
from app.strategy_lab_v2.nautilus_equity_trace import (
    NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE,
    NAUTILUS_ACCOUNT_EQUITY_TRACE_SCHEMA,
    NautilusAccountEquityTraceReference,
)
from app.strategy_lab_v2.nautilus_result_metrics import build_nautilus_oos_equity_metric_set


def _reference(*, windowed: bool = True) -> NautilusAccountEquityTraceReference:
    artifact_digest = content_digest("account-equity-trace")
    artifact = ArtifactManifest(
        content_digest=artifact_digest,
        byte_length=128,
        media_type=NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE,
        schema_version=NAUTILUS_ACCOUNT_EQUITY_TRACE_SCHEMA,
        storage_key=artifact_digest,
        retention_class=ArtifactRetention.PINNED_RESULT,
    )
    return NautilusAccountEquityTraceReference(
        artifact=artifact,
        trial_id=content_digest("trial"),
        attempt_id="attempt-1",
        portfolio_fingerprint=content_digest("portfolio"),
        snapshot_fingerprint=content_digest("snapshot"),
        source_tape_fingerprint=content_digest("source-tape"),
        evaluation_window_fingerprint=(content_digest("evaluation-window") if windowed else None),
        scoring_start_ns=100 if windowed else None,
        scoring_end_ns=200 if windowed else None,
        base_currency="USD",
        initial_capital=Decimal("1000"),
        observation_count=3,
    )


def test_build_nautilus_oos_equity_metric_set_binds_trial_attempt_and_trace() -> None:
    reference = _reference()
    metric_set = build_nautilus_oos_equity_metric_set(
        reference,
        (Decimal("1200"), Decimal("1300"), Decimal("1260")),
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metric_set.trial_id == reference.trial_id
    assert metric_set.attempt_id == reference.attempt_id
    assert metric_set.definition_version == METRIC_DEFINITION_VERSION
    assert metrics["total_pnl"].value == Decimal("60")
    assert metrics["total_return"].value == Decimal("0.05")
    assert metrics["total_return"].evidence_references[0].digest == (
        reference.artifact.content_digest
    )
    assert metrics["annualized_return"].value is None


def test_build_nautilus_oos_equity_metric_set_rejects_non_oos_receipts() -> None:
    reference = _reference(windowed=False)

    with pytest.raises(ValueError, match="require an OOS evaluation window"):
        build_nautilus_oos_equity_metric_set(
            reference,
            (Decimal("1200"), Decimal("1300"), Decimal("1260")),
            created_at=datetime(2026, 10, 4, tzinfo=UTC),
        )
