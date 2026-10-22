"""Deterministic event-boundary scheduling for frozen Nautilus rebalance plans.

This module only binds planned occurrences to the authenticated native event
sequence. It does not read calendars, inspect prices, allocate targets, or
submit orders; the native callback adapter owns those operations.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.rebalance import (
    RebalanceExecutionPlan,
    RebalanceMisfirePolicy,
    RebalanceTrigger,
    ScheduledRebalance,
)

NAUTILUS_REBALANCE_SCHEDULE_VERSION = "strategy-lab.nautilus-rebalance-schedule.v1"
NAUTILUS_REBALANCE_AUDIT_SCHEMA = "strategy-lab.nautilus.rebalance-audit.v1"
NAUTILUS_REBALANCE_AUDIT_MEDIA_TYPE = (
    "application/vnd.charting.strategy-lab.nautilus-rebalance-audit+json"
)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class RebalanceBoundaryAction(StrEnum):
    APPLY_BEFORE_EVENT = "apply_before_event"
    APPLY_AFTER_EVENT_GROUP = "apply_after_event_group"
    SKIP_MISFIRE = "skip_misfire"
    FAIL_MISFIRE = "fail_misfire"


class RebalanceBoundaryPhase(StrEnum):
    BEFORE_EVENT = "before_event"
    AFTER_EVENT_GROUP = "after_event_group"
    END_OF_TAPE = "end_of_tape"


class RebalanceBoundaryReason(StrEnum):
    EXACT_SESSION_OPEN = "exact_session_open"
    EXACT_SESSION_CLOSE = "exact_session_close"
    EVENT_AFTER_BOUNDARY = "event_after_boundary"
    TAPE_ENDED_BEFORE_BOUNDARY = "tape_ended_before_boundary"


@dataclass(frozen=True, slots=True)
class RebalanceBoundaryTransition:
    """One stable outcome when the event tape reaches or misses an occurrence."""

    definition_version: str
    plan_fingerprint: str
    occurrence: ScheduledRebalance
    action: RebalanceBoundaryAction
    phase: RebalanceBoundaryPhase
    reason: RebalanceBoundaryReason
    observed_event_time_ns: int | None

    def __post_init__(self) -> None:
        if self.definition_version != NAUTILUS_REBALANCE_SCHEDULE_VERSION:
            raise ValueError("unsupported Nautilus rebalance schedule version")
        require_sha256_digest(self.plan_fingerprint, field_name="plan_fingerprint")
        if not isinstance(self.occurrence, ScheduledRebalance):
            raise TypeError("occurrence must be a ScheduledRebalance")
        if not isinstance(self.action, RebalanceBoundaryAction):
            raise TypeError("action must be a RebalanceBoundaryAction")
        if not isinstance(self.phase, RebalanceBoundaryPhase):
            raise TypeError("phase must be a RebalanceBoundaryPhase")
        if not isinstance(self.reason, RebalanceBoundaryReason):
            raise TypeError("reason must be a RebalanceBoundaryReason")
        if self.observed_event_time_ns is not None and (
            not isinstance(self.observed_event_time_ns, int)
            or isinstance(self.observed_event_time_ns, bool)
            or self.observed_event_time_ns < 0
        ):
            raise ValueError("observed_event_time_ns must be a non-negative integer or None")
        if self.action is RebalanceBoundaryAction.APPLY_BEFORE_EVENT and (
            self.phase is not RebalanceBoundaryPhase.BEFORE_EVENT
            or self.reason is not RebalanceBoundaryReason.EXACT_SESSION_OPEN
            or self.occurrence.trigger is not RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS
            or self.observed_event_time_ns != _event_time_ns(self.occurrence.event_time)
        ):
            raise ValueError("before-event applications require an exact session-open boundary")
        if self.action is RebalanceBoundaryAction.APPLY_AFTER_EVENT_GROUP and (
            self.phase is not RebalanceBoundaryPhase.AFTER_EVENT_GROUP
            or self.reason is not RebalanceBoundaryReason.EXACT_SESSION_CLOSE
            or self.occurrence.trigger is not RebalanceTrigger.SESSION_CLOSE_AFTER_EVENTS
            or self.observed_event_time_ns != _event_time_ns(self.occurrence.event_time)
        ):
            raise ValueError("after-group applications require an exact session-close boundary")
        if self.action in {
            RebalanceBoundaryAction.SKIP_MISFIRE,
            RebalanceBoundaryAction.FAIL_MISFIRE,
        } and self.reason not in {
            RebalanceBoundaryReason.EVENT_AFTER_BOUNDARY,
            RebalanceBoundaryReason.TAPE_ENDED_BEFORE_BOUNDARY,
        }:
            raise ValueError("misfire outcomes require an explicit missing-boundary reason")
        if self.action in {
            RebalanceBoundaryAction.SKIP_MISFIRE,
            RebalanceBoundaryAction.FAIL_MISFIRE,
        }:
            expected_action = (
                RebalanceBoundaryAction.FAIL_MISFIRE
                if self.occurrence.misfire_policy is RebalanceMisfirePolicy.FAIL_RUN
                else RebalanceBoundaryAction.SKIP_MISFIRE
            )
            if self.action is not expected_action:
                raise ValueError("misfire action differs from the occurrence policy")
            if self.reason is RebalanceBoundaryReason.EVENT_AFTER_BOUNDARY and (
                self.observed_event_time_ns is None
                or self.observed_event_time_ns <= _event_time_ns(self.occurrence.event_time)
            ):
                raise ValueError("event-after-boundary misfires require a later observed event")
            if (
                self.reason is RebalanceBoundaryReason.TAPE_ENDED_BEFORE_BOUNDARY
                and self.observed_event_time_ns is not None
            ):
                raise ValueError("end-of-tape misfires must not claim an observed event")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    def to_wire(self) -> dict[str, object]:
        occurrence = self.occurrence
        return {
            "definition_version": self.definition_version,
            "plan_fingerprint": self.plan_fingerprint,
            "occurrence_id": occurrence.occurrence_id,
            "policy_fingerprint": occurrence.policy_fingerprint,
            "calendar_fingerprint": occurrence.calendar_fingerprint,
            "session_id": occurrence.session_id,
            "session_label": occurrence.session_label.isoformat(),
            "scheduled_event_time_ns": _event_time_ns(occurrence.event_time),
            "trigger": occurrence.trigger.value,
            "cadence_period": occurrence.cadence_period,
            "misfire_policy": occurrence.misfire_policy.value,
            "action": self.action.value,
            "phase": self.phase.value,
            "reason": self.reason.value,
            "observed_event_time_ns": self.observed_event_time_ns,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_wire(
        cls,
        value: object,
        *,
        plan: RebalanceExecutionPlan,
    ) -> RebalanceBoundaryTransition:
        """Decode one transition only when its occurrence belongs to the frozen plan."""

        fields = {
            "definition_version",
            "plan_fingerprint",
            "occurrence_id",
            "policy_fingerprint",
            "calendar_fingerprint",
            "session_id",
            "session_label",
            "scheduled_event_time_ns",
            "trigger",
            "cadence_period",
            "misfire_policy",
            "action",
            "phase",
            "reason",
            "observed_event_time_ns",
            "fingerprint",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise ValueError("rebalance transition fields are invalid")
        if value["plan_fingerprint"] != plan.fingerprint:
            raise ValueError("rebalance transition references a different plan")
        occurrence_id = value["occurrence_id"]
        occurrence = next(
            (item for item in plan.occurrences if item.occurrence_id == occurrence_id),
            None,
        )
        if occurrence is None:
            raise ValueError("rebalance transition references an unknown occurrence")
        expected_occurrence = {
            "policy_fingerprint": occurrence.policy_fingerprint,
            "calendar_fingerprint": occurrence.calendar_fingerprint,
            "session_id": occurrence.session_id,
            "session_label": occurrence.session_label.isoformat(),
            "scheduled_event_time_ns": _event_time_ns(occurrence.event_time),
            "trigger": occurrence.trigger.value,
            "cadence_period": occurrence.cadence_period,
            "misfire_policy": occurrence.misfire_policy.value,
        }
        if any(value[field] != expected for field, expected in expected_occurrence.items()):
            raise ValueError("rebalance transition occurrence identity differs from its plan")
        observed_event_time_ns = value["observed_event_time_ns"]
        transition = cls(
            definition_version=value["definition_version"],
            plan_fingerprint=plan.fingerprint,
            occurrence=occurrence,
            action=RebalanceBoundaryAction(value["action"]),
            phase=RebalanceBoundaryPhase(value["phase"]),
            reason=RebalanceBoundaryReason(value["reason"]),
            observed_event_time_ns=observed_event_time_ns,
        )
        if value["fingerprint"] != transition.fingerprint:
            raise ValueError("rebalance transition fingerprint is invalid")
        return transition


class RebalanceExecutionStatus(StrEnum):
    SKIPPED_MISFIRE = "skipped_misfire"
    FAILED_MISFIRE = "failed_misfire"
    APPLIED_WITHOUT_CACHED_TARGETS = "applied_without_cached_targets"
    APPLIED_WITHOUT_ORDERS = "applied_without_orders"
    ORDERS_SUBMITTED = "orders_submitted"
    NOT_APPLIED_RUN_ABORTED = "not_applied_run_aborted"


@dataclass(frozen=True, slots=True)
class RebalanceScheduleOutcome:
    """One callback's disposition and native-order submission count."""

    transition: RebalanceBoundaryTransition
    execution_status: RebalanceExecutionStatus
    submitted_order_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.transition, RebalanceBoundaryTransition):
            raise TypeError("transition must be a RebalanceBoundaryTransition")
        if not isinstance(self.execution_status, RebalanceExecutionStatus):
            raise TypeError("execution_status must be a RebalanceExecutionStatus")
        if (
            not isinstance(self.submitted_order_count, int)
            or isinstance(self.submitted_order_count, bool)
            or self.submitted_order_count < 0
        ):
            raise ValueError("submitted_order_count must be a non-negative integer")
        if self.transition.action is RebalanceBoundaryAction.SKIP_MISFIRE:
            valid = self.execution_status is RebalanceExecutionStatus.SKIPPED_MISFIRE
        elif self.transition.action is RebalanceBoundaryAction.FAIL_MISFIRE:
            valid = self.execution_status is RebalanceExecutionStatus.FAILED_MISFIRE
        else:
            valid = self.execution_status in {
                RebalanceExecutionStatus.APPLIED_WITHOUT_CACHED_TARGETS,
                RebalanceExecutionStatus.APPLIED_WITHOUT_ORDERS,
                RebalanceExecutionStatus.ORDERS_SUBMITTED,
                RebalanceExecutionStatus.NOT_APPLIED_RUN_ABORTED,
            }
        if not valid:
            raise ValueError("execution status does not match the rebalance transition")
        if (self.execution_status is RebalanceExecutionStatus.ORDERS_SUBMITTED) != (
            self.submitted_order_count > 0
        ):
            raise ValueError("order-submission status must match its submitted order count")

    def to_wire(self) -> dict[str, object]:
        return {
            "transition": self.transition.to_wire(),
            "execution_status": self.execution_status.value,
            "submitted_order_count": self.submitted_order_count,
        }


