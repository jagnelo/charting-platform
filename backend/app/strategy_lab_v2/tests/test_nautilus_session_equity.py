from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.nautilus_equity_trace import (
    NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE,
    NAUTILUS_ACCOUNT_EQUITY_TRACE_SCHEMA,
    NautilusAccountEquityObservation,
    NautilusAccountEquityTraceReference,
)
from app.strategy_lab_v2.nautilus_runner import _read_session_close_equity_observations
from app.strategy_lab_v2.nautilus_session_equity import (
    NautilusSessionCloseEquityObservation,
    build_nautilus_session_equity_intervals_artifact,
)
from app.strategy_lab_v2.rebalance import (
    CalendarDay,
    CalendarDayStatus,
    SessionCalendarSnapshot,
    SessionSegment,
    TradingSession,
)


def _unix_ns(value: datetime) -> int:
    delta = value.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return ((delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds) * 1_000


def _session_fixture():
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
        definition_version="XNYS-session-risk-test-v1",
        timezone_name="America/New_York",
        timezone_database_version="test-tzdb-v1",
        coverage_start=labels[0],
        coverage_end=labels[-1],
        days=tuple(
            CalendarDay(label, CalendarDayStatus.TRADING, session)
            for label, session in zip(labels, sessions, strict=True)
        ),
        source_evidence_digest=content_digest("session-risk-test-calendar"),
    )
    start_ns = _unix_ns(sessions[0].close_time)
    end_ns = _unix_ns(sessions[-1].close_time) + 1_000
    artifact_digest = content_digest("account-equity-trace")
    reference = NautilusAccountEquityTraceReference(
        artifact=ArtifactManifest(
            content_digest=artifact_digest,
            byte_length=128,
            media_type=NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE,
            schema_version=NAUTILUS_ACCOUNT_EQUITY_TRACE_SCHEMA,
            storage_key=artifact_digest,
            retention_class=ArtifactRetention.PINNED_RESULT,
        ),
        trial_id=content_digest("trial"),
        attempt_id="attempt-1",
        portfolio_fingerprint=content_digest("portfolio"),
        snapshot_fingerprint=content_digest("snapshot"),
        source_tape_fingerprint=content_digest("source-tape"),
        evaluation_window_fingerprint=content_digest("evaluation-window"),
        scoring_start_ns=start_ns,
        scoring_end_ns=end_ns,
        base_currency="USD",
        initial_capital=Decimal("1000"),
        observation_count=4,
    )
    equity = tuple(
        NautilusAccountEquityObservation(
            _unix_ns(session.close_time),
            Decimal(value),
            index,
        )
        for index, (session, value) in enumerate(
            zip(sessions, ("1000", "1020", "990", "1050"), strict=True)
        )
    )
    closes = tuple(
        NautilusSessionCloseEquityObservation(
            session_label=sessions[index].session_label,
            event_time_ns=_unix_ns(sessions[index].close_time),
            event_index=index + 4,
            account_equity=Decimal(value),
            account_cash_balance=Decimal("500"),
        )
        for index, value in enumerate(("1020", "990", "1050"), start=1)
    )
    return reference, calendar, equity, closes, sessions


def test_native_session_equity_artifact_binds_exact_close_intervals() -> None:
    reference, calendar, equity, closes, _sessions = _session_fixture()

    result = build_nautilus_session_equity_intervals_artifact(
        reference,
        equity,
        closes,
        calendar=calendar,
        engine_evidence_digest=content_digest("engine evidence"),
        session_periods_per_year=252,
    )

    assert result.expected_session_labels == (
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
    )
    assert result.observed_session_labels == result.expected_session_labels
    assert [item.starting_equity for item in result.intervals] == [
        Decimal("1000"),
        Decimal("1020"),
        Decimal("990"),
    ]
    assert [item.ending_equity for item in result.intervals] == [
        Decimal("1020"),
        Decimal("990"),
        Decimal("1050"),
    ]
    assert all(
        item.external_cash_flow_report_status.value == "complete" for item in result.intervals
    )
    assert result.artifact.content_digest == f"sha256:{hashlib.sha256(result.payload).hexdigest()}"
    assert b"post_event_group_at_exact_calendar_session_close" in result.payload


def test_native_session_equity_artifact_does_not_bridge_missing_closes() -> None:
    reference, calendar, equity, closes, _sessions = _session_fixture()

    result = build_nautilus_session_equity_intervals_artifact(
        reference,
        equity,
        (closes[0], closes[2]),
        calendar=calendar,
        engine_evidence_digest=content_digest("engine evidence"),
        session_periods_per_year=252,
    )

    assert result.observed_session_labels == (date(2026, 9, 2),)
    assert result.expected_session_labels == (
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
    )
    assert len(result.intervals) == 1


def test_native_session_equity_artifact_rejects_inferred_or_misbound_closes() -> None:
    reference, calendar, equity, closes, _sessions = _session_fixture()
    off_close = NautilusSessionCloseEquityObservation(
        session_label=closes[0].session_label,
        event_time_ns=closes[0].event_time_ns + 1_000,
        event_index=closes[0].event_index,
        account_equity=closes[0].account_equity,
        account_cash_balance=closes[0].account_cash_balance,
    )

    with pytest.raises(ValueError, match="frozen calendar"):
        build_nautilus_session_equity_intervals_artifact(
            reference,
            equity,
            (off_close, *closes[1:]),
            calendar=calendar,
            engine_evidence_digest=content_digest("engine evidence"),
            session_periods_per_year=252,
        )

    unaligned_reference = replace(reference, scoring_start_ns=reference.scoring_start_ns + 1_000)
    with pytest.raises(ValueError, match="actual session close"):
        build_nautilus_session_equity_intervals_artifact(
            unaligned_reference,
            equity,
            closes,
            calendar=calendar,
            engine_evidence_digest=content_digest("engine evidence"),
            session_periods_per_year=252,
        )


def test_runner_accepts_only_final_native_event_index_at_each_session_close() -> None:
    reference, calendar, _equity, closes, sessions = _session_fixture()
    expected_events = tuple(
        {
            "index": item.event_index,
            "event": {"event_time_ns": _unix_ns(sessions[index].close_time)},
        }
        for index, item in enumerate(closes, start=1)
    )
    encoded = [item.to_wire() for item in closes]

    assert (
        _read_session_close_equity_observations(
            encoded,
            calendar=calendar,
            session_periods_per_year=252,
            equity_reference=reference,
            expected_events=expected_events,
        )
        == closes
    )
    wrong_group_index = dict(encoded[0], event_index=closes[0].event_index - 1)
    with pytest.raises(ValueError, match="complete native event group"):
        _read_session_close_equity_observations(
            [wrong_group_index, *encoded[1:]],
            calendar=calendar,
            session_periods_per_year=252,
            equity_reference=reference,
            expected_events=expected_events,
        )
