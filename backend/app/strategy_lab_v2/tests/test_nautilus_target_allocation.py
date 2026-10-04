from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    PortfolioComponent,
    PortfolioComposition,
    SharedRiskPolicy,
)
from app.strategy_lab_v2.nautilus_order_routing import resolve_nautilus_component_order_batches
from app.strategy_lab_v2.nautilus_portfolio_wire import (
    portfolio_composition_from_wire,
    portfolio_composition_to_wire,
)
from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError
from app.strategy_lab_v2.nautilus_target_allocation import (
    resolve_nautilus_component_target_position_batches,
    resolve_nautilus_target_position_intents,
)
from app.strategy_lab_v2.sdk import (
    OrderIntent,
    OrderSide,
    OrderType,
    TargetPositionIntent,
    TimeInForce,
)

EVENT_TIME = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)


def _portfolio(*, max_gross: Decimal = Decimal("1")) -> PortfolioComposition:
    return PortfolioComposition(
        portfolio_id="portfolio-1",
        version_id="portfolio-v1",
        initial_capital=Decimal("100000"),
        base_currency="USD",
        components=(
            PortfolioComponent(
                component_id="core",
                strategy_fingerprint=content_digest("strategy"),
                instrument_ids=("US.AAPL",),
                capital_weight=Decimal("1"),
            ),
        ),
        shared_risk_policy=SharedRiskPolicy(
            max_gross_exposure_fraction=max_gross,
            risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,),
        ),
    )


def _instruments(*, quote_currency: str = "USD") -> dict[str, dict[str, object]]:
    return {
        "US.AAPL": {
            "instrument_id": "US.AAPL",
            "product_class": "equity",
            "quote_currency": quote_currency,
            "multiplier": "1",
            "price_increment": "0.01",
            "size_increment": "1",
            "size_precision": 0,
            "min_quantity": "1",
            "max_quantity": None,
        }
    }


def _multi_portfolio(*, max_gross: Decimal = Decimal("1")) -> PortfolioComposition:
    return PortfolioComposition(
        portfolio_id="portfolio-multi",
        version_id="portfolio-multi-v1",
        initial_capital=Decimal("100000"),
        base_currency="USD",
        components=(
            PortfolioComponent(
                component_id="core",
                strategy_fingerprint=content_digest("strategy-core"),
                instrument_ids=("US.AAPL",),
                capital_weight=Decimal("0.5"),
                priority=0,
            ),
            PortfolioComponent(
                component_id="satellite",
                strategy_fingerprint=content_digest("strategy-satellite"),
                instrument_ids=("US.MSFT",),
                capital_weight=Decimal("0.5"),
                priority=1,
            ),
        ),
        shared_risk_policy=SharedRiskPolicy(
            max_gross_exposure_fraction=max_gross,
            risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,),
        ),
    )


def _multi_target_resolution(*, max_gross: Decimal = Decimal("1")):
    portfolio = _multi_portfolio(max_gross=max_gross)
    instruments = {
        **_instruments(),
        "US.MSFT": {
            "instrument_id": "US.MSFT",
            "product_class": "equity",
            "quote_currency": "USD",
            "multiplier": "1",
            "size_increment": "1",
            "size_precision": 0,
            "min_quantity": "1",
            "max_quantity": None,
        },
    }
    empty_ledger: dict[str, dict[str, Decimal]] = {"core": {}, "satellite": {}}
    return resolve_nautilus_component_target_position_batches(
        portfolio=portfolio,
        intents_by_component={
            "core": (TargetPositionIntent("US.AAPL", Decimal("0.4")),),
            "satellite": (TargetPositionIntent("US.MSFT", Decimal("0.4")),),
        },
        run_attempt_id="attempt-multi",
        event_time=EVENT_TIME,
        event_sequence=5,
        account_equity=Decimal("100000"),
        account_cash_balance=Decimal("100000"),
        current_base_exposures={},
        current_quantities={},
        current_component_exposures=empty_ledger,
        current_component_quantities=empty_ledger,
        mark_prices={"US.AAPL": Decimal("200"), "US.MSFT": Decimal("100")},
        instruments=instruments,
    )


