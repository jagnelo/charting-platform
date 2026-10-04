"""Bridge exact native valuation evidence into the platform order-risk gate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from typing import Any

from app.strategy_lab_v2.allocation import (
    ComponentPositionExposure,
    InstrumentRiskBinding,
    PortfolioExposureSnapshot,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    CRYPTO_SPOT_NOTIONAL_RISK_MODEL,
    FUTURE_CONTRACT_NOTIONAL_RISK_MODEL,
    PortfolioComposition,
    ProductClass,
)
from app.strategy_lab_v2.margin_risk import (
    MarginCapacitySnapshot,
    MarginRiskDecision,
    MarginRiskPolicy,
    apply_margin_risk_gate,
)
from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError
from app.strategy_lab_v2.order_routing import (
    InstrumentOrderEconomics,
    OrderRoutingDecision,
    route_order_intents,
)
from app.strategy_lab_v2.sdk import OrderIntent


@dataclass(frozen=True, slots=True)
class NautilusOrderRoutingResolution:
    """Pre-trade risk evidence and the exact approved SDK intents."""

    exposure_snapshot: PortfolioExposureSnapshot
    decision: OrderRoutingDecision
    order_intents: tuple[OrderIntent, ...]
    margin_decision: MarginRiskDecision | None = None


@dataclass(frozen=True, slots=True)
class NautilusComponentOrderRoutingResolution:
    """One shared-account decision with approved intents retained by component."""

    exposure_snapshot: PortfolioExposureSnapshot
    decision: OrderRoutingDecision
    component_order_intents: tuple[tuple[str, tuple[OrderIntent, ...]], ...]
    margin_decision: MarginRiskDecision | None = None

    @property
    def order_intents(self) -> tuple[OrderIntent, ...]:
        """Return the approved intents in deterministic component order."""

        return tuple(
            intent for _component_id, intents in self.component_order_intents for intent in intents
        )


def _native_money_amount(value: Any, *, currency_code: str, field_name: str) -> Decimal:
    currency = getattr(value, "currency", None)
    observed_currency = getattr(currency, "code", None)
    as_decimal = getattr(value, "as_decimal", None)
    if observed_currency != currency_code or not callable(as_decimal):
        raise NautilusRuntimeDataError(
            f"native {field_name} does not resolve to exact {currency_code} money"
        )
    amount = as_decimal()
    if not isinstance(amount, Decimal) or not amount.is_finite():
        raise NautilusRuntimeDataError(f"native {field_name} is not a finite decimal")
    return amount


def _native_futures_margin_decision(
    *,
    portfolio: PortfolioComposition,
    account_type: str,
    native_margin_account: Any | None,
    native_instruments: Mapping[str, Any] | None,
    current_quantities: Mapping[str, Decimal],
    mark_prices: Mapping[str, Decimal],
    margin_prices: Mapping[str, Decimal] | None,
    instrument_definitions: Mapping[str, Mapping[str, object]],
    routing_decision: OrderRoutingDecision,
    account_equity: Decimal,
    event_time: datetime,
    event_sequence: int,
) -> MarginRiskDecision:
    """Use RC5's native margin calculator for the post-order futures positions."""

    if account_type.upper() != "MARGIN":
        raise NautilusRuntimeDataError("native futures order admission requires a margin account")
    account = native_margin_account
    if account is None or not callable(getattr(account, "is_margin_account", None)):
        raise NautilusRuntimeDataError("native futures order admission has no margin account")
    if not account.is_margin_account():
        raise NautilusRuntimeDataError(
            "native futures order admission account is not margin-enabled"
        )
    account_currency = getattr(account, "base_currency", None)
    if getattr(account_currency, "code", None) != portfolio.base_currency:
        raise NautilusRuntimeDataError("native futures margin account currency differs")
    instruments = native_instruments
    if not isinstance(instruments, Mapping):
        raise NautilusRuntimeDataError("native futures order admission has no native instruments")

    from nautilus_trader.model import (  # type: ignore[import-not-found,attr-defined]
        Currency,
        InstrumentId,
        Price,
        Quantity,
    )

    currency = Currency.from_str(portfolio.base_currency)
    try:
        current_initial = _native_money_amount(
            account.total_initial_margin(currency),
            currency_code=portfolio.base_currency,
            field_name="initial margin requirement",
        )
        current_maintenance = _native_money_amount(
            account.total_maintenance_margin(currency),
            currency_code=portfolio.base_currency,
            field_name="maintenance margin requirement",
        )
        balance_capacity = _native_money_amount(
            account.balance_total(currency),
            currency_code=portfolio.base_currency,
            field_name="margin capacity",
        )
    except Exception as error:
        if isinstance(error, NautilusRuntimeDataError):
            raise
        raise NautilusRuntimeDataError(
            "native margin account did not provide complete currency-bound requirements"
        ) from error
    if current_initial < 0 or current_maintenance < 0 or balance_capacity <= 0:
        raise NautilusRuntimeDataError(
            "native margin account returned invalid requirements or capacity"
        )
    if not isinstance(account_equity, Decimal) or not account_equity.is_finite():
        raise NautilusRuntimeDataError("native margin capacity has no finite account equity")
    capacity = min(balance_capacity, account_equity)
    if capacity <= 0:
        raise NautilusRuntimeDataError("native futures margin capacity is not positive")

    future_ids = {
        instrument_id
        for instrument_id, definition in instrument_definitions.items()
        if _product_class(definition) is ProductClass.FUTURE
        and (
            current_quantities.get(instrument_id, Decimal(0)) != 0
            or any(
                order.instrument_id == instrument_id for order in routing_decision.proposed_orders
            )
        )
    }
    orders_by_instrument: dict[str, list[Any]] = {item: [] for item in future_ids}
    projected_quantities = {
        instrument_id: current_quantities.get(instrument_id, Decimal(0))
        for instrument_id in future_ids
    }
    for order in routing_decision.proposed_orders:
        if order.instrument_id not in future_ids:
            continue
        signed_quantity = order.quantity if order.side.value == "buy" else -order.quantity
        projected_quantities[order.instrument_id] += signed_quantity
        orders_by_instrument[order.instrument_id].append(order)

    existing_future_initial = Decimal(0)
    existing_future_maintenance = Decimal(0)
    projected_future_initial = Decimal(0)
    projected_future_maintenance = Decimal(0)
    margin_evidence: dict[str, object] = {}
    if not isinstance(margin_prices, Mapping):
        raise NautilusRuntimeDataError(
            "native futures margin requires event-aligned execution-price evidence"
        )
    adverse_prices = margin_prices
    for instrument_id in sorted(future_ids):
        definition = instrument_definitions[instrument_id]
        if definition.get("quote_currency") != portfolio.base_currency:
            raise NautilusRuntimeDataError(
                "native futures margin currently requires base-currency contract settlement"
            )
        native_instrument = instruments.get(instrument_id)
        if native_instrument is None or str(getattr(native_instrument, "id", "")) != instrument_id:
            raise NautilusRuntimeDataError("native futures margin instrument identity differs")
        native_id = InstrumentId.from_str(instrument_id)
        initial_calculator = getattr(account, "calculate_initial_margin", None)
        maintenance_calculator = getattr(account, "calculate_maintenance_margin", None)
        if not callable(initial_calculator) or not callable(maintenance_calculator):
            raise NautilusRuntimeDataError("native account has no futures margin calculator")

        current_quantity = current_quantities.get(instrument_id, Decimal(0))
        if current_quantity:
            native_current_initial = account.initial_margin(native_id)
            if native_current_initial is None:
                raise NautilusRuntimeDataError(
                    "native account omitted initial margin for an open futures position"
                )
            existing_future_initial += _native_money_amount(
                native_current_initial,
                currency_code=portfolio.base_currency,
                field_name="position initial margin",
            )
            native_current_maintenance = account.maintenance_margin(native_id)
            if native_current_maintenance is None:
                raise NautilusRuntimeDataError(
                    "native account omitted maintenance margin for an open futures position"
                )
            existing_future_maintenance += _native_money_amount(
                native_current_maintenance,
                currency_code=portfolio.base_currency,
                field_name="position maintenance margin",
            )

        if not projected_quantities[instrument_id]:
            margin_evidence[instrument_id] = {
                "current_quantity": current_quantity,
                "projected_quantity": Decimal(0),
                "margin_price": None,
                "initial_margin": Decimal(0),
                "maintenance_margin": Decimal(0),
            }
            continue

        price_value = adverse_prices.get(instrument_id)
        price_tick = _decimal_field(definition, "price_increment")
        size_precision = definition.get("size_precision")
        price_precision = definition.get("price_precision")
        if (
            not isinstance(price_value, Decimal)
            or not price_value.is_finite()
            or price_value <= 0
            or price_tick is None
            or price_tick <= 0
            or not isinstance(size_precision, int)
            or isinstance(size_precision, bool)
            or not isinstance(price_precision, int)
            or isinstance(price_precision, bool)
        ):
            raise NautilusRuntimeDataError(
                "native futures margin requires an exact event-aligned price and lot definition"
            )
        for order in orders_by_instrument[instrument_id]:
            if order.order_type.value == "stop_market":
                raise NautilusRuntimeDataError(
                    "native futures stop-market orders lack a bounded margin price"
                )
            if order.order_type.value in {"limit", "stop_limit"}:
                if order.limit_price is None or order.limit_price <= 0:
                    raise NautilusRuntimeDataError(
                        "native futures limit orders require an explicit positive limit price"
                    )
                price_value = max(price_value, order.limit_price)
            elif order.order_type.value != "market":
                raise NautilusRuntimeDataError("native futures order type has no margin policy")
        rounded_price = (price_value / price_tick).to_integral_value(
            rounding=ROUND_CEILING
        ) * price_tick
        precision = Decimal(1).scaleb(-price_precision)
        if rounded_price != rounded_price.quantize(precision):
            raise NautilusRuntimeDataError(
                "native futures margin price cannot be represented exactly"
            )
        native_quantity = Quantity(abs(projected_quantities[instrument_id]), size_precision)
        native_price = Price(rounded_price, price_precision)
        try:
            initial_amount = _native_money_amount(
                initial_calculator(native_instrument, native_quantity, native_price),
                currency_code=portfolio.base_currency,
                field_name="projected initial margin",
            )
            maintenance_amount = _native_money_amount(
                maintenance_calculator(native_instrument, native_quantity, native_price),
                currency_code=portfolio.base_currency,
                field_name="projected maintenance margin",
            )
        except Exception as error:
            if isinstance(error, NautilusRuntimeDataError):
                raise
            raise NautilusRuntimeDataError(
                "native futures margin calculator rejected the projected position"
            ) from error
        if initial_amount < 0 or maintenance_amount < 0 or maintenance_amount > initial_amount:
            raise NautilusRuntimeDataError(
                "native futures margin calculator returned invalid terms"
            )
        projected_future_initial += initial_amount
        projected_future_maintenance += maintenance_amount
        margin_evidence[instrument_id] = {
            "current_quantity": current_quantity,
            "projected_quantity": projected_quantities[instrument_id],
            "margin_price": rounded_price,
            "initial_margin": initial_amount,
            "maintenance_margin": maintenance_amount,
            "order_fingerprints": tuple(
                order.fingerprint for order in orders_by_instrument[instrument_id]
            ),
        }

    if existing_future_initial > current_initial:
        raise NautilusRuntimeDataError(
            "native per-instrument futures initial exceeds the account requirement"
        )
    if existing_future_maintenance > current_maintenance:
        raise NautilusRuntimeDataError(
            "native per-instrument futures maintenance exceeds the account requirement"
        )
    projected_initial = current_initial - existing_future_initial + projected_future_initial
    projected_maintenance = (
        current_maintenance - existing_future_maintenance + projected_future_maintenance
    )
    evidence_digest = content_digest(
        {
            "account_currency": portfolio.base_currency,
            "account_initial_margin": current_initial,
            "account_maintenance_margin": current_maintenance,
            "account_balance_capacity": balance_capacity,
            "account_equity_capacity": account_equity,
            "futures": margin_evidence,
            "portfolio_fingerprint": portfolio.fingerprint,
            "routing_fingerprint": routing_decision.fingerprint,
            "event_time": event_time,
            "event_sequence": event_sequence,
        }
    )
    margin_snapshot = MarginCapacitySnapshot(
        portfolio_fingerprint=routing_decision.portfolio_fingerprint,
        exposure_snapshot_fingerprint=routing_decision.exposure_snapshot_fingerprint,
        event_time=event_time,
        event_sequence=event_sequence,
        base_currency=portfolio.base_currency,
        initial_requirement=projected_initial,
        maintenance_requirement=projected_maintenance,
        initial_capacity=capacity,
        maintenance_capacity=capacity,
        valuation_evidence_digest=evidence_digest,
    )
    margin_decision = apply_margin_risk_gate(
        routing_decision,
        margin_snapshot,
        MarginRiskPolicy(),
    )
    if not margin_decision.risk_limits_satisfied:
        raise NautilusRuntimeDataError("native futures order batch breaches shared margin capacity")
    return margin_decision


