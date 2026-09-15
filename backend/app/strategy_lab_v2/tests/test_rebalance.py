from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.rebalance import (
    CalendarDay,
    CalendarDayStatus,
    CalendarRebalancePolicy,
    RebalanceCadence,
    RebalanceMisfirePolicy,
    RebalanceSelection,
    RebalanceTrigger,
    SessionCalendarSnapshot,
    SessionSegment,
    TradingSession,
    schedule_rebalances,
)

CALENDAR_ID = "XNYS"
TZ = ZoneInfo("America/New_York")


def _trading_day(
    label: date,
    *,
    open_local: datetime | None = None,
    close_local: datetime | None = None,
    segments_local: tuple[tuple[datetime, datetime], ...] | None = None,
) -> CalendarDay:
    if segments_local is None:
        segments_local = (
            (
                open_local or datetime(label.year, label.month, label.day, 9, 30, tzinfo=TZ),
                close_local or datetime(label.year, label.month, label.day, 16, 0, tzinfo=TZ),
            ),
        )
    session = TradingSession(
        session_id=f"XNYS:{label.isoformat()}",
        session_label=label,
        segments=tuple(SessionSegment(open_time, close_time) for open_time, close_time in segments_local),
    )
    return CalendarDay(label, CalendarDayStatus.TRADING, session)


def _calendar(
    start: date,
    end: date,
    sessions: dict[date, CalendarDay] | None = None,
    *,
    days: tuple[CalendarDay, ...] | None = None,
) -> SessionCalendarSnapshot:
    session_days = sessions or {}
    if days is None:
        values: list[CalendarDay] = []
        current = start
        while current <= end:
            values.append(
                session_days.get(
                    current,
                    CalendarDay(current, CalendarDayStatus.CLOSED),
                )
            )
            current += timedelta(days=1)
        days = tuple(values)
    return SessionCalendarSnapshot(
        calendar_id=CALENDAR_ID,
        definition_version="XNYS-reg-hours-v1",
        timezone_name="America/New_York",
        timezone_database_version="2024a-test-fixture",
        coverage_start=start,
        coverage_end=end,
        days=days,
        source_evidence_digest=content_digest("test-calendar-source-v1"),
    )


def _policy(
    calendar: SessionCalendarSnapshot,
    cadence: RebalanceCadence,
    trigger: RebalanceTrigger,
    *,
    selection: RebalanceSelection = RebalanceSelection.FIRST_SESSION,
    misfire: RebalanceMisfirePolicy = RebalanceMisfirePolicy.FAIL_RUN,
) -> CalendarRebalancePolicy:
    return CalendarRebalancePolicy(
        calendar_id=calendar.calendar_id,
        calendar_fingerprint=calendar.fingerprint,
        cadence=cadence,
        trigger=trigger,
        selection=selection,
        misfire_policy=misfire,
    )


def test_monthly_schedule_uses_first_actual_sessions_after_explicit_holidays() -> None:
    calendar = _calendar(
        date(2024, 1, 1),
        date(2024, 3, 31),
        {
            date(2024, 1, 2): _trading_day(date(2024, 1, 2)),
            date(2024, 1, 31): _trading_day(date(2024, 1, 31)),
            date(2024, 2, 1): _trading_day(date(2024, 2, 1)),
            date(2024, 2, 29): _trading_day(date(2024, 2, 29)),
            date(2024, 3, 1): _trading_day(date(2024, 3, 1)),
            date(2024, 3, 11): _trading_day(date(2024, 3, 11)),
        },
    )
    policy = _policy(
        calendar,
        RebalanceCadence.MONTHLY,
        RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
        misfire=RebalanceMisfirePolicy.SKIP_OCCURRENCE,
    )

    schedule = schedule_rebalances(
        calendar,
        policy,
        from_session_label=date(2024, 1, 1),
        through_session_label=date(2024, 3, 31),
    )

    assert [item.session_label for item in schedule] == [
        date(2024, 1, 2),
        date(2024, 2, 1),
        date(2024, 3, 1),
    ]
    assert [item.event_time for item in schedule] == [
        datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
        datetime(2024, 2, 1, 14, 30, tzinfo=UTC),
        datetime(2024, 3, 1, 14, 30, tzinfo=UTC),
    ]
    assert all(item.trigger is RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS for item in schedule)
    assert all(item.misfire_policy is RebalanceMisfirePolicy.SKIP_OCCURRENCE for item in schedule)
    assert schedule[0].occurrence_id == schedule_rebalances(
        calendar,
        policy,
        from_session_label=date(2024, 1, 1),
        through_session_label=date(2024, 3, 31),
    )[0].occurrence_id


