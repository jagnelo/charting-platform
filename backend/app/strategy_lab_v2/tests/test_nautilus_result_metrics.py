from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]
import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.metrics import METRIC_DEFINITION_VERSION
from app.strategy_lab_v2.nautilus_equity_trace import (
    NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE,
    NAUTILUS_ACCOUNT_EQUITY_TRACE_SCHEMA,
    NautilusAccountEquityTraceReference,
)
from app.strategy_lab_v2.nautilus_native_reports import NautilusNativeReportsWriter
from app.strategy_lab_v2.nautilus_result_metrics import (
    build_nautilus_oos_equity_metric_set,
    build_nautilus_oos_metric_set,
)


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


def test_build_nautilus_oos_metric_set_filters_and_binds_native_reports(tmp_path) -> None:
    equity_reference = _reference()
    reports_path = tmp_path / "native-reports.parquet"
    writer = NautilusNativeReportsWriter(
        reports_path,
        engine_input={
            "trial_id": equity_reference.trial_id,
            "attempt_id": equity_reference.attempt_id,
            "data_snapshot_fingerprint": equity_reference.snapshot_fingerprint,
            "event_tape": {
                "source_tape_fingerprint": equity_reference.source_tape_fingerprint,
            },
            "evaluation_window": {
                "fingerprint": equity_reference.evaluation_window_fingerprint,
                "start_ns": equity_reference.scoring_start_ns,
                "end_ns": equity_reference.scoring_end_ns,
            },
        },
        portfolio={"fingerprint": equity_reference.portfolio_fingerprint},
    )
    writer.write_reports(
        {
            "account": pd.DataFrame([{"currency": "USD", "total": "1,000.00"}]),
            "fills": pd.DataFrame(
                [
                    {"ts_event": 99, "commission": "1.00 USD"},
                    {"ts_event": 100, "commission": "1.25 USD"},
                    {"ts_event": 199, "commission": None},
                    {"ts_event": 200, "commission": "4.00 USD"},
                ]
            ),
            "orders": pd.DataFrame([{"ts_init": 100}, {"ts_init": 200}]),
            "positions": pd.DataFrame(
                [
                    {
                        "ts_opened": 150,
                        "ts_closed": 190,
                        "realized_pnl": "12.50 USD",
                    },
                    {"ts_opened": 50, "ts_closed": None, "realized_pnl": None},
                ]
            ),
        }
    )
    report_reference = writer.finish()

    metric_set = build_nautilus_oos_metric_set(
        equity_reference,
        (Decimal("1000"), Decimal("1020"), Decimal("1010")),
        report_reference,
        reports_path,
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metrics["oos_fill_count"].value == Decimal(2)
    assert metrics["oos_order_submission_count"].value == Decimal(1)
    assert metrics["oos_position_records_opened_count"].value == Decimal(1)
    assert metrics["oos_position_records_closed_count"].value == Decimal(1)
    assert metrics["oos_commission_reported_fill_count"].value == Decimal(1)
    assert metrics["oos_commission_unreported_fill_count"].value == Decimal(1)
    assert metrics["oos_commission_reporting_coverage"].value == Decimal("0.5")
    assert metrics["oos_reported_commission:USD"].value == Decimal("1.25")
    assert metrics["oos_reported_realized_position_pnl:USD"].value == Decimal("12.50")
    assert metrics["oos_reported_commission:USD"].evidence_references[0].digest == (
        report_reference.artifact.content_digest
    )
    assert (
        metric_set.metric_set_id
        != build_nautilus_oos_equity_metric_set(
            equity_reference,
            (Decimal("1000"), Decimal("1020"), Decimal("1010")),
            created_at=datetime(2026, 10, 4, tzinfo=UTC),
        ).metric_set_id
    )


def test_build_nautilus_oos_metric_set_rejects_report_scope_mismatch(tmp_path) -> None:
    equity_reference = _reference()
    writer = NautilusNativeReportsWriter(
        tmp_path / "native-reports.parquet",
        engine_input={
            "trial_id": equity_reference.trial_id,
            "attempt_id": equity_reference.attempt_id,
            "data_snapshot_fingerprint": content_digest("different-snapshot"),
            "event_tape": {
                "source_tape_fingerprint": equity_reference.source_tape_fingerprint,
            },
            "evaluation_window": {
                "fingerprint": equity_reference.evaluation_window_fingerprint,
                "start_ns": equity_reference.scoring_start_ns,
                "end_ns": equity_reference.scoring_end_ns,
            },
        },
        portfolio={"fingerprint": equity_reference.portfolio_fingerprint},
    )
    writer.write_reports(
        {
            "account": pd.DataFrame([{"currency": "USD"}]),
            "fills": pd.DataFrame(columns=["ts_event", "commission"]),
            "orders": pd.DataFrame(columns=["ts_init"]),
            "positions": pd.DataFrame(columns=["ts_opened", "ts_closed"]),
        }
    )
    report_reference = writer.finish()

    with pytest.raises(ValueError, match="do not share one OOS scope"):
        build_nautilus_oos_metric_set(
            equity_reference,
            (Decimal("1000"), Decimal("1020"), Decimal("1010")),
            report_reference,
            tmp_path / "native-reports.parquet",
            created_at=datetime(2026, 10, 4, tzinfo=UTC),
        )


def test_build_nautilus_oos_metric_set_marks_incomplete_timestamps_unavailable(tmp_path) -> None:
    equity_reference = _reference()
    reports_path = tmp_path / "native-reports.parquet"
    writer = NautilusNativeReportsWriter(
        reports_path,
        engine_input={
            "trial_id": equity_reference.trial_id,
            "attempt_id": equity_reference.attempt_id,
            "data_snapshot_fingerprint": equity_reference.snapshot_fingerprint,
            "event_tape": {
                "source_tape_fingerprint": equity_reference.source_tape_fingerprint,
            },
            "evaluation_window": {
                "fingerprint": equity_reference.evaluation_window_fingerprint,
                "start_ns": equity_reference.scoring_start_ns,
                "end_ns": equity_reference.scoring_end_ns,
            },
        },
        portfolio={"fingerprint": equity_reference.portfolio_fingerprint},
    )
    writer.write_reports(
        {
            "account": pd.DataFrame([{"currency": "USD"}]),
            "fills": pd.DataFrame(
                [
                    {"ts_event": 100, "commission": "1.00 USD"},
                    {"commission": "2.00 USD"},
                ]
            ),
            "orders": pd.DataFrame(columns=["ts_init"]),
            "positions": pd.DataFrame(columns=["ts_opened", "ts_closed"]),
        }
    )
    reports_reference = writer.finish()

    metric_set = build_nautilus_oos_metric_set(
        equity_reference,
        (Decimal("1000"), Decimal("1020"), Decimal("1010")),
        reports_reference,
        reports_path,
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metrics["oos_fill_count"].value is None
    assert "timestamp" in (metrics["oos_fill_count"].null_reason or "")
    assert metrics["oos_commission_reported_fill_count"].value is None
    assert metrics["oos_commission_reporting_coverage"].value is None
    assert "timestamp" in (metrics["oos_commission_reporting_coverage"].null_reason or "")
