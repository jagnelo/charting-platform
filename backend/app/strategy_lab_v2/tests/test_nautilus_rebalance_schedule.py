from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.nautilus_rebalance_schedule import (
    NAUTILUS_REBALANCE_AUDIT_SCHEMA,
    NautilusRebalanceScheduleAudit,
    NautilusRebalanceScheduleCursor,
    RebalanceBoundaryAction,
    RebalanceBoundaryPhase,
    RebalanceBoundaryReason,
    RebalanceExecutionStatus,
    RebalanceScheduleOutcome,
)
from app.strategy_lab_v2.rebalance import (
    RebalanceExecutionPlan,
    RebalanceMisfirePolicy,
    RebalanceTrigger,
    ScheduledRebalance,
)


def _ns(value: datetime) -> int:
    delta = value - datetime(1970, 1, 1, tzinfo=UTC)
    return ((delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds) * 1_000


def _occurrence(
    event_time: datetime,
    trigger: RebalanceTrigger,
    misfire_policy: RebalanceMisfirePolicy = RebalanceMisfirePolicy.FAIL_RUN,
) -> ScheduledRebalance:
    policy_fingerprint = content_digest("policy")
    calendar_fingerprint = content_digest("calendar")
    identity = {
        "policy_fingerprint": policy_fingerprint,
        "calendar_fingerprint": calendar_fingerprint,
        "session_id": f"XNYS:{event_time.date().isoformat()}",
        "session_label": event_time.date(),
        "event_time": event_time,
        "trigger": trigger,
        "cadence_period": f"session:{event_time.date().isoformat()}",
    }
    return ScheduledRebalance(
        occurrence_id=content_digest(identity),
        policy_fingerprint=policy_fingerprint,
        calendar_fingerprint=calendar_fingerprint,
        session_id=f"XNYS:{event_time.date().isoformat()}",
        session_label=event_time.date(),
        event_time=event_time,
        trigger=trigger,
        cadence_period=f"session:{event_time.date().isoformat()}",
        misfire_policy=misfire_policy,
    )


def _plan(*occurrences: ScheduledRebalance) -> RebalanceExecutionPlan:
    return RebalanceExecutionPlan(
        policy_fingerprint=content_digest("policy"),
        calendar_fingerprint=content_digest("calendar"),
        occurrences=tuple(sorted(occurrences, key=lambda item: item.event_time)),
    )


def test_open_occurrence_is_due_before_the_exact_event() -> None:
    boundary = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    plan = _plan(_occurrence(boundary, RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS))
    cursor = NautilusRebalanceScheduleCursor(plan)

    transition = cursor.before_event(_ns(boundary))

    assert len(transition) == 1
    assert transition[0].action is RebalanceBoundaryAction.APPLY_BEFORE_EVENT
    assert transition[0].phase is RebalanceBoundaryPhase.BEFORE_EVENT
    assert transition[0].reason is RebalanceBoundaryReason.EXACT_SESSION_OPEN
    assert transition[0].plan_fingerprint == plan.fingerprint
    assert transition[0].occurrence.occurrence_id == plan.occurrences[0].occurrence_id
    assert cursor.after_event_group(_ns(boundary), next_event_time_ns=None) == ()
    assert cursor.finish() == ()


def test_close_occurrence_waits_for_every_event_at_its_timestamp() -> None:
    boundary = datetime(2024, 1, 2, 21, 0, tzinfo=UTC)
    plan = _plan(_occurrence(boundary, RebalanceTrigger.SESSION_CLOSE_AFTER_EVENTS))
    cursor = NautilusRebalanceScheduleCursor(plan)

    assert cursor.before_event(_ns(boundary)) == ()
    assert cursor.before_event(_ns(boundary)) == ()
    with pytest.raises(ValueError, match="final callback"):
        cursor.after_event_group(_ns(boundary), next_event_time_ns=_ns(boundary))

    transition = cursor.after_event_group(
        _ns(boundary), next_event_time_ns=_ns(boundary + timedelta(seconds=1))
    )

    assert len(transition) == 1
    assert transition[0].action is RebalanceBoundaryAction.APPLY_AFTER_EVENT_GROUP
    assert transition[0].phase is RebalanceBoundaryPhase.AFTER_EVENT_GROUP
    assert transition[0].reason is RebalanceBoundaryReason.EXACT_SESSION_CLOSE
    assert cursor.finish() == ()


@pytest.mark.parametrize(
    ("policy", "expected"),
    (
        (RebalanceMisfirePolicy.FAIL_RUN, RebalanceBoundaryAction.FAIL_MISFIRE),
        (RebalanceMisfirePolicy.SKIP_OCCURRENCE, RebalanceBoundaryAction.SKIP_MISFIRE),
    ),
)
def test_event_after_boundary_applies_declared_misfire_policy(
    policy: RebalanceMisfirePolicy,
    expected: RebalanceBoundaryAction,
) -> None:
    boundary = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    occurrence = _occurrence(
        boundary,
        RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
        policy,
    )
    cursor = NautilusRebalanceScheduleCursor(_plan(occurrence))

    transition = cursor.before_event(_ns(boundary + timedelta(microseconds=1)))

    assert len(transition) == 1
    assert transition[0].action is expected
    assert transition[0].phase is RebalanceBoundaryPhase.BEFORE_EVENT
    assert transition[0].reason is RebalanceBoundaryReason.EVENT_AFTER_BOUNDARY
    assert transition[0].observed_event_time_ns == _ns(boundary + timedelta(microseconds=1))


@pytest.mark.parametrize(
    ("policy", "expected"),
    (
        (RebalanceMisfirePolicy.FAIL_RUN, RebalanceBoundaryAction.FAIL_MISFIRE),
        (RebalanceMisfirePolicy.SKIP_OCCURRENCE, RebalanceBoundaryAction.SKIP_MISFIRE),
    ),
)
def test_end_of_tape_classifies_unobserved_occurrences(
    policy: RebalanceMisfirePolicy,
    expected: RebalanceBoundaryAction,
) -> None:
    occurrence = _occurrence(
        datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
        RebalanceTrigger.SESSION_CLOSE_AFTER_EVENTS,
        policy,
    )
    cursor = NautilusRebalanceScheduleCursor(_plan(occurrence))

    transition = cursor.finish()

    assert len(transition) == 1
    assert transition[0].action is expected
    assert transition[0].phase is RebalanceBoundaryPhase.END_OF_TAPE
    assert transition[0].reason is RebalanceBoundaryReason.TAPE_ENDED_BEFORE_BOUNDARY
    assert transition[0].observed_event_time_ns is None


def test_cursor_rejects_non_monotonic_events_and_post_finish_calls() -> None:
    cursor = NautilusRebalanceScheduleCursor(_plan())
    cursor.before_event(100)

    with pytest.raises(ValueError, match="monotonic"):
        cursor.before_event(99)

    cursor.finish()
    with pytest.raises(RuntimeError, match="already finished"):
        cursor.before_event(101)


def test_rebalance_schedule_audit_is_plan_bound_and_content_addressed() -> None:
    boundary = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    plan = _plan(_occurrence(boundary, RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS))
    transition = NautilusRebalanceScheduleCursor(plan).before_event(_ns(boundary))[0]
    audit = NautilusRebalanceScheduleAudit(
        attempt_id="attempt-rebalance-audit",
        plan_fingerprint=plan.fingerprint,
        outcomes=(
            RebalanceScheduleOutcome(
                transition,
                RebalanceExecutionStatus.APPLIED_WITHOUT_CACHED_TARGETS,
                0,
            ),
        ),
    )

    wire = audit.to_wire()
    decoded = NautilusRebalanceScheduleAudit.from_wire(
        wire,
        attempt_id="attempt-rebalance-audit",
        plan=plan,
    )
    artifact_bytes = decoded.artifact_bytes()
    artifact = decoded.artifact_manifest()

    assert decoded == audit
    assert wire["schema"] == NAUTILUS_REBALANCE_AUDIT_SCHEMA
    assert artifact.content_digest == artifact_content_digest(artifact_bytes)
    assert artifact.byte_length == len(artifact_bytes)

    malformed = {
        **wire,
        "outcomes": [],
    }
    with pytest.raises(ValueError, match="cover every frozen occurrence"):
        NautilusRebalanceScheduleAudit.from_wire(
            malformed,
            attempt_id="attempt-rebalance-audit",
            plan=plan,
        )