def _resolve(
    *,
    portfolio: PortfolioComposition | None = None,
    fraction: Decimal = Decimal("0.5"),
    current_quantity: Decimal = Decimal(0),
    current_exposure: Decimal = Decimal(0),
    quote_currency: str = "USD",
):
    selected_portfolio = portfolio or _portfolio()
    return resolve_nautilus_target_position_intents(
        portfolio=selected_portfolio,
        component_id="core",
        intents=(TargetPositionIntent("US.AAPL", fraction),),
        run_attempt_id="attempt-1",
        event_time=EVENT_TIME,
        event_sequence=4,
        account_equity=Decimal("100000"),
        account_cash_balance=Decimal("100000"),
        current_base_exposures=({} if current_exposure == 0 else {"US.AAPL": current_exposure}),
        current_quantities={"US.AAPL": current_quantity},
        mark_prices={"US.AAPL": Decimal("200")},
        instruments=_instruments(quote_currency=quote_currency),
    )


def test_portfolio_allocation_policy_round_trips_with_exact_fingerprint() -> None:
    portfolio = _portfolio()
    restored = portfolio_composition_from_wire(portfolio_composition_to_wire(portfolio))

    assert restored == portfolio
    tampered = portfolio_composition_to_wire(portfolio)
    tampered["shared_risk_policy"]["max_gross_exposure_fraction"] = "2"
    with pytest.raises(ValueError, match="fingerprint"):
        portfolio_composition_from_wire(tampered)


def test_target_fraction_is_allocated_then_translated_to_a_lot_sized_market_order() -> None:
    result = _resolve()

    assert result.allocation.risk_limits_satisfied is True
    assert result.allocation.risk_approved_instrument_targets[0].target_signed_base_notional == (
        Decimal("50000")
    )
    assert len(result.order_intents) == 1
    assert result.order_intents[0].side is OrderSide.BUY
    assert result.order_intents[0].quantity == Decimal("250")


def test_target_allocation_submits_only_the_delta_from_native_position() -> None:
    result = _resolve(current_quantity=Decimal("50"), current_exposure=Decimal("10000"))

    assert len(result.order_intents) == 1
    assert result.order_intents[0].side is OrderSide.BUY
    assert result.order_intents[0].quantity == Decimal("200")


def test_target_allocation_fails_closed_on_shared_risk_breach() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="breaches shared portfolio risk"):
        _resolve(fraction=Decimal("1.5"))


def test_target_sizing_fails_closed_when_quote_currency_needs_conversion() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="base-quoted linear spot"):
        _resolve(quote_currency="EUR")


def test_target_allocation_fails_closed_on_short_without_policy_permission() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="breaches shared portfolio risk"):
        _resolve(fraction=Decimal("-0.1"))


def test_component_targets_share_one_allocation_and_keep_order_attribution() -> None:
    result = _multi_target_resolution()

    assert result.allocation.gross_exposure_fraction == Decimal("0.4")
    assert tuple(component_id for component_id, _orders in result.component_order_intents) == (
        "core",
        "satellite",
    )
    assert tuple(
        (orders[0].instrument_id, orders[0].quantity)
        for _component_id, orders in result.component_order_intents
    ) == (("US.AAPL", Decimal("100")), ("US.MSFT", Decimal("200")))


def test_component_target_delta_uses_its_attributed_native_quantity() -> None:
    portfolio = _multi_portfolio()
    instruments = {
        **_instruments(),
        "US.MSFT": {
            "instrument_id": "US.MSFT",
            "product_class": "equity",
            "quote_currency": "USD",
            "multiplier": "1",
            "size_increment": "1",
            "size_precision": 0,
            "min_quantity": "1",
            "max_quantity": None,
        },
    }
    result = resolve_nautilus_component_target_position_batches(
        portfolio=portfolio,
        intents_by_component={
            "core": (TargetPositionIntent("US.AAPL", Decimal("0.4")),),
            "satellite": (TargetPositionIntent("US.MSFT", Decimal("0.4")),),
        },
        run_attempt_id="attempt-multi",
        event_time=EVENT_TIME,
        event_sequence=5,
        account_equity=Decimal("100000"),
        account_cash_balance=Decimal("90000"),
        current_base_exposures={"US.AAPL": Decimal("10000")},
        current_quantities={"US.AAPL": Decimal("50")},
        current_component_exposures={
            "core": {"US.AAPL": Decimal("10000")},
            "satellite": {},
        },
        current_component_quantities={
            "core": {"US.AAPL": Decimal("50")},
            "satellite": {},
        },
        mark_prices={"US.AAPL": Decimal("200"), "US.MSFT": Decimal("100")},
        instruments=instruments,
    )

    assert tuple(
        (component_id, orders[0].instrument_id, orders[0].quantity)
        for component_id, orders in result.component_order_intents
    ) == (
        ("core", "US.AAPL", Decimal("50")),
        ("satellite", "US.MSFT", Decimal("200")),
    )


