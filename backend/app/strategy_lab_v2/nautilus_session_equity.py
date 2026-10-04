"""Exact native session-close marks and persisted OOS equity intervals.

Session marks are accepted only from a native runtime callback after a complete
same-timestamp event group. This module never interpolates or carries a mark
forward to manufacture a missing close.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.nautilus_equity_trace import (
    NautilusAccountEquityObservation,
    NautilusAccountEquityTraceReference,
)
from app.strategy_lab_v2.observations import (
    AccountEquityIntervalObservation,
    ExternalCashFlowReportStatus,
    ObservationPoint,
)
from app.strategy_lab_v2.rebalance import SessionCalendarSnapshot

NAUTILUS_SESSION_EQUITY_INTERVALS_MEDIA_TYPE = (
    "application/vnd.charting.strategy-lab.nautilus-session-equity-intervals+json"
)
NAUTILUS_SESSION_EQUITY_INTERVALS_SCHEMA = "strategy-lab.nautilus.session-equity-intervals.v1"
_MAX_SESSION_CLOSE_OBSERVATIONS = 100_000


def _positive_integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _timestamp_ns(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = normalized - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


def _datetime_from_ns(value: int) -> datetime:
    if value < 0 or value % 1_000:
        raise ValueError("session-close timestamps must be non-negative microsecond instants")
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=value // 1_000)


@dataclass(frozen=True, slots=True, order=True)
class NautilusSessionCloseEquityObservation:
    """One native account valuation sampled after all callbacks at a session close."""

    session_label: date
    event_time_ns: int
    event_index: int
    account_equity: Decimal
    account_cash_balance: Decimal

    def __post_init__(self) -> None:
        if type(self.session_label) is not date:
            raise TypeError("session_label must be a date, not a datetime")
        for name in ("event_time_ns", "event_index"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.account_equity, Decimal) or not self.account_equity.is_finite():
            raise ValueError("account_equity must be a finite Decimal")
        if self.account_equity < 0:
            raise ValueError("account_equity must be non-negative")
        if (
            not isinstance(self.account_cash_balance, Decimal)
            or not self.account_cash_balance.is_finite()
        ):
            raise ValueError("account_cash_balance must be a finite Decimal")

    @classmethod
    def from_wire(cls, value: object) -> NautilusSessionCloseEquityObservation:
        if not isinstance(value, Mapping) or set(value) != {
            "session_label",
            "event_time_ns",
            "event_index",
            "account_equity",
            "account_cash_balance",
        }:
            raise ValueError("Nautilus session-close equity fields are invalid")
        label_text = value["session_label"]
        if not isinstance(label_text, str):
            raise ValueError("session-close session_label must be canonical text")
        label = date.fromisoformat(label_text)
        if label.isoformat() != label_text:
            raise ValueError("session-close session_label is not canonical")
        try:
            return cls(
                session_label=label,
                event_time_ns=value["event_time_ns"],
                event_index=value["event_index"],
                account_equity=Decimal(value["account_equity"]),
                account_cash_balance=Decimal(value["account_cash_balance"]),
            )
        except (ArithmeticError, TypeError, ValueError) as error:
            raise ValueError("Nautilus session-close equity observation is invalid") from error

    def to_wire(self) -> dict[str, object]:
        return {
            "session_label": self.session_label.isoformat(),
            "event_time_ns": self.event_time_ns,
            "event_index": self.event_index,
            "account_equity": format(self.account_equity, "f"),
            "account_cash_balance": format(self.account_cash_balance, "f"),
        }


@dataclass(frozen=True, slots=True)
class NautilusSessionEquityIntervalsArtifact:
    """Deterministic persisted interval bytes plus the metrics-ready observations."""

    artifact: ArtifactManifest
    payload: bytes
    intervals: tuple[AccountEquityIntervalObservation, ...]
    expected_session_labels: tuple[date, ...]
    observed_session_labels: tuple[date, ...]
    session_periods_per_year: int

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactManifest):
            raise TypeError("artifact must be an ArtifactManifest")
        if (
            self.artifact.media_type != NAUTILUS_SESSION_EQUITY_INTERVALS_MEDIA_TYPE
            or self.artifact.schema_version != NAUTILUS_SESSION_EQUITY_INTERVALS_SCHEMA
            or self.artifact.retention_class is not ArtifactRetention.PINNED_RESULT
        ):
            raise ValueError("session interval artifact identity is unsupported")
        if not isinstance(self.payload, bytes) or len(self.payload) != self.artifact.byte_length:
            raise ValueError("session interval payload length differs from its artifact")
        digest = f"sha256:{hashlib.sha256(self.payload).hexdigest()}"
        if digest != self.artifact.content_digest:
            raise ValueError("session interval payload digest differs from its artifact")
        intervals = tuple(self.intervals)
        expected = tuple(self.expected_session_labels)
        observed = tuple(self.observed_session_labels)
        if any(not isinstance(item, AccountEquityIntervalObservation) for item in intervals):
            raise TypeError("intervals must contain AccountEquityIntervalObservation values")
        if any(type(item) is not date for item in (*expected, *observed)):
            raise TypeError("session labels must be dates")
        if tuple(item.session_label for item in intervals) != observed:
            raise ValueError("observed session labels differ from the persisted intervals")
        if tuple(sorted(set(expected))) != expected or tuple(sorted(set(observed))) != observed:
            raise ValueError("session labels must be unique and chronologically ordered")
        if any(label not in expected for label in observed):
            raise ValueError("observed session labels must belong to the expected range")
        _positive_integer(self.session_periods_per_year, "session_periods_per_year")
        object.__setattr__(self, "intervals", intervals)
        object.__setattr__(self, "expected_session_labels", expected)
        object.__setattr__(self, "observed_session_labels", observed)


def build_nautilus_session_equity_intervals_artifact(
    reference: NautilusAccountEquityTraceReference,
    equity_observations: Iterable[NautilusAccountEquityObservation],
    session_close_observations: Iterable[NautilusSessionCloseEquityObservation],
    *,
    calendar: SessionCalendarSnapshot,
    engine_evidence_digest: str,
    session_periods_per_year: int,
) -> NautilusSessionEquityIntervalsArtifact:
    """Bind exact native closes to consecutive OOS intervals and immutable bytes.

    The OOS opening valuation must coincide with a declared prior session close.
    A close sample is accepted only when its UTC instant exactly equals the
    calendar boundary and its producer reports the final event index in that
    same-time native event group. Gaps are recorded, never bridged.
    """

    if not isinstance(reference, NautilusAccountEquityTraceReference):
        raise TypeError("reference must be a NautilusAccountEquityTraceReference")
    if not isinstance(calendar, SessionCalendarSnapshot):
        raise TypeError("calendar must be a SessionCalendarSnapshot")
    if reference.scoring_start_ns is None or reference.scoring_end_ns is None:
        raise ValueError("session equity intervals require a bounded OOS trace")
    require_sha256_digest(engine_evidence_digest, field_name="engine_evidence_digest")
    periods_per_year = _positive_integer(session_periods_per_year, "session_periods_per_year")

    sessions_by_label = {day.label: day.session for day in calendar.days if day.session is not None}
    opening_label = next(
        (
            label
            for label, session in sessions_by_label.items()
            if _timestamp_ns(session.close_time) == reference.scoring_start_ns
        ),
        None,
    )
    if opening_label is None:
        raise ValueError("OOS opening valuation must equal an actual session close")
    expected_labels = tuple(
        label
        for label, session in sorted(sessions_by_label.items())
        if label > opening_label
        and reference.scoring_start_ns
        < _timestamp_ns(session.close_time)
        < reference.scoring_end_ns
    )
    opening: NautilusAccountEquityObservation | None = None
    observed_equity_count = 0
    for equity_observation in equity_observations:
        if not isinstance(equity_observation, NautilusAccountEquityObservation):
            raise TypeError("equity_observations must contain verified native observations")
        observed_equity_count += 1
        if equity_observation.event_time_ns == reference.scoring_start_ns and opening is None:
            opening = equity_observation
    if observed_equity_count != reference.observation_count:
        raise ValueError("verified OOS equity observations differ from their trace receipt")
    if opening is None:
        raise ValueError("native OOS trace omitted the exact opening session-close valuation")

    closes = tuple(session_close_observations)
    if len(closes) > _MAX_SESSION_CLOSE_OBSERVATIONS:
        raise ValueError("native session-close observations exceed their count bound")
    close_by_label: dict[date, NautilusSessionCloseEquityObservation] = {}
    prior_time_ns = reference.scoring_start_ns
    prior_index = opening.event_index
    expected_by_label = set(expected_labels)
    for close_observation in closes:
        if not isinstance(close_observation, NautilusSessionCloseEquityObservation):
            raise TypeError("session_close_observations must contain typed native observations")
        session = sessions_by_label.get(close_observation.session_label)
        if (
            session is None
            or close_observation.session_label not in expected_by_label
            or close_observation.event_time_ns != _timestamp_ns(session.close_time)
        ):
            raise ValueError("native session-close observation differs from the frozen calendar")
        if close_observation.session_label in close_by_label:
            raise ValueError("native session-close observations repeat a calendar session")
        if (
            close_observation.event_time_ns <= prior_time_ns
            or close_observation.event_index <= prior_index
        ):
            raise ValueError("native session-close observations are not in event order")
        close_by_label[close_observation.session_label] = close_observation
        prior_time_ns = close_observation.event_time_ns
        prior_index = close_observation.event_index

    intervals: list[AccountEquityIntervalObservation] = []
    previous_label = opening_label
    previous_time_ns = reference.scoring_start_ns
    previous_index = opening.event_index
    previous_equity = opening.account_equity
    for label in expected_labels:
        close = close_by_label.get(label)
        if close is None:
            previous_label = label
            previous_time_ns = _timestamp_ns(sessions_by_label[label].close_time)
            previous_index = -1
            previous_equity = Decimal(0)
            continue
        if previous_index >= 0 and previous_label in sessions_by_label:
            intervals.append(
                AccountEquityIntervalObservation(
                    portfolio_fingerprint=reference.portfolio_fingerprint,
                    run_attempt_id=reference.attempt_id,
                    calendar_fingerprint=calendar.fingerprint,
                    session_label=label,
                    start_point=ObservationPoint(
                        _datetime_from_ns(previous_time_ns), previous_index
                    ),
                    end_point=ObservationPoint(
                        _datetime_from_ns(close.event_time_ns), close.event_index
                    ),
                    starting_equity=previous_equity,
                    ending_equity=close.account_equity,
                    external_cash_flow=Decimal(0),
                    external_cash_flow_occurred=False,
                    external_cash_flow_report_status=ExternalCashFlowReportStatus.COMPLETE,
                    base_currency=reference.base_currency,
                    engine_evidence_digest=engine_evidence_digest,
                )
            )
        previous_label = label
        previous_time_ns = close.event_time_ns
        previous_index = close.event_index
        previous_equity = close.account_equity
    observed_labels = tuple(item.session_label for item in intervals)
    payload_value = {
        "schema": NAUTILUS_SESSION_EQUITY_INTERVALS_SCHEMA,
        "trial_id": reference.trial_id,
        "attempt_id": reference.attempt_id,
        "portfolio_fingerprint": reference.portfolio_fingerprint,
        "snapshot_fingerprint": reference.snapshot_fingerprint,
        "source_tape_fingerprint": reference.source_tape_fingerprint,
        "evaluation_window_fingerprint": reference.evaluation_window_fingerprint,
        "scoring_start_ns": reference.scoring_start_ns,
        "scoring_end_ns": reference.scoring_end_ns,
        "calendar_id": calendar.calendar_id,
        "calendar_fingerprint": calendar.fingerprint,
        "engine_evidence_digest": engine_evidence_digest,
        "base_currency": reference.base_currency,
        "session_periods_per_year": periods_per_year,
        "sampling_convention": "post_event_group_at_exact_calendar_session_close",
        "external_cash_flow_policy": "strategy_sdk_orders_only_no_external_cash_flows",
        "expected_session_labels": [item.isoformat() for item in expected_labels],
        "observed_session_labels": [item.isoformat() for item in observed_labels],
        "missing_session_labels": [
            item.isoformat() for item in expected_labels if item not in set(observed_labels)
        ],
        "intervals": [
            {
                "session_label": item.session_label.isoformat(),
                "start_time_ns": _timestamp_ns(item.start_point.event_time),
                "start_event_index": item.start_point.event_sequence,
                "end_time_ns": _timestamp_ns(item.end_point.event_time),
                "end_event_index": item.end_point.event_sequence,
                "starting_equity": format(item.starting_equity, "f"),
                "ending_equity": format(item.ending_equity, "f"),
                "external_cash_flow": "0",
                "external_cash_flow_report_status": "complete",
                "base_currency": item.base_currency,
                "engine_evidence_digest": item.engine_evidence_digest,
            }
            for item in intervals
        ],
    }
    payload = json.dumps(
        payload_value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    artifact = ArtifactManifest(
        content_digest=digest,
        byte_length=len(payload),
        media_type=NAUTILUS_SESSION_EQUITY_INTERVALS_MEDIA_TYPE,
        schema_version=NAUTILUS_SESSION_EQUITY_INTERVALS_SCHEMA,
        storage_key=digest,
        retention_class=ArtifactRetention.PINNED_RESULT,
    )
    return NautilusSessionEquityIntervalsArtifact(
        artifact=artifact,
        payload=payload,
        intervals=tuple(intervals),
        expected_session_labels=expected_labels,
        observed_session_labels=observed_labels,
        session_periods_per_year=periods_per_year,
    )


__all__ = [
    "NAUTILUS_SESSION_EQUITY_INTERVALS_MEDIA_TYPE",
    "NAUTILUS_SESSION_EQUITY_INTERVALS_SCHEMA",
    "NautilusSessionCloseEquityObservation",
    "NautilusSessionEquityIntervalsArtifact",
    "build_nautilus_session_equity_intervals_artifact",
]
