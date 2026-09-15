"""Small, engine-neutral strategy SDK surface with typed immutable intents.

This is an application contract, not a Python sandbox. Untrusted code must still
run in the later no-network, resource-limited worker environment.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol, TypeAlias

from app.strategy_lab_v2.canonical import content_digest, freeze_json
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import StrategyDependency, StrategyVersion


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


@dataclass(frozen=True, slots=True)
class StrategyDataDependency:
    dependency_id: str
    requirement: CapabilityRequirement
    fields: tuple[str, ...]
    lookback_periods: int = 0

    def __post_init__(self) -> None:
        if not self.dependency_id.strip():
            raise ValueError("data dependency id must not be empty")
        fields = tuple(self.fields)
        if not fields or any(not value.strip() for value in fields):
            raise ValueError("data dependencies must declare one or more fields")
        if len(set(fields)) != len(fields):
            raise ValueError("data dependency fields must be unique")
        if (
            not isinstance(self.lookback_periods, int)
            or isinstance(self.lookback_periods, bool)
            or self.lookback_periods < 0
        ):
            raise ValueError("lookback_periods must be a non-negative integer")
        object.__setattr__(self, "fields", fields)


@dataclass(frozen=True, slots=True)
class StrategySdkManifest:
    strategy: StrategyVersion
    data_dependencies: tuple[StrategyDataDependency, ...]
    model_dependencies: tuple[StrategyDependency, ...] = ()

    def __post_init__(self) -> None:
        if not self.data_dependencies:
            raise ValueError("strategy SDK manifest must declare market-data dependencies")
        dependency_ids = [item.dependency_id for item in self.data_dependencies]
        if len(set(dependency_ids)) != len(dependency_ids):
            raise ValueError("strategy data dependency ids must be unique")
        object.__setattr__(self, "data_dependencies", tuple(self.data_dependencies))
        object.__setattr__(self, "model_dependencies", tuple(self.model_dependencies))

    @property
    def capability_requirements(self) -> tuple[CapabilityRequirement, ...]:
        return tuple(item.requirement for item in self.data_dependencies)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class MarketEvent:
    dependency_id: str
    event_id: str
    instrument_id: str
    event_time: datetime
    sequence: int
    values: Mapping[str, Any]

    def __post_init__(self) -> None:
        if (
            not self.dependency_id.strip()
            or not self.event_id.strip()
            or not self.instrument_id.strip()
        ):
            raise ValueError("market event identifiers must not be empty")
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("market event time must be timezone-aware")
        if self.sequence < 0:
            raise ValueError("market event sequence must be non-negative")
        object.__setattr__(self, "values", freeze_json(self.values))


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    instrument_id: str
    quantity: Decimal
    average_price: Decimal | None
    market_value: Decimal | None

    def __post_init__(self) -> None:
        if not self.instrument_id.strip():
            raise ValueError("position instrument_id must not be empty")
        for name in ("quantity", "average_price", "market_value"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
                raise ValueError(f"{name} must be finite")


@dataclass(frozen=True, slots=True)
class StrategyContext:
    event_time: datetime
    event_sequence: int
    random_seed: int
    parameters: Mapping[str, Any]
    market_events: Mapping[str, tuple[MarketEvent, ...]]
    positions: Mapping[str, PositionSnapshot] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("strategy event_time must be timezone-aware")
        if self.event_sequence < 0:
            raise ValueError("event_sequence must be non-negative")
        frozen_parameters = freeze_json(self.parameters)
        event_map: dict[str, tuple[MarketEvent, ...]] = {}
        for dependency_id, events in self.market_events.items():
            if not dependency_id.strip():
                raise ValueError("market data dependency ids must not be empty")
            immutable_events = tuple(events)
            if any(event.dependency_id != dependency_id for event in immutable_events):
                raise ValueError("market event does not match its declared dependency key")
            if any(
                event.event_time > self.event_time
                or (event.event_time == self.event_time and event.sequence > self.event_sequence)
                for event in immutable_events
            ):
                raise ValueError(
                    "strategy context cannot expose events after its current event time"
                )
            if tuple(
                sorted(immutable_events, key=lambda item: (item.event_time, item.sequence))
            ) != (immutable_events):
                raise ValueError("market data events must be chronological")
            event_map[dependency_id] = immutable_events
        position_map = dict(self.positions)
        if any(not isinstance(value, PositionSnapshot) for value in position_map.values()):
            raise TypeError("strategy positions must use PositionSnapshot records")
        if any(key != value.instrument_id for key, value in position_map.items()):
            raise ValueError("position map keys must match position instrument ids")
        object.__setattr__(self, "parameters", frozen_parameters)
        object.__setattr__(self, "market_events", MappingProxyType(event_map))
        object.__setattr__(self, "positions", MappingProxyType(position_map))


def build_strategy_context(
    manifest: StrategySdkManifest,
    *,
    event_time: datetime,
    event_sequence: int,
    random_seed: int,
    parameters: Mapping[str, Any],
    market_events: Mapping[str, tuple[MarketEvent, ...]],
    positions: Mapping[str, PositionSnapshot] | None = None,
) -> StrategyContext:
    """Build context only from manifest-declared series, fields, and lookbacks."""

    declared = {item.dependency_id: item for item in manifest.data_dependencies}
    provided = set(market_events)
    if provided != set(declared):
        missing = sorted(set(declared) - provided)
        extra = sorted(provided - set(declared))
        raise ValueError(f"market-data dependency mismatch; missing={missing}, extra={extra}")
    allowed_instruments = {item.requirement.instrument_id for item in manifest.data_dependencies}
    position_snapshot = positions or {}
    if not set(position_snapshot).issubset(allowed_instruments):
        raise ValueError("strategy context contains an undeclared portfolio instrument")

    for dependency_id, events in market_events.items():
        dependency = declared[dependency_id]
        if len(events) > dependency.lookback_periods + 1:
            raise ValueError(f"dependency {dependency_id!r} exceeds its declared lookback")
        allowed_fields = set(dependency.fields)
        for event in events:
            if event.instrument_id != dependency.requirement.instrument_id:
                raise ValueError(f"dependency {dependency_id!r} contains an undeclared instrument")
            extra_fields = set(event.values) - allowed_fields
            if extra_fields:
                raise ValueError(
                    f"dependency {dependency_id!r} contains undeclared fields: "
                    f"{sorted(extra_fields)}"
                )
            missing_fields = allowed_fields - set(event.values)
            if missing_fields:
                raise ValueError(
                    f"dependency {dependency_id!r} is missing required fields: "
                    f"{sorted(missing_fields)}"
                )

    return StrategyContext(
        event_time=event_time,
        event_sequence=event_sequence,
        random_seed=random_seed,
        parameters=parameters,
        market_events=market_events,
        positions=position_snapshot,
    )


class IntentKind(StrEnum):
    ORDER = "order"
    TARGET_POSITION = "target_position"


@dataclass(frozen=True, slots=True)
class OrderIntent:
    instrument_id: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    client_tag: str | None = None
    kind: IntentKind = field(default=IntentKind.ORDER, init=False)

    def __post_init__(self) -> None:
        if not self.instrument_id.strip():
            raise ValueError("order instrument_id must not be empty")
        if (
            not isinstance(self.quantity, Decimal)
            or not self.quantity.is_finite()
            or self.quantity <= 0
        ):
            raise ValueError("order quantity must be finite and positive")
        requires_limit = self.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT}
        requires_stop = self.order_type in {OrderType.STOP_MARKET, OrderType.STOP_LIMIT}
        if requires_limit != (self.limit_price is not None):
            raise ValueError("limit orders require exactly one positive limit_price")
        if requires_stop != (self.stop_price is not None):
            raise ValueError("stop orders require exactly one positive stop_price")
        for name in ("limit_price", "stop_price"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, Decimal) or not value.is_finite() or value <= 0
            ):
                raise ValueError(f"{name} must be finite and positive")
        if self.client_tag is not None and not self.client_tag.strip():
            raise ValueError("client_tag must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class TargetPositionIntent:
    instrument_id: str
    target_fraction: Decimal
    kind: IntentKind = field(default=IntentKind.TARGET_POSITION, init=False)

    def __post_init__(self) -> None:
        if not self.instrument_id.strip():
            raise ValueError("target-position instrument_id must not be empty")
        if not isinstance(self.target_fraction, Decimal) or not self.target_fraction.is_finite():
            raise ValueError("target_fraction must be finite")


StrategyIntent: TypeAlias = OrderIntent | TargetPositionIntent  # noqa: UP040


class EngineNeutralStrategy(Protocol):
    """Strategy entry point; it receives only the per-event immutable context."""

    def on_event(self, context: StrategyContext) -> Iterable[StrategyIntent]: ...


def validate_strategy_output(
    manifest: StrategySdkManifest,
    intents: Iterable[StrategyIntent],
    *,
    max_intents_per_event: int = 100,
) -> tuple[StrategyIntent, ...]:
    """Check intent shape and declared instrument scope before host allocation/risk."""

    if max_intents_per_event < 1:
        raise ValueError("max_intents_per_event must be positive")
    allowed_instruments = {
        requirement.instrument_id for requirement in manifest.capability_requirements
    }
    output: list[StrategyIntent] = []
    for intent in intents:
        if not isinstance(intent, OrderIntent | TargetPositionIntent):
            raise TypeError("strategy output must contain only typed order/target intents")
        if intent.instrument_id not in allowed_instruments:
            raise ValueError(f"strategy emitted undeclared instrument {intent.instrument_id!r}")
        output.append(intent)
        if len(output) > max_intents_per_event:
            raise ValueError("strategy exceeded max_intents_per_event")
    return tuple(output)
