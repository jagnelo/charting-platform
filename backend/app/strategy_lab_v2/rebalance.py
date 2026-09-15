"""Immutable venue calendars and deterministic portfolio rebalance schedules.

This module defines schedule semantics only. It does not fetch calendars, infer
holidays, size orders, or assert that an engine can fill at a scheduled instant.
Calendar dates, closures, and UTC session segments are explicit input evidence.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _date(value: date, field_name: str) -> None:
    if type(value) is not date:
        raise TypeError(f"{field_name} must be a date, not a datetime")


class CalendarDayStatus(StrEnum):
    TRADING = "trading"
    CLOSED = "closed"


class RebalanceCadence(StrEnum):
    EACH_SESSION = "each_session"
    ISO_WEEKLY = "iso_weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class RebalanceSelection(StrEnum):
    FIRST_SESSION = "first_session"
    LAST_SESSION = "last_session"


class RebalanceTrigger(StrEnum):
    SESSION_OPEN_BEFORE_EVENTS = "session_open_before_events"
    SESSION_CLOSE_AFTER_EVENTS = "session_close_after_events"


class RebalanceMisfirePolicy(StrEnum):
    FAIL_RUN = "fail_run"
    SKIP_OCCURRENCE = "skip_occurrence"


@dataclass(frozen=True, slots=True)
class SessionSegment:
    """A half-open tradable interval; breaks are represented by multiple segments."""

    open_time: datetime
    close_time: datetime

    def __post_init__(self) -> None:
        for name in ("open_time", "close_time"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            object.__setattr__(self, name, value.astimezone(UTC))
        if self.close_time <= self.open_time:
            raise ValueError("session segment close_time must be after open_time")


@dataclass(frozen=True, slots=True)
class TradingSession:
    """One official venue session labeled by its trading date.

    The venue label may differ from the open/close civil date for an overnight
    session. UTC segment boundaries preserve DST and early-close behavior without
    converting local wall times during strategy execution.
    """

    session_id: str
    session_label: date
    segments: tuple[SessionSegment, ...]

    def __post_init__(self) -> None:
        _nonempty(self.session_id, "session_id")
        _date(self.session_label, "session_label")
        segments = tuple(self.segments)
        if not segments:
            raise ValueError("a trading session must contain at least one segment")
        if any(not isinstance(item, SessionSegment) for item in segments):
            raise TypeError("segments must contain SessionSegment values")
        segments = tuple(sorted(segments, key=lambda item: item.open_time))
        for previous, current in zip(segments, segments[1:]):
            if current.open_time < previous.close_time:
                raise ValueError("session segments must not overlap")
        object.__setattr__(self, "segments", segments)

    @property
    def open_time(self) -> datetime:
        return self.segments[0].open_time

    @property
    def close_time(self) -> datetime:
        return self.segments[-1].close_time


@dataclass(frozen=True, slots=True)
class CalendarDay:
    """An explicit local calendar label, including explicit closed dates."""

    label: date
    status: CalendarDayStatus
    session: TradingSession | None = None

    def __post_init__(self) -> None:
        _date(self.label, "label")
        if not isinstance(self.status, CalendarDayStatus):
            raise TypeError("status must be a CalendarDayStatus")
        if self.status is CalendarDayStatus.TRADING:
            if not isinstance(self.session, TradingSession):
                raise TypeError("trading calendar days require a TradingSession")
            if self.session.session_label != self.label:
                raise ValueError("session label must equal its calendar day label")
        elif self.session is not None:
            raise ValueError("closed calendar days must not include a session")


@dataclass(frozen=True, slots=True)
class SessionCalendarSnapshot:
    """A complete, content-addressed calendar slice for one market definition."""

    calendar_id: str
    definition_version: str
    timezone_name: str
    timezone_database_version: str
    coverage_start: date
    coverage_end: date
    days: tuple[CalendarDay, ...]
    source_evidence_digest: str

    def __post_init__(self) -> None:
        for name in (
            "calendar_id",
            "definition_version",
            "timezone_name",
            "timezone_database_version",
        ):
            _nonempty(getattr(self, name), name)
        _date(self.coverage_start, "coverage_start")
        _date(self.coverage_end, "coverage_end")
        if self.coverage_end < self.coverage_start:
            raise ValueError("calendar coverage_end must not precede coverage_start")
        require_sha256_digest(
            self.source_evidence_digest,
            field_name="source_evidence_digest",
        )
        days = tuple(self.days)
        if any(not isinstance(item, CalendarDay) for item in days):
            raise TypeError("days must contain CalendarDay values")
        days = tuple(sorted(days, key=lambda item: item.label))
        expected_count = (self.coverage_end - self.coverage_start).days + 1
        if len(days) != expected_count:
            raise ValueError("calendar must explicitly cover every date in its inclusive range")
        expected_label = self.coverage_start
        for item in days:
            if item.label != expected_label:
                raise ValueError("calendar days must be unique and contiguous across coverage")
            expected_label += timedelta(days=1)
        sessions = [item.session for item in days if item.session is not None]
        identifiers = [item.session_id for item in sessions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("session ids must be unique within a calendar")
        segments = sorted(
            (segment for session in sessions for segment in session.segments),
            key=lambda item: item.open_time,
        )
        for previous, current in zip(segments, segments[1:]):
            if current.open_time < previous.close_time:
                raise ValueError("sessions in one calendar must not overlap in UTC time")
        object.__setattr__(self, "days", days)

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "schema": "strategy-lab.session-calendar.v1",
                "calendar_id": self.calendar_id,
                "definition_version": self.definition_version,
                "timezone_name": self.timezone_name,
                "timezone_database_version": self.timezone_database_version,
                "coverage_start": self.coverage_start,
                "coverage_end": self.coverage_end,
                "days": self.days,
                "source_evidence_digest": self.source_evidence_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class CalendarRebalancePolicy:
    """A cadence and event-boundary rule pinned to one calendar version."""

    calendar_id: str
    calendar_fingerprint: str
    cadence: RebalanceCadence
    trigger: RebalanceTrigger
    selection: RebalanceSelection = RebalanceSelection.FIRST_SESSION
    misfire_policy: RebalanceMisfirePolicy = RebalanceMisfirePolicy.FAIL_RUN
    definition_version: str = "strategy-lab.rebalance-policy.v1"

    def __post_init__(self) -> None:
        _nonempty(self.calendar_id, "calendar_id")
        _nonempty(self.definition_version, "definition_version")
        require_sha256_digest(self.calendar_fingerprint, field_name="calendar_fingerprint")
        if not isinstance(self.cadence, RebalanceCadence):
            raise TypeError("cadence must be a RebalanceCadence")
        if not isinstance(self.trigger, RebalanceTrigger):
            raise TypeError("trigger must be a RebalanceTrigger")
        if not isinstance(self.selection, RebalanceSelection):
            raise TypeError("selection must be a RebalanceSelection")
        if not isinstance(self.misfire_policy, RebalanceMisfirePolicy):
            raise TypeError("misfire_policy must be a RebalanceMisfirePolicy")
        if (
            self.cadence is RebalanceCadence.EACH_SESSION
            and self.selection is not RebalanceSelection.FIRST_SESSION
        ):
            raise ValueError("each-session cadence does not accept a period selection rule")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ScheduledRebalance:
    """A deterministic decision boundary, not an order or fill instruction."""

    occurrence_id: str
    policy_fingerprint: str
    calendar_fingerprint: str
    session_id: str
    session_label: date
    event_time: datetime
    trigger: RebalanceTrigger
    cadence_period: str
    misfire_policy: RebalanceMisfirePolicy

    def __post_init__(self) -> None:
        for name in ("occurrence_id", "policy_fingerprint", "calendar_fingerprint"):
            require_sha256_digest(getattr(self, name), field_name=name)
        _nonempty(self.session_id, "session_id")
        _date(self.session_label, "session_label")
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        if not isinstance(self.trigger, RebalanceTrigger):
            raise TypeError("trigger must be a RebalanceTrigger")
        if not isinstance(self.misfire_policy, RebalanceMisfirePolicy):
            raise TypeError("misfire_policy must be a RebalanceMisfirePolicy")
        _nonempty(self.cadence_period, "cadence_period")


def _period_key(value: date, cadence: RebalanceCadence) -> str:
    if cadence is RebalanceCadence.EACH_SESSION:
        return f"session:{value.isoformat()}"
    if cadence is RebalanceCadence.ISO_WEEKLY:
        iso_year, iso_week, _ = value.isocalendar()
        return f"iso-week:{iso_year:04d}-W{iso_week:02d}"
    if cadence is RebalanceCadence.MONTHLY:
        return f"month:{value.year:04d}-{value.month:02d}"
    if cadence is RebalanceCadence.QUARTERLY:
        quarter = (value.month - 1) // 3 + 1
        return f"quarter:{value.year:04d}-Q{quarter}"
    if cadence is RebalanceCadence.YEARLY:
        return f"year:{value.year:04d}"
    raise ValueError(f"unsupported rebalance cadence: {cadence!r}")


def _period_start(value: date, cadence: RebalanceCadence) -> date:
    if cadence is RebalanceCadence.ISO_WEEKLY:
        return value - timedelta(days=value.isoweekday() - 1)
    if cadence is RebalanceCadence.MONTHLY:
        return date(value.year, value.month, 1)
    if cadence is RebalanceCadence.QUARTERLY:
        month = ((value.month - 1) // 3) * 3 + 1
        return date(value.year, month, 1)
    if cadence is RebalanceCadence.YEARLY:
        return date(value.year, 1, 1)
    return value


def _period_end(value: date, cadence: RebalanceCadence) -> date:
    if cadence is RebalanceCadence.ISO_WEEKLY:
        return _period_start(value, cadence) + timedelta(days=6)
    if cadence is RebalanceCadence.MONTHLY:
        return date(value.year, value.month, monthrange(value.year, value.month)[1])
    if cadence is RebalanceCadence.QUARTERLY:
        first = _period_start(value, cadence)
        last_month = first.month + 2
        return date(first.year, last_month, monthrange(first.year, last_month)[1])
    if cadence is RebalanceCadence.YEARLY:
        return date(value.year, 12, 31)
    return value


def _require_complete_period_coverage(
    calendar: SessionCalendarSnapshot,
    cadence: RebalanceCadence,
) -> None:
    if cadence is RebalanceCadence.EACH_SESSION:
        return
    if (
        calendar.coverage_start != _period_start(calendar.coverage_start, cadence)
        or calendar.coverage_end != _period_end(calendar.coverage_end, cadence)
    ):
        raise ValueError(
            "calendar coverage must include complete cadence periods so omitted sessions "
            "cannot be mistaken for holidays"
        )


def schedule_rebalances(
    calendar: SessionCalendarSnapshot,
    policy: CalendarRebalancePolicy,
    *,
    from_session_label: date,
    through_session_label: date,
) -> tuple[ScheduledRebalance, ...]:
    """Select deterministic calendar occurrences in an inclusive label range.

    Weekly buckets use ISO Monday-Sunday labels. Monthly, quarterly, and yearly
    buckets use venue-assigned session labels. Selection is among actual trading
    sessions after complete calendar-day coverage is verified. Holidays and
    weekends are explicit closed days; no session is shifted into another period.

    Open triggers occur before all events in that session; close triggers occur
    after all segments/events. The future engine adapter must map these UTC
    boundaries onto canonical event availability, apply the declared misfire
    policy, and enforce its own order/fill semantics. This planner never implies
    that an order fills at the open or close price.
    """

    if not isinstance(calendar, SessionCalendarSnapshot):
        raise TypeError("calendar must be a SessionCalendarSnapshot")
    if not isinstance(policy, CalendarRebalancePolicy):
        raise TypeError("policy must be a CalendarRebalancePolicy")
    _date(from_session_label, "from_session_label")
    _date(through_session_label, "through_session_label")
    if policy.calendar_id != calendar.calendar_id:
        raise ValueError("rebalance policy calendar_id does not match the supplied calendar")
    if policy.calendar_fingerprint != calendar.fingerprint:
        raise ValueError("rebalance policy calendar fingerprint is stale or mismatched")
    if from_session_label > through_session_label:
        raise ValueError("from_session_label must not follow through_session_label")
    if (
        from_session_label < calendar.coverage_start
        or through_session_label > calendar.coverage_end
    ):
        raise ValueError("requested rebalance range is outside calendar coverage")
    _require_complete_period_coverage(calendar, policy.cadence)

    sessions_by_period: dict[str, list[TradingSession]] = {}
    for day in calendar.days:
        if day.session is not None:
            period = _period_key(day.label, policy.cadence)
            sessions_by_period.setdefault(period, []).append(day.session)

    selected: list[tuple[str, TradingSession]] = []
    if policy.cadence is RebalanceCadence.EACH_SESSION:
        selected = [
            (period, sessions[0])
            for period, sessions in sessions_by_period.items()
        ]
    else:
        for period, sessions in sessions_by_period.items():
            session = (
                sessions[0]
                if policy.selection is RebalanceSelection.FIRST_SESSION
                else sessions[-1]
            )
            selected.append((period, session))
    selected.sort(key=lambda item: item[1].session_label)

    scheduled: list[ScheduledRebalance] = []
    for period, session in selected:
        if not (from_session_label <= session.session_label <= through_session_label):
            continue
        event_time = (
            session.open_time
            if policy.trigger is RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS
            else session.close_time
        )
        identity = {
            "policy_fingerprint": policy.fingerprint,
            "calendar_fingerprint": calendar.fingerprint,
            "session_id": session.session_id,
            "session_label": session.session_label,
            "event_time": event_time,
            "trigger": policy.trigger,
            "cadence_period": period,
        }
        scheduled.append(
            ScheduledRebalance(
                occurrence_id=content_digest(identity),
                policy_fingerprint=policy.fingerprint,
                calendar_fingerprint=calendar.fingerprint,
                session_id=session.session_id,
                session_label=session.session_label,
                event_time=event_time,
                trigger=policy.trigger,
                cadence_period=period,
                misfire_policy=policy.misfire_policy,
            )
        )
    return tuple(scheduled)
