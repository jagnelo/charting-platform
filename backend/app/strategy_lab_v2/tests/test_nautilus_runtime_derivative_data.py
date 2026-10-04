from __future__ import annotations

import sys
from decimal import Decimal
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from app.strategy_lab_v2.nautilus_runtime_data import (
    NautilusRuntimeDataError,
    materialize_native_instrument,
)


class _NativeValue:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs


class _NativeInstrumentId:
    @classmethod
    def from_str(cls, value: str) -> str:
        return f"instrument:{value}"


class _NativeCurrency:
    @classmethod
    def from_str(cls, value: str) -> str:
        return f"currency:{value}"


class _NativePrice(_NativeValue):
    pass


class _NativeQuantity(_NativeValue):
    pass


class _NativeSymbol(str):
    pass


def _install_native_model(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    model = ModuleType("nautilus_trader.model")
    for name, value in {
        "AssetClass": SimpleNamespace(COMMODITY="asset:commodity", EQUITY="asset:equity"),
        "Currency": _NativeCurrency,
        "CurrencyPair": type("CurrencyPair", (_NativeValue,), {}),
        "Equity": type("Equity", (_NativeValue,), {}),
        "FuturesContract": type("FuturesContract", (_NativeValue,), {}),
        "InstrumentId": _NativeInstrumentId,
        "OptionContract": type("OptionContract", (_NativeValue,), {}),
        "OptionKind": SimpleNamespace(CALL="option:call", PUT="option:put"),
        "Price": _NativePrice,
        "Quantity": _NativeQuantity,
        "Symbol": _NativeSymbol,
    }.items():
        setattr(model, name, value)
    package = ModuleType("nautilus_trader")
    package.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nautilus_trader", package)
    monkeypatch.setitem(sys.modules, "nautilus_trader.model", model)
    return SimpleNamespace(model=model)


def _derivative_definition(product_class: str) -> dict[str, Any]:
    return {
        "instrument_id": "CLZ26.NYMEX" if product_class == "future" else "CLZ26C080.NYMEX",
        "raw_symbol": "CLZ26" if product_class == "future" else "CLZ26C080",
        "venue_id": "NYMEX",
        "product_class": product_class,
        "base_currency": None,
        "quote_currency": "USD",
        "price_precision": 2,
        "size_precision": 0,
        "price_increment": "0.01",
        "size_increment": "1",
        "multiplier": "1000" if product_class == "future" else "100",
        "min_quantity": "1",
        "max_quantity": None,
        "activation_ns": 1_767_225_600_000_000_000,
        "expiration_ns": 1_800_748_800_000_000_000,
        "bar_type": None,
        "asset_class": "COMMODITY",
        "underlying": "CL",
        "option_kind": "CALL" if product_class == "option" else None,
        "strike_price": "80" if product_class == "option" else None,
        "margin_init": "0.12",
        "margin_maint": "0.11",
    }


def test_materializes_listed_future_with_explicit_contract_and_margin_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = _install_native_model(monkeypatch)

    result = materialize_native_instrument(_derivative_definition("future"))

    assert isinstance(result, native.model.FuturesContract)
    assert result.args[0] == "instrument:CLZ26.NYMEX"
    assert result.args[2] == "asset:commodity"
    assert result.args[3] == "CL"
    assert result.args[4:6] == (1_767_225_600_000_000_000, 1_800_748_800_000_000_000)
    assert result.kwargs["margin_init"] == Decimal("0.12")
    assert result.kwargs["margin_maint"] == Decimal("0.11")


def test_materializes_vanilla_option_with_explicit_right_strike_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = _install_native_model(monkeypatch)

    result = materialize_native_instrument(_derivative_definition("option"))

    assert isinstance(result, native.model.OptionContract)
    assert result.args[0] == "instrument:CLZ26C080.NYMEX"
    assert result.args[2:5] == ("asset:commodity", "CL", "option:call")
    strike = result.args[5]
    assert strike.args == (Decimal("80"), 2)
    assert result.kwargs["margin_init"] == Decimal("0.12")
    assert result.kwargs["margin_maint"] == Decimal("0.11")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("activation_ns", None, "activation and expiration"),
        ("margin_init", None, "margin_init"),
        ("min_quantity", None, "whole-contract lot terms"),
        ("asset_class", "UNKNOWN", "supported asset_class"),
    ),
)
def test_rejects_incomplete_derivative_metadata_before_native_import(
    field: str,
    value: Any,
    message: str,
) -> None:
    definition = _derivative_definition("future")
    definition[field] = value

    with pytest.raises(NautilusRuntimeDataError, match=message):
        materialize_native_instrument(definition)


def test_rejects_legacy_payloads_that_claim_derivatives_without_v7_terms() -> None:
    definition = _derivative_definition("future")
    del definition["asset_class"]
    del definition["underlying"]
    del definition["option_kind"]
    del definition["strike_price"]
    del definition["margin_init"]
    del definition["margin_maint"]

    with pytest.raises(NautilusRuntimeDataError, match="supported asset_class"):
        materialize_native_instrument(definition)