def resolve_nautilus_order_intents(
    *,
    portfolio: PortfolioComposition,
    component_id: str,
    intents: Sequence[OrderIntent],
    run_attempt_id: str,
    event_time: datetime,
    event_sequence: int,
    account_equity: Decimal,
    account_cash_balance: Decimal,
    current_base_exposures: Mapping[str, Decimal],
    current_quantities: Mapping[str, Decimal],
    mark_prices: Mapping[str, Decimal],
    instruments: Mapping[str, Mapping[str, object]],
    account_type: str = "CASH",
    margin_prices: Mapping[str, Decimal] | None = None,
    native_margin_account: Any | None = None,
    native_instruments: Mapping[str, Any] | None = None,
) -> NautilusOrderRoutingResolution:
    """Compatibility wrapper for one component's native-backed order batch."""

    resolution = resolve_nautilus_component_order_batches(
        portfolio=portfolio,
        intents_by_component={component_id: intents},
        run_attempt_id=run_attempt_id,
        event_time=event_time,
        event_sequence=event_sequence,
        account_equity=account_equity,
        account_cash_balance=account_cash_balance,
        current_base_exposures=current_base_exposures,
        current_quantities=current_quantities,
        mark_prices=mark_prices,
        instruments=instruments,
        account_type=account_type,
        margin_prices=margin_prices,
        native_margin_account=native_margin_account,
        native_instruments=native_instruments,
        current_component_exposures={component_id: current_base_exposures},
    )
    return NautilusOrderRoutingResolution(
        resolution.exposure_snapshot,
        resolution.decision,
        resolution.order_intents,
        resolution.margin_decision,
    )