def test_component_targets_fail_closed_on_combined_shared_risk_breach() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="breaches shared portfolio risk"):
        _multi_target_resolution(max_gross=Decimal("0.3"))


def test_component_targets_and_raw_orders_share_one_combined_risk_decision() -> None:
    portfolio = _multi_portfolio(max_gross=Decimal("0.21"))
    instruments = {
        **_instruments(),
        "US.MSFT": {
            "instrument_id": "US.MSFT",
            "product_class": "equity",
            "quote_currency": "USD",
            "multiplier": "1",
            "price_increment": "0.01",
            "size_increment": "1",
            "size_precision": 0,
            "min_quantity": "1",
            "max_quantity": None,
        },
    }
    empty_ledger: dict[str, dict[str, Decimal]] = {"core": {}, "satellite": {}}
    target_resolution = resolve_nautilus_component_target_position_batches(
        portfolio=portfolio,
        intents_by_component={
            "core": (TargetPositionIntent("US.AAPL", Decimal("0.4")),),
        },
        run_attempt_id="attempt-mixed-intents",
        event_time=EVENT_TIME,
        event_sequence=5,
        account_equity=Decimal("100000"),
        account_cash_balance=Decimal("100000"),
        current_base_exposures={},
        current_quantities={},
        current_component_exposures=empty_ledger,
        current_component_quantities=empty_ledger,
        mark_prices={"US.AAPL": Decimal("200"), "US.MSFT": Decimal("100")},
        instruments=instruments,
    )
    combined_orders: dict[str, tuple[OrderIntent, ...]] = {
        "satellite": (
            OrderIntent(
                "US.MSFT",
                OrderSide.BUY,
                Decimal("10"),
                OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
            ),
        )
    }
    for component_id, target_orders in target_resolution.component_order_intents:
        combined_orders[component_id] = combined_orders.get(component_id, ()) + target_orders

    with pytest.raises(NautilusRuntimeDataError, match="breaches shared portfolio risk"):
        resolve_nautilus_component_order_batches(
            portfolio=_multi_portfolio(max_gross=Decimal("0.205")),
            intents_by_component=combined_orders,
            run_attempt_id="attempt-mixed-intents",
            event_time=EVENT_TIME,
            event_sequence=5,
            account_equity=Decimal("100000"),
            account_cash_balance=Decimal("100000"),
            current_base_exposures={},
            current_quantities={},
            current_component_exposures=empty_ledger,
            mark_prices={"US.AAPL": Decimal("200"), "US.MSFT": Decimal("100")},
            instruments=instruments,
        )

    order_resolution = resolve_nautilus_component_order_batches(
        portfolio=portfolio,
        intents_by_component=combined_orders,
        run_attempt_id="attempt-mixed-intents",
        event_time=EVENT_TIME,
        event_sequence=5,
        account_equity=Decimal("100000"),
        account_cash_balance=Decimal("100000"),
        current_base_exposures={},
        current_quantities={},
        current_component_exposures=empty_ledger,
        mark_prices={"US.AAPL": Decimal("200"), "US.MSFT": Decimal("100")},
        instruments=instruments,
    )

    assert order_resolution.decision.risk_limits_satisfied is True
    assert order_resolution.decision.gross_exposure_fraction == Decimal("0.21")
    assert tuple(
        (component_id, tuple(intent.instrument_id for intent in intents))
        for component_id, intents in order_resolution.component_order_intents
    ) == (("core", ("US.AAPL",)), ("satellite", ("US.MSFT",)))


