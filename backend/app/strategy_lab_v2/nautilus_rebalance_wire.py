"""Strict wire codec for frozen Nautilus rebalance execution plans."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.strategy_lab_v2.rebalance import (
    REBALANCE_EXECUTION_PLAN_VERSION,
    RebalanceExecutionPlan,
    RebalanceMisfirePolicy,
    RebalanceTrigger,
    ScheduledRebalance,
)


def rebalance_execution_plan_to_wire(
    plan: RebalanceExecutionPlan | None,
) -> dict[str, Any] | None:
    """Serialize exact schedule identity and UTC occurrence boundaries."""

    if plan is None:
        return None
    if not isinstance(plan, RebalanceExecutionPlan):
        raise TypeError("plan must be a RebalanceExecutionPlan or None")
    return {
        "definition_version": plan.definition_version,
        "policy_fingerprint": plan.policy_fingerprint,
        "calendar_fingerprint": plan.calendar_fingerprint,
        "occurrences": [
            {
                "occurrence_id": item.occurrence_id,
                "policy_fingerprint": item.policy_fingerprint,
                "calendar_fingerprint": item.calendar_fingerprint,
                "session_id": item.session_id,
                "session_label": item.session_label.isoformat(),
                "event_time_ns": _timestamp_ns(item.event_time),
                "trigger": item.trigger.value,
                "cadence_period": item.cadence_period,
                "misfire_policy": item.misfire_policy.value,
            }
            for item in plan.occurrences
        ],
        "fingerprint": plan.fingerprint,
    }


def rebalance_execution_plan_from_wire(value: object) -> RebalanceExecutionPlan | None:
    """Reconstruct and fingerprint-check a serialized execution plan."""

    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {
        "definition_version",
        "policy_fingerprint",
        "calendar_fingerprint",
        "occurrences",
        "fingerprint",
    }:
        raise ValueError("rebalance execution-plan fields are invalid")
    if value["definition_version"] != REBALANCE_EXECUTION_PLAN_VERSION:
        raise ValueError("unsupported rebalance execution-plan version")
    raw_occurrences = value["occurrences"]
    if not isinstance(raw_occurrences, list):
        raise ValueError("rebalance execution-plan occurrences must be a list")
    occurrences: list[ScheduledRebalance] = []
    for raw in raw_occurrences:
        if not isinstance(raw, Mapping) or set(raw) != {
            "occurrence_id",
            "policy_fingerprint",
            "calendar_fingerprint",
            "session_id",
            "session_label",
            "event_time_ns",
            "trigger",
            "cadence_period",
            "misfire_policy",
        }:
            raise ValueError("rebalance occurrence fields are invalid")
        label_text = _text(raw["session_label"], "session_label")
        session_label = date.fromisoformat(label_text)
        if session_label.isoformat() != label_text:
            raise ValueError("rebalance occurrence session label is not canonical")
        occurrences.append(
            ScheduledRebalance(
                occurrence_id=_text(raw["occurrence_id"], "occurrence_id"),
                policy_fingerprint=_text(raw["policy_fingerprint"], "policy_fingerprint"),
                calendar_fingerprint=_text(raw["calendar_fingerprint"], "calendar_fingerprint"),
                session_id=_text(raw["session_id"], "session_id"),
                session_label=session_label,
                event_time=_datetime_from_ns(raw["event_time_ns"]),
                trigger=RebalanceTrigger(_text(raw["trigger"], "trigger")),
                cadence_period=_text(raw["cadence_period"], "cadence_period"),
                misfire_policy=RebalanceMisfirePolicy(
                    _text(raw["misfire_policy"], "misfire_policy")
                ),
            )
        )
    plan = RebalanceExecutionPlan(
        policy_fingerprint=_text(value["policy_fingerprint"], "policy_fingerprint"),
        calendar_fingerprint=_text(value["calendar_fingerprint"], "calendar_fingerprint"),
        occurrences=tuple(occurrences),
        definition_version=_text(value["definition_version"], "definition_version"),
    )
    if value["fingerprint"] != plan.fingerprint:
        raise ValueError("rebalance execution-plan fingerprint is invalid")
    return plan


def _timestamp_ns(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = normalized - epoch
    result = (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000
    if result < 0:
        raise ValueError("rebalance event time predates the supported Nautilus epoch")
    return result


def _datetime_from_ns(value: object) -> datetime:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value % 1_000:
        raise ValueError("rebalance event_time_ns must be non-negative microsecond precision")
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=value // 1_000)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    if any(character in value for character in "\x00\r\n"):
        raise ValueError(f"{field_name} contains a control character")
    return value


__all__ = ["rebalance_execution_plan_from_wire", "rebalance_execution_plan_to_wire"]
