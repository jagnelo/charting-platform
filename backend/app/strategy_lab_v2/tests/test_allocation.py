from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from app.strategy_lab_v2.allocation import (
    AllocationRejectionCode,
    ComponentPositionExposure,
    ComponentTargetRequest,
    InstrumentRiskBinding,
    PortfolioExposureSnapshot,
    RiskBreach,
    allocate_component_targets,
    component_targets_from_intents,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    ProductRiskModel,
    RiskExposureMeasure,
    SharedRiskPolicy,
    TargetConflictPolicy,
)
from app.strategy_lab_v2.sdk import OrderIntent, OrderSide, TargetPositionIntent

EVENT_TIME = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)
VALUATION_DIGEST = content_digest({"source": "test-engine-account-valuation"})


def _portfolio(
    policy: SharedRiskPolicy | None = None,
    *,
    components: tuple[PortfolioComponent, ...] | None = None,
) -> PortfolioComposition:
    if components is None:
        components = (
            PortfolioComponent(
                "alpha", content_digest("alpha-strategy"), ("US.AAPL",), Decimal("0.60")
            ),
            PortfolioComponent(
                "beta",
                content_digest("beta-strategy"),
                ("US.AAPL", "US.MSFT", "US.NVDA"),
                Decimal("0.40"),
            ),
        )
    if policy is None:
        policy = SharedRiskPolicy(risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,))
    elif not policy.risk_models:
        policy = replace(policy, risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,))
    return PortfolioComposition(
        "portfolio-1",
        "v1",
        Decimal("100000"),
        "USD",
        components,
        shared_risk_policy=policy or SharedRiskPolicy(),
    )


def _snapshot(
    portfolio: PortfolioComposition,
    *,
    positions: tuple[ComponentPositionExposure, ...] = (),
    account_equity: Decimal = Decimal("100000"),
    event_sequence: int = 10,
) -> PortfolioExposureSnapshot:
    return PortfolioExposureSnapshot(
        portfolio_fingerprint=portfolio.fingerprint,
        run_attempt_id="allocation-test-attempt",
        event_time=EVENT_TIME,
        event_sequence=event_sequence,
        account_equity=account_equity,
        account_cash_balance=Decimal("50000"),
        base_currency="USD",
        valuation_evidence_digest=VALUATION_DIGEST,
        positions=positions,
        instrument_risk_models=tuple(
            InstrumentRiskBinding(instrument_id, CASH_EQUITY_NOTIONAL_RISK_MODEL)
            for instrument_id in sorted(
                {
                    instrument_id
                    for component in portfolio.components
                    for instrument_id in component.instrument_ids
                }
            )
        ),
    )


def _request(
    component_id: str, instrument_id: str, fraction: str, *, sequence: int = 10
) -> ComponentTargetRequest:
    return ComponentTargetRequest(
        component_id,
        instrument_id,
        Decimal(fraction),
        EVENT_TIME,
        sequence,
    )


def test_target_intents_are_scaled_by_component_budget_and_netted_after_gross_risk() -> None:
    policy = SharedRiskPolicy(
        max_gross_exposure_fraction=Decimal("1.0"),
        max_net_exposure_fraction=Decimal("1.0"),
        max_instrument_gross_exposure_fraction=Decimal("1.0"),
        max_component_gross_exposure_fraction=Decimal("1.0"),
        allow_short_positions=True,
        target_conflict_policy=TargetConflictPolicy.SUM_COMPONENT_TARGETS,
    )
    portfolio = _portfolio(policy)
    requests = component_targets_from_intents(
        portfolio,
        {
            "alpha": (TargetPositionIntent("US.AAPL", Decimal("0.5")),),
            "beta": (TargetPositionIntent("US.AAPL", Decimal("-0.25")),),
        },
        event_time=EVENT_TIME,
        event_sequence=10,
    )

    decision = allocate_component_targets(portfolio, _snapshot(portfolio), requests)

    assert decision.risk_limits_satisfied
    assert decision.gross_exposure_fraction == Decimal("0.4")
    assert decision.net_exposure_fraction == Decimal("0.20")
    assert len(decision.proposed_component_exposures) == 2
    assert decision.proposed_instrument_targets[0].target_fraction_of_equity == Decimal("0.20")
    assert decision.proposed_instrument_targets[0].target_signed_base_notional == Decimal("20000.00")
    assert decision.risk_approved_instrument_targets == decision.proposed_instrument_targets