def test_combined_risk_router_can_accept_raw_hedge_of_a_target_batch() -> None:
    portfolio = PortfolioComposition(
        portfolio_id="portfolio-offsetting-intents",
        version_id="portfolio-offsetting-intents-v1",
        initial_capital=Decimal("100000"),
        base_currency="USD",
        components=(
            PortfolioComponent(
                "core",
                content_digest("strategy-core"),
                ("US.AAPL",),
                Decimal("0.5"),
                priority=0,
            ),
            PortfolioComponent(
                "satellite",
                content_digest("strategy-satellite"),
                ("US.AAPL",),
                Decimal("0.5"),
                priority=1,
            ),
        ),
        shared_risk_policy=SharedRiskPolicy(
            max_gross_exposure_fraction=Decimal("0.4"),
            max_net_exposure_fraction=Decimal("0.01"),
            allow_short_positions=True,
            risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,),
        ),
    )
    empty_ledger: dict[str, dict[str, Decimal]] = {"core": {}, "satellite": {}}
    allocation = resolve_nautilus_component_target_position_batches(
        portfolio=portfolio,
        intents_by_component={
            "core": (TargetPositionIntent("US.AAPL", Decimal("0.4")),),
        },
        run_attempt_id="attempt-offsetting-intents",
        event_time=EVENT_TIME,
        event_sequence=5,
        account_equity=Decimal("100000"),
        account_cash_balance=Decimal("100000"),
        current_base_exposures={},
        current_quantities={},
        current_component_exposures=empty_ledger,
        current_component_quantities=empty_ledger,
        mark_prices={"US.AAPL": Decimal("200")},
        instruments=_instruments(),
        defer_shared_risk_validation=True,
    )

    assert allocation.allocation.risk_limits_satisfied is False
    target_orders = dict(allocation.component_order_intents)
    assert target_orders["core"][0].quantity == Decimal("100")
    combined = resolve_nautilus_component_order_batches(
        portfolio=portfolio,
        intents_by_component={
            "core": target_orders["core"],
            "satellite": (
                OrderIntent(
                    "US.AAPL",
                    OrderSide.SELL,
                    Decimal("100"),
                    OrderType.MARKET,
                    time_in_force=TimeInForce.DAY,
                ),
            ),
        },
        run_attempt_id="attempt-offsetting-intents",
        event_time=EVENT_TIME,
        event_sequence=5,
        account_equity=Decimal("100000"),
        account_cash_balance=Decimal("100000"),
        current_base_exposures={},
        current_quantities={},
        current_component_exposures=empty_ledger,
        mark_prices={"US.AAPL": Decimal("200")},
        instruments=_instruments(),
    )

    assert combined.decision.risk_limits_satisfied is True
    assert combined.decision.gross_exposure_fraction == Decimal("0.4")
    assert combined.decision.net_exposure_fraction == Decimal(0)
    assert tuple(component_id for component_id, _orders in combined.component_order_intents) == (
        "core",
        "satellite",
    )


def test_component_target_positions_must_reconcile_to_native_account() -> None:
    portfolio = _multi_portfolio()
    empty_ledger: dict[str, dict[str, Decimal]] = {"core": {}, "satellite": {}}
    with pytest.raises(NautilusRuntimeDataError, match="do not reconcile"):
        resolve_nautilus_component_target_position_batches(
            portfolio=portfolio,
            intents_by_component={"core": (TargetPositionIntent("US.AAPL", Decimal("0.2")),)},
            run_attempt_id="attempt-multi",
            event_time=EVENT_TIME,
            event_sequence=5,
            account_equity=Decimal("100000"),
            account_cash_balance=Decimal("99000"),
            current_base_exposures={"US.AAPL": Decimal("1000")},
            current_quantities={"US.AAPL": Decimal("5")},
            current_component_exposures=empty_ledger,
            current_component_quantities=empty_ledger,
            mark_prices={"US.AAPL": Decimal("200")},
            instruments=_instruments(),
        )
