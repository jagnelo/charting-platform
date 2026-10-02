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
from decimal import Decimal

from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import ProductClass
from app.strategy_lab_v2.nautilus_event_adapter import NautilusEventTape

NAUTILUS_ENGINE_INPUT_VERSION = "strategy-lab.nautilus-engine-input.v1"


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
            object.__setattr__(self, "base_currency", _currency(self.base_currency, "base_currency"))
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
    strategy_source_digest: str
    strategy_manifest_fingerprint: str
    entrypoint: str
    parameters: Mapping[str, object]
    random_seed: int
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
        instruments = tuple(self.instruments)
        if not instruments or any(
            not isinstance(item, NautilusInstrumentDefinition) for item in instruments
        ):
            raise ValueError("engine input requires instrument definitions")
        instrument_ids = [item.instrument_id for item in instruments]
        if len(instrument_ids) != len(set(instrument_ids)):
            raise ValueError("instrument definitions must be unique")
        instrument_map = {item.instrument_id: item for item in instruments}
        if any(
            record.instrument_id not in instrument_map for record in self.event_tape.events
        ):
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
            not part or any(not token.isidentifier() for token in part.split("."))
            for part in parts
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
        object.__setattr__(self, "instruments", tuple(sorted(instruments, key=lambda item: item.instrument_id)))
        object.__setattr__(self, "parameters", frozen_parameters)

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
    strategy_source_digest: str,
    strategy_manifest_fingerprint: str,
    entrypoint: str,
    parameters: Mapping[str, object],
    random_seed: int,
) -> NautilusEngineInput:
    """Construct and validate the complete engine-input boundary."""

    return NautilusEngineInput(
        trial_id=trial_id,
        attempt_id=attempt_id,
        data_snapshot_fingerprint=data_snapshot_fingerprint,
        event_tape=event_tape,
        instruments=tuple(instruments),
        venue=venue,
        strategy_source_digest=strategy_source_digest,
        strategy_manifest_fingerprint=strategy_manifest_fingerprint,
        entrypoint=entrypoint,
        parameters=parameters,
        random_seed=random_seed,
    )


__all__ = [
    "NAUTILUS_ENGINE_INPUT_VERSION",
    "NautilusCashDefinition",
    "NautilusEngineInput",
    "NautilusInstrumentDefinition",
    "NautilusVenueDefinition",
    "build_nautilus_engine_input",
]
