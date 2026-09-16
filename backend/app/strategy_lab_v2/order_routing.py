"""Engine-neutral sizing and pre-trade routing for typed order intents.

The allocator works with target positions because raw quantities have no shared
account meaning until an instrument adapter supplies authoritative economics.
This module is the corresponding boundary for explicit ``OrderIntent`` values:
it turns a quantity into an auditable estimated base notional, applies the
portfolio's all-or-nothing shared-risk gate, and returns an engine-neutral
order record.  It never submits an order or claims that the estimate is a fill.

The first registered model is cash-equity market value as signed base notional.
Derivative and other product models must add their own validated economics and
remain rejected until their semantics are explicitly registered.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.strategy_lab_v2.allocation import (
    PortfolioExposureSnapshot,
    RiskBreach,
    _risk_breaches,
)
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    PortfolioComposition,
    ProductRiskModel,
)
from app.strategy_lab_v2.decimal_math import DECIMAL_PRECISION, deterministic_decimal_math
from app.strategy_lab_v2.sdk import OrderIntent, OrderSide, OrderType, TimeInForce

ORDER_ROUTING_DEFINITION_VERSION = (
    f"strategy-lab.order-routing.v1.decimal{DECIMAL_PRECISION}-half-even"
)


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _currency(value: str, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 3
        or not value.isascii()
        or not value.isalpha()
    ):
        raise ValueError(f"{field_name} must be a three-letter currency code")
    return value.upper()


def _positive_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{field_name} must be a finite positive Decimal")


@dataclass(frozen=True, slots=True)
class InstrumentOrderEconomics:
    """Adapter-supplied, digest-bound economics for sizing one instrument.

    ``mark_price`` is used only for a conservative pre-trade exposure estimate;
    it is not a fill price.  The adapter must bind it, the FX conversion, and
    all lot/tick semantics to ``valuation_evidence_digest`` before constructing
    this value.
    """

    instrument_id: str
    risk_model: ProductRiskModel
    mark_price: Decimal
    contract_multiplier: Decimal
    quantity_step: Decimal
    minimum_quantity: Decimal
    quote_currency: str
    base_currency: str
    quote_to_base_rate: Decimal
    valuation_evidence_digest: str
    price_tick: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, str) or not self.instrument_id.strip():
            raise ValueError("instrument_id must not be empty")
        if not isinstance(self.risk_model, ProductRiskModel):
            raise TypeError("risk_model must be a ProductRiskModel")
        for name in (
            "mark_price",
            "contract_multiplier",
            "quantity_step",
            "minimum_quantity",
            "quote_to_base_rate",
        ):
            _positive_decimal(getattr(self, name), name)
        if self.price_tick is not None:
            _positive_decimal(self.price_tick, "price_tick")
        object.__setattr__(self, "quote_currency", _currency(self.quote_currency, "quote_currency"))
        object.__setattr__(self, "base_currency", _currency(self.base_currency, "base_currency"))
        require_sha256_digest(self.valuation_evidence_digest, field_name="valuation_evidence_digest")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class RoutedOrder:
    """A sized but not submitted order with an auditable valuation estimate."""

    component_id: str
    intent_fingerprint: str
    economics_fingerprint: str
    instrument_id: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    time_in_force: TimeInForce
    limit_price: Decimal | None
    stop_price: Decimal | None
    client_tag: str | None
    estimated_signed_base_notional: Decimal
    valuation_evidence_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, str) or not self.component_id.strip():
            raise ValueError("component_id must not be empty")
        for name in ("intent_fingerprint", "economics_fingerprint", "valuation_evidence_digest"):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.instrument_id, str) or not self.instrument_id.strip():
            raise ValueError("instrument_id must not be empty")
        if not isinstance(self.side, OrderSide):
            raise TypeError("side must be an OrderSide")
        if not isinstance(self.order_type, OrderType):
            raise TypeError("order_type must be an OrderType")
        if not isinstance(self.time_in_force, TimeInForce):
            raise TypeError("time_in_force must be a TimeInForce")
        _positive_decimal(self.quantity, "quantity")
        if (
            not isinstance(self.estimated_signed_base_notional, Decimal)
            or not self.estimated_signed_base_notional.is_finite()
            or self.estimated_signed_base_notional == 0
        ):
            raise ValueError("estimated_signed_base_notional must be finite and non-zero")
        if self.side is OrderSide.BUY and self.estimated_signed_base_notional < 0:
            raise ValueError("buy estimated notional must be positive")
        if self.side is OrderSide.SELL and self.estimated_signed_base_notional > 0:
            raise ValueError("sell estimated notional must be negative")
        if self.client_tag is not None and not self.client_tag.strip():
            raise ValueError("client_tag must be non-empty when provided")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class OrderRoutingDecisionKind(StrEnum):
    APPROVED = "approved"
    RISK_REJECTED = "risk_rejected"


@dataclass(frozen=True, slots=True)
class OrderRoutingDecision:
    """All-or-nothing result of sizing and shared-account risk evaluation."""

    definition_version: str
    portfolio_fingerprint: str
    exposure_snapshot_fingerprint: str
    policy_fingerprint: str
    event_time: datetime
    event_sequence: int
    kind: OrderRoutingDecisionKind
    risk_limits_satisfied: bool
    proposed_orders: tuple[RoutedOrder, ...]
    risk_approved_orders: tuple[RoutedOrder, ...]
    risk_breaches: tuple[RiskBreach, ...]
    gross_exposure_fraction: Decimal
    net_exposure_fraction: Decimal
    max_instrument_gross_exposure_fraction: Decimal
    max_component_gross_exposure_fraction: Decimal
    open_instrument_count: int

    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        require_sha256_digest(
            self.exposure_snapshot_fingerprint,
            field_name="exposure_snapshot_fingerprint",
        )
        require_sha256_digest(self.policy_fingerprint, field_name="policy_fingerprint")
        _aware(self.event_time, "event_time")
        if (
            not isinstance(self.event_sequence, int)
            or isinstance(self.event_sequence, bool)
            or self.event_sequence < 0
        ):
            raise ValueError("event_sequence must be a non-negative integer")
        if not isinstance(self.kind, OrderRoutingDecisionKind):
            raise TypeError("kind must be an OrderRoutingDecisionKind")
        if not isinstance(self.risk_limits_satisfied, bool):
            raise TypeError("risk_limits_satisfied must be a bool")
        proposed = tuple(self.proposed_orders)
        approved = tuple(self.risk_approved_orders)
        if any(not isinstance(item, RoutedOrder) for item in (*proposed, *approved)):
            raise TypeError("orders must contain RoutedOrder values")
        if tuple(sorted(proposed, key=lambda item: (item.component_id, item.fingerprint))) != proposed:
            raise ValueError("proposed orders must be deterministically ordered")
        if not set(approved).issubset(set(proposed)):
            raise ValueError("approved orders must be a subset of proposed orders")
        if self.risk_limits_satisfied != (self.kind is OrderRoutingDecisionKind.APPROVED):
            raise ValueError("decision kind must match risk_limits_satisfied")
        if self.risk_limits_satisfied and approved != proposed:
            raise ValueError("an approved decision must expose every proposed order")
        if not self.risk_limits_satisfied and approved:
            raise ValueError("a risk-rejected decision must expose no approved orders")
        for name in (
            "gross_exposure_fraction",
            "net_exposure_fraction",
            "max_instrument_gross_exposure_fraction",
            "max_component_gross_exposure_fraction",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")
        if (
            not isinstance(self.open_instrument_count, int)
            or isinstance(self.open_instrument_count, bool)
            or self.open_instrument_count < 0
        ):
            raise ValueError("open_instrument_count must be a non-negative integer")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        object.__setattr__(self, "proposed_orders", proposed)
        object.__setattr__(self, "risk_approved_orders", approved)
        breaches = tuple(self.risk_breaches)
        if any(not isinstance(item, RiskBreach) for item in breaches):
            raise TypeError("risk_breaches must contain RiskBreach values")
        object.__setattr__(self, "risk_breaches", breaches)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def _is_multiple(value: Decimal, step: Decimal) -> bool:
    return value % step == 0


def _validate_price_tick(value: Decimal | None, tick: Decimal, field_name: str) -> None:
    if value is not None and not _is_multiple(value, tick):
        raise ValueError(f"{field_name} must align to the instrument price_tick")


@deterministic_decimal_math
def route_order_intents(
    portfolio: PortfolioComposition,
    exposure_snapshot: PortfolioExposureSnapshot,
    intents_by_component: Mapping[str, Iterable[OrderIntent]],
    instrument_economics: Mapping[str, InstrumentOrderEconomics],
    *,
    event_time: datetime,
    event_sequence: int,
) -> OrderRoutingDecision:
    """Size explicit orders, then apply shared account risk as one batch.

    The supplied exposure snapshot is the pre-order account state.  Each order
    adds its estimated signed base notional to the component-attributed current
    exposure before gross/net/concentration/short-position checks.  Any breach
    withholds every order; quantities and estimated notionals are diagnostic
    until the authoritative engine adapter accepts them.
    """

    _aware(event_time, "event_time")
    if (
        not isinstance(event_sequence, int)
        or isinstance(event_sequence, bool)
        or event_sequence < 0
    ):
        raise ValueError("event_sequence must be a non-negative integer")
    if exposure_snapshot.portfolio_fingerprint != portfolio.fingerprint:
        raise ValueError("exposure snapshot does not belong to this portfolio version")
    if exposure_snapshot.base_currency != portfolio.base_currency:
        raise ValueError("exposure snapshot base currency does not match the portfolio")
    if exposure_snapshot.event_time != event_time or exposure_snapshot.event_sequence != event_sequence:
        raise ValueError("order intents must match the exposure snapshot event")

    components = {item.component_id: item for item in portfolio.components}
    policy = portfolio.shared_risk_policy
    allowed_models = {item.product_class: item for item in policy.risk_models}
    snapshot_models = {
        item.instrument_id: item.risk_model for item in exposure_snapshot.instrument_risk_models
    }
    for instrument_id, model in snapshot_models.items():
        if model != CASH_EQUITY_NOTIONAL_RISK_MODEL:
            raise ValueError(f"instrument {instrument_id!r} uses an unsupported order risk model")
        if allowed_models.get(model.product_class) != model:
            raise ValueError(f"instrument {instrument_id!r} risk model is not allowed by the portfolio policy")

    resolved: dict[tuple[str, str], Decimal] = {}
    for position in exposure_snapshot.positions:
        component = components.get(position.component_id)
        if component is None:
            raise ValueError(f"unknown position component {position.component_id!r}")
        if position.instrument_id not in component.instrument_ids:
            raise ValueError(
                f"component {position.component_id!r} holds undeclared instrument "
                f"{position.instrument_id!r}"
            )
        if position.instrument_id not in snapshot_models:
            raise ValueError(f"instrument {position.instrument_id!r} has no risk-model evidence")
        resolved[(position.component_id, position.instrument_id)] = (
            position.signed_base_risk_exposure / exposure_snapshot.account_equity
        )

    routed: list[RoutedOrder] = []
    seen_intents: set[tuple[str, str]] = set()
    for component_id in sorted(intents_by_component):
        component = components.get(component_id)
        if component is None:
            raise ValueError(f"unknown portfolio component {component_id!r}")
        for intent in intents_by_component[component_id]:
            if not isinstance(intent, OrderIntent):
                raise TypeError("order routing accepts only OrderIntent values")
            if not isinstance(intent.side, OrderSide):
                raise TypeError("order side must be an OrderSide")
            if not isinstance(intent.order_type, OrderType):
                raise TypeError("order_type must be an OrderType")
            if not isinstance(intent.time_in_force, TimeInForce):
                raise TypeError("time_in_force must be a TimeInForce")
            if intent.instrument_id not in component.instrument_ids:
                raise ValueError(
                    f"component {component_id!r} emitted undeclared instrument "
                    f"{intent.instrument_id!r}"
                )
            economics = instrument_economics.get(intent.instrument_id)
            if economics is None:
                raise ValueError(f"instrument {intent.instrument_id!r} has no order economics")
            if economics.base_currency != portfolio.base_currency:
                raise ValueError(
                    f"instrument {intent.instrument_id!r} economics use a different base currency"
                )
            if economics.risk_model != CASH_EQUITY_NOTIONAL_RISK_MODEL:
                raise ValueError(
                    f"instrument {intent.instrument_id!r} uses an unsupported order risk model"
                )
            if snapshot_models.get(intent.instrument_id) != economics.risk_model:
                raise ValueError(
                    f"instrument {intent.instrument_id!r} snapshot/economics risk model mismatch"
                )
            if allowed_models.get(economics.risk_model.product_class) != economics.risk_model:
                raise ValueError(
                    f"instrument {intent.instrument_id!r} risk model is not allowed by the portfolio policy"
                )
            if not _is_multiple(intent.quantity, economics.quantity_step):
                raise ValueError("order quantity must align to the instrument quantity_step")
            if intent.quantity < economics.minimum_quantity:
                raise ValueError("order quantity is below the instrument minimum_quantity")
            if economics.price_tick is not None:
                _validate_price_tick(intent.limit_price, economics.price_tick, "limit_price")
                _validate_price_tick(intent.stop_price, economics.price_tick, "stop_price")

            intent_fingerprint = content_digest(intent)
            identity = (component_id, intent_fingerprint)
            if identity in seen_intents:
                raise ValueError("duplicate order intent in one component batch")
            seen_intents.add(identity)
            sign = Decimal(1) if intent.side is OrderSide.BUY else Decimal(-1)
            estimated_notional = (
                sign
                * intent.quantity
                * economics.mark_price
                * economics.contract_multiplier
                * economics.quote_to_base_rate
            )
            routed_order = RoutedOrder(
                component_id=component_id,
                intent_fingerprint=intent_fingerprint,
                economics_fingerprint=economics.fingerprint,
                instrument_id=intent.instrument_id,
                side=intent.side,
                quantity=intent.quantity,
                order_type=intent.order_type,
                time_in_force=intent.time_in_force,
                limit_price=intent.limit_price,
                stop_price=intent.stop_price,
                client_tag=intent.client_tag,
                estimated_signed_base_notional=estimated_notional,
                valuation_evidence_digest=economics.valuation_evidence_digest,
            )
            routed.append(routed_order)
            resolved[(component_id, intent.instrument_id)] = resolved.get(
                (component_id, intent.instrument_id), Decimal(0)
            ) + (estimated_notional / exposure_snapshot.account_equity)

    proposed = tuple(sorted(routed, key=lambda item: (item.component_id, item.fingerprint)))
    risk_breaches = _risk_breaches(resolved, policy, components)
    instrument_gross: dict[str, Decimal] = defaultdict(Decimal)
    component_gross: dict[str, Decimal] = defaultdict(Decimal)
    for (component_id, instrument_id), value in resolved.items():
        if value == 0:
            continue
        instrument_gross[instrument_id] += abs(value)
        component_gross[component_id] += abs(value)
    gross = sum((abs(value) for value in resolved.values()), Decimal(0))
    net = sum(resolved.values(), Decimal(0))
    risk_limits_satisfied = not risk_breaches
    return OrderRoutingDecision(
        definition_version=ORDER_ROUTING_DEFINITION_VERSION,
        portfolio_fingerprint=portfolio.fingerprint,
        exposure_snapshot_fingerprint=exposure_snapshot.fingerprint,
        policy_fingerprint=policy.fingerprint,
        event_time=event_time,
        event_sequence=event_sequence,
        kind=(
            OrderRoutingDecisionKind.APPROVED
            if risk_limits_satisfied
            else OrderRoutingDecisionKind.RISK_REJECTED
        ),
        risk_limits_satisfied=risk_limits_satisfied,
        proposed_orders=proposed,
        risk_approved_orders=proposed if risk_limits_satisfied else (),
        risk_breaches=risk_breaches,
        gross_exposure_fraction=gross,
        net_exposure_fraction=net,
        max_instrument_gross_exposure_fraction=max(instrument_gross.values(), default=Decimal(0)),
        max_component_gross_exposure_fraction=max(component_gross.values(), default=Decimal(0)),
        open_instrument_count=sum(value > 0 for value in instrument_gross.values()),
    )
