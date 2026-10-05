from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]
import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import AttemptState
from app.strategy_lab_v2.metrics import METRIC_DEFINITION_VERSION
from app.strategy_lab_v2.nautilus_equity_trace import (
    NautilusAccountEquityTraceWriter,
)
from app.strategy_lab_v2.nautilus_native_reports import NautilusNativeReportsWriter
from app.strategy_lab_v2.nautilus_result_materialization import (
    materialize_nautilus_oos_run_result,
)
from app.strategy_lab_v2.nautilus_session_equity import NautilusSessionCloseEquityObservation
from app.strategy_lab_v2.rebalance import (
    CalendarDay,
    CalendarDayStatus,
    SessionCalendarSnapshot,
    SessionSegment,
    TradingSession,
)
from app.strategy_lab_v2.result_materialization import (
    EngineResultEvidence,
    ResultMaterializationDecision,
    materialize_run_result,
)
from app.strategy_lab_v2.tests.test_result_publication import _result as result_fixture

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _inputs():
    result, *_ = result_fixture()
    evidence = EngineResultEvidence(
        result.trial_id,
        result.attempt_id,
        result.engine_name,
        result.engine_version,
        result.engine_build_digest,
        result.allocation_definition_version,
        result.dependency_catalog_digest,
        result.assumptions_digest,
        result.metric_set.fingerprint,
        tuple(item.content_digest for item in result.output_artifacts),
        NOW,
        True,
        result.engine_provenance,
    )
    return result, evidence


def test_result_materialization_builds_reproducible_manifest_and_replays() -> None:
    result, evidence = _inputs()
    materialized = materialize_run_result(
        result.trial,
        result.attempt,
        result.strategy_packages,
        result.portfolio,
        result.snapshot,
        evidence,
        result.metric_set,
        result.output_artifacts,
        created_at=NOW,
    )
    assert materialized.decision is ResultMaterializationDecision.MATERIALIZE
    assert materialized.manifest == result

    replay = materialize_run_result(
        result.trial,
        result.attempt,
        result.strategy_packages,
        result.portfolio,
        result.snapshot,
        evidence,
        result.metric_set,
        result.output_artifacts,
        created_at=NOW,
        existing=result,
    )
    assert replay.decision is ResultMaterializationDecision.REPLAY_EXISTING
    assert replay.manifest == result


def test_result_identity_normalizes_offset_equivalent_timestamps() -> None:
    result, evidence = _inputs()
    offset = timezone(timedelta(hours=1))
    equivalent_metric_set = replace(
        result.metric_set,
        created_at=datetime(2024, 1, 1, 1, tzinfo=offset),
    )
    assert equivalent_metric_set == result.metric_set
    equivalent_evidence = replace(
        evidence,
        observed_at=datetime(2024, 1, 1, 1, tzinfo=offset),
    )
    equivalent = materialize_run_result(
        result.trial,
        result.attempt,
        result.strategy_packages,
        result.portfolio,
        result.snapshot,
        equivalent_evidence,
        result.metric_set,
        result.output_artifacts,
        created_at=datetime(2024, 1, 1, 1, tzinfo=offset),
    )
    assert equivalent.manifest == result
    assert equivalent.manifest is not None
    assert equivalent.manifest.created_at.tzinfo is UTC
    assert equivalent_evidence.observed_at.tzinfo is UTC


def test_result_materialization_rejects_provenance_drift_and_failed_attempts() -> None:
    result, evidence = _inputs()
    drifted = replace(evidence, metric_set_fingerprint=content_digest("other-metrics"))
    rejected = materialize_run_result(
        result.trial,
        result.attempt,
        result.strategy_packages,
        result.portfolio,
        result.snapshot,
        drifted,
        result.metric_set,
        result.output_artifacts,
        created_at=NOW,
    )
    assert rejected.decision is ResultMaterializationDecision.REJECT
    assert "result_metric_evidence_mismatch" in (rejected.rejection_reason or "")

    failed_attempt = replace(result.attempt, state=AttemptState.FAILED)
    failed = materialize_run_result(
        result.trial,
        failed_attempt,
        result.strategy_packages,
        result.portfolio,
        result.snapshot,
        evidence,
        result.metric_set,
        result.output_artifacts,
        created_at=NOW,
    )
    assert failed.decision is ResultMaterializationDecision.REJECT
    assert "result_attempt_not_succeeded" in (failed.rejection_reason or "")


