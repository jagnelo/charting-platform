"""
Black-Scholes Greek estimation for European options.

Used to estimate delta and gamma when a data provider (e.g. yfinance) supplies
implied volatility but no Greeks. Estimates are clearly labelled in extra_greeks.
"""
from __future__ import annotations

import math


def estimate_greeks(
    spot: float,
    strike: float,
    tte_years: float,
    implied_vol: float,
    rfr: float,
    div_yield: float = 0.0,
    *,
    is_call: bool,
) -> tuple[float, float]:
    """
    Black-Scholes delta and gamma for a European option.

    Parameters
    ----------
    spot        : current underlying price
    strike      : option strike price
    tte_years   : time-to-expiry in years (must be > 0)
    implied_vol : annualised implied volatility (e.g. 0.25 for 25%)
    rfr         : continuous risk-free rate (e.g. 0.0527 for 5.27%)
    div_yield   : continuous dividend yield (default 0)
    is_call     : True for calls, False for puts

    Returns
    -------
    (delta, gamma) — both zero on degenerate inputs
    """
    if spot <= 0 or strike <= 0 or tte_years <= 0 or implied_vol <= 0:
        return 0.0, 0.0

    sqrt_t = math.sqrt(tte_years)
    vol_sqrt_t = implied_vol * sqrt_t

    d1 = (math.log(spot / strike) + (rfr - div_yield + 0.5 * implied_vol**2) * tte_years) / vol_sqrt_t

    discount = math.exp(-div_yield * tte_years)
    nd1 = _norm_cdf(d1)
    phi_d1 = _norm_pdf(d1)

    gamma = discount * phi_d1 / (spot * vol_sqrt_t)
    delta = discount * nd1 if is_call else discount * (nd1 - 1.0)
    return delta, gamma


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
