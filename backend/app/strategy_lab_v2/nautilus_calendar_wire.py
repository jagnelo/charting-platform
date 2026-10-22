"""Strict, fingerprint-checked wire codec for frozen session calendars."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.strategy_lab_v2.rebalance import (
    CalendarDay,
    CalendarDayStatus,
    SessionCalendarSnapshot,
    SessionSegment,
    TradingSession,
)

NAUTILUS_SESSION_CALENDAR_WIRE_SCHEMA = "strategy-lab.nautilus-session-calendar.v1"


def session_calendar_to_wire(calendar: SessionCalendarSnapshot | None) -> dict[str, Any] | None:
    if calendar is None:
        return None
    if not isinstance(calendar, SessionCalendarSnapshot):
        raise TypeError("calendar must be a SessionCalendarSnapshot or None")
    return {
        "schema": NAUTILUS_SESSION_CALENDAR_WIRE_SCHEMA,
        "calendar_id": calendar.calendar_id,
        "definition_version": calendar.definition_version,
        "timezone_name": calendar.timezone_name,
        "timezone_database_version": calendar.timezone_database_version,
        "coverage_start": calendar.coverage_start.isoformat(),
        "coverage_end": calendar.coverage_end.isoformat(),
        "source_evidence_digest": calendar.source_evidence_digest,
        "days": [
            {
                "label": day.label.isoformat(),
                "status": day.status.value,
                "session": (
                    None
                    if day.session is None
                    else {
                        "session_id": day.session.session_id,
                        "session_label": day.session.session_label.isoformat(),
                        "segments": [
                            {
                                "open_time_ns": _timestamp_ns(segment.open_time),
                                "close_time_ns": _timestamp_ns(segment.close_time),
                            }
                            for segment in day.session.segments
                        ],
                    }
                ),
            }
            for day in calendar.days
        ],
        "fingerprint": calendar.fingerprint,
    }


def session_calendar_from_wire(value: object) -> SessionCalendarSnapshot | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "calendar_id",
        "definition_version",
        "timezone_name",
        "timezone_database_version",
        "coverage_start",
        "coverage_end",
        "source_evidence_digest",
        "days",
        "fingerprint",
    }:
        raise ValueError("session calendar wire fields are invalid")
    if value["schema"] != NAUTILUS_SESSION_CALENDAR_WIRE_SCHEMA:
        raise ValueError("session calendar wire schema is unsupported")
    raw_days = value["days"]
    if not isinstance(raw_days, list):
        raise ValueError("session calendar days must be a list")
    days: list[CalendarDay] = []
    for raw_day in raw_days:
        if not isinstance(raw_day, Mapping) or set(raw_day) != {"label", "status", "session"}:
            raise ValueError("session calendar day fields are invalid")
        label = _date(raw_day["label"], "calendar day label")
        status = CalendarDayStatus(_text(raw_day["status"], "calendar day status"))
        raw_session = raw_day["session"]
        session = None
        if raw_session is not None:
            if not isinstance(raw_session, Mapping) or set(raw_session) != {
                "session_id",
                "session_label",
                "segments",
            }:
                raise ValueError("session calendar trading session fields are invalid")
            raw_segments = raw_session["segments"]
            if not isinstance(raw_segments, list) or not raw_segments:
                raise ValueError("session calendar segments must be a non-empty list")
            segments: list[SessionSegment] = []
            for raw_segment in raw_segments:
                if not isinstance(raw_segment, Mapping) or set(raw_segment) != {
                    "open_time_ns",
                    "close_time_ns",
                }:
                    raise ValueError("session calendar segment fields are invalid")
                segments.append(
                    SessionSegment(
                        _datetime_from_ns(raw_segment["open_time_ns"]),
                        _datetime_from_ns(raw_segment["close_time_ns"]),
                    )
                )
            session = TradingSession(
                session_id=_text(raw_session["session_id"], "session_id"),
                session_label=_date(raw_session["session_label"], "session_label"),
                segments=tuple(segments),
            )
        days.append(CalendarDay(label=label, status=status, session=session))
    calendar = SessionCalendarSnapshot(
        calendar_id=_text(value["calendar_id"], "calendar_id"),
        definition_version=_text(value["definition_version"], "definition_version"),
        timezone_name=_text(value["timezone_name"], "timezone_name"),
        timezone_database_version=_text(
            value["timezone_database_version"], "timezone_database_version"
        ),
        coverage_start=_date(value["coverage_start"], "coverage_start"),
        coverage_end=_date(value["coverage_end"], "coverage_end"),
        days=tuple(days),
        source_evidence_digest=_text(value["source_evidence_digest"], "source_evidence_digest"),
    )
    if value["fingerprint"] != calendar.fingerprint:
        raise ValueError("session calendar fingerprint differs from its wire content")
    return calendar


def _timestamp_ns(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = normalized - epoch
    result = (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000
    if result < 0:
        raise ValueError("session calendar timestamps before the Nautilus epoch are unsupported")
    return result


def _datetime_from_ns(value: object) -> datetime:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value % 1_000:
        raise ValueError("session calendar timestamps must be microsecond-aligned nanoseconds")
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=value // 1_000)


def _date(value: object, field_name: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be canonical ISO date text")
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError(f"{field_name} is not canonical ISO date text")
    return result


def _text(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(character in value for character in "\x00\r\n")
    ):
        raise ValueError(f"{field_name} must be non-empty control-free text")
    return value


__all__ = [
    "NAUTILUS_SESSION_CALENDAR_WIRE_SCHEMA",
    "session_calendar_from_wire",
    "session_calendar_to_wire",
]
