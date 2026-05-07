"""
Unit tests for Black-Scholes greek estimation.

Reference values are computed analytically and cross-checked against
published BS tables.  All inputs are deliberately simple round numbers
so that expected values can be verified by inspection.
"""

from __future__ import annotations

import math

import pytest

from app.lib.bs_greeks import estimate_greeks

# ── Helpers ───────────────────────────────────────────────────────────────────


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs_reference(S, K, T, sigma, r, q=0.0):
    """Return (call_delta, put_delta, gamma) via direct BS formula."""
    sqrt_t = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt_t)
    discount = math.exp(-q * T)
    gamma = discount * _norm_pdf(d1) / (S * sigma * sqrt_t)
    call_delta = discount * _norm_cdf(d1)
    put_delta = discount * (_norm_cdf(d1) - 1.0)
    return call_delta, put_delta, gamma


# ── Degenerate inputs ─────────────────────────────────────────────────────────


class TestDegenerateInputs:
    def test_zero_tte_returns_zeros(self):
        delta, gamma = estimate_greeks(100, 100, 0.0, 0.25, 0.05, is_call=True)
        assert delta == 0.0
        assert gamma == 0.0

    def test_negative_tte_returns_zeros(self):
        delta, gamma = estimate_greeks(100, 100, -0.1, 0.25, 0.05, is_call=True)
        assert delta == 0.0
        assert gamma == 0.0

    def test_zero_vol_returns_zeros(self):
        delta, gamma = estimate_greeks(100, 100, 1.0, 0.0, 0.05, is_call=True)
        assert delta == 0.0
        assert gamma == 0.0

    def test_zero_spot_returns_zeros(self):
        delta, gamma = estimate_greeks(0, 100, 1.0, 0.25, 0.05, is_call=True)
        assert delta == 0.0
        assert gamma == 0.0

    def test_zero_strike_returns_zeros(self):
        delta, gamma = estimate_greeks(100, 0, 1.0, 0.25, 0.05, is_call=True)
        assert delta == 0.0
        assert gamma == 0.0


# ── Call vs put symmetry ──────────────────────────────────────────────────────


class TestCallPutRelations:
    """Put-call parity implies: call_delta - put_delta = exp(-q*T)."""

    def test_atm_call_delta_in_valid_range(self):
        # With r=0.05, T=1, sigma=0.20: d1 ≈ 0.35 → N(d1) ≈ 0.636
        delta, _ = estimate_greeks(100, 100, 1.0, 0.20, 0.05, is_call=True)
        assert 0.0 < delta < 1.0

    def test_atm_put_delta_negative(self):
        delta, _ = estimate_greeks(100, 100, 1.0, 0.20, 0.05, is_call=False)
        assert -1.0 < delta < 0.0

    def test_call_minus_put_delta_equals_discount(self):
        """call_delta - put_delta = e^(-q*T); with q=0 this equals 1.0."""
        S, K, T, sigma, r = 100.0, 100.0, 0.5, 0.25, 0.04
        call_delta, _ = estimate_greeks(S, K, T, sigma, r, is_call=True)
        put_delta, _ = estimate_greeks(S, K, T, sigma, r, is_call=False)
        assert call_delta - put_delta == pytest.approx(1.0, abs=1e-9)

    def test_call_and_put_share_same_gamma(self):
        args = (100.0, 100.0, 1.0, 0.20, 0.05)
        _, call_gamma = estimate_greeks(*args, is_call=True)
        _, put_gamma = estimate_greeks(*args, is_call=False)
        assert call_gamma == pytest.approx(put_gamma, abs=1e-12)

    def test_gamma_is_positive(self):
        _, gamma = estimate_greeks(100, 100, 1.0, 0.20, 0.05, is_call=True)
        assert gamma > 0


# ── Numeric accuracy ──────────────────────────────────────────────────────────


class TestNumericAccuracy:
    @pytest.mark.parametrize(
        "S,K,T,sigma,r,q",
        [
            (100, 100, 1.0, 0.20, 0.05, 0.0),
            (110, 100, 0.5, 0.30, 0.03, 0.0),
            (95, 100, 0.25, 0.15, 0.02, 0.01),
            (200, 150, 2.0, 0.40, 0.06, 0.02),
        ],
    )
    def test_call_delta_matches_reference(self, S, K, T, sigma, r, q):
        ref_call, _, _ = _bs_reference(S, K, T, sigma, r, q)
        delta, _ = estimate_greeks(S, K, T, sigma, r, q, is_call=True)
        assert delta == pytest.approx(ref_call, abs=1e-9)

    @pytest.mark.parametrize(
        "S,K,T,sigma,r,q",
        [
            (100, 100, 1.0, 0.20, 0.05, 0.0),
            (110, 100, 0.5, 0.30, 0.03, 0.0),
            (95, 100, 0.25, 0.15, 0.02, 0.01),
        ],
    )
    def test_put_delta_matches_reference(self, S, K, T, sigma, r, q):
        _, ref_put, _ = _bs_reference(S, K, T, sigma, r, q)
        delta, _ = estimate_greeks(S, K, T, sigma, r, q, is_call=False)
        assert delta == pytest.approx(ref_put, abs=1e-9)

    @pytest.mark.parametrize(
        "S,K,T,sigma,r,q",
        [
            (100, 100, 1.0, 0.20, 0.05, 0.0),
            (110, 100, 0.5, 0.30, 0.03, 0.0),
        ],
    )
    def test_gamma_matches_reference(self, S, K, T, sigma, r, q):
        _, _, ref_gamma = _bs_reference(S, K, T, sigma, r, q)
        _, gamma = estimate_greeks(S, K, T, sigma, r, q, is_call=True)
        assert gamma == pytest.approx(ref_gamma, abs=1e-9)


# ── Moneyness intuition ───────────────────────────────────────────────────────


class TestMoneyness:
    def test_deep_itm_call_delta_near_one(self):
        delta, _ = estimate_greeks(200, 100, 1.0, 0.20, 0.05, is_call=True)
        assert delta > 0.95

    def test_deep_otm_call_delta_near_zero(self):
        delta, _ = estimate_greeks(50, 100, 1.0, 0.20, 0.05, is_call=True)
        assert delta < 0.05

    def test_deep_itm_put_delta_near_minus_one(self):
        delta, _ = estimate_greeks(50, 100, 1.0, 0.20, 0.05, is_call=False)
        assert delta < -0.95

    def test_deep_otm_put_delta_near_zero(self):
        delta, _ = estimate_greeks(200, 100, 1.0, 0.20, 0.05, is_call=False)
        assert delta > -0.05

    def test_gamma_higher_atm_than_deep_itm_or_deep_otm(self):
        # Deep ITM (S=150, K=100) and deep OTM (S=60, K=100) should have lower gamma
        gamma_atm = estimate_greeks(100, 100, 1.0, 0.20, 0.05, is_call=True)[1]
        gamma_deep_itm = estimate_greeks(150, 100, 1.0, 0.20, 0.05, is_call=True)[1]
        gamma_deep_otm = estimate_greeks(60, 100, 1.0, 0.20, 0.05, is_call=True)[1]
        assert gamma_atm > gamma_deep_itm
        assert gamma_atm > gamma_deep_otm