def test_priority_policy_selects_one_component_independent_of_request_order() -> None:
    portfolio = _portfolio(
        SharedRiskPolicy(
            target_conflict_policy=TargetConflictPolicy.HIGHEST_PRIORITY,
        ),
        components=(
            PortfolioComponent(
                "low", content_digest("low"), ("US.AAPL",), Decimal("0.5"), priority=1
            ),
            PortfolioComponent(
                "high", content_digest("high"), ("US.AAPL",), Decimal("0.5"), priority=7
            ),
        ),
    )
    requests = (_request("low", "US.AAPL", "0.8"), _request("high", "US.AAPL", "0.4"))

    decision = allocate_component_targets(portfolio, _snapshot(portfolio), reversed(requests))

    assert decision.risk_limits_satisfied
    assert decision.gross_exposure_fraction == Decimal("0.20")
    assert decision.proposed_component_exposures[0].component_id == "high"
    assert decision.rejected_targets == (
        type(decision.rejected_targets[0])(
            "low", "US.AAPL", AllocationRejectionCode.LOWER_PRIORITY
        ),
    )


def test_priority_tie_and_reject_conflict_fail_closed_for_the_conflicting_symbol() -> None:
    for conflict_policy, expected_code in (
        (TargetConflictPolicy.HIGHEST_PRIORITY, AllocationRejectionCode.PRIORITY_TIE),
        (TargetConflictPolicy.REJECT, AllocationRejectionCode.TARGET_CONFLICT),
    ):
        portfolio = _portfolio(
            SharedRiskPolicy(target_conflict_policy=conflict_policy),
            components=(
                PortfolioComponent(
                    "alpha", content_digest("alpha"), ("US.AAPL",), Decimal("0.5"), priority=4
                ),
                PortfolioComponent(
                    "beta", content_digest("beta"), ("US.AAPL",), Decimal("0.5"), priority=4
                ),
            ),
        )
        decision = allocate_component_targets(
            portfolio,
            _snapshot(portfolio),
            (_request("beta", "US.AAPL", "0.5"), _request("alpha", "US.AAPL", "0.5")),
        )

        assert decision.risk_limits_satisfied
        assert decision.proposed_component_exposures == ()
        assert decision.risk_approved_instrument_targets == ()
        assert {item.code for item in decision.rejected_targets} == {expected_code}
        assert {item.component_id for item in decision.rejected_targets} == {"alpha", "beta"}


def test_shared_risk_breach_reports_proposal_but_exposes_no_routable_targets() -> None:
    portfolio = _portfolio(
        SharedRiskPolicy(
            max_gross_exposure_fraction=Decimal("0.50"),
            max_component_gross_exposure_fraction=Decimal("0.50"),
        )
    )
    decision = allocate_component_targets(
        portfolio,
        _snapshot(portfolio),
        (_request("alpha", "US.AAPL", "1.0"),),
    )

    assert not decision.risk_limits_satisfied
    assert decision.gross_exposure_fraction == Decimal("0.60")
    assert decision.risk_breaches == (
        RiskBreach.GROSS_EXPOSURE,
        RiskBreach.COMPONENT_CONCENTRATION,
    )
    assert len(decision.proposed_instrument_targets) == 1
    assert decision.risk_approved_instrument_targets == ()