@dataclass(frozen=True, slots=True)
class NautilusRebalanceScheduleAudit:
    """Complete, typed decision evidence for one frozen schedule and attempt."""

    attempt_id: str
    plan_fingerprint: str
    outcomes: tuple[RebalanceScheduleOutcome, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        require_sha256_digest(self.plan_fingerprint, field_name="plan_fingerprint")
        outcomes = tuple(self.outcomes)
        if any(not isinstance(item, RebalanceScheduleOutcome) for item in outcomes):
            raise TypeError("outcomes must contain RebalanceScheduleOutcome values")
        if any(item.transition.plan_fingerprint != self.plan_fingerprint for item in outcomes):
            raise ValueError("audit outcomes differ from the frozen plan")
        occurrence_ids = [item.transition.occurrence.occurrence_id for item in outcomes]
        if len(occurrence_ids) != len(set(occurrence_ids)):
            raise ValueError("audit outcomes must contain unique rebalance occurrences")
        object.__setattr__(self, "outcomes", outcomes)

    @classmethod
    def from_callback_outcomes(
        cls,
        *,
        attempt_id: str,
        plan: RebalanceExecutionPlan,
        outcomes: object,
    ) -> NautilusRebalanceScheduleAudit:
        """Strictly bind callback output to every occurrence in the frozen plan."""

        if not isinstance(plan, RebalanceExecutionPlan):
            raise TypeError("plan must be a RebalanceExecutionPlan")
        if not isinstance(outcomes, list) or len(outcomes) != len(plan.occurrences):
            raise ValueError("rebalance callback outcomes must cover every frozen occurrence")
        decoded: list[RebalanceScheduleOutcome] = []
        for raw in outcomes:
            if not isinstance(raw, Mapping) or set(raw) != {
                "transition",
                "execution_status",
                "submitted_order_count",
            }:
                raise ValueError("rebalance schedule outcome fields are invalid")
            status = raw["execution_status"]
            if not isinstance(status, str):
                raise ValueError("rebalance schedule execution status must be a string")
            order_count = raw["submitted_order_count"]
            if not isinstance(order_count, int) or isinstance(order_count, bool) or order_count < 0:
                raise ValueError("rebalance submitted-order count must be non-negative")
            decoded.append(
                RebalanceScheduleOutcome(
                    transition=RebalanceBoundaryTransition.from_wire(
                        raw["transition"],
                        plan=plan,
                    ),
                    execution_status=RebalanceExecutionStatus(status),
                    submitted_order_count=order_count,
                )
            )
        if tuple(item.transition.occurrence.occurrence_id for item in decoded) != tuple(
            item.occurrence_id for item in plan.occurrences
        ):
            raise ValueError("rebalance callback outcomes are not in frozen plan order")
        return cls(attempt_id, plan.fingerprint, tuple(decoded))

    @classmethod
    def from_wire(
        cls,
        value: object,
        *,
        attempt_id: str,
        plan: RebalanceExecutionPlan,
    ) -> NautilusRebalanceScheduleAudit:
        fields = {"schema", "attempt_id", "plan_fingerprint", "outcomes", "fingerprint"}
        if not isinstance(value, Mapping) or set(value) != fields:
            raise ValueError("rebalance schedule audit fields are invalid")
        if value["schema"] != NAUTILUS_REBALANCE_AUDIT_SCHEMA:
            raise ValueError("rebalance schedule audit schema is unsupported")
        if value["attempt_id"] != attempt_id or value["plan_fingerprint"] != plan.fingerprint:
            raise ValueError("rebalance schedule audit identity differs from the attempt plan")
        raw_outcomes = value["outcomes"]
        audit = cls.from_callback_outcomes(
            attempt_id=attempt_id,
            plan=plan,
            outcomes=raw_outcomes,
        )
        if value["fingerprint"] != audit.fingerprint:
            raise ValueError("rebalance schedule audit fingerprint is invalid")
        return audit

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    def to_wire(self) -> dict[str, object]:
        return {
            "schema": NAUTILUS_REBALANCE_AUDIT_SCHEMA,
            "attempt_id": self.attempt_id,
            "plan_fingerprint": self.plan_fingerprint,
            "outcomes": [item.to_wire() for item in self.outcomes],
            "fingerprint": self.fingerprint,
        }

    def artifact_bytes(self) -> bytes:
        return json.dumps(
            self.to_wire(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def artifact_manifest(self) -> ArtifactManifest:
        payload = self.artifact_bytes()
        digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        return ArtifactManifest(
            content_digest=digest,
            byte_length=len(payload),
            media_type=NAUTILUS_REBALANCE_AUDIT_MEDIA_TYPE,
            schema_version=NAUTILUS_REBALANCE_AUDIT_SCHEMA,
            storage_key=digest,
            retention_class=ArtifactRetention.PINNED_RESULT,
        )


def _event_time_ns(value: datetime) -> int:
    delta = value.astimezone(UTC) - _EPOCH
    if delta.days < 0:
        raise ValueError("rebalance event boundaries before the Unix epoch are unsupported")
    return ((delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds) * 1_000


class NautilusRebalanceScheduleCursor:
    """Consume a frozen plan exactly once in canonical native-event order."""

    __slots__ = ("_plan", "_index", "_last_event_time_ns", "_finished")

    def __init__(self, plan: RebalanceExecutionPlan) -> None:
        if not isinstance(plan, RebalanceExecutionPlan):
            raise TypeError("plan must be a RebalanceExecutionPlan")
        self._plan = plan
        self._index = 0
        self._last_event_time_ns: int | None = None
        self._finished = False

    @property
    def plan_fingerprint(self) -> str:
        return self._plan.fingerprint

    @property
    def remaining_count(self) -> int:
        return len(self._plan.occurrences) - self._index

    def before_event(self, event_time_ns: int) -> tuple[RebalanceBoundaryTransition, ...]:
        """Return misfires preceding this event and any exact session-open action."""

        self._require_event_time(event_time_ns)
        if self._finished:
            raise RuntimeError("rebalance schedule cursor is already finished")
        if self._last_event_time_ns is not None and event_time_ns < self._last_event_time_ns:
            raise ValueError("native event timestamps must be monotonic")
        self._last_event_time_ns = event_time_ns
        transitions: list[RebalanceBoundaryTransition] = []
        while self._index < len(self._plan.occurrences):
            occurrence = self._plan.occurrences[self._index]
            boundary_ns = _event_time_ns(occurrence.event_time)
            if boundary_ns > event_time_ns:
                break
            if boundary_ns == event_time_ns:
                if occurrence.trigger is RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS:
                    transitions.append(
                        self._transition(
                            occurrence,
                            RebalanceBoundaryAction.APPLY_BEFORE_EVENT,
                            RebalanceBoundaryPhase.BEFORE_EVENT,
                            RebalanceBoundaryReason.EXACT_SESSION_OPEN,
                            event_time_ns,
                        )
                    )
                    self._index += 1
                break
            transitions.append(
                self._misfire(
                    occurrence,
                    RebalanceBoundaryPhase.BEFORE_EVENT,
                    RebalanceBoundaryReason.EVENT_AFTER_BOUNDARY,
                    event_time_ns,
                )
            )
            self._index += 1
        return tuple(transitions)

    def after_event_group(
        self,
        event_time_ns: int,
        *,
        next_event_time_ns: int | None,
    ) -> tuple[RebalanceBoundaryTransition, ...]:
        """Apply an exact session-close occurrence after its whole timestamp group."""

        self._require_event_time(event_time_ns)
        if self._finished:
            raise RuntimeError("rebalance schedule cursor is already finished")
        if self._last_event_time_ns != event_time_ns:
            raise ValueError("event group must follow the matching before_event callback")
        if next_event_time_ns is not None:
            self._require_event_time(next_event_time_ns)
            if next_event_time_ns <= event_time_ns:
                raise ValueError("after_event_group requires the final callback at this timestamp")
        if self._index == len(self._plan.occurrences):
            return ()
        occurrence = self._plan.occurrences[self._index]
        if (
            _event_time_ns(occurrence.event_time) != event_time_ns
            or occurrence.trigger is not RebalanceTrigger.SESSION_CLOSE_AFTER_EVENTS
        ):
            return ()
        self._index += 1
        return (
            self._transition(
                occurrence,
                RebalanceBoundaryAction.APPLY_AFTER_EVENT_GROUP,
                RebalanceBoundaryPhase.AFTER_EVENT_GROUP,
                RebalanceBoundaryReason.EXACT_SESSION_CLOSE,
                event_time_ns,
            ),
        )

    def finish(self) -> tuple[RebalanceBoundaryTransition, ...]:
        """Classify every unobserved occurrence when the authenticated tape ends."""

        if self._finished:
            raise RuntimeError("rebalance schedule cursor is already finished")
        self._finished = True
        transitions: list[RebalanceBoundaryTransition] = []
        while self._index < len(self._plan.occurrences):
            occurrence = self._plan.occurrences[self._index]
            transitions.append(
                self._misfire(
                    occurrence,
                    RebalanceBoundaryPhase.END_OF_TAPE,
                    RebalanceBoundaryReason.TAPE_ENDED_BEFORE_BOUNDARY,
                    None,
                )
            )
            self._index += 1
        return tuple(transitions)

    def _misfire(
        self,
        occurrence: ScheduledRebalance,
        phase: RebalanceBoundaryPhase,
        reason: RebalanceBoundaryReason,
        observed_event_time_ns: int | None,
    ) -> RebalanceBoundaryTransition:
        action = (
            RebalanceBoundaryAction.FAIL_MISFIRE
            if occurrence.misfire_policy is RebalanceMisfirePolicy.FAIL_RUN
            else RebalanceBoundaryAction.SKIP_MISFIRE
        )
        return self._transition(occurrence, action, phase, reason, observed_event_time_ns)

    def _transition(
        self,
        occurrence: ScheduledRebalance,
        action: RebalanceBoundaryAction,
        phase: RebalanceBoundaryPhase,
        reason: RebalanceBoundaryReason,
        observed_event_time_ns: int | None,
    ) -> RebalanceBoundaryTransition:
        return RebalanceBoundaryTransition(
            definition_version=NAUTILUS_REBALANCE_SCHEDULE_VERSION,
            plan_fingerprint=self._plan.fingerprint,
            occurrence=occurrence,
            action=action,
            phase=phase,
            reason=reason,
            observed_event_time_ns=observed_event_time_ns,
        )

    @staticmethod
    def _require_event_time(value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("event time must be a non-negative integer nanosecond timestamp")


__all__ = [
    "NAUTILUS_REBALANCE_AUDIT_MEDIA_TYPE",
    "NAUTILUS_REBALANCE_AUDIT_SCHEMA",
    "NAUTILUS_REBALANCE_SCHEDULE_VERSION",
    "NautilusRebalanceScheduleAudit",
    "NautilusRebalanceScheduleCursor",
    "RebalanceBoundaryAction",
    "RebalanceBoundaryPhase",
    "RebalanceBoundaryReason",
    "RebalanceBoundaryTransition",
    "RebalanceExecutionStatus",
    "RebalanceScheduleOutcome",
]
