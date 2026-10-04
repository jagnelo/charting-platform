"""Bridge exact native valuation evidence into the platform order-risk gate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.strategy_lab_v2.allocation import (
    ComponentPositionExposure,
    InstrumentRiskBinding,
    PortfolioExposureSnapshot,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    CRYPTO_SPOT_NOTIONAL_RISK_MODEL,
    PortfolioComposition,
    ProductClass,
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
) -> NautilusOrderRoutingResolution:
    """Apply platform shared-risk checks to native-valuation-backed orders.

    The first runtime bridge intentionally enables only base-quoted cash
    equities and crypto spot. Other products require product-specific native
    risk inputs such as FX conversion, option delta, or contract economics and
    remain fail-closed until those values are part of the exact adapter input.
    """

    if not isinstance(portfolio, PortfolioComposition):
        raise TypeError("portfolio must be a PortfolioComposition")
    if any(not isinstance(intent, OrderIntent) for intent in intents):
        raise NautilusRuntimeDataError("native order routing accepts only OrderIntent values")
    component = next(
        (item for item in portfolio.components if item.component_id == component_id), None
    )
    if component is None:
        raise NautilusRuntimeDataError("native order component is outside the portfolio")
    declared = set(component.instrument_ids)
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

    positions = tuple(
        ComponentPositionExposure(component_id, instrument_id, exposure)
        for instrument_id, exposure in sorted(current_base_exposures.items())
        if exposure != 0
    )
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
        positions=positions,
        instrument_risk_models=tuple(bindings),
    )

    economics: dict[str, InstrumentOrderEconomics] = {}
    for intent in intents:
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
        supported_model = (
            product_class is ProductClass.EQUITY and model == CASH_EQUITY_NOTIONAL_RISK_MODEL
        ) or (product_class is ProductClass.CRYPTO and model == CRYPTO_SPOT_NOTIONAL_RISK_MODEL)
        if (
            not supported_model
            or model is None
            or quote_currency != portfolio.base_currency
            or multiplier != Decimal(1)
            or quantity_step is None
            or price_tick is None
            or not isinstance(size_precision, int)
            or isinstance(size_precision, bool)
            or (
                product_class is ProductClass.CRYPTO
                and (not isinstance(base_currency, str) or not base_currency.strip())
            )
        ):
            raise NautilusRuntimeDataError(
                "native order economics require base-quoted linear cash equity or crypto spot"
            )
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
            {component_id: intents},
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

    intent_by_fingerprint = {content_digest(intent): intent for intent in intents}
    try:
        approved = tuple(
            intent_by_fingerprint[item.intent_fingerprint] for item in decision.risk_approved_orders
        )
    except KeyError as error:  # pragma: no cover - adapter invariant
        raise NautilusRuntimeDataError(
            "approved native order differs from its SDK intent"
        ) from error
    if len(approved) != len(intents):
        raise NautilusRuntimeDataError("native order risk decision did not approve the full batch")
    return NautilusOrderRoutingResolution(snapshot, decision, approved)


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


__all__ = ["NautilusOrderRoutingResolution", "resolve_nautilus_order_intents"]