def test_flat_target_is_preserved_as_an_explicit_zero_instrument_target() -> None:
    portfolio = _portfolio()
    decision = allocate_component_targets(
        portfolio,
        _snapshot(
            portfolio,
            positions=(
                ComponentPositionExposure("alpha", "US.AAPL", Decimal("20000")),
            ),
        ),
        (_request("alpha", "US.AAPL", "0"),),
    )

    assert decision.risk_limits_satisfied
    assert decision.proposed_component_exposures[0].target_fraction_of_equity == Decimal(0)
    assert len(decision.proposed_instrument_targets) == 1
    assert decision.proposed_instrument_targets[0].target_fraction_of_equity == Decimal(0)
    assert decision.proposed_instrument_targets[0].target_signed_base_notional == Decimal(0)
    assert decision.risk_approved_instrument_targets == decision.proposed_instrument_targets
    assert decision.open_instrument_count == 0


def test_allocation_decisions_ignore_ambient_decimal_context() -> None:
    portfolio = _portfolio()
    snapshot = _snapshot(portfolio, account_equity=Decimal("100000.00"))
    requests = (_request("alpha", "US.AAPL", "0.3333333333333333333333333333"),)
    baseline = allocate_component_targets(portfolio, snapshot, requests)
    with localcontext() as decimal_context:
        decimal_context.prec = 6
        decimal_context.rounding = ROUND_DOWN
        constrained = allocate_component_targets(portfolio, snapshot, requests)
    assert constrained == baseline


def test_component_capital_weights_do_not_leverage_without_an_explicit_cap() -> None:
    components = (
        PortfolioComponent(
            "small", content_digest("small"), ("US.AAPL",), Decimal("0.10")
        ),
        PortfolioComponent(
            "large", content_digest("large"), ("US.MSFT",), Decimal("0.90")
        ),
    )
    portfolio = _portfolio(SharedRiskPolicy(), components=components)
    request = (_request("small", "US.AAPL", "2.0"),)

    decision = allocate_component_targets(portfolio, _snapshot(portfolio), request)

    assert not decision.risk_limits_satisfied
    assert decision.risk_breaches == (RiskBreach.COMPONENT_LEVERAGE,)
    assert decision.risk_approved_instrument_targets == ()

    leveraged = _portfolio(
        SharedRiskPolicy(max_component_leverage=Decimal("2.0")),
        components=components,
    )
    leveraged_decision = allocate_component_targets(
        leveraged, _snapshot(leveraged), request
    )
    assert leveraged_decision.risk_limits_satisfied
    assert leveraged_decision.gross_exposure_fraction == Decimal("0.20")


def test_instruments_without_an_explicit_supported_risk_model_fail_closed() -> None:
    portfolio = _portfolio()
    snapshot = _snapshot(portfolio)
    option_model = ProductRiskModel(
        ProductClass.OPTION,
        RiskExposureMeasure.SIGNED_BASE_NOTIONAL,
        content_digest("unimplemented-option-risk-model"),
    )
    option_snapshot = replace(
        snapshot,
        instrument_risk_models=(InstrumentRiskBinding("US.AAPL", option_model),),
    )

    with pytest.raises(ValueError, match="unsupported product risk model"):
        allocate_component_targets(
            portfolio, option_snapshot, (_request("alpha", "US.AAPL", "0.25"),)
        )
    with pytest.raises(ValueError, match="no risk-model evidence"):
        allocate_component_targets(
            portfolio,
            replace(snapshot, instrument_risk_models=()),
            (_request("alpha", "US.AAPL", "0.25"),),
        )


