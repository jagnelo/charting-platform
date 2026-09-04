from datetime import date, timedelta

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
