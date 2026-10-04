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


_INSTRUMENT_FIELDS_V6 = frozenset(
    {
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
)
_INSTRUMENT_FIELDS_V7 = _INSTRUMENT_FIELDS_V6 | frozenset(
    {
        "asset_class",
        "underlying",
        "option_kind",
        "strike_price",
        "margin_init",
        "margin_maint",
    }
)
_NAUTILUS_ASSET_CLASSES = frozenset(
    {"ALTERNATIVE", "COMMODITY", "CRYPTOCURRENCY", "DEBT", "EQUITY", "FX", "INDEX"}
)


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
        raise NautilusRuntimeDataError(
            "instrument_id is not a valid Nautilus identifier"
        ) from error


def materialize_native_instrument(definition: Mapping[str, Any]) -> Any:
    """Construct one explicit spot, futures, or vanilla-option instrument."""

    item = _required_mapping(definition, "instrument definition")
    instrument_fields = frozenset(item)
    if instrument_fields not in {_INSTRUMENT_FIELDS_V6, _INSTRUMENT_FIELDS_V7}:
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
    asset_class = item.get("asset_class")
    underlying = item.get("underlying")
    option_kind = item.get("option_kind")
    strike_price = item.get("strike_price")
    margin_init = item.get("margin_init")
    margin_maint = item.get("margin_maint")
    for field_name in ("min_quantity", "max_quantity"):
        if item[field_name] is not None:
            _decimal(item[field_name], field_name, positive=True)
    for field_name in ("activation_ns", "expiration_ns"):
        if item[field_name] is not None:
            _non_negative_int(item[field_name], field_name)
    if item["activation_ns"] is not None and item["expiration_ns"] is not None:
        if item["expiration_ns"] <= item["activation_ns"]:
            raise NautilusRuntimeDataError("expiration_ns must be after activation_ns")

    derivative = product_class in {"future", "option"}
    native_asset_class: str | None = None
    native_option_kind: str | None = None
    if derivative:
        if not isinstance(asset_class, str) or asset_class not in _NAUTILUS_ASSET_CLASSES:
            raise NautilusRuntimeDataError("listed derivatives require a supported asset_class")
        native_asset_class = asset_class
        underlying = _required_text(underlying, "underlying")
        if item["activation_ns"] is None or item["expiration_ns"] is None:
            raise NautilusRuntimeDataError(
                "listed derivatives require activation and expiration timestamps"
            )
        if item["base_currency"] is not None:
            raise NautilusRuntimeDataError(
                "listed derivatives must not declare a spot base_currency"
            )
        if (
            size_precision != 0
            or size_increment != 1
            or item["min_quantity"] is None
            or _decimal(item["min_quantity"], "min_quantity")
            != _decimal(item["min_quantity"], "min_quantity").to_integral_value()
        ):
            raise NautilusRuntimeDataError(
                "listed derivatives require explicit whole-contract lot terms"
            )
        margin_init = _decimal(margin_init, "margin_init", positive=True)
        margin_maint = _decimal(margin_maint, "margin_maint", positive=True)
        if margin_maint > margin_init:
            raise NautilusRuntimeDataError("margin_maint must not exceed margin_init")
        if product_class == "future":
            if option_kind is not None or strike_price is not None:
                raise NautilusRuntimeDataError("futures must not declare option-only terms")
        else:
            if not isinstance(option_kind, str) or option_kind not in {"CALL", "PUT"}:
                raise NautilusRuntimeDataError("listed options require option_kind CALL or PUT")
            native_option_kind = option_kind
            strike_price = _decimal(strike_price, "strike_price", positive=True)
    elif any(
        value is not None
        for value in (
            asset_class,
            underlying,
            option_kind,
            strike_price,
            margin_init,
            margin_maint,
        )
    ):
        raise NautilusRuntimeDataError(
            "non-derivative instruments must not declare listed derivative terms"
        )

    from nautilus_trader.model import (  # type: ignore[import-not-found,attr-defined]
        AssetClass,
        Currency,
        CurrencyPair,
        Equity,
        FuturesContract,
        OptionContract,
        OptionKind,
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
            raise NautilusRuntimeDataError("equity multiplier requires an explicit native adapter")
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
    if product_class == "future":
        assert native_asset_class is not None
        return FuturesContract(
            native_id,
            Symbol(raw_symbol),
            getattr(AssetClass, native_asset_class),
            underlying,
            item["activation_ns"],
            item["expiration_ns"],
            Currency.from_str(quote_currency),
            price_precision,
            price_step,
            Quantity(multiplier, size_precision),
            size_step,
            0,
            0,
            max_quantity=(
                Quantity(_decimal(item["max_quantity"], "max_quantity"), size_precision)
                if item["max_quantity"] is not None
                else None
            ),
            min_quantity=Quantity(_decimal(item["min_quantity"], "min_quantity"), size_precision),
            margin_init=margin_init,
            margin_maint=margin_maint,
        )
    if product_class == "option":
        assert native_asset_class is not None
        assert native_option_kind is not None
        return OptionContract(
            native_id,
            Symbol(raw_symbol),
            getattr(AssetClass, native_asset_class),
            underlying,
            getattr(OptionKind, native_option_kind),
            Price(strike_price, price_precision),
            Currency.from_str(quote_currency),
            item["activation_ns"],
            item["expiration_ns"],
            price_precision,
            price_step,
            Quantity(multiplier, size_precision),
            size_step,
            0,
            0,
            max_quantity=(
                Quantity(_decimal(item["max_quantity"], "max_quantity"), size_precision)
                if item["max_quantity"] is not None
                else None
            ),
            min_quantity=Quantity(_decimal(item["min_quantity"], "min_quantity"), size_precision),
            margin_init=margin_init,
            margin_maint=margin_maint,
        )
    raise NautilusRuntimeDataError(
        f"product_class {product_class!r} requires an explicit native adapter"
    )


def materialize_native_venue(definition: Mapping[str, Any]) -> tuple[Any, Any, Any, list[Any]]:
    """Construct one shared venue/account tuple for ``BacktestEngine.add_venue``."""

    item = _required_mapping(definition, "venue definition")
    required = {"venue_id", "oms_type", "account_type", "base_currency", "cash", "fee_model"}
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


def materialize_native_fee_model(definition: Any) -> Any | None:
    """Build a pinned-runtime fixed-per-fill model, including signed rebates."""

    if definition is None:
        return None
    item = _required_mapping(definition, "fee model")
    if set(item) != {"kind", "amount", "currency"}:
        raise NautilusRuntimeDataError("fee model fields are invalid")
    if _required_text(item["kind"], "fee_model.kind") != "fixed_per_fill":
        raise NautilusRuntimeDataError("fee model kind is unsupported")
    amount = _decimal(item["amount"], "fee_model.amount")
    currency_code = _required_text(item["currency"], "fee_model.currency")
    if (
        len(currency_code) != 3
        or not currency_code.isascii()
        or not currency_code.isalpha()
        or currency_code != currency_code.upper()
    ):
        raise NautilusRuntimeDataError("fee model currency must be a canonical three-letter code")

    from nautilus_trader.execution import FeeModel  # type: ignore[import-not-found,attr-defined]
    from nautilus_trader.model import Currency, Money  # type: ignore[import-not-found,attr-defined]

    try:
        commission = Money(amount, Currency.from_str(currency_code))
    except (TypeError, ValueError) as error:
        raise NautilusRuntimeDataError("fee model commission is not representable") from error
    commission_parts = str(commission).split()
    try:
        represented_amount = Decimal(commission_parts[0])
    except (IndexError, InvalidOperation, ValueError) as error:
        raise NautilusRuntimeDataError("fee model commission representation is invalid") from error
    if len(commission_parts) != 2 or commission_parts[1] != currency_code:
        raise NautilusRuntimeDataError(
            "fee model commission currency changed during materialization"
        )
    if represented_amount != amount:
        raise NautilusRuntimeDataError("fee model commission exceeds native currency precision")

    class FixedPerFillFeeModel(FeeModel):
        def get_commission(
            self, order: Any, fill_quantity: Any, fill_px: Any, instrument: Any
        ) -> Any:
            del order, fill_quantity, fill_px, instrument
            return commission

    return FixedPerFillFeeModel()


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
    *,
    native_init_time_ns: int | None = None,
) -> Any:
    """Convert one strict wire record into a Nautilus quote/trade/bar."""

    instrument_id, event_type, event_time_ns, values = _event_values(event)
    if native_init_time_ns is None:
        native_init_time_ns = event_time_ns
    if (
        not isinstance(native_init_time_ns, int)
        or isinstance(native_init_time_ns, bool)
        or native_init_time_ns < event_time_ns
    ):
        raise NautilusRuntimeDataError(
            "native event init time must be an integer no earlier than event time"
        )
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
            native_init_time_ns,
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
            aggressor_side = getattr(
                AggressorSide,
                _required_text(values["aggressor_side"], "trade.aggressor_side").upper(),
            )
        except AttributeError as error:
            raise NautilusRuntimeDataError("trade aggressor_side is unsupported") from error
        return TradeTick(
            instrument_id,
            Price(_decimal(values["price"], "trade.price"), price_precision),
            Quantity(_decimal(values["size"], "trade.size"), size_precision),
            aggressor_side,
            TradeId(trade_id),
            event_time_ns,
            native_init_time_ns,
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
                "ts_init": native_init_time_ns,
            }
        )
    raise NautilusRuntimeDataError(f"event_type {event_type!r} is unsupported")


__all__ = [
    "NautilusRuntimeDataError",
    "materialize_native_fee_model",
    "materialize_native_event",
    "materialize_native_instrument",
    "materialize_native_venue",
]
