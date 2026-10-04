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


@dataclass(frozen=True, slots=True)
class NautilusComponentOrderRoutingResolution:
    """One shared-account decision with approved intents retained by component."""

    exposure_snapshot: PortfolioExposureSnapshot
    decision: OrderRoutingDecision
    component_order_intents: tuple[tuple[str, tuple[OrderIntent, ...]], ...]

    @property
    def order_intents(self) -> tuple[OrderIntent, ...]:
        """Return the approved intents in deterministic component order."""

        return tuple(
            intent for _component_id, intents in self.component_order_intents for intent in intents
        )


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
        current_component_exposures={component_id: current_base_exposures},
    )
    return NautilusOrderRoutingResolution(
        resolution.exposure_snapshot,
        resolution.decision,
        resolution.order_intents,
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
) -> NautilusComponentOrderRoutingResolution:
    """Apply one shared-risk decision to native-backed batches from all components.

    The first runtime bridge intentionally enables only base-quoted cash
    equities and crypto spot. Other products require product-specific native
    risk inputs such as FX conversion, option delta, or contract economics and
    remain fail-closed until those values are part of the exact adapter input.
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

    intents_by_identity = {
        (component_id, content_digest(intent)): intent
        for component_id, component_intents in batches.items()
        for intent in component_intents
    }
    try:
        approved_by_component: dict[str, list[OrderIntent]] = {
            component_id: [] for component_id in batches
        }
        for routed_order in decision.risk_approved_orders:
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
    return NautilusComponentOrderRoutingResolution(snapshot, decision, approved)


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
