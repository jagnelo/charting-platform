"""Digest-bound engine input contracts for the isolated Nautilus adapter.

The canonical event tape intentionally contains market-event values only.  A
Nautilus runtime also needs an instrument catalog and one shared venue/account
definition before it can construct native instruments, orders, fills, and
account state.  This module is the engine-neutral boundary for that material;
it does not import Nautilus, discover products, or acquire data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    EvaluationWindow,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    ProductRiskModel,
    RiskExposureMeasure,
    SharedRiskPolicy,
    TargetConflictPolicy,
)
from app.strategy_lab_v2.nautilus_event_adapter import NautilusEventTape
from app.strategy_lab_v2.nautilus_strategy_binding import (
    NautilusComponentStrategyBinding,
    component_strategy_binding_to_wire,
    component_strategy_bindings_from_wire,
)

NAUTILUS_ENGINE_INPUT_VERSION = "strategy-lab.nautilus-engine-input.v4"


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if any(character in value for character in "\x00\r\n"):
        raise ValueError(f"{field_name} must not contain control characters")


def _currency(value: str, field_name: str) -> str:
    _nonempty(value, field_name)
    if len(value) != 3 or not value.isascii() or not value.isalpha():
        raise ValueError(f"{field_name} must be a three-letter currency code")
    return value.upper()


def _positive_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{field_name} must be a finite positive Decimal")


def _optional_positive_decimal(value: Decimal | None, field_name: str) -> None:
    if value is not None:
        _positive_decimal(value, field_name)


@dataclass(frozen=True, slots=True)
class NautilusInstrumentDefinition:
    """Provider-supplied metadata required to construct one native instrument."""

    instrument_id: str
    raw_symbol: str
    venue_id: str
    product_class: ProductClass
    quote_currency: str
    price_precision: int
    size_precision: int
    price_increment: Decimal
    size_increment: Decimal
    base_currency: str | None = None
    multiplier: Decimal = Decimal("1")
    min_quantity: Decimal | None = None
    max_quantity: Decimal | None = None
    activation_ns: int | None = None
    expiration_ns: int | None = None
    bar_type: str | None = None

    def __post_init__(self) -> None:
        for name in ("instrument_id", "raw_symbol", "venue_id"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.product_class, ProductClass):
            raise TypeError("product_class must be a ProductClass")
        object.__setattr__(self, "quote_currency", _currency(self.quote_currency, "quote_currency"))
        if self.base_currency is not None:
            object.__setattr__(
                self, "base_currency", _currency(self.base_currency, "base_currency")
            )
        for name in ("price_precision", "size_precision"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in ("price_increment", "size_increment", "multiplier"):
            _positive_decimal(getattr(self, name), name)
        _optional_positive_decimal(self.min_quantity, "min_quantity")
        _optional_positive_decimal(self.max_quantity, "max_quantity")
        if (
            self.min_quantity is not None
            and self.max_quantity is not None
            and self.max_quantity < self.min_quantity
        ):
            raise ValueError("max_quantity must not be below min_quantity")
        for name in ("activation_ns", "expiration_ns"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if (
            self.activation_ns is not None
            and self.expiration_ns is not None
            and self.expiration_ns <= self.activation_ns
        ):
            raise ValueError("expiration_ns must be after activation_ns")
        if self.bar_type is not None:
            _nonempty(self.bar_type, "bar_type")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusCashDefinition:
    """One initial account cash balance in a native currency."""

    currency: str
    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _currency(self.currency, "currency"))
        _positive_decimal(self.amount, "amount")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusVenueDefinition:
    """One shared venue/account model for a backtest portfolio."""

    venue_id: str
    oms_type: str
    account_type: str
    cash: tuple[NautilusCashDefinition, ...]
    base_currency: str

    def __post_init__(self) -> None:
        _nonempty(self.venue_id, "venue_id")
        _nonempty(self.oms_type, "oms_type")
        _nonempty(self.account_type, "account_type")
        object.__setattr__(self, "base_currency", _currency(self.base_currency, "base_currency"))
        cash = tuple(self.cash)
        if not cash or any(not isinstance(item, NautilusCashDefinition) for item in cash):
            raise ValueError("venue cash must contain at least one NautilusCashDefinition")
        currencies = [item.currency for item in cash]
        if len(currencies) != len(set(currencies)):
            raise ValueError("venue cash currencies must be unique")
        if self.base_currency not in currencies:
            raise ValueError("venue base currency must have an initial cash balance")
        object.__setattr__(self, "cash", tuple(sorted(cash, key=lambda item: item.currency)))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusEngineInput:
    """Complete immutable input needed by a Nautilus backtest callback."""

    trial_id: str
    attempt_id: str
    data_snapshot_fingerprint: str
    event_tape: NautilusEventTape
    instruments: tuple[NautilusInstrumentDefinition, ...]
    venue: NautilusVenueDefinition
    portfolio: PortfolioComposition
    strategy_source_digest: str
    strategy_manifest_fingerprint: str
    entrypoint: str
    parameters: Mapping[str, object]
    random_seed: int
    strategy_bindings: tuple[NautilusComponentStrategyBinding, ...] = ()
    evaluation_window: EvaluationWindow | None = None
    input_version: str = NAUTILUS_ENGINE_INPUT_VERSION

    def __post_init__(self) -> None:
        for name in ("trial_id", "attempt_id", "entrypoint"):
            _nonempty(getattr(self, name), name)
        require_sha256_digest(
            self.data_snapshot_fingerprint,
            field_name="data_snapshot_fingerprint",
        )
        if not isinstance(self.event_tape, NautilusEventTape):
            raise TypeError("event_tape must be a NautilusEventTape")
        if not isinstance(self.venue, NautilusVenueDefinition):
            raise TypeError("venue must be a NautilusVenueDefinition")
        if not isinstance(self.portfolio, PortfolioComposition):
            raise TypeError("portfolio must be a PortfolioComposition")
        if self.evaluation_window is not None and not isinstance(
            self.evaluation_window, EvaluationWindow
        ):
            raise TypeError("evaluation_window must use EvaluationWindow")
        if self.portfolio.base_currency != self.venue.base_currency:
            raise ValueError("portfolio and venue base currencies must match")
        if self.portfolio.rebalance_policy is not None:
            raise ValueError("calendar rebalancing is not represented by the current engine input")
        instruments = tuple(self.instruments)
        if not instruments or any(
            not isinstance(item, NautilusInstrumentDefinition) for item in instruments
        ):
            raise ValueError("engine input requires instrument definitions")
        instrument_ids = [item.instrument_id for item in instruments]
        if len(instrument_ids) != len(set(instrument_ids)):
            raise ValueError("instrument definitions must be unique")
        instrument_map = {item.instrument_id: item for item in instruments}
        if any(record.instrument_id not in instrument_map for record in self.event_tape.events):
            raise ValueError("event tape contains an instrument without a definition")
        if any(
            instrument_map[record.instrument_id].venue_id != self.venue.venue_id
            for record in self.event_tape.events
        ):
            raise ValueError("event tape contains an instrument from a different venue")
        require_sha256_digest(self.strategy_source_digest, field_name="strategy_source_digest")
        require_sha256_digest(
            self.strategy_manifest_fingerprint,
            field_name="strategy_manifest_fingerprint",
        )
        parts = self.entrypoint.split(":")
        if len(parts) != 2 or any(
            not part or any(not token.isidentifier() for token in part.split(".")) for part in parts
        ):
            raise ValueError("entrypoint must use module.path:callable syntax")
        if not isinstance(self.parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        frozen_parameters = freeze_json(self.parameters)
        if not isinstance(frozen_parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        if not isinstance(self.random_seed, int) or isinstance(self.random_seed, bool):
            raise TypeError("random_seed must be an integer")
        if self.input_version != NAUTILUS_ENGINE_INPUT_VERSION:
            raise ValueError("unsupported Nautilus engine input version")
        bindings = tuple(self.strategy_bindings)
        if not bindings:
            if len(self.portfolio.components) != 1:
                raise ValueError(
                    "multi-component engine input requires explicit component strategy bindings"
                )
            component = self.portfolio.components[0]
            bindings = (
                NautilusComponentStrategyBinding(
                    component_id=component.component_id,
                    strategy_fingerprint=component.strategy_fingerprint,
                    strategy_source_digest=self.strategy_source_digest,
                    strategy_manifest_fingerprint=self.strategy_manifest_fingerprint,
                    entrypoint=self.entrypoint,
                    parameters_digest=content_digest(frozen_parameters),
                ),
            )
        if any(not isinstance(item, NautilusComponentStrategyBinding) for item in bindings):
            raise TypeError(
                "strategy_bindings must contain NautilusComponentStrategyBinding values"
            )
        binding_ids = [item.component_id for item in bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("component strategy binding ids must be unique")
        if set(binding_ids) != {item.component_id for item in self.portfolio.components}:
            raise ValueError("component strategy bindings must cover the complete portfolio")
        bindings_by_component = {item.component_id: item for item in bindings}
        for component in self.portfolio.components:
            if (
                bindings_by_component[component.component_id].strategy_fingerprint
                != component.strategy_fingerprint
            ):
                raise ValueError("component strategy binding differs from portfolio identity")
        bindings = tuple(sorted(bindings, key=lambda item: item.component_id))
        primary_binding = bindings[0]
        if (
            primary_binding.strategy_source_digest != self.strategy_source_digest
            or primary_binding.strategy_manifest_fingerprint != self.strategy_manifest_fingerprint
            or primary_binding.entrypoint != self.entrypoint
            or primary_binding.parameters_digest != content_digest(frozen_parameters)
        ):
            raise ValueError("legacy strategy fields must match the first component binding")
        object.__setattr__(
            self, "instruments", tuple(sorted(instruments, key=lambda item: item.instrument_id))
        )
        object.__setattr__(self, "parameters", frozen_parameters)
        object.__setattr__(self, "strategy_bindings", bindings)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def build_nautilus_engine_input(
    *,
    trial_id: str,
    attempt_id: str,
    data_snapshot_fingerprint: str,
    event_tape: NautilusEventTape,
    instruments: Sequence[NautilusInstrumentDefinition],
    venue: NautilusVenueDefinition,
    portfolio: PortfolioComposition,
    strategy_source_digest: str,
    strategy_manifest_fingerprint: str,
    entrypoint: str,
    parameters: Mapping[str, object],
    random_seed: int,
    strategy_bindings: Sequence[NautilusComponentStrategyBinding] | None = None,
    evaluation_window: EvaluationWindow | None = None,
) -> NautilusEngineInput:
    """Construct and validate the complete engine-input boundary."""

    return NautilusEngineInput(
        trial_id=trial_id,
        attempt_id=attempt_id,
        data_snapshot_fingerprint=data_snapshot_fingerprint,
        event_tape=event_tape,
        instruments=tuple(instruments),
        venue=venue,
        portfolio=portfolio,
        strategy_source_digest=strategy_source_digest,
        strategy_manifest_fingerprint=strategy_manifest_fingerprint,
        entrypoint=entrypoint,
        parameters=parameters,
        random_seed=random_seed,
        strategy_bindings=tuple(strategy_bindings or ()),
        evaluation_window=evaluation_window,
    )


def evaluation_window_to_wire(value: EvaluationWindow | None) -> dict[str, object] | None:
    """Serialize the exact half-open warm-up/evaluation range for the isolated engine."""

    if value is None:
        return None
    if not isinstance(value, EvaluationWindow):
        raise TypeError("evaluation_window must use EvaluationWindow")

    def timestamp_ns(timestamp: datetime) -> int:
        normalized = timestamp.astimezone(UTC)
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        delta = normalized - epoch
        return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000

    return {
        "fingerprint": value.fingerprint,
        "purpose": value.purpose,
        "warmup_start_ns": (
            None if value.warmup_start is None else timestamp_ns(value.warmup_start)
        ),
        "start_ns": timestamp_ns(value.start),
        "end_ns": timestamp_ns(value.end),
    }


def portfolio_composition_to_wire(portfolio: PortfolioComposition) -> dict[str, object]:
    """Serialize the exact allocation policy needed by the isolated callback bridge."""

    if not isinstance(portfolio, PortfolioComposition):
        raise TypeError("portfolio must be a PortfolioComposition")
    if portfolio.rebalance_policy is not None:
        raise ValueError("calendar rebalancing is not represented by the current engine input")
    policy = portfolio.shared_risk_policy
    return {
        "fingerprint": portfolio.fingerprint,
        "portfolio_id": portfolio.portfolio_id,
        "version_id": portfolio.version_id,
        "initial_capital": str(portfolio.initial_capital),
        "base_currency": portfolio.base_currency,
        "components": [
            {
                "component_id": item.component_id,
                "strategy_fingerprint": item.strategy_fingerprint,
                "instrument_ids": list(item.instrument_ids),
                "capital_weight": str(item.capital_weight),
                "priority": item.priority,
            }
            for item in portfolio.components
        ],
        "shared_risk_policy": {
            "max_gross_exposure_fraction": str(policy.max_gross_exposure_fraction),
            "max_net_exposure_fraction": str(policy.max_net_exposure_fraction),
            "max_instrument_gross_exposure_fraction": str(
                policy.max_instrument_gross_exposure_fraction
            ),
            "max_component_gross_exposure_fraction": str(
                policy.max_component_gross_exposure_fraction
            ),
            "max_component_leverage": str(policy.max_component_leverage),
            "max_open_instruments": policy.max_open_instruments,
            "allow_short_positions": policy.allow_short_positions,
            "target_conflict_policy": policy.target_conflict_policy.value,
            "risk_models": [
                {
                    "product_class": item.product_class.value,
                    "exposure_measure": item.exposure_measure.value,
                    "definition_digest": item.definition_digest,
                }
                for item in policy.risk_models
            ],
            "definition_version": policy.definition_version,
        },
        "rebalance_policy": None,
    }


def portfolio_composition_from_wire(value: object) -> PortfolioComposition:
    """Validate and reconstruct the allocation policy supplied to the worker."""

    if not isinstance(value, Mapping):
        raise ValueError("portfolio execution policy must be a mapping")
    if set(value) != {
        "fingerprint",
        "portfolio_id",
        "version_id",
        "initial_capital",
        "base_currency",
        "components",
        "shared_risk_policy",
        "rebalance_policy",
    }:
        raise ValueError("portfolio execution policy fields are invalid")
    if value["rebalance_policy"] is not None:
        raise ValueError("calendar rebalancing is not represented by the current engine input")
    components_wire = value["components"]
    if not isinstance(components_wire, list):
        raise ValueError("portfolio components must be a list")
    components: list[PortfolioComponent] = []
    for item in components_wire:
        if not isinstance(item, Mapping) or set(item) != {
            "component_id",
            "strategy_fingerprint",
            "instrument_ids",
            "capital_weight",
            "priority",
        }:
            raise ValueError("portfolio component fields are invalid")
        instrument_ids = item["instrument_ids"]
        if not isinstance(instrument_ids, list) or any(
            not isinstance(instrument_id, str) for instrument_id in instrument_ids
        ):
            raise ValueError("portfolio component instrument ids are invalid")
        if not isinstance(item["priority"], int) or isinstance(item["priority"], bool):
            raise ValueError("portfolio component priority is invalid")
        components.append(
            PortfolioComponent(
                component_id=_wire_text(item["component_id"], "component_id"),
                strategy_fingerprint=_wire_text(
                    item["strategy_fingerprint"], "strategy_fingerprint"
                ),
                instrument_ids=tuple(instrument_ids),
                capital_weight=_wire_decimal(item["capital_weight"], "capital_weight"),
                priority=item["priority"],
            )
        )
    policy_wire = value["shared_risk_policy"]
    if not isinstance(policy_wire, Mapping) or set(policy_wire) != {
        "max_gross_exposure_fraction",
        "max_net_exposure_fraction",
        "max_instrument_gross_exposure_fraction",
        "max_component_gross_exposure_fraction",
        "max_component_leverage",
        "max_open_instruments",
        "allow_short_positions",
        "target_conflict_policy",
        "risk_models",
        "definition_version",
    }:
        raise ValueError("shared risk policy fields are invalid")
    models_wire = policy_wire["risk_models"]
    if not isinstance(models_wire, list):
        raise ValueError("portfolio risk models must be a list")
    risk_models: list[ProductRiskModel] = []
    for item in models_wire:
        if not isinstance(item, Mapping) or set(item) != {
            "product_class",
            "exposure_measure",
            "definition_digest",
        }:
            raise ValueError("portfolio risk model fields are invalid")
        risk_models.append(
            ProductRiskModel(
                product_class=ProductClass(_wire_text(item["product_class"], "product_class")),
                exposure_measure=RiskExposureMeasure(
                    _wire_text(item["exposure_measure"], "exposure_measure")
                ),
                definition_digest=_wire_text(item["definition_digest"], "definition_digest"),
            )
        )
    max_open = policy_wire["max_open_instruments"]
    if max_open is not None and (not isinstance(max_open, int) or isinstance(max_open, bool)):
        raise ValueError("shared risk max_open_instruments is invalid")
    allow_short = policy_wire["allow_short_positions"]
    if not isinstance(allow_short, bool):
        raise ValueError("shared risk allow_short_positions is invalid")
    portfolio = PortfolioComposition(
        portfolio_id=_wire_text(value["portfolio_id"], "portfolio_id"),
        version_id=_wire_text(value["version_id"], "version_id"),
        initial_capital=_wire_decimal(value["initial_capital"], "initial_capital"),
        base_currency=_wire_text(value["base_currency"], "base_currency"),
        components=tuple(components),
        shared_risk_policy=SharedRiskPolicy(
            max_gross_exposure_fraction=_wire_decimal(
                policy_wire["max_gross_exposure_fraction"], "max_gross_exposure_fraction"
            ),
            max_net_exposure_fraction=_wire_decimal(
                policy_wire["max_net_exposure_fraction"], "max_net_exposure_fraction"
            ),
            max_instrument_gross_exposure_fraction=_wire_decimal(
                policy_wire["max_instrument_gross_exposure_fraction"],
                "max_instrument_gross_exposure_fraction",
            ),
            max_component_gross_exposure_fraction=_wire_decimal(
                policy_wire["max_component_gross_exposure_fraction"],
                "max_component_gross_exposure_fraction",
            ),
            max_component_leverage=_wire_decimal(
                policy_wire["max_component_leverage"], "max_component_leverage"
            ),
            max_open_instruments=max_open,
            allow_short_positions=allow_short,
            target_conflict_policy=TargetConflictPolicy(
                _wire_text(policy_wire["target_conflict_policy"], "target_conflict_policy")
            ),
            risk_models=tuple(risk_models),
            definition_version=_wire_text(policy_wire["definition_version"], "definition_version"),
        ),
    )
    if value["fingerprint"] != portfolio.fingerprint:
        raise ValueError("portfolio execution policy fingerprint is invalid")
    return portfolio


def _wire_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _wire_decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be encoded as text")
    try:
        parsed = Decimal(value)
    except Exception as error:
        raise ValueError(f"{field_name} is not a valid decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed


__all__ = [
    "NAUTILUS_ENGINE_INPUT_VERSION",
    "NautilusCashDefinition",
    "NautilusComponentStrategyBinding",
    "NautilusEngineInput",
    "NautilusInstrumentDefinition",
    "NautilusVenueDefinition",
    "build_nautilus_engine_input",
    "evaluation_window_to_wire",
    "component_strategy_binding_to_wire",
    "component_strategy_bindings_from_wire",
]
