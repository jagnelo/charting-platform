from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.nautilus_rebalance_wire import (
    rebalance_execution_plan_from_wire,
    rebalance_execution_plan_to_wire,
)
from app.strategy_lab_v2.rebalance import (
    RebalanceExecutionPlan,
    RebalanceMisfirePolicy,
    RebalanceTrigger,
    ScheduledRebalance,
)


def _plan() -> RebalanceExecutionPlan:
    policy_fingerprint = content_digest("policy")
    calendar_fingerprint = content_digest("calendar")
    occurrence_payload = {
        "policy_fingerprint": policy_fingerprint,
        "calendar_fingerprint": calendar_fingerprint,
        "session_id": "XNYS:2024-01-02",
        "session_label": date(2024, 1, 2),
        "event_time": datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
        "trigger": RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
        "cadence_period": "month:2024-01",
    }
    return RebalanceExecutionPlan(
        policy_fingerprint=policy_fingerprint,
        calendar_fingerprint=calendar_fingerprint,
        occurrences=(
            ScheduledRebalance(
                occurrence_id=content_digest(occurrence_payload),
                policy_fingerprint=policy_fingerprint,
                calendar_fingerprint=calendar_fingerprint,
                session_id="XNYS:2024-01-02",
                session_label=date(2024, 1, 2),
                event_time=datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
                trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
                cadence_period="month:2024-01",
                misfire_policy=RebalanceMisfirePolicy.FAIL_RUN,
            ),
        ),
    )


def test_rebalance_plan_wire_round_trip_preserves_exact_occurrence_identity() -> None:
    plan = _plan()

    assert rebalance_execution_plan_from_wire(rebalance_execution_plan_to_wire(plan)) == plan
    assert rebalance_execution_plan_from_wire(None) is None


def test_rebalance_plan_wire_rejects_tampered_fingerprint() -> None:
    wire = rebalance_execution_plan_to_wire(_plan())
    assert wire is not None
    wire["fingerprint"] = content_digest("tampered")

    with pytest.raises(ValueError, match="fingerprint is invalid"):
        rebalance_execution_plan_from_wire(wire)


def test_rebalance_plan_wire_rejects_nanosecond_precision_loss() -> None:
    wire = rebalance_execution_plan_to_wire(_plan())
    assert wire is not None
    wire["occurrences"][0]["event_time_ns"] += 1
    wire["fingerprint"] = _plan().fingerprint

    with pytest.raises(ValueError, match="microsecond precision"):
        rebalance_execution_plan_from_wire(wire)
