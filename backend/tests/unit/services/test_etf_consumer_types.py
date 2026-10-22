from app.services.etf_consumer_types import (
    is_equity_holding_type,
    is_placeholder_symbol,
    normalize_holding_type,
)


def test_holding_type_normalization_preserves_equity_eligibility_contract() -> None:
    assert normalize_holding_type(" Common Stock ") == "common_stock"
    assert is_equity_holding_type("Real Estate Investment Trust")
    assert is_equity_holding_type("Stock")
    assert not is_equity_holding_type("Money Market Fund")
    assert not is_equity_holding_type(None)


def test_placeholder_symbol_classification_is_case_insensitive_and_narrow() -> None:
    assert is_placeholder_symbol(" holding-123 ")
    assert not is_placeholder_symbol("SPY")
    assert not is_placeholder_symbol(None)
