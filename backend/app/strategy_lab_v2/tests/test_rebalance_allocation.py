from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.strategy_lab_v2.allocation import (
    InstrumentRiskBinding,
    PortfolioExposureSnapshot,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    PortfolioComponent,
    PortfolioComposition,
    SharedRiskPolicy,
)
from app.strategy_lab_v2.rebalance import (
    CalendarRebalancePolicy,
    RebalanceCadence,
    RebalanceMisfirePolicy,
    RebalanceTrigger,
    ScheduledRebalance,
)
from app.strategy_lab_v2.rebalance_allocation import (
    RebalanceAllocationDecision,
    RebalanceApplicationKind,
    RebalanceApplicationReason,
    apply_scheduled_rebalance,
)
from app.strategy_lab_v2.sdk import TargetPositionIntent

EVENT = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
CALENDAR = content_digest({"calendar": "XNYS", "version": 1})


def _portfolio(
    *,
    event: datetime = EVENT,
    misfire_policy: RebalanceMisfirePolicy = RebalanceMisfirePolicy.FAIL_RUN,
) -> tuple[PortfolioComposition, ScheduledRebalance]:
    policy = CalendarRebalancePolicy(
        calendar_id="XNYS",
        calendar_fingerprint=CALENDAR,
        cadence=RebalanceCadence.MONTHLY,
        trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
        misfire_policy=misfire_policy,
    )
    portfolio = PortfolioComposition(
        "portfolio-1",
        "v1",
        Decimal("100000"),
        "USD",
        (
            PortfolioComponent(
                "alpha",
                content_digest("alpha-strategy"),
                ("US.AAPL",),
                Decimal("1.0"),
            ),
        ),
        rebalance_policy=policy,
        shared_risk_policy=SharedRiskPolicy(
            risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,),
        ),
    )
    scheduled = ScheduledRebalance(
        occurrence_id=content_digest({"occurrence": event.isoformat()}),
        policy_fingerprint=policy.fingerprint,
        calendar_fingerprint=CALENDAR,
        session_id="XNYS:2024-01-02",
        session_label=event.date(),
        event_time=event,
        trigger=policy.trigger,
        cadence_period="month:2024-01",
        misfire_policy=policy.misfire_policy,
    )
    return portfolio, scheduled


def _snapshot(
    portfolio: PortfolioComposition,
    event: datetime,
) -> PortfolioExposureSnapshot:
    return PortfolioExposureSnapshot(
        portfolio_fingerprint=portfolio.fingerprint,
        run_attempt_id="attempt-1",
        event_time=event,
        event_sequence=7,
        account_equity=Decimal("100000"),
        account_cash_balance=Decimal("100000"),
        base_currency="USD",
        valuation_evidence_digest=content_digest("valuation"),
        instrument_risk_models=(
            InstrumentRiskBinding("US.AAPL", CASH_EQUITY_NOTIONAL_RISK_MODEL),
        ),
    )


def _intents() -> dict[str, tuple[TargetPositionIntent, ...]]:
    return {"alpha": (TargetPositionIntent("US.AAPL", Decimal("0.5")),)}


def test_exact_boundary_applies_targets_through_existing_risk_allocator() -> None:
    portfolio, scheduled = _portfolio()
    result = apply_scheduled_rebalance(
        portfolio,
        _snapshot(portfolio, EVENT),
        scheduled,
        _intents(),
    )

    assert isinstance(result, RebalanceAllocationDecision)
    assert result.kind is RebalanceApplicationKind.APPLIED
    assert result.reason is RebalanceApplicationReason.EXACT_BOUNDARY
    assert result.request_count == 1
    assert result.allocation is not None
    assert result.allocation.proposed_instrument_targets[0].target_fraction_of_equity == Decimal("0.5")
    assert result.allocation.risk_limits_satisfied


def test_before_boundary_withholds_targets_without_catch_up() -> None:
    portfolio, scheduled = _portfolio()
    result = apply_scheduled_rebalance(
        portfolio,
        _snapshot(portfolio, EVENT.replace(minute=29)),
        scheduled,
        _intents(),
    )

    assert result.kind is RebalanceApplicationKind.NOT_DUE
    assert result.reason is RebalanceApplicationReason.BEFORE_BOUNDARY
    assert result.allocation is None
    assert result.request_count == 1


def test_late_event_fail_run_is_misfire_and_never_allocates_at_a_later_time() -> None:
    portfolio, scheduled = _portfolio()
    result = apply_scheduled_rebalance(
        portfolio,
        _snapshot(portfolio, EVENT.replace(minute=31)),
        scheduled,
        _intents(),
    )

    assert result.kind is RebalanceApplicationKind.MISFIRED
    assert result.reason is RebalanceApplicationReason.AFTER_BOUNDARY_FAIL_RUN
    assert result.allocation is None


def test_late_event_skip_policy_is_explicitly_skipped() -> None:
    portfolio, scheduled = _portfolio(
        misfire_policy=RebalanceMisfirePolicy.SKIP_OCCURRENCE,
    )
    result = apply_scheduled_rebalance(
        portfolio,
        _snapshot(portfolio, EVENT.replace(minute=31)),
        scheduled,
        _intents(),
    )

    assert result.kind is RebalanceApplicationKind.SKIPPED
    assert result.reason is RebalanceApplicationReason.AFTER_BOUNDARY_SKIP_OCCURRENCE
    assert result.allocation is None


def test_same_input_is_content_addressed_and_stale_schedule_is_rejected() -> None:
    portfolio, scheduled = _portfolio()
    snapshot = _snapshot(portfolio, EVENT)
    first = apply_scheduled_rebalance(portfolio, snapshot, scheduled, _intents())
    second = apply_scheduled_rebalance(portfolio, snapshot, scheduled, _intents())
    assert first == second
    assert first.fingerprint == second.fingerprint

    stale = replace(scheduled, policy_fingerprint=content_digest("stale-policy"))
    with pytest.raises(ValueError, match="policy is stale or mismatched"):
        apply_scheduled_rebalance(portfolio, snapshot, stale, _intents())


def test_calendar_identity_and_policy_presence_are_required() -> None:
    portfolio, scheduled = _portfolio()
    snapshot = _snapshot(portfolio, EVENT)
    stale_calendar = replace(scheduled, calendar_fingerprint=content_digest("stale-calendar"))
    with pytest.raises(ValueError, match="calendar is stale or mismatched"):
        apply_scheduled_rebalance(portfolio, snapshot, stale_calendar, _intents())

    without_policy = replace(portfolio, rebalance_policy=None)
    with pytest.raises(ValueError, match="no calendar rebalance policy"):
        apply_scheduled_rebalance(without_policy, snapshot, scheduled, _intents())


def test_exact_boundary_retains_allocation_risk_rejection() -> None:
    portfolio, scheduled = _portfolio()
    constrained = replace(
        portfolio,
        shared_risk_policy=replace(
            portfolio.shared_risk_policy,
            max_gross_exposure_fraction=Decimal("0.25"),
        ),
    )
    # Rebuild the schedule against the changed portfolio policy identity.
    constrained_policy = constrained.rebalance_policy
    assert constrained_policy is not None
    scheduled = replace(scheduled, policy_fingerprint=constrained_policy.fingerprint)
    result = apply_scheduled_rebalance(
        constrained,
        _snapshot(constrained, EVENT),
        scheduled,
        _intents(),
    )

    assert result.kind is RebalanceApplicationKind.APPLIED
    assert result.allocation is not None
    assert not result.allocation.risk_limits_satisfied
    assert result.allocation.risk_approved_instrument_targets == ()
