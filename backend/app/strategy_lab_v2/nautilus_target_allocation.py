"""Fail-closed translation from approved target weights to native order intents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from app.strategy_lab_v2.allocation import (
    AllocationDecision,
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
        quote_currency = definition.get("quote_currency")
        multiplier = _decimal_field(definition, "multiplier")
        size_increment = _decimal_field(definition, "size_increment")
        size_precision = definition.get("size_precision")
        min_quantity = _optional_decimal_field(definition, "min_quantity")
        max_quantity = _optional_decimal_field(definition, "max_quantity")
        if product_class is ProductClass.EQUITY and model == CASH_EQUITY_NOTIONAL_RISK_MODEL:
            supported_model = True
        elif product_class is ProductClass.CRYPTO and model == CRYPTO_SPOT_NOTIONAL_RISK_MODEL:
            supported_model = True
        else:
            supported_model = False
        if (
            not supported_model
            or quote_currency != portfolio.base_currency
            or multiplier != Decimal(1)
            or not isinstance(size_precision, int)
            or isinstance(size_precision, bool)
            or size_increment is None
        ):
            raise NautilusRuntimeDataError(
                "target order economics require supported base-quoted linear spot instruments"
            )
        target_quantity = target.target_signed_base_notional / mark_price
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
    "NautilusTargetAllocationResolution",
    "resolve_nautilus_target_position_intents",
]