def resolve_nautilus_component_order_batches(
    *,
    portfolio: PortfolioComposition,
    intents_by_component: Mapping[str, Sequence[OrderIntent]],
    run_attempt_id: str,
    event_time: datetime,
    event_sequence: int,
    account_equity: Decimal,
    account_cash_balance: Decimal,
    current_base_exposures: Mapping[str, Decimal],
    current_quantities: Mapping[str, Decimal],
    mark_prices: Mapping[str, Decimal],
    instruments: Mapping[str, Mapping[str, object]],
    current_component_exposures: Mapping[str, Mapping[str, Decimal]],
    account_type: str = "CASH",
    margin_prices: Mapping[str, Decimal] | None = None,
    native_margin_account: Any | None = None,
    native_instruments: Mapping[str, Any] | None = None,
) -> NautilusComponentOrderRoutingResolution:
    """Apply one shared-risk decision to native-backed batches from all components.

    The runtime bridge enables base-quoted cash equities and crypto spot, plus
    listed futures on a native margin account after its exact account and
    instrument calculators approve the projected position. Other products
    require product-specific risk inputs such as FX conversion or option delta
    and remain fail-closed until those values are part of the exact adapter input.
    """

    if not isinstance(portfolio, PortfolioComposition):
        raise TypeError("portfolio must be a PortfolioComposition")
    if not isinstance(intents_by_component, Mapping) or not intents_by_component:
        raise NautilusRuntimeDataError("native component order batches are required")
    if not isinstance(current_component_exposures, Mapping):
        raise NautilusRuntimeDataError("native component exposure attribution is required")
    components = {item.component_id: item for item in portfolio.components}
    declared = {
        instrument_id for item in portfolio.components for instrument_id in item.instrument_ids
    }
    batches: dict[str, tuple[OrderIntent, ...]] = {}
    for component_id, raw_intents in intents_by_component.items():
        if component_id not in components:
            raise NautilusRuntimeDataError("native order component is outside the portfolio")
        if not isinstance(raw_intents, Sequence) or isinstance(raw_intents, str | bytes):
            raise NautilusRuntimeDataError("native component orders must be a sequence")
        component_intents = tuple(raw_intents)
        if any(not isinstance(intent, OrderIntent) for intent in component_intents):
            raise NautilusRuntimeDataError("native order routing accepts only OrderIntent values")
        if component_intents:
            batches[component_id] = component_intents
    if not batches:
        raise NautilusRuntimeDataError("native component order batches must not be empty")

    attributed_exposures: dict[str, Decimal] = {}
    positions: list[ComponentPositionExposure] = []
    for component_id, raw_exposures in current_component_exposures.items():
        component = components.get(component_id)
        if component is None or not isinstance(raw_exposures, Mapping):
            raise NautilusRuntimeDataError("native component position attribution is invalid")
        for instrument_id, exposure in raw_exposures.items():
            if instrument_id not in component.instrument_ids:
                raise NautilusRuntimeDataError(
                    "native component attribution contains an undeclared instrument"
                )
            if not isinstance(exposure, Decimal) or not exposure.is_finite():
                raise NautilusRuntimeDataError("native component exposure is not finite")
            if exposure == 0:
                continue
            attributed_exposures[instrument_id] = (
                attributed_exposures.get(instrument_id, Decimal(0)) + exposure
            )
            positions.append(ComponentPositionExposure(component_id, instrument_id, exposure))
    normalized_account_exposures = {
        instrument_id: exposure
        for instrument_id, exposure in current_base_exposures.items()
        if exposure != 0
    }
    if (
        any(
            not isinstance(exposure, Decimal) or not exposure.is_finite()
            for exposure in current_base_exposures.values()
        )
        or attributed_exposures != normalized_account_exposures
    ):
        raise NautilusRuntimeDataError(
            "component-attributed positions do not reconcile to native account exposure"
        )
    for values, field_name in (
        (current_base_exposures, "current exposure"),
        (current_quantities, "current quantity"),
        (mark_prices, "mark price"),
    ):
        if any(instrument_id not in declared for instrument_id in values):
            raise NautilusRuntimeDataError(f"{field_name} contains an undeclared instrument")

    policy_models = {item.product_class: item for item in portfolio.shared_risk_policy.risk_models}
    bindings: list[InstrumentRiskBinding] = []
    for instrument_id in sorted(declared):
        definition = instruments.get(instrument_id)
        if definition is None:
            raise NautilusRuntimeDataError("portfolio instrument is missing native economics")
        product_class = _product_class(definition)
        model = policy_models.get(product_class)
        if model is not None:
            bindings.append(InstrumentRiskBinding(instrument_id, model))

    valuation_evidence_digest = content_digest(
        {
            "attempt_id": run_attempt_id,
            "event_time": event_time,
            "event_sequence": event_sequence,
            "account_equity": account_equity,
            "account_cash_balance": account_cash_balance,
            "current_base_exposures": dict(current_base_exposures),
            "current_quantities": dict(current_quantities),
            "mark_prices": dict(mark_prices),
            "current_component_exposures": {
                component_id: dict(exposures)
                for component_id, exposures in current_component_exposures.items()
            },
            "portfolio_fingerprint": portfolio.fingerprint,
        }
    )
    snapshot = PortfolioExposureSnapshot(
        portfolio_fingerprint=portfolio.fingerprint,
        run_attempt_id=run_attempt_id,
        event_time=event_time,
        event_sequence=event_sequence,
        account_equity=account_equity,
        account_cash_balance=account_cash_balance,
        base_currency=portfolio.base_currency,
        valuation_evidence_digest=valuation_evidence_digest,
        positions=tuple(positions),
        instrument_risk_models=tuple(bindings),
    )

    economics: dict[str, InstrumentOrderEconomics] = {}
    for component_intents in batches.values():
        for intent in component_intents:
            definition = instruments.get(intent.instrument_id)
            mark_price = mark_prices.get(intent.instrument_id)
            if definition is None or mark_price is None or mark_price <= 0:
                raise NautilusRuntimeDataError(
                    "native order requires exact instrument and mark evidence"
                )
            product_class = _product_class(definition)
            model = policy_models.get(product_class)
            quote_currency = definition.get("quote_currency")
            base_currency = definition.get("base_currency")
            multiplier = _decimal_field(definition, "multiplier")
            quantity_step = _decimal_field(definition, "size_increment")
            price_tick = _decimal_field(definition, "price_increment")
            size_precision = definition.get("size_precision")
            minimum_quantity = _optional_decimal_field(definition, "min_quantity")
            maximum_quantity = _optional_decimal_field(definition, "max_quantity")
            is_future = product_class is ProductClass.FUTURE
            if is_future:
                margin_init = _decimal_field(definition, "margin_init")
                margin_maint = _decimal_field(definition, "margin_maint")
                supported_model = model == FUTURE_CONTRACT_NOTIONAL_RISK_MODEL
                complete_margin_terms = (
                    margin_init is not None
                    and margin_init > 0
                    and margin_maint is not None
                    and margin_maint > 0
                    and margin_maint <= margin_init
                )
            else:
                margin_init = None
                margin_maint = None
                supported_model = (
                    product_class is ProductClass.EQUITY
                    and model == CASH_EQUITY_NOTIONAL_RISK_MODEL
                ) or (
                    product_class is ProductClass.CRYPTO
                    and model == CRYPTO_SPOT_NOTIONAL_RISK_MODEL
                )
                complete_margin_terms = False
            if (
                not supported_model
                or model is None
                or quote_currency != portfolio.base_currency
                or multiplier is None
                or (not is_future and multiplier != Decimal(1))
                or quantity_step is None
                or price_tick is None
                or not isinstance(size_precision, int)
                or isinstance(size_precision, bool)
                or (is_future and (base_currency is not None or not complete_margin_terms))
                or (
                    product_class is ProductClass.CRYPTO
                    and (not isinstance(base_currency, str) or not base_currency.strip())
                )
            ):
                message = (
                    "native futures orders require base-quoted linear contracts and complete margin terms"
                    if is_future
                    else "native order economics require base-quoted linear cash equity or crypto spot"
                )
                raise NautilusRuntimeDataError(message)
            if is_future and (size_precision != 0 or quantity_step != Decimal(1)):
                raise NautilusRuntimeDataError("native futures orders require whole-contract lots")
            if maximum_quantity is not None and intent.quantity > maximum_quantity:
                raise NautilusRuntimeDataError("native order quantity exceeds instrument maximum")
            if intent.quantity != intent.quantity.quantize(Decimal(1).scaleb(-size_precision)):
                raise NautilusRuntimeDataError("native order quantity exceeds instrument precision")
            minimum = max(minimum_quantity or quantity_step, quantity_step)
            economics[intent.instrument_id] = InstrumentOrderEconomics(
                instrument_id=intent.instrument_id,
                risk_model=model,
                mark_price=mark_price,
                contract_multiplier=multiplier,
                quantity_step=quantity_step,
                minimum_quantity=minimum,
                quote_currency=str(quote_currency),
                base_currency=portfolio.base_currency,
                quote_to_base_rate=Decimal(1),
                valuation_evidence_digest=valuation_evidence_digest,
                price_tick=price_tick,
            )

    try:
        decision = route_order_intents(
            portfolio,
            snapshot,
            batches,
            economics,
            event_time=event_time,
            event_sequence=event_sequence,
        )
    except (TypeError, ValueError) as error:
        raise NautilusRuntimeDataError(
            "native order risk routing could not be validated"
        ) from error
    if not decision.risk_limits_satisfied:
        raise NautilusRuntimeDataError("native order batch breaches shared portfolio risk")

    future_order_ids = {
        order.instrument_id
        for order in decision.proposed_orders
        if _product_class(instruments[order.instrument_id]) is ProductClass.FUTURE
    }
    open_future_ids = {
        instrument_id
        for instrument_id, quantity in current_quantities.items()
        if quantity and _product_class(instruments[instrument_id]) is ProductClass.FUTURE
    }
    margin_decision = None
    if future_order_ids or open_future_ids:
        if not isinstance(account_type, str) or not account_type.strip():
            raise NautilusRuntimeDataError("native futures order admission account type is invalid")
        margin_decision = _native_futures_margin_decision(
            portfolio=portfolio,
            account_type=account_type,
            native_margin_account=native_margin_account,
            native_instruments=native_instruments,
            current_quantities=current_quantities,
            mark_prices=mark_prices,
            margin_prices=margin_prices,
            instrument_definitions=instruments,
            routing_decision=decision,
            account_equity=account_equity,
            event_time=event_time,
            event_sequence=event_sequence,
        )

    intents_by_identity = {
        (component_id, content_digest(intent)): intent
        for component_id, component_intents in batches.items()
        for intent in component_intents
    }
    try:
        approved_by_component: dict[str, list[OrderIntent]] = {
            component_id: [] for component_id in batches
        }
        approved_orders = (
            decision.risk_approved_orders
            if margin_decision is None
            else margin_decision.risk_approved_orders
        )
        for routed_order in approved_orders:
            approved_by_component[routed_order.component_id].append(
                intents_by_identity[(routed_order.component_id, routed_order.intent_fingerprint)]
            )
    except KeyError as error:  # pragma: no cover - adapter invariant
        raise NautilusRuntimeDataError(
            "approved native order differs from its SDK intent"
        ) from error
    approved = tuple(
        (
            component_id,
            tuple(
                sorted(
                    component_intents,
                    key=lambda intent: (
                        content_digest(intent),
                        intent.instrument_id,
                        intent.side.value,
                    ),
                )
            ),
        )
        for component_id, component_intents in sorted(approved_by_component.items())
        if component_intents
    )
    if sum(len(component_intents) for _, component_intents in approved) != sum(
        len(component_intents) for component_intents in batches.values()
    ):
        raise NautilusRuntimeDataError("native order risk decision did not approve the full batch")
    return NautilusComponentOrderRoutingResolution(snapshot, decision, approved, margin_decision)


def _product_class(definition: Mapping[str, object]) -> ProductClass:
    value = definition.get("product_class")
    if not isinstance(value, str):
        raise NautilusRuntimeDataError("native product class is invalid")
    try:
        return ProductClass(value)
    except ValueError as error:
        raise NautilusRuntimeDataError("native product class is unsupported") from error


def _decimal_field(definition: Mapping[str, object], field_name: str) -> Decimal | None:
    value = definition.get(field_name)
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, str):
        try:
            parsed = Decimal(value)
        except Exception:
            return None
        return parsed if parsed.is_finite() else None
    return None


def _optional_decimal_field(definition: Mapping[str, object], field_name: str) -> Decimal | None:
    value = definition.get(field_name)
    return None if value is None else _decimal_field(definition, field_name)


__all__ = [
    "NautilusComponentOrderRoutingResolution",
    "NautilusOrderRoutingResolution",
    "resolve_nautilus_component_order_batches",
    "resolve_nautilus_order_intents",
]