def test_monthly_last_session_uses_early_close_and_close_after_all_segments() -> None:
    early_close = date(2024, 3, 28)
    early_close_day = _trading_day(
        early_close,
        close_local=datetime(2024, 3, 28, 13, 0, tzinfo=TZ),
    )
    lunch_break_day = _trading_day(
        date(2024, 3, 27),
        segments_local=(
            (datetime(2024, 3, 27, 9, 0, tzinfo=TZ), datetime(2024, 3, 27, 12, 0, tzinfo=TZ)),
            (datetime(2024, 3, 27, 13, 0, tzinfo=TZ), datetime(2024, 3, 27, 16, 0, tzinfo=TZ)),
        ),
    )
    calendar = _calendar(
        date(2024, 3, 1),
        date(2024, 3, 31),
        {
            date(2024, 3, 1): _trading_day(date(2024, 3, 1)),
            date(2024, 3, 27): lunch_break_day,
            early_close: early_close_day,
        },
    )
    policy = _policy(
        calendar,
        RebalanceCadence.MONTHLY,
        RebalanceTrigger.SESSION_CLOSE_AFTER_EVENTS,
        selection=RebalanceSelection.LAST_SESSION,
    )

    schedule = schedule_rebalances(
        calendar,
        policy,
        from_session_label=date(2024, 3, 1),
        through_session_label=date(2024, 3, 31),
    )

    assert len(schedule) == 1
    assert schedule[0].session_label == early_close
    assert schedule[0].event_time == datetime(2024, 3, 28, 17, 0, tzinfo=UTC)
    assert schedule[0].trigger is RebalanceTrigger.SESSION_CLOSE_AFTER_EVENTS


def test_weekly_uses_iso_labels_and_first_actual_session_after_new_year_holiday() -> None:
    calendar = _calendar(
        date(2023, 12, 25),
        date(2024, 1, 7),
        {
            date(2023, 12, 26): _trading_day(date(2023, 12, 26)),
            date(2023, 12, 29): _trading_day(date(2023, 12, 29)),
            date(2024, 1, 2): _trading_day(date(2024, 1, 2)),
            date(2024, 1, 5): _trading_day(date(2024, 1, 5)),
        },
    )
    schedule = schedule_rebalances(
        calendar,
        _policy(
            calendar,
            RebalanceCadence.ISO_WEEKLY,
            RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
        ),
        from_session_label=date(2023, 12, 25),
        through_session_label=date(2024, 1, 7),
    )

    assert [item.session_label for item in schedule] == [date(2023, 12, 26), date(2024, 1, 2)]
    assert [item.cadence_period for item in schedule] == ["iso-week:2023-W52", "iso-week:2024-W01"]


def test_quarterly_first_session_and_run_label_filter_do_not_catch_up() -> None:
    calendar = _calendar(
        date(2024, 1, 1),
        date(2024, 6, 30),
        {
            date(2024, 1, 2): _trading_day(date(2024, 1, 2)),
            date(2024, 3, 28): _trading_day(date(2024, 3, 28)),
            date(2024, 4, 1): _trading_day(date(2024, 4, 1)),
            date(2024, 6, 28): _trading_day(date(2024, 6, 28)),
        },
    )
    schedule = schedule_rebalances(
        calendar,
        _policy(
            calendar,
            RebalanceCadence.QUARTERLY,
            RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
        ),
        from_session_label=date(2024, 1, 3),
        through_session_label=date(2024, 6, 30),
    )

    assert [item.session_label for item in schedule] == [date(2024, 4, 1)]
    assert [item.cadence_period for item in schedule] == ["quarter:2024-Q2"]


def test_each_session_supports_overnight_labels_and_dst_resolved_utc_boundaries() -> None:
    label = date(2024, 3, 11)
    overnight = _trading_day(
        label,
        open_local=datetime(2024, 3, 10, 18, 0, tzinfo=TZ),
        close_local=datetime(2024, 3, 11, 17, 0, tzinfo=TZ),
    )
    calendar = _calendar(label, label, {label: overnight})
    policy = _policy(
        calendar,
        RebalanceCadence.EACH_SESSION,
        RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
    )
    schedule = schedule_rebalances(
        calendar,
        policy,
        from_session_label=label,
        through_session_label=label,
    )

    assert schedule[0].session_label == label
    assert schedule[0].event_time == datetime(2024, 3, 10, 22, 0, tzinfo=UTC)
    assert schedule[0].cadence_period == "session:2024-03-11"


