import math
from datetime import date, timedelta

import pytest

from app.lib.quantlib_greeks import calculate_greeks


def test_american_quantlib_greeks_are_finite_and_labeled():
    result = calculate_greeks(
        spot=100,
        strike=100,
        expiry=date.today() + timedelta(days=90),
        implied_vol=0.25,
        risk_free_rate=0.05,
        is_call=True,
    )
    assert result["model"].startswith("quantlib_american")
    assert result["fallback"] is False
    assert 0 < result["delta"] < 1
    assert result["gamma"] > 0
    assert result["model_version"] == "quantlib-1.36-crr"


def test_degenerate_inputs_use_explicit_fallback():
    result = calculate_greeks(
        spot=0,
        strike=100,
        expiry=date.today() + timedelta(days=90),
        implied_vol=0.25,
        risk_free_rate=0.05,
        is_call=False,
    )
    assert result["fallback"] is True
    assert result["model"] == "black_scholes"
    assert result["delta"] == 0


@pytest.mark.parametrize(
    ("spot", "strike", "days", "implied_vol", "rate", "dividend", "is_call"),
    [
        (100.0, 100.0, 1, 0.80, -0.01, 0.02, False),
        (150.0, 100.0, 30, 0.35, 0.04, 0.03, False),
        (60.0, 100.0, 365, 0.90, 0.00, 0.00, True),
    ],
)
def test_american_greeks_remain_finite_for_short_and_extreme_contracts(
    spot, strike, days, implied_vol, rate, dividend, is_call
):
    result = calculate_greeks(
        spot=spot,
        strike=strike,
        expiry=date.today() + timedelta(days=days),
        implied_vol=implied_vol,
        risk_free_rate=rate,
        dividend_yield=dividend,
        is_call=is_call,
        steps=100,
    )

    assert result["fallback"] is False
    assert result["model"] == "quantlib_american_binomial_crr"
    for name in ("delta", "gamma", "theta", "vega", "rho"):
        assert result[name] is not None
        assert math.isfinite(result[name])


def test_quantlib_failure_uses_labeled_legacy_fallback(monkeypatch):
    import app.lib.quantlib_greeks as module

    monkeypatch.setattr(module, "ql", None)
    result = module.calculate_greeks(
        spot=100,
        strike=100,
        expiry=date.today() + timedelta(days=90),
        implied_vol=0.25,
        risk_free_rate=0.05,
        is_call=False,
    )

    assert result["fallback"] is True
    assert result["model"] == "black_scholes"
    assert result["model_version"] == "legacy-bs-v1"
    assert result["delta"] < 0
    assert result["gamma"] > 0
    assert result["theta"] is None
    assert result["vega"] is None
    assert result["rho"] is None
