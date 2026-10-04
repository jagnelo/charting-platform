"""Fail-closed translation from approved target weights to native order intents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from app.strategy_lab_v2.allocation import (
    AllocationDecision,
    AllocationRejectionCode,
    ComponentPositionExposure,
    InstrumentRiskBinding,
    PortfolioExposureSnapshot,
    allocate_component_targets,
    component_targets_from_intents,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    CRYPTO_SPOT_NOTIONAL_RISK_MODEL,
    FUTURE_CONTRACT_NOTIONAL_RISK_MODEL,
    PortfolioComposition,
    ProductClass,
)
from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError
from app.strategy_lab_v2.sdk import OrderIntent, OrderSide, OrderType, TargetPositionIntent


@dataclass(frozen=True, slots=True)
class NautilusTargetAllocationResolution:
    """Auditable allocation snapshot, risk decision, and native-ready intents."""

    exposure_snapshot: PortfolioExposureSnapshot
    allocation: AllocationDecision
    order_intents: tuple[OrderIntent, ...]


@dataclass(frozen=True, slots=True)
class NautilusComponentTargetAllocationResolution:
    """One shared target-allocation decision with orders retained by component."""

    exposure_snapshot: PortfolioExposureSnapshot
    allocation: AllocationDecision
    component_order_intents: tuple[tuple[str, tuple[OrderIntent, ...]], ...]

    @property
    def order_intents(self) -> tuple[OrderIntent, ...]:
        """Return the native-ready orders in deterministic component order."""

        return tuple(
            intent for _component_id, intents in self.component_order_intents for intent in intents
        )


def resolve_nautilus_target_position_intents(
    *,
    portfolio: PortfolioComposition,
    component_id: str,
    intents: Sequence[TargetPositionIntent],
    run_attempt_id: str,
    event_time: datetime,
    event_sequence: int,
    account_equity: Decimal,
    account_cash_balance: Decimal,
    current_base_exposures: Mapping[str, Decimal],
    current_quantities: Mapping[str, Decimal],
    mark_prices: Mapping[str, Decimal],
    instruments: Mapping[str, Mapping[str, object]],
) -> NautilusTargetAllocationResolution:
    """Run the platform allocator and size only supported linear spot targets.

    Native account and position values must already have been read and converted
    by the exact Nautilus adapter. This function does not estimate FX, contract,
    option, margin, or lot economics from guessed metadata.
    """

    if not isinstance(portfolio, PortfolioComposition):
        raise TypeError("portfolio must be a PortfolioComposition")
    component = next(
        (item for item in portfolio.components if item.component_id == component_id), None
    )
    if component is None:
        raise NautilusRuntimeDataError("target-position component is outside the portfolio")
    if any(not isinstance(item, TargetPositionIntent) for item in intents):
        raise NautilusRuntimeDataError("target-position allocation accepts only target intents")
    declared = set(component.instrument_ids)
    for values, field_name in (
        (current_base_exposures, "current exposure"),
        (current_quantities, "current quantity"),
        (mark_prices, "mark price"),
    ):
        if any(instrument_id not in declared for instrument_id in values):
            raise NautilusRuntimeDataError(f"{field_name} contains an undeclared instrument")
    instrument_bindings: list[InstrumentRiskBinding] = []
    policy_models = {item.product_class: item for item in portfolio.shared_risk_policy.risk_models}
    for instrument_id in sorted(declared):
        definition = instruments.get(instrument_id)
        if definition is None:
            raise NautilusRuntimeDataError("portfolio instrument is missing native economics")
        product_class = _product_class(definition)
        model = policy_models.get(product_class)
        if model is not None:
            instrument_bindings.append(InstrumentRiskBinding(instrument_id, model))
    positions = tuple(
        ComponentPositionExposure(component_id, instrument_id, exposure)
        for instrument_id, exposure in sorted(current_base_exposures.items())
        if exposure != 0
    )
    evidence_digest = content_digest(
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
        valuation_evidence_digest=evidence_digest,
        positions=positions,
        instrument_risk_models=tuple(instrument_bindings),
    )
    requests = component_targets_from_intents(
        portfolio,
        {component_id: intents},
        event_time=event_time,
        event_sequence=event_sequence,
    )
    try:
        allocation = allocate_component_targets(portfolio, snapshot, requests)
    except (TypeError, ValueError) as error:
        raise NautilusRuntimeDataError(
            "target-position allocation could not be validated"
        ) from error
    if not allocation.risk_limits_satisfied:
        raise NautilusRuntimeDataError("target-position allocation breaches shared portfolio risk")
    if allocation.rejected_targets:
        raise NautilusRuntimeDataError("target-position allocation contains rejected targets")

    orders: list[OrderIntent] = []
    for target in allocation.risk_approved_instrument_targets:
        definition = instruments.get(target.instrument_id)
        mark_price = mark_prices.get(target.instrument_id)
        current_quantity = current_quantities.get(target.instrument_id, Decimal(0))
        if definition is None or mark_price is None or mark_price <= 0:
            raise NautilusRuntimeDataError("target order requires verified instrument marks")
        product_class = _product_class(definition)
        model = policy_models.get(product_class)
        size_increment = _decimal_field(definition, "size_increment")
        size_precision = definition.get("size_precision")
        min_quantity = _optional_decimal_field(definition, "min_quantity")
        max_quantity = _optional_decimal_field(definition, "max_quantity")
        quantity_value_multiplier = _target_quantity_value_multiplier(
            definition=definition,
            product_class=product_class,
            risk_model=model,
            base_currency=portfolio.base_currency,
        )
        if (
            quantity_value_multiplier is None
            or size_increment is None
            or size_increment <= 0
            or not isinstance(size_precision, int)
            or isinstance(size_precision, bool)
        ):
            raise NautilusRuntimeDataError(
                "target order economics require supported base-quoted linear spot or complete futures terms"
            )
        target_quantity = target.target_signed_base_notional / (
            mark_price * quantity_value_multiplier
        )
        lot_count = (abs(target_quantity) / size_increment).to_integral_value(rounding=ROUND_DOWN)
        sized_target = lot_count * size_increment
        if target_quantity < 0:
            sized_target = -sized_target
        position_lots = current_quantity / size_increment
        if position_lots != position_lots.to_integral_value():
            raise NautilusRuntimeDataError(
                "native position quantity is outside instrument lot size"
            )
        delta = sized_target - current_quantity
        if delta == 0:
            continue
        quantity = abs(delta)
        order_lots = quantity / size_increment
        if order_lots != order_lots.to_integral_value():
            raise NautilusRuntimeDataError("target delta is outside instrument lot size")
        if min_quantity is not None and quantity < min_quantity:
            raise NautilusRuntimeDataError("target delta is below native minimum quantity")
        if max_quantity is not None and quantity > max_quantity:
            raise NautilusRuntimeDataError("target delta exceeds native maximum quantity")
        quantity = quantity.quantize(Decimal(1).scaleb(-size_precision))
        orders.append(
            OrderIntent(
                instrument_id=target.instrument_id,
                side=OrderSide.BUY if delta > 0 else OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=quantity,
            )
        )
    return NautilusTargetAllocationResolution(snapshot, allocation, tuple(orders))


def resolve_nautilus_component_target_position_batches(
    *,
    portfolio: PortfolioComposition,
    intents_by_component: Mapping[str, Sequence[TargetPositionIntent]],
    run_attempt_id: str,
    event_time: datetime,
    event_sequence: int,
    account_equity: Decimal,
    account_cash_balance: Decimal,
    current_base_exposures: Mapping[str, Decimal],
    current_quantities: Mapping[str, Decimal],
    current_component_exposures: Mapping[str, Mapping[str, Decimal]],
    current_component_quantities: Mapping[str, Mapping[str, Decimal]],
    mark_prices: Mapping[str, Decimal],
    instruments: Mapping[str, Mapping[str, object]],
    defer_shared_risk_validation: bool = False,
) -> NautilusComponentTargetAllocationResolution:
    """Allocate simultaneous component targets once, then size attributed deltas.

    The component exposure and quantity ledgers must reconcile exactly to the
    native account before allocation. By default, shared-account risk breaches
    fail closed here. A caller that will combine these candidate orders with
    other same-event orders may defer that verdict to the final shared-order
    router; this is intended for the native bridge only.
    """

    if not isinstance(portfolio, PortfolioComposition):
        raise TypeError("portfolio must be a PortfolioComposition")
    if not isinstance(defer_shared_risk_validation, bool):
        raise TypeError("defer_shared_risk_validation must be a bool")
    if not isinstance(intents_by_component, Mapping) or not intents_by_component:
        raise NautilusRuntimeDataError("native component target batches are required")
    if not isinstance(current_component_exposures, Mapping) or not isinstance(
        current_component_quantities, Mapping
    ):
        raise NautilusRuntimeDataError("native component position attribution is invalid")
    if not isinstance(instruments, Mapping):
        raise NautilusRuntimeDataError("native instrument catalog is invalid")
    components = {item.component_id: item for item in portfolio.components}
    component_ids = set(components)
    if (
        set(current_component_exposures) != component_ids
        or set(current_component_quantities) != component_ids
    ):
        raise NautilusRuntimeDataError(
            "native component exposure and quantity ledgers must cover the portfolio"
        )

    def reconcile_component_ledger(
        ledger: Mapping[str, Mapping[str, Decimal]],
        account_values: Mapping[str, Decimal],
        field_name: str,
    ) -> dict[str, Decimal]:
        if not isinstance(ledger, Mapping) or not isinstance(account_values, Mapping):
            raise NautilusRuntimeDataError(f"native {field_name} attribution is invalid")
        totals: dict[str, Decimal] = {}
        for component_id, values in ledger.items():
            component = components.get(component_id)
            if component is None or not isinstance(values, Mapping):
                raise NautilusRuntimeDataError(f"native {field_name} attribution is invalid")
            for instrument_id, value in values.items():
                if instrument_id not in component.instrument_ids:
                    raise NautilusRuntimeDataError(
                        f"native {field_name} attribution contains an undeclared instrument"
                    )
                if not isinstance(value, Decimal) or not value.is_finite():
                    raise NautilusRuntimeDataError(f"native {field_name} attribution is not finite")
                if value != 0:
                    totals[instrument_id] = totals.get(instrument_id, Decimal(0)) + value
        normalized_account = {
            instrument_id: value for instrument_id, value in account_values.items() if value != 0
        }
        if any(
            not isinstance(value, Decimal) or not value.is_finite()
            for value in account_values.values()
        ):
            raise NautilusRuntimeDataError(f"native {field_name} account values are not finite")
        if totals != normalized_account:
            raise NautilusRuntimeDataError(
                f"component-attributed {field_name} do not reconcile to the native account"
            )
        return totals

    reconcile_component_ledger(
        current_component_exposures,
        current_base_exposures,
        "exposures",
    )
    reconcile_component_ledger(
        current_component_quantities,
        current_quantities,
        "quantities",
    )
    declared_instruments = {
        instrument_id
        for component in portfolio.components
        for instrument_id in component.instrument_ids
    }
    for values, field_name in (
        (current_base_exposures, "current exposure"),
        (current_quantities, "current quantity"),
        (mark_prices, "mark price"),
    ):
        if any(instrument_id not in declared_instruments for instrument_id in values):
            raise NautilusRuntimeDataError(f"{field_name} contains an undeclared instrument")

    positions: list[ComponentPositionExposure] = []
    for component_id in sorted(component_ids):
        for instrument_id, exposure in sorted(current_component_exposures[component_id].items()):
            if exposure != 0:
                positions.append(ComponentPositionExposure(component_id, instrument_id, exposure))

    policy_models = {item.product_class: item for item in portfolio.shared_risk_policy.risk_models}
    risk_bindings: list[InstrumentRiskBinding] = []
    for instrument_id in sorted(declared_instruments):
        definition = instruments.get(instrument_id)
        if definition is None:
            raise NautilusRuntimeDataError("portfolio instrument is missing native economics")
        risk_model = policy_models.get(_product_class(definition))
        if risk_model is not None:
            risk_bindings.append(InstrumentRiskBinding(instrument_id, risk_model))

    evidence_digest = content_digest(
        {
            "attempt_id": run_attempt_id,
            "event_time": event_time,
            "event_sequence": event_sequence,
            "account_equity": account_equity,
            "account_cash_balance": account_cash_balance,
            "current_base_exposures": dict(current_base_exposures),
            "current_quantities": dict(current_quantities),
            "current_component_exposures": {
                component_id: dict(values)
                for component_id, values in current_component_exposures.items()
            },
            "current_component_quantities": {
                component_id: dict(values)
                for component_id, values in current_component_quantities.items()
            },
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
        valuation_evidence_digest=evidence_digest,
        positions=tuple(positions),
        instrument_risk_models=tuple(risk_bindings),
    )
    try:
        requests = component_targets_from_intents(
            portfolio,
            intents_by_component,
            event_time=event_time,
            event_sequence=event_sequence,
        )
        allocation = allocate_component_targets(portfolio, snapshot, requests)
    except (TypeError, ValueError) as error:
        raise NautilusRuntimeDataError(
            "component target allocation could not be validated"
        ) from error
    if not allocation.risk_limits_satisfied and not defer_shared_risk_validation:
        raise NautilusRuntimeDataError("target-position allocation breaches shared portfolio risk")
    unexpected_rejections = tuple(
        item
        for item in allocation.rejected_targets
        if item.code is not AllocationRejectionCode.LOWER_PRIORITY
    )
    if unexpected_rejections:
        raise NautilusRuntimeDataError("component target allocation contains rejected targets")

    request_keys = {
        (component_id, intent.instrument_id)
        for component_id, intents in intents_by_component.items()
        for intent in intents
    }
    rejected_keys = {
        (item.component_id, item.instrument_id) for item in allocation.rejected_targets
    }
    resolved_targets = {
        (item.component_id, item.instrument_id): item.target_fraction_of_equity
        for item in allocation.proposed_component_exposures
        if (item.component_id, item.instrument_id) in request_keys
        and (item.component_id, item.instrument_id) not in rejected_keys
    }
    orders_by_component: dict[str, list[OrderIntent]] = {
        component_id: [] for component_id in sorted(component_ids)
    }
    for component_id, instrument_id in sorted(resolved_targets):
        definition = instruments[instrument_id]
        mark_price = mark_prices.get(instrument_id)
        current_quantity = current_component_quantities[component_id].get(instrument_id, Decimal(0))
        if mark_price is None or mark_price <= 0:
            raise NautilusRuntimeDataError("target order requires verified instrument marks")
        product_class = _product_class(definition)
        risk_model = policy_models.get(product_class)
        size_increment = _decimal_field(definition, "size_increment")
        size_precision = definition.get("size_precision")
        minimum_quantity = _optional_decimal_field(definition, "min_quantity")
        maximum_quantity = _optional_decimal_field(definition, "max_quantity")
        quantity_value_multiplier = _target_quantity_value_multiplier(
            definition=definition,
            product_class=product_class,
            risk_model=risk_model,
            base_currency=portfolio.base_currency,
        )
        if (
            quantity_value_multiplier is None
            or size_increment is None
            or size_increment <= 0
            or not isinstance(size_precision, int)
            or isinstance(size_precision, bool)
        ):
            raise NautilusRuntimeDataError(
                "target order economics require supported base-quoted linear spot or complete futures terms"
            )
        target_notional = resolved_targets[(component_id, instrument_id)] * account_equity
        target_quantity = target_notional / (mark_price * quantity_value_multiplier)
        lot_count = (abs(target_quantity) / size_increment).to_integral_value(rounding=ROUND_DOWN)
        sized_target = lot_count * size_increment
        if target_quantity < 0:
            sized_target = -sized_target
        position_lots = current_quantity / size_increment
        if position_lots != position_lots.to_integral_value():
            raise NautilusRuntimeDataError(
                "native position quantity is outside instrument lot size"
            )
        delta = sized_target - current_quantity
        if delta == 0:
            continue
        quantity = abs(delta)
        order_lots = quantity / size_increment
        if order_lots != order_lots.to_integral_value():
            raise NautilusRuntimeDataError("target delta is outside instrument lot size")
        if minimum_quantity is not None and quantity < minimum_quantity:
            raise NautilusRuntimeDataError("target delta is below native minimum quantity")
        if maximum_quantity is not None and quantity > maximum_quantity:
            raise NautilusRuntimeDataError("target delta exceeds native maximum quantity")
        quantity = quantity.quantize(Decimal(1).scaleb(-size_precision))
        orders_by_component[component_id].append(
            OrderIntent(
                instrument_id=instrument_id,
                side=OrderSide.BUY if delta > 0 else OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=quantity,
            )
        )
    return NautilusComponentTargetAllocationResolution(
        snapshot,
        allocation,
        tuple(
            (component_id, tuple(orders))
            for component_id, orders in sorted(orders_by_component.items())
            if orders
        ),
    )


def _product_class(definition: Mapping[str, object]) -> ProductClass:
    value = definition.get("product_class")
    if not isinstance(value, str):
        raise NautilusRuntimeDataError("native product class is invalid")
    try:
        return ProductClass(value)
    except ValueError as error:
        raise NautilusRuntimeDataError("native product class is unsupported") from error


def _target_quantity_value_multiplier(
    *,
    definition: Mapping[str, object],
    product_class: ProductClass,
    risk_model: object,
    base_currency: str,
) -> Decimal | None:
    """Return base-notional per price unit only for fully specified sizing terms."""

    multiplier = _decimal_field(definition, "multiplier")
    size_increment = _decimal_field(definition, "size_increment")
    size_precision = definition.get("size_precision")
    if (
        definition.get("quote_currency") != base_currency
        or multiplier is None
        or multiplier <= 0
        or size_increment is None
        or size_increment <= 0
        or not isinstance(size_precision, int)
        or isinstance(size_precision, bool)
    ):
        return None
    if (
        product_class is ProductClass.EQUITY
        and risk_model == CASH_EQUITY_NOTIONAL_RISK_MODEL
        or product_class is ProductClass.CRYPTO
        and risk_model == CRYPTO_SPOT_NOTIONAL_RISK_MODEL
    ):
        return multiplier if multiplier == Decimal(1) else None
    if (
        product_class is not ProductClass.FUTURE
        or risk_model != FUTURE_CONTRACT_NOTIONAL_RISK_MODEL
    ):
        return None
    margin_initial = _decimal_field(definition, "margin_init")
    margin_maintenance = _decimal_field(definition, "margin_maint")
    price_increment = _decimal_field(definition, "price_increment")
    if (
        definition.get("base_currency") is not None
        or size_increment != Decimal(1)
        or size_precision != 0
        or margin_initial is None
        or margin_initial <= 0
        or margin_maintenance is None
        or margin_maintenance <= 0
        or margin_maintenance > margin_initial
        or price_increment is None
        or price_increment <= 0
    ):
        return None
    return multiplier


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
    "NautilusComponentTargetAllocationResolution",
    "NautilusTargetAllocationResolution",
    "resolve_nautilus_component_target_position_batches",
    "resolve_nautilus_target_position_intents",
]