def test_current_positions_are_repriced_into_account_equity_and_checked_before_netting() -> None:
    policy = SharedRiskPolicy(
        max_gross_exposure_fraction=Decimal("0.75"),
        max_net_exposure_fraction=Decimal("0.25"),
        max_instrument_gross_exposure_fraction=Decimal("0.75"),
        max_component_gross_exposure_fraction=Decimal("0.75"),
        allow_short_positions=True,
        target_conflict_policy=TargetConflictPolicy.SUM_COMPONENT_TARGETS,
    )
    portfolio = _portfolio(policy)
    snapshot = _snapshot(
        portfolio,
        account_equity=Decimal("50000"),
        positions=(
            ComponentPositionExposure("alpha", "US.AAPL", Decimal("20000")),
            ComponentPositionExposure("beta", "US.AAPL", Decimal("-10000")),
        ),
    )

    decision = allocate_component_targets(portfolio, snapshot, ())

    assert decision.gross_exposure_fraction == Decimal("0.6")
    assert decision.net_exposure_fraction == Decimal("0.2")
    assert decision.proposed_instrument_targets[0].target_fraction_of_equity == Decimal("0.2")
    assert decision.proposed_instrument_targets[0].target_signed_base_notional == Decimal("10000.0")
    assert decision.risk_limits_satisfied


def test_current_shorts_and_open_instrument_count_are_shared_risk_breaches() -> None:
    portfolio = _portfolio(
        SharedRiskPolicy(max_open_instruments=2),
    )
    decision = allocate_component_targets(
        portfolio,
        _snapshot(
            portfolio,
            positions=(
                ComponentPositionExposure("alpha", "US.AAPL", Decimal("-10000")),
                ComponentPositionExposure("beta", "US.MSFT", Decimal("10000")),
                ComponentPositionExposure("beta", "US.NVDA", Decimal(0)),
            ),
        ),
        (),
    )

    assert not decision.risk_limits_satisfied
    assert decision.risk_breaches == (RiskBreach.SHORT_POSITION,)
    assert decision.open_instrument_count == 2
    assert decision.risk_approved_instrument_targets == ()


def test_allocator_rejects_wrong_event_or_portfolio_and_undeclared_current_instrument() -> None:
    portfolio = _portfolio()
    with pytest.raises(ValueError, match="match the exposure snapshot event"):
        allocate_component_targets(
            portfolio, _snapshot(portfolio), (_request("alpha", "US.AAPL", "0.5", sequence=11),)
        )
    with pytest.raises(ValueError, match="does not belong to this portfolio"):
        allocate_component_targets(
            portfolio,
            PortfolioExposureSnapshot(
                content_digest("different-portfolio"),
                "allocation-test-attempt",
                EVENT_TIME,
                10,
                Decimal("100000"),
                Decimal("50000"),
                "USD",
                VALUATION_DIGEST,
            ),
            (),
        )
    with pytest.raises(ValueError, match="holds undeclared instrument"):
        allocate_component_targets(
            portfolio,
            _snapshot(
                portfolio,
                positions=(
                    ComponentPositionExposure("alpha", "US.MSFT", Decimal("1000")),
                ),
            ),
            (),
        )


def test_raw_order_intents_and_duplicate_component_targets_fail_closed() -> None:
    portfolio = _portfolio()
    with pytest.raises(ValueError, match="raw OrderIntent sizing requires"):
        component_targets_from_intents(
            portfolio,
            {"alpha": (OrderIntent("US.AAPL", OrderSide.BUY, Decimal("1")),)},
            event_time=EVENT_TIME,
            event_sequence=10,
        )
    with pytest.raises(ValueError, match="only once per event"):
        component_targets_from_intents(
            portfolio,
            {
                "alpha": (
                    TargetPositionIntent("US.AAPL", Decimal("0.2")),
                    TargetPositionIntent("US.AAPL", Decimal("0.3")),
                )
            },
            event_time=EVENT_TIME,
            event_sequence=10,
        )


def test_risk_policy_validation_rejects_nonfinite_limits_and_boolean_priority() -> None:
    with pytest.raises(ValueError, match="finite positive"):
        SharedRiskPolicy(max_gross_exposure_fraction=Decimal("NaN"))
    with pytest.raises(ValueError, match="non-negative integer"):
        PortfolioComponent(
            "alpha", content_digest("alpha"), ("US.AAPL",), Decimal("1"), priority=True
        )
