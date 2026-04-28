"""
Unit tests for the options exposure computation functions.

All tests are pure — no DB, no async. They exercise _compute_exposure,
_find_gamma_flip, _find_max_pain, _compute_implied_move, and _compute_key_levels
directly using hand-crafted _ContractQuote lists with known answers.
"""

from datetime import date
from decimal import Decimal

import pytest

from tests.unit.conftest import AsyncSessionAdapter

from app.models.instrument import OptionRight
from app.services.options_exposure import (
    ExposureLadderRow,
    _ContractQuote,
    _compute_exposure,
    _compute_implied_move,
    _find_gamma_flip,
    _find_max_pain,
    get_options_exposure,
    list_exposure_expirations,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

EXP_1 = date(2024, 1, 19)
EXP_2 = date(2024, 2, 16)
SPOT = 180.0


def _call(strike, gamma, delta, oi, expiry=EXP_1, cs=100, vol=None, mark=None):
    return _ContractQuote(
        strike=Decimal(str(strike)),
        right=OptionRight.CALL,
        expiry_date=expiry,
        contract_size=Decimal(str(cs)),
        gamma=Decimal(str(gamma)) if gamma is not None else None,
        delta=Decimal(str(delta)) if delta is not None else None,
        open_interest=Decimal(str(oi)),
        volume=Decimal("500"),
        implied_vol=Decimal(str(vol)) if vol is not None else None,
        mark=Decimal(str(mark)) if mark is not None else None,
        bid=None,
        ask=None,
    )


def _put(strike, gamma, delta, oi, expiry=EXP_1, cs=100, vol=None, mark=None):
    return _ContractQuote(
        strike=Decimal(str(strike)),
        right=OptionRight.PUT,
        expiry_date=expiry,
        contract_size=Decimal(str(cs)),
        gamma=Decimal(str(gamma)) if gamma is not None else None,
        delta=Decimal(str(delta)) if delta is not None else None,
        open_interest=Decimal(str(oi)),
        volume=Decimal("300"),
        implied_vol=Decimal(str(vol)) if vol is not None else None,
        mark=Decimal(str(mark)) if mark is not None else None,
        bid=None,
        ask=None,
    )


# ── GEX sign convention ───────────────────────────────────────────────────────

class TestGexSignConvention:
    def test_call_gex_is_positive(self):
        quotes = [_call(strike=180, gamma=0.01, delta=0.5, oi=100)]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        assert len(ladder) == 1
        assert ladder[0].call_gex > 0

    def test_put_gex_is_negative(self):
        quotes = [_put(strike=180, gamma=0.01, delta=-0.5, oi=100)]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        assert ladder[0].put_gex < 0

    def test_net_gex_call_dominates(self):
        # Same gamma/OI but call dominates → net positive
        quotes = [
            _call(strike=180, gamma=0.02, delta=0.5, oi=200),
            _put(strike=180, gamma=0.01, delta=-0.5, oi=100),
        ]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        assert ladder[0].net_gex > 0

    def test_net_gex_put_dominates(self):
        quotes = [
            _call(strike=180, gamma=0.01, delta=0.5, oi=100),
            _put(strike=180, gamma=0.02, delta=-0.5, oi=200),
        ]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        assert ladder[0].net_gex < 0

    def test_gex_formula_exact(self):
        # call_gex = gamma × OI × contract_size × spot²
        gamma, oi, cs = 0.01, 100, 100
        expected_call = gamma * oi * cs * SPOT * SPOT
        quotes = [_call(strike=180, gamma=gamma, delta=0.5, oi=oi, cs=cs)]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        assert ladder[0].call_gex == pytest.approx(expected_call)


# ── DEX ────────────────────────────────────────────────────────────────────────

class TestDex:
    def test_call_dex_positive(self):
        quotes = [_call(strike=180, gamma=0.01, delta=0.5, oi=100)]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        assert ladder[0].call_dex > 0

    def test_put_dex_negative(self):
        quotes = [_put(strike=180, gamma=0.01, delta=-0.5, oi=100)]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        assert ladder[0].put_dex < 0

    def test_dex_formula_exact(self):
        delta, oi, cs = 0.5, 100, 100
        expected_call = delta * oi * cs
        quotes = [_call(strike=180, gamma=0.01, delta=delta, oi=oi, cs=cs)]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        assert ladder[0].call_dex == pytest.approx(expected_call)


# ── Ladder structure ─────────────────────────────────────────────────────────

class TestLadderStructure:
    def test_strikes_sorted_ascending(self):
        quotes = [
            _call(strike=185, gamma=0.01, delta=0.4, oi=50),
            _call(strike=175, gamma=0.01, delta=0.6, oi=50),
            _call(strike=180, gamma=0.01, delta=0.5, oi=50),
        ]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        strikes = [r.strike for r in ladder]
        assert strikes == sorted(strikes)

    def test_one_row_per_strike(self):
        quotes = [
            _call(strike=180, gamma=0.01, delta=0.5, oi=100),
            _put(strike=180, gamma=0.01, delta=-0.5, oi=80),
            _call(strike=185, gamma=0.008, delta=0.4, oi=60),
        ]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        assert len(ladder) == 2

    def test_empty_quotes_returns_empty_ladder(self):
        ladder, kl, tg, td, pcr_oi, pcr_vol, imp, exps, _estimated = _compute_exposure([], SPOT)
        assert ladder == []
        assert tg == 0.0
        assert exps == []

    def test_by_expiry_present_in_rows(self):
        quotes = [
            _call(strike=180, gamma=0.01, delta=0.5, oi=100, expiry=EXP_1),
            _call(strike=180, gamma=0.01, delta=0.5, oi=80, expiry=EXP_2),
        ]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        assert EXP_1.isoformat() in ladder[0].by_expiry
        assert EXP_2.isoformat() in ladder[0].by_expiry

    def test_by_expiry_call_gex_matches_total(self):
        quotes = [
            _call(strike=180, gamma=0.01, delta=0.5, oi=100, expiry=EXP_1),
        ]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        breakdown = ladder[0].by_expiry[EXP_1.isoformat()]
        assert breakdown.call_gex == pytest.approx(ladder[0].call_gex)


# ── Key levels ───────────────────────────────────────────────────────────────

class TestKeyLevels:
    def test_call_wall_is_highest_call_oi_strike(self):
        quotes = [
            _call(strike=180, gamma=0.01, delta=0.5, oi=500),
            _call(strike=185, gamma=0.01, delta=0.4, oi=200),
        ]
        _, kl, *_ = _compute_exposure(quotes, SPOT)
        assert kl.call_wall == pytest.approx(180.0)

    def test_put_wall_is_highest_put_oi_strike(self):
        quotes = [
            _put(strike=175, gamma=0.01, delta=-0.5, oi=800),
            _put(strike=170, gamma=0.01, delta=-0.6, oi=300),
        ]
        _, kl, *_ = _compute_exposure(quotes, SPOT)
        assert kl.put_wall == pytest.approx(175.0)

    def test_no_call_wall_when_no_calls(self):
        quotes = [_put(strike=175, gamma=0.01, delta=-0.5, oi=100)]
        _, kl, *_ = _compute_exposure(quotes, SPOT)
        assert kl.call_wall is None

    def test_no_put_wall_when_no_puts(self):
        quotes = [_call(strike=185, gamma=0.01, delta=0.4, oi=100)]
        _, kl, *_ = _compute_exposure(quotes, SPOT)
        assert kl.put_wall is None


# ── Gamma flip ────────────────────────────────────────────────────────────────

class TestGammaFlip:
    def test_finds_zero_crossing(self):
        # Ladder: strike 175 → net_gex > 0, strike 185 → net_gex < 0
        quotes = [
            _call(strike=175, gamma=0.02, delta=0.6, oi=200),  # positive
            _put(strike=185, gamma=0.03, delta=-0.3, oi=300),  # negative dominates
        ]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        flip = _find_gamma_flip(ladder)
        assert flip is not None
        assert 175.0 < flip < 185.0

    def test_no_flip_when_all_positive(self):
        quotes = [
            _call(strike=175, gamma=0.02, delta=0.6, oi=200),
            _call(strike=185, gamma=0.02, delta=0.4, oi=200),
        ]
        ladder, *_ = _compute_exposure(quotes, SPOT)
        assert _find_gamma_flip(ladder) is None

    def test_no_flip_single_strike(self):
        rows = [ExposureLadderRow(
            strike=180, call_gex=100, put_gex=-50, net_gex=50,
            call_dex=200, put_dex=-100, net_dex=100,
            call_oi=100, put_oi=50, call_iv=None, put_iv=None,
            call_mark=None, put_mark=None,
        )]
        assert _find_gamma_flip(rows) is None


# ── Max pain ──────────────────────────────────────────────────────────────────

class TestMaxPain:
    def test_symmetric_chain_max_pain_is_atm(self):
        # Perfectly symmetric call/put distribution → max pain ≈ ATM
        quotes = [
            _call(strike=175, gamma=0.01, delta=0.7, oi=100),
            _call(strike=180, gamma=0.01, delta=0.5, oi=200),
            _call(strike=185, gamma=0.01, delta=0.3, oi=100),
            _put(strike=175, gamma=0.01, delta=-0.7, oi=100),
            _put(strike=180, gamma=0.01, delta=-0.5, oi=200),
            _put(strike=185, gamma=0.01, delta=-0.3, oi=100),
        ]
        mp = _find_max_pain(quotes)
        assert mp == pytest.approx(180.0)

    def test_empty_quotes_returns_none(self):
        assert _find_max_pain([]) is None


# ── Implied move ──────────────────────────────────────────────────────────────

class TestImpliedMove:
    def test_basic_calculation(self):
        # ATM straddle: call mark 5.0 + put mark 5.0 = 10.0 / spot 100 = 10%
        rows = [ExposureLadderRow(
            strike=100, call_gex=0, put_gex=0, net_gex=0,
            call_dex=0, put_dex=0, net_dex=0,
            call_oi=100, put_oi=100, call_iv=0.2, put_iv=0.22,
            call_mark=5.0, put_mark=5.0,
        )]
        result = _compute_implied_move(rows, 100.0)
        assert result == pytest.approx(0.10)

    def test_picks_closest_strike_to_spot(self):
        rows = [
            ExposureLadderRow(
                strike=175, call_gex=0, put_gex=0, net_gex=0,
                call_dex=0, put_dex=0, net_dex=0,
                call_oi=50, put_oi=50, call_iv=0.3, put_iv=0.32,
                call_mark=20.0, put_mark=1.0,
            ),
            ExposureLadderRow(
                strike=180, call_gex=0, put_gex=0, net_gex=0,
                call_dex=0, put_dex=0, net_dex=0,
                call_oi=100, put_oi=100, call_iv=0.25, put_iv=0.27,
                call_mark=3.0, put_mark=3.0,
            ),
        ]
        result = _compute_implied_move(rows, 180.0)
        # Should use strike 180, not 175
        assert result == pytest.approx(6.0 / 180.0)

    def test_none_when_no_marks(self):
        rows = [ExposureLadderRow(
            strike=180, call_gex=0, put_gex=0, net_gex=0,
            call_dex=0, put_dex=0, net_dex=0,
            call_oi=0, put_oi=0, call_iv=None, put_iv=None,
            call_mark=None, put_mark=None,
        )]
        assert _compute_implied_move(rows, 180.0) is None

    def test_none_on_empty_ladder(self):
        assert _compute_implied_move([], 180.0) is None


# ── Aggregates ────────────────────────────────────────────────────────────────

class TestAggregates:
    def test_pcr_oi(self):
        quotes = [
            _call(strike=180, gamma=0.01, delta=0.5, oi=200),
            _put(strike=180, gamma=0.01, delta=-0.5, oi=100),
        ]
        _, _, _, _, pcr_oi, _, _, _, _ = _compute_exposure(quotes, SPOT)
        assert pcr_oi == pytest.approx(0.5)

    def test_pcr_none_when_no_calls(self):
        quotes = [_put(strike=180, gamma=0.01, delta=-0.5, oi=100)]
        _, _, _, _, pcr_oi, _, _, _, _ = _compute_exposure(quotes, SPOT)
        assert pcr_oi is None

    def test_total_gex_sum(self):
        quotes = [
            _call(strike=175, gamma=0.01, delta=0.6, oi=100),
            _call(strike=180, gamma=0.01, delta=0.5, oi=100),
            _put(strike=175, gamma=0.01, delta=-0.6, oi=50),
        ]
        ladder, _, total_gex, _, _, _, _, _, _ = _compute_exposure(quotes, SPOT)
        assert total_gex == pytest.approx(sum(r.net_gex for r in ladder))

    def test_expirations_sorted(self):
        quotes = [
            _call(strike=180, gamma=0.01, delta=0.5, oi=100, expiry=EXP_2),
            _call(strike=180, gamma=0.01, delta=0.5, oi=80, expiry=EXP_1),
        ]
        _, _, _, _, _, _, _, expirations, _ = _compute_exposure(quotes, SPOT)
        assert expirations == sorted(expirations)
        assert expirations[0] == EXP_1.isoformat()


@pytest.mark.asyncio
async def test_get_options_exposure_uses_provider_expiration_list(db, instrument, monkeypatch):
    async_db = AsyncSessionAdapter(db)

    async def _ensure(*_args, **_kwargs):
        return None

    async def _quotes(*_args, **kwargs):
        expiration = kwargs.get("expiration")
        if expiration is not None:
            return [_call(strike=100, gamma=0.01, delta=0.5, oi=10, expiry=expiration)]
        return [
            _call(strike=100, gamma=0.01, delta=0.5, oi=10, expiry=date(2026, 6, 19)),
            _put(strike=100, gamma=0.01, delta=-0.5, oi=10, expiry=date(2026, 6, 19)),
            _call(strike=100, gamma=0.01, delta=0.5, oi=5, expiry=date(2026, 4, 27)),
        ]

    async def _spot(*_args, **_kwargs):
        return 100.0

    async def _expirations(*_args, **_kwargs):
        return [date(2026, 6, 19), date(2026, 7, 17)]

    async def _rfr(*_args, **_kwargs):
        return 0.05

    monkeypatch.setattr("app.services.options_exposure._ensure_option_quotes_available", _ensure)
    monkeypatch.setattr("app.services.options_exposure._fetch_latest_contract_quotes", _quotes)
    monkeypatch.setattr("app.services.options_exposure._get_spot_price", _spot)
    monkeypatch.setattr("app.services.options_exposure.list_option_expirations", _expirations)
    monkeypatch.setattr("app.services.options_exposure.get_risk_free_rate", _rfr)

    result = await get_options_exposure(async_db, instrument)

    assert result.expirations == ["2026-06-19", "2026-07-17"]
    assert "2026-04-27" not in result.expirations


@pytest.mark.asyncio
async def test_list_exposure_expirations_filters_out_non_provider_expirations(db, instrument, monkeypatch):
    async_db = AsyncSessionAdapter(db)

    async def _ensure(*_args, **_kwargs):
        return None

    async def _quotes(*_args, **_kwargs):
        return [
            _call(strike=100, gamma=0.01, delta=0.5, oi=10, expiry=date(2026, 6, 19)),
            _put(strike=100, gamma=0.01, delta=-0.5, oi=8, expiry=date(2026, 6, 19)),
            _call(strike=100, gamma=0.01, delta=0.5, oi=5, expiry=date(2026, 4, 27)),
        ]

    async def _spot(*_args, **_kwargs):
        return 100.0

    async def _expirations(*_args, **_kwargs):
        return [date(2026, 6, 19)]

    monkeypatch.setattr("app.services.options_exposure._ensure_option_quotes_available", _ensure)
    monkeypatch.setattr("app.services.options_exposure._fetch_latest_contract_quotes", _quotes)
    monkeypatch.setattr("app.services.options_exposure._get_spot_price", _spot)
    monkeypatch.setattr("app.services.options_exposure.list_option_expirations", _expirations)

    summaries = await list_exposure_expirations(async_db, instrument)

    assert [summary.expiration for summary in summaries] == ["2026-06-19"]
