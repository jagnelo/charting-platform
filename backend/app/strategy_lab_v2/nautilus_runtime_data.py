"""Runtime-local conversion of authenticated wire data to Nautilus values.

The module has no Nautilus import at module load time so backend validation can
exercise its schema guards without the isolated engine dependency.  The
materializers import the pinned runtime types only when called inside the
Nautilus image.  They accept explicit metadata; they never infer precision,
currency, venue, or product semantics from a symbol string.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any


class NautilusRuntimeDataError(ValueError):
    """Stable schema/materialization failure for the isolated runtime."""


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NautilusRuntimeDataError(f"{field_name} must be a non-empty string")
    if any(character in value for character in "\x00\r\n"):
        raise NautilusRuntimeDataError(f"{field_name} contains control characters")
    return value


def _required_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise NautilusRuntimeDataError(f"{field_name} must be a string-keyed mapping")
    return value


def _decimal(value: Any, field_name: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal):
        raise NautilusRuntimeDataError(f"{field_name} must be a finite decimal value")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise NautilusRuntimeDataError(f"{field_name} must be a finite decimal value") from error
    if not result.is_finite() or (positive and result <= 0):
        qualifier = "positive " if positive else ""
        raise NautilusRuntimeDataError(f"{field_name} must be a finite {qualifier}decimal value")
    return result


def _non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise NautilusRuntimeDataError(f"{field_name} must be a non-negative integer")
    return value


def _precision(value: Any, field_name: str) -> int:
    return _non_negative_int(value, field_name)


def _instrument_id(value: str) -> Any:
    from nautilus_trader.model import InstrumentId  # type: ignore[import-not-found,attr-defined]

    try:
        return InstrumentId.from_str(value)
    except (TypeError, ValueError) as error:
        raise NautilusRuntimeDataError("instrument_id is not a valid Nautilus identifier") from error


def materialize_native_instrument(definition: Mapping[str, Any]) -> Any:
    """Construct one explicit FX/crypto/equity instrument in Nautilus."""

    item = _required_mapping(definition, "instrument definition")
    required = {
        "instrument_id",
        "raw_symbol",
        "venue_id",
        "product_class",
        "base_currency",
        "quote_currency",
        "price_precision",
        "size_precision",
        "price_increment",
        "size_increment",
        "multiplier",
        "min_quantity",
        "max_quantity",
        "activation_ns",
        "expiration_ns",
        "bar_type",
    }
    if set(item) != required:
        raise NautilusRuntimeDataError("instrument definition fields are invalid")
    instrument_id = _required_text(item["instrument_id"], "instrument_id")
    raw_symbol = _required_text(item["raw_symbol"], "raw_symbol")
    _required_text(item["venue_id"], "venue_id")
    product_class = _required_text(item["product_class"], "product_class")
    quote_currency = _required_text(item["quote_currency"], "quote_currency")
    if len(quote_currency) != 3 or not quote_currency.isascii() or not quote_currency.isalpha():
        raise NautilusRuntimeDataError("quote_currency must be a three-letter currency code")
    price_precision = _precision(item["price_precision"], "price_precision")
    size_precision = _precision(item["size_precision"], "size_precision")
    price_increment = _decimal(item["price_increment"], "price_increment", positive=True)
    size_increment = _decimal(item["size_increment"], "size_increment", positive=True)
    multiplier = _decimal(item["multiplier"], "multiplier", positive=True)
    for field_name in ("min_quantity", "max_quantity"):
        if item[field_name] is not None:
            _decimal(item[field_name], field_name, positive=True)
    for field_name in ("activation_ns", "expiration_ns"):
        if item[field_name] is not None:
            _non_negative_int(item[field_name], field_name)
    if item["activation_ns"] is not None and item["expiration_ns"] is not None:
        if item["expiration_ns"] <= item["activation_ns"]:
            raise NautilusRuntimeDataError("expiration_ns must be after activation_ns")

    from nautilus_trader.model import (  # type: ignore[import-not-found,attr-defined]
        Currency,
        CurrencyPair,
        Equity,
        Price,
        Quantity,
        Symbol,
    )

    native_id = _instrument_id(instrument_id)
    price_step = Price(price_increment, price_precision)
    size_step = Quantity(size_increment, size_precision)
    if product_class in {"fx", "crypto"}:
        base_currency = item.get("base_currency")
        base_currency = _required_text(base_currency, "base_currency")
        if len(base_currency) != 3 or not base_currency.isascii() or not base_currency.isalpha():
            raise NautilusRuntimeDataError("base_currency must be a three-letter currency code")
        return CurrencyPair(
            native_id,
            Symbol(raw_symbol),
            Currency.from_str(base_currency),
            Currency.from_str(quote_currency),
            price_precision,
            size_precision,
            price_step,
            size_step,
            0,
            0,
            multiplier=Quantity(multiplier, size_precision),
            min_quantity=(
                Quantity(_decimal(item["min_quantity"], "min_quantity"), size_precision)
                if item["min_quantity"] is not None
                else None
            ),
            max_quantity=(
                Quantity(_decimal(item["max_quantity"], "max_quantity"), size_precision)
                if item["max_quantity"] is not None
                else None
            ),
        )
    if product_class == "equity":
        if multiplier != 1:
            raise NautilusRuntimeDataError(
                "equity multiplier requires an explicit native adapter"
            )
        return Equity(
            native_id,
            Symbol(raw_symbol),
            Currency.from_str(quote_currency),
            price_precision,
            price_step,
            0,
            0,
            min_quantity=(
                Quantity(_decimal(item["min_quantity"], "min_quantity"), size_precision)
                if item["min_quantity"] is not None
                else None
            ),
            max_quantity=(
                Quantity(_decimal(item["max_quantity"], "max_quantity"), size_precision)
                if item["max_quantity"] is not None
                else None
            ),
        )
    raise NautilusRuntimeDataError(
        f"product_class {product_class!r} requires an explicit native adapter"
    )


def materialize_native_venue(definition: Mapping[str, Any]) -> tuple[Any, Any, Any, list[Any]]:
    """Construct one shared venue/account tuple for ``BacktestEngine.add_venue``."""

    item = _required_mapping(definition, "venue definition")
    required = {"venue_id", "oms_type", "account_type", "base_currency", "cash"}
    if set(item) != required:
        raise NautilusRuntimeDataError("venue definition fields are invalid")
    venue_id = _required_text(item["venue_id"], "venue_id")
    oms_name = _required_text(item["oms_type"], "oms_type").upper()
    account_name = _required_text(item["account_type"], "account_type").upper()
    base_currency = _required_text(item["base_currency"], "base_currency")
    cash_values = item["cash"]
    if not isinstance(cash_values, list) or not cash_values:
        raise NautilusRuntimeDataError("venue cash must be a non-empty list")

    from nautilus_trader.model import (  # type: ignore[import-not-found,attr-defined]
        AccountType,
        Currency,
        Money,
        OmsType,
        Venue,
    )

    try:
        oms_type = getattr(OmsType, oms_name)
        account_type = getattr(AccountType, account_name)
    except AttributeError as error:
        raise NautilusRuntimeDataError("venue account or OMS type is unsupported") from error
    balances: list[Any] = []
    currencies: set[str] = set()
    for raw in cash_values:
        cash = _required_mapping(raw, "venue cash")
        if set(cash) != {"currency", "amount"}:
            raise NautilusRuntimeDataError("venue cash fields are invalid")
        currency = _required_text(cash["currency"], "cash currency")
        amount = _decimal(cash["amount"], "cash amount", positive=True)
        if currency in currencies:
            raise NautilusRuntimeDataError("venue cash currencies must be unique")
        currencies.add(currency)
        balances.append(Money(amount, Currency.from_str(currency)))
    if base_currency not in currencies:
        raise NautilusRuntimeDataError("venue base currency must have an initial cash balance")
    return Venue(venue_id), oms_type, account_type, balances


def _event_values(event: Mapping[str, Any]) -> tuple[Any, str, int, Any]:
    item = _required_mapping(event, "event")
    required = {
        "dependency_id",
        "event_id",
        "instrument_id",
        "event_type",
        "event_time_ns",
        "sequence",
        "values",
    }
    if set(item) != required:
        raise NautilusRuntimeDataError("event fields are invalid")
    instrument_id = _required_text(item["instrument_id"], "event.instrument_id")
    event_type = _required_text(item["event_type"], "event.event_type")
    event_time_ns = _non_negative_int(item["event_time_ns"], "event.event_time_ns")
    values = _required_mapping(item["values"], "event.values")
    return _instrument_id(instrument_id), event_type, event_time_ns, values


def materialize_native_event(
    event: Mapping[str, Any],
    instrument_definition: Mapping[str, Any],
) -> Any:
    """Convert one strict wire record into a Nautilus quote/trade/bar."""

    instrument_id, event_type, event_time_ns, values = _event_values(event)
    definition = _required_mapping(instrument_definition, "instrument definition")
    price_precision = _precision(definition.get("price_precision"), "price_precision")
    size_precision = _precision(definition.get("size_precision"), "size_precision")
    from nautilus_trader.model import (  # type: ignore[import-not-found,attr-defined]
        Price,
        Quantity,
        QuoteTick,
        TradeTick,
    )

    if event_type == "quote":
        required = {"bid", "ask", "bid_size", "ask_size"}
        if set(values) != required:
            raise NautilusRuntimeDataError("quote event values are invalid")
        return QuoteTick(
            instrument_id,
            Price(_decimal(values["bid"], "quote.bid"), price_precision),
            Price(_decimal(values["ask"], "quote.ask"), price_precision),
            Quantity(_decimal(values["bid_size"], "quote.bid_size"), size_precision),
            Quantity(_decimal(values["ask_size"], "quote.ask_size"), size_precision),
            event_time_ns,
            event_time_ns,
        )
    if event_type == "trade":
        required = {"price", "size", "aggressor_side"}
        if set(values) != required:
            raise NautilusRuntimeDataError("trade event values are invalid")
        from nautilus_trader.model import (  # type: ignore[import-not-found,attr-defined]
            AggressorSide,
            TradeId,
        )

        trade_id = _required_text(event["event_id"], "event.event_id")
        try:
            aggressor_side = getattr(AggressorSide, _required_text(values["aggressor_side"], "trade.aggressor_side").upper())
        except AttributeError as error:
            raise NautilusRuntimeDataError("trade aggressor_side is unsupported") from error
        return TradeTick(
            instrument_id,
            Price(_decimal(values["price"], "trade.price"), price_precision),
            Quantity(_decimal(values["size"], "trade.size"), size_precision),
            aggressor_side,
            TradeId(trade_id),
            event_time_ns,
            event_time_ns,
        )
    if event_type == "ohlcv":
        from nautilus_trader.model import Bar  # type: ignore[import-not-found,attr-defined]

        bar_type = _required_text(definition.get("bar_type"), "instrument.bar_type")
        required = {"open", "high", "low", "close", "volume"}
        if set(values) != required:
            raise NautilusRuntimeDataError("ohlcv event values are invalid")
        return Bar.from_dict(
            {
                "bar_type": bar_type,
                "open": str(_decimal(values["open"], "ohlcv.open")),
                "high": str(_decimal(values["high"], "ohlcv.high")),
                "low": str(_decimal(values["low"], "ohlcv.low")),
                "close": str(_decimal(values["close"], "ohlcv.close")),
                "volume": str(_decimal(values["volume"], "ohlcv.volume")),
                "ts_event": event_time_ns,
                "ts_init": event_time_ns,
            }
        )
    raise NautilusRuntimeDataError(f"event_type {event_type!r} is unsupported")


__all__ = [
    "NautilusRuntimeDataError",
    "materialize_native_event",
    "materialize_native_instrument",
    "materialize_native_venue",
]