def test_calendar_is_canonical_and_rejects_omitted_dates_and_stale_policy() -> None:
    start = date(2024, 1, 1)
    end = date(2024, 1, 31)
    complete = _calendar(
        start,
        end,
        {date(2024, 1, 2): _trading_day(date(2024, 1, 2))},
    )
    permuted = _calendar(start, end, days=tuple(reversed(complete.days)))
    assert permuted.fingerprint == complete.fingerprint

    with pytest.raises(ValueError, match="explicitly cover every date"):
        _calendar(start, end, days=complete.days[:-1])
    incomplete_calendar = _calendar(
        date(2024, 1, 2),
        end,
        {date(2024, 1, 2): _trading_day(date(2024, 1, 2))},
    )
    with pytest.raises(ValueError, match="complete cadence periods"):
        schedule_rebalances(
            incomplete_calendar,
            CalendarRebalancePolicy(
                calendar_id=CALENDAR_ID,
                calendar_fingerprint=incomplete_calendar.fingerprint,
                cadence=RebalanceCadence.MONTHLY,
                trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
            ),
            from_session_label=date(2024, 1, 2),
            through_session_label=end,
        )

    stale_policy = _policy(complete, RebalanceCadence.MONTHLY, RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS)
    with pytest.raises(ValueError, match="stale or mismatched"):
        schedule_rebalances(
            permuted,
            CalendarRebalancePolicy(
                calendar_id=stale_policy.calendar_id,
                calendar_fingerprint=content_digest("a-different-calendar"),
                cadence=stale_policy.cadence,
                trigger=stale_policy.trigger,
            ),
            from_session_label=start,
            through_session_label=end,
        )


def test_calendar_rejects_invalid_period_boundaries_and_malformed_segments() -> None:
    label = date(2024, 1, 2)
    with pytest.raises(ValueError, match="timezone-aware"):
        SessionSegment(datetime(2024, 1, 2, 9), datetime(2024, 1, 2, 16, tzinfo=UTC))

    with pytest.raises(ValueError, match="must not overlap"):
        TradingSession(
            "overlap",
            label,
            (
                SessionSegment(datetime(2024, 1, 2, 9, tzinfo=UTC), datetime(2024, 1, 2, 12, tzinfo=UTC)),
                SessionSegment(datetime(2024, 1, 2, 11, tzinfo=UTC), datetime(2024, 1, 2, 15, tzinfo=UTC)),
            ),
        )

    with pytest.raises(ValueError, match="must equal its calendar day label"):
        CalendarDay(label, CalendarDayStatus.TRADING, _trading_day(date(2024, 1, 3)).session)

    with pytest.raises(ValueError, match="does not accept a period selection"):
        CalendarRebalancePolicy(
            calendar_id=CALENDAR_ID,
            calendar_fingerprint=content_digest("calendar"),
            cadence=RebalanceCadence.EACH_SESSION,
            trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
            selection=RebalanceSelection.LAST_SESSION,
        )


def test_yearly_last_session_selects_from_a_complete_calendar_year() -> None:
    calendar = _calendar(
        date(2024, 1, 1),
        date(2024, 12, 31),
        {
            date(2024, 1, 2): _trading_day(date(2024, 1, 2)),
            date(2024, 12, 30): _trading_day(date(2024, 12, 30)),
            date(2024, 12, 31): _trading_day(date(2024, 12, 31)),
        },
    )
    schedule = schedule_rebalances(
        calendar,
        _policy(
            calendar,
            RebalanceCadence.YEARLY,
            RebalanceTrigger.SESSION_CLOSE_AFTER_EVENTS,
            selection=RebalanceSelection.LAST_SESSION,
        ),
        from_session_label=date(2024, 1, 1),
        through_session_label=date(2024, 12, 31),
    )

    assert [item.session_label for item in schedule] == [date(2024, 12, 31)]
    assert [item.cadence_period for item in schedule] == ["year:2024"]


def test_rebalance_policy_semantics_are_explicitly_versioned() -> None:
    calendar = _calendar(
        date(2024, 1, 1),
        date(2024, 1, 31),
        {date(2024, 1, 2): _trading_day(date(2024, 1, 2))},
    )
    policy = _policy(
        calendar,
        RebalanceCadence.MONTHLY,
        RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
    )

    assert policy.definition_version == "strategy-lab.rebalance-policy.v1"
    assert policy.fingerprint == content_digest(policy)
