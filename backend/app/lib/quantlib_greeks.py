"""QuantLib-backed American-option Greeks with explicit provenance."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.lib.bs_greeks import estimate_greeks

try:  # QuantLib is an optional deployment dependency for lightweight workers.
    import QuantLib as ql
except ImportError:  # pragma: no cover - exercised in minimal deployments
    ql = None  # type: ignore[assignment]


def calculate_greeks(
    *,
    spot: float,
    strike: float,
    expiry: date,
    implied_vol: float,
    risk_free_rate: float,
    dividend_yield: float = 0.0,
    is_call: bool,
    valuation_date: date | None = None,
    steps: int = 200,
) -> dict[str, Any]:
    """Calculate American Greeks and return model/input provenance.

    If QuantLib is unavailable or rejects degenerate inputs, delta/gamma fall
    back to the existing Black-Scholes estimator and the result says so.
    """

    valuation = valuation_date or date.today()
    tte_days = (expiry - valuation).days
    base = {
        "valuation_date": valuation.isoformat(),
        "expiry": expiry.isoformat(),
        "spot": spot,
        "strike": strike,
        "implied_vol": implied_vol,
        "risk_free_rate": risk_free_rate,
        "dividend_yield": dividend_yield,
        "option_style": "american",
    }
    if (
        ql is None
        or spot <= 0
        or strike <= 0
        or implied_vol <= 0
        or tte_days <= 0
    ):
        delta, gamma = estimate_greeks(
            spot,
            strike,
            max(tte_days, 0) / 365.0,
            implied_vol,
            risk_free_rate,
            dividend_yield,
            is_call=is_call,
        )
        return {
            **base,
            "model": "black_scholes",
            "model_version": "legacy-bs-v1",
            "delta": delta,
            "gamma": gamma,
            "theta": None,
            "vega": None,
            "rho": None,
            "fallback": True,
        }

    try:
        ql_date = ql.Date(valuation.day, valuation.month, valuation.year)
        ql.Settings.instance().evaluationDate = ql_date
        maturity = ql.Date(expiry.day, expiry.month, expiry.year)
        day_count = ql.Actual365Fixed()
        calendar = ql.NullCalendar()
        spot_handle = ql.QuoteHandle(ql.SimpleQuote(spot))
        rate_handle = ql.YieldTermStructureHandle(ql.FlatForward(ql_date, risk_free_rate, day_count))
        div_handle = ql.YieldTermStructureHandle(ql.FlatForward(ql_date, dividend_yield, day_count))
        vol_handle = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(ql_date, calendar, implied_vol, day_count)
        )
        process = ql.BlackScholesMertonProcess(spot_handle, div_handle, rate_handle, vol_handle)
        payoff = ql.PlainVanillaPayoff(ql.Option.Call if is_call else ql.Option.Put, strike)
        exercise = ql.AmericanExercise(ql_date, maturity)
        option = ql.VanillaOption(payoff, exercise)
        option.setPricingEngine(ql.BinomialVanillaEngine(process, "crr", max(50, steps)))
        def optional_greek(name: str) -> float | None:
            try:
                return float(getattr(option, name)())
            except Exception:
                return None

        return {
            **base,
            "model": "quantlib_american_binomial_crr",
            "model_version": "quantlib-1.36-crr",
            "delta": float(option.delta()),
            "gamma": float(option.gamma()),
            "theta": optional_greek("theta"),
            "vega": optional_greek("vega"),
            "rho": optional_greek("rho"),
            "fallback": False,
            "steps": max(50, steps),
        }
    except Exception as exc:  # Keep provider data usable, but preserve cause.
        delta, gamma = estimate_greeks(
            spot,
            strike,
            tte_days / 365.0,
            implied_vol,
            risk_free_rate,
            dividend_yield,
            is_call=is_call,
        )
        return {
            **base,
            "model": "black_scholes",
            "model_version": "legacy-bs-v1",
            "delta": delta,
            "gamma": gamma,
            "theta": None,
            "vega": None,
            "rho": None,
            "fallback": True,
            "fallback_reason": str(exc),
        }