def test_result_materialization_conflicts_with_changed_existing_content() -> None:
    result, evidence = _inputs()
    changed = replace(result, assumptions_digest=content_digest("changed"))
    conflict = materialize_run_result(
        result.trial,
        result.attempt,
        result.strategy_packages,
        result.portfolio,
        result.snapshot,
        evidence,
        result.metric_set,
        result.output_artifacts,
        created_at=NOW,
        existing=changed,
    )
    assert conflict.decision is ResultMaterializationDecision.CONFLICT
    assert conflict.rejection_reason == "attempt is already bound to different result content"


def test_result_materialization_validates_types_and_time() -> None:
    result, evidence = _inputs()
    with pytest.raises(TypeError, match="trial"):
        materialize_run_result(
            "bad",  # type: ignore[arg-type]
            result.attempt,
            result.strategy_packages,
            result.portfolio,
            result.snapshot,
            evidence,
            result.metric_set,
            result.output_artifacts,
            created_at=NOW,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        materialize_run_result(
            result.trial,
            result.attempt,
            result.strategy_packages,
            result.portfolio,
            result.snapshot,
            evidence,
            result.metric_set,
            result.output_artifacts,
            created_at=datetime(2024, 1, 1),
        )


def test_engine_evidence_canonicalizes_artifact_order() -> None:
    result, _ = _inputs()
    first = content_digest("first-artifact")
    second = content_digest("second-artifact")
    evidence = EngineResultEvidence(
        result.trial_id,
        result.attempt_id,
        result.engine_name,
        result.engine_version,
        result.engine_build_digest,
        result.allocation_definition_version,
        result.dependency_catalog_digest,
        result.assumptions_digest,
        result.metric_set.fingerprint,
        (second, first),
        NOW,
        True,
        result.engine_provenance,
    )
    assert evidence.artifact_content_digests == tuple(sorted((first, second)))


def _nautilus_oos_references(
    result,
    equity_path,
    reports_path,
    *,
    event_times_ns: tuple[int, ...] = (100, 150, 199),
    scoring_end_ns: int | None = None,
    equity_values: tuple[str, ...] | None = None,
):
    window_fingerprint = content_digest("oos-window")
    scoring_end = scoring_end_ns if scoring_end_ns is not None else event_times_ns[-1] + 1
    engine_input = {
        "trial_id": result.trial.trial_id,
        "attempt_id": result.attempt.attempt_id,
        "data_snapshot_fingerprint": result.snapshot.fingerprint,
        "event_tape": {"source_tape_fingerprint": content_digest("source-tape")},
        "evaluation_window": {
            "fingerprint": window_fingerprint,
            "start_ns": event_times_ns[0],
            "end_ns": scoring_end,
        },
    }
    equity_writer = NautilusAccountEquityTraceWriter(
        equity_path,
        engine_input=engine_input,
        portfolio={
            "fingerprint": result.portfolio.fingerprint,
            "base_currency": result.portfolio.base_currency,
            "initial_capital": format(result.portfolio.initial_capital, "f"),
        },
    )
    expected_events = []
    resolved_equity_values = (
        equity_values or ("1000", "1010", "1005", "1020")[: len(event_times_ns)]
    )
    if len(resolved_equity_values) != len(event_times_ns):
        raise ValueError("test equity values must match their event timestamps")
    for index, timestamp in enumerate(event_times_ns):
        event_id = f"scoring-event-{index}"
        sequence = index + 1
        event = {"event_id": event_id, "event_time_ns": timestamp, "sequence": sequence}
        equity_writer.write(
            event_id=event_id,
            event_time_ns=timestamp,
            event_index=index,
            source_sequence=sequence,
            account_equity=Decimal(resolved_equity_values[index]),
            account_cash_balance=Decimal("1000"),
        )
        expected_events.append({"index": index, "event": event})
    trace_reference = equity_writer.finish()
    writer = NautilusNativeReportsWriter(
        reports_path,
        engine_input={
            "trial_id": trace_reference.trial_id,
            "attempt_id": trace_reference.attempt_id,
            "data_snapshot_fingerprint": trace_reference.snapshot_fingerprint,
            "event_tape": {"source_tape_fingerprint": trace_reference.source_tape_fingerprint},
            "evaluation_window": {
                "fingerprint": window_fingerprint,
                "start_ns": event_times_ns[0],
                "end_ns": scoring_end,
            },
        },
        portfolio={"fingerprint": trace_reference.portfolio_fingerprint},
    )
    writer.write_reports(
        {
            "account": pd.DataFrame([{"currency": "USD", "total": "1000"}]),
            "fills": pd.DataFrame([{"ts_event": 150, "commission": "2.00 USD"}]),
            "orders": pd.DataFrame([{"ts_init": 150}]),
            "positions": pd.DataFrame(columns=["ts_opened", "ts_closed", "realized_pnl"]),
        }
    )
    return trace_reference, tuple(expected_events), writer.finish()


def _datetime_ns(value: datetime) -> int:
    delta = value.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return ((delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds) * 1_000


def test_nautilus_oos_result_materialization_binds_metrics_and_native_artifacts(tmp_path) -> None:
    existing_result, evidence = _inputs()
    equity_path = tmp_path / "account-equity.parquet"
    reports_path = tmp_path / "native-reports.parquet"
    trace_reference, expected_events, reports_reference = _nautilus_oos_references(
        existing_result,
        equity_path,
        reports_path,
    )
    arguments = (
        existing_result.trial,
        existing_result.attempt,
        existing_result.strategy_packages,
        existing_result.portfolio,
        existing_result.snapshot,
        evidence,
        trace_reference,
        equity_path,
        expected_events,
        reports_reference,
        reports_path,
        existing_result.output_artifacts,
    )

    materialized = materialize_nautilus_oos_run_result(
        *arguments,
        created_at=NOW,
    )

    assert materialized.decision is ResultMaterializationDecision.MATERIALIZE
    assert materialized.manifest is not None
    manifest = materialized.manifest
    manifest_digests = {item.content_digest for item in manifest.output_artifacts}
    assert trace_reference.artifact.content_digest in manifest_digests
    assert reports_reference.artifact.content_digest in manifest_digests
    metrics = {item.name: item for item in manifest.metric_set.values}
    assert metrics["oos_fill_count"].value == Decimal(1)
    assert metrics["oos_reported_commission:USD"].value == Decimal("2.00")
    assert metrics["maximum_drawdown_duration_seconds"].value == Decimal("0.000000049")
    cash_ratio = metrics["average_account_cash_to_equity"]
    assert cash_ratio.value is not None
    assert cash_ratio.sample_size == trace_reference.observation_count
    assert cash_ratio.unit == "ratio"
    assert cash_ratio.definition_version == METRIC_DEFINITION_VERSION
    assert any(
        reference.role == "native_account_cash_trace"
        and reference.digest == trace_reference.artifact.content_digest
        for reference in cash_ratio.evidence_references
    )

    replay = materialize_nautilus_oos_run_result(
        *arguments,
        created_at=NOW,
        existing=manifest,
    )
    assert replay.decision is ResultMaterializationDecision.REPLAY_EXISTING
    assert replay.manifest == manifest


def test_nautilus_oos_materialization_persists_calendar_bound_session_intervals(tmp_path) -> None:
    existing_result, evidence = _inputs()
    labels = tuple(date(2026, 9, 1) + timedelta(days=index) for index in range(4))
    sessions = tuple(
        TradingSession(
            f"XNYS:{label.isoformat()}",
            label,
            (
                SessionSegment(
                    datetime(label.year, label.month, label.day, 14, 30, tzinfo=UTC),
                    datetime(label.year, label.month, label.day, 21, 0, tzinfo=UTC),
                ),
            ),
        )
        for label in labels
    )
    calendar = SessionCalendarSnapshot(
        calendar_id="XNYS",
        definition_version="XNYS-result-test-v1",
        timezone_name="America/New_York",
        timezone_database_version="test-tzdb-v1",
        coverage_start=labels[0],
        coverage_end=labels[-1],
        days=tuple(
            CalendarDay(label, CalendarDayStatus.TRADING, session)
            for label, session in zip(labels, sessions, strict=True)
        ),
        source_evidence_digest=content_digest("XNYS-result-calendar"),
    )
    event_times = tuple(_datetime_ns(session.close_time) for session in sessions)
    equity_path = tmp_path / "account-equity-session.parquet"
    reports_path = tmp_path / "native-reports-session.parquet"
    trace_reference, expected_events, reports_reference = _nautilus_oos_references(
        existing_result,
        equity_path,
        reports_path,
        event_times_ns=event_times,
        scoring_end_ns=event_times[-1] + 1_000,
    )
    session_closes = tuple(
        NautilusSessionCloseEquityObservation(
            session_label=sessions[index].session_label,
            event_time_ns=event_times[index],
            event_index=index,
            account_equity=Decimal(("1010", "1005", "1020")[index - 1]),
            account_cash_balance=Decimal("1000"),
        )
        for index in range(1, 4)
    )
    result = materialize_nautilus_oos_run_result(
        existing_result.trial,
        existing_result.attempt,
        existing_result.strategy_packages,
        existing_result.portfolio,
        existing_result.snapshot,
        evidence,
        trace_reference,
        equity_path,
        expected_events,
        reports_reference,
        reports_path,
        existing_result.output_artifacts,
        created_at=NOW,
        session_calendar=calendar,
        session_close_observations=session_closes,
        session_periods_per_year=252,
    )

    assert result.decision is ResultMaterializationDecision.MATERIALIZE
    assert result.manifest is not None
    assert result.generated_session_intervals is not None
    interval_artifact = result.generated_session_intervals
    assert interval_artifact.observed_session_labels == labels[1:]
    assert interval_artifact.artifact in result.manifest.output_artifacts
    metrics = {item.name: item for item in result.manifest.metric_set.values}
    assert metrics["historical_value_at_risk"].value is not None
    assert metrics["historical_value_at_risk"].sample_size == 3

    missing_closes = materialize_nautilus_oos_run_result(
        existing_result.trial,
        existing_result.attempt,
        existing_result.strategy_packages,
        existing_result.portfolio,
        existing_result.snapshot,
        evidence,
        trace_reference,
        equity_path,
        expected_events,
        reports_reference,
        reports_path,
        existing_result.output_artifacts,
        created_at=NOW,
        session_calendar=calendar,
        session_close_observations=(),
        session_periods_per_year=252,
    )
    assert missing_closes.manifest is not None
    assert missing_closes.generated_session_intervals is not None
    assert missing_closes.generated_session_intervals.expected_session_labels == labels[1:]
    assert missing_closes.generated_session_intervals.observed_session_labels == ()
    assert missing_closes.generated_session_intervals.artifact in (
        missing_closes.manifest.output_artifacts
    )
    missing_metric_names = {item.name for item in missing_closes.manifest.metric_set.values}
    assert "historical_value_at_risk" not in missing_metric_names


def test_nautilus_oos_result_materialization_rejects_identity_drift(tmp_path) -> None:
    existing_result, evidence = _inputs()
    equity_path = tmp_path / "account-equity.parquet"
    reports_path = tmp_path / "native-reports.parquet"
    trace_reference, expected_events, reports_reference = _nautilus_oos_references(
        existing_result,
        equity_path,
        reports_path,
    )
    drifted_reference = replace(
        trace_reference,
        portfolio_fingerprint=content_digest("different-portfolio"),
    )

    with pytest.raises(ValueError, match="do not match the result identities"):
        materialize_nautilus_oos_run_result(
            existing_result.trial,
            existing_result.attempt,
            existing_result.strategy_packages,
            existing_result.portfolio,
            existing_result.snapshot,
            evidence,
            drifted_reference,
            equity_path,
            expected_events,
            reports_reference,
            reports_path,
            existing_result.output_artifacts,
            created_at=NOW,
        )
