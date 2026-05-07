"""
Integration tests for the options-exposure endpoints.

Fixtures seed a minimal but realistic chain:
  - 2 expirations (EXP_1 = 2024-01-19, EXP_2 = 2024-02-16)
  - 3 strikes each (175, 180, 185)
  - Both calls and puts at every strike/expiry

All OptionQuotePoint rows are inserted directly into the test DB;
no provider mocks are needed because the endpoints read from persisted data.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

EXP_1 = date(2024, 1, 19)
EXP_2 = date(2024, 2, 16)
STRIKES = [175, 180, 185]
SPOT = 180.0


# ── Shared fixture ─────────────────────────────────────────────────────────────


def _seed_chain(db, underlying):
    """Insert option instruments + details + quote points for the test chain."""
    from app.models.data_source import DataSource
    from app.models.instrument import Instrument, OptionDetail, OptionRight, OptionStyle
    from app.models.provider_observation import OptionQuotePoint

    ds = DataSource(name="test-ds-exposure", is_active=True)
    db.add(ds)
    db.flush()

    contracts = []
    for expiry in (EXP_1, EXP_2):
        for strike in STRIKES:
            for right, delta_sign in ((OptionRight.CALL, 1), (OptionRight.PUT, -1)):
                moneyness = (strike - 180) / 180
                delta = Decimal(str(round(0.5 - moneyness * 2 * delta_sign, 4)))
                opt_inst = Instrument(
                    symbol=f"AAPL{expiry.strftime('%y%m%d')}{right.value[0]}{strike}",
                    name=f"AAPL {expiry} {right.value} {strike}",
                    currency="USD",
                    instrument_type_id=underlying.instrument_type_id,
                    is_active=True,
                )
                db.add(opt_inst)
                db.flush()

                detail = OptionDetail(
                    instrument_id=opt_inst.id,
                    underlying_instrument_id=underlying.id,
                    right=right,
                    style=OptionStyle.AMERICAN,
                    strike=Decimal(str(strike)),
                    expiry_date=expiry,
                    contract_size=Decimal("100"),
                )
                db.add(detail)
                db.flush()

                quote = OptionQuotePoint(
                    option_instrument_id=opt_inst.id,
                    data_source_id=ds.id,
                    observed_at=datetime(2024, 1, 15, 16, 0, tzinfo=UTC),
                    gamma=Decimal("0.01"),
                    delta=delta,
                    open_interest=Decimal("500"),
                    volume=Decimal("200"),
                    implied_vol=Decimal("0.25"),
                    mark=Decimal("5.00"),
                )
                db.add(quote)
                contracts.append(opt_inst)

    db.flush()
    return contracts


# ── Auth guard ─────────────────────────────────────────────────────────────────


class TestOptionsExposureAuth:
    def test_exposure_requires_auth(self, client, instrument):
        res = client.get(f"/api/v1/instruments/{instrument.symbol}/options/exposure")
        assert res.status_code == 401

    def test_expirations_requires_auth(self, client, instrument):
        res = client.get(f"/api/v1/instruments/{instrument.symbol}/options/exposure/expirations")
        assert res.status_code == 401

    def test_unknown_symbol_returns_404(self, client, auth_headers):
        res = client.get("/api/v1/instruments/ZZZNOPE/options/exposure", headers=auth_headers)
        assert res.status_code == 404

    def test_invalid_expiration_returns_400(self, client, auth_headers, instrument, ohlcv_bars):
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
            params={"expiration": "not-a-date"},
        )
        assert res.status_code == 400


# ── Combined exposure (no filter) ─────────────────────────────────────────────


class TestExposureCombined:
    def test_returns_expected_shape(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == instrument.symbol
        assert isinstance(data["spot"], float)
        assert isinstance(data["ladder"], list)
        assert isinstance(data["key_levels"], dict)
        assert "computed_at" in data

    def test_ladder_has_correct_strikes(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
        )
        strikes = [r["strike"] for r in res.json()["ladder"]]
        assert strikes == sorted(strikes)
        assert len(strikes) == len(STRIKES)

    def test_ladder_rows_have_required_fields(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
        )
        row = res.json()["ladder"][0]
        for field in (
            "strike",
            "call_gex",
            "put_gex",
            "net_gex",
            "call_dex",
            "put_dex",
            "net_dex",
            "call_oi",
            "put_oi",
            "by_expiry",
        ):
            assert field in row, f"Missing field: {field}"

    def test_by_expiry_contains_both_expirations(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
        )
        by_expiry = res.json()["ladder"][0]["by_expiry"]
        assert EXP_1.isoformat() in by_expiry
        assert EXP_2.isoformat() in by_expiry

    def test_gex_sign_convention(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
        )
        for row in res.json()["ladder"]:
            assert row["call_gex"] >= 0
            assert row["put_gex"] <= 0

    def test_expirations_list_sorted(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
        )
        exps = res.json()["expirations"]
        assert exps == sorted(exps)
        assert EXP_1.isoformat() in exps
        assert EXP_2.isoformat() in exps

    def test_pcr_oi_present(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
        )
        data = res.json()
        assert "pcr_oi" in data
        assert data["pcr_oi"] == 1.0  # equal call and put OI in our seeded chain

    def test_total_gex_matches_ladder_sum(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
        )
        data = res.json()
        ladder_sum = sum(r["net_gex"] for r in data["ladder"])
        assert abs(data["total_gex"] - ladder_sum) < 0.01

    def test_key_levels_shape(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
        )
        kl = res.json()["key_levels"]
        for field in ("call_wall", "put_wall", "gamma_flip", "max_pain"):
            assert field in kl

    def test_implied_move_present_when_marks_available(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
        )
        assert res.json()["implied_move_pct"] is not None


# ── Single-expiration filter ───────────────────────────────────────────────────


class TestExposureFiltered:
    def test_filtered_active_expirations(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
            params={"expiration": EXP_1.isoformat()},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["active_expirations"] == [EXP_1.isoformat()]

    def test_full_expirations_still_populated_when_filtered(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
            params={"expiration": EXP_1.isoformat()},
        )
        data = res.json()
        # Full list present even when filtering
        assert EXP_2.isoformat() in data["expirations"]

    def test_filtered_ladder_only_shows_exp1_data(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
            params={"expiration": EXP_1.isoformat()},
        )
        for row in res.json()["ladder"]:
            by_expiry = row["by_expiry"]
            assert EXP_1.isoformat() in by_expiry
            assert EXP_2.isoformat() not in by_expiry

    def test_unknown_expiration_returns_empty_ladder(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure",
            headers=auth_headers,
            params={"expiration": "2030-12-31"},
        )
        assert res.status_code == 200
        assert res.json()["ladder"] == []


# ── Expirations list endpoint ──────────────────────────────────────────────────


class TestExpirationsList:
    def test_returns_list(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure/expirations",
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_both_expirations_present(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure/expirations",
            headers=auth_headers,
        )
        exps = [s["expiration"] for s in res.json()]
        assert EXP_1.isoformat() in exps
        assert EXP_2.isoformat() in exps

    def test_summary_fields_present(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure/expirations",
            headers=auth_headers,
        )
        summary = res.json()[0]
        for field in ("expiration", "dte", "total_call_oi", "total_put_oi", "pcr_oi", "total_gex"):
            assert field in summary, f"Missing field: {field}"

    def test_sorted_ascending(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure/expirations",
            headers=auth_headers,
        )
        exps = [s["expiration"] for s in res.json()]
        assert exps == sorted(exps)

    def test_expirations_unknown_symbol_returns_404(self, client, auth_headers):
        res = client.get(
            "/api/v1/instruments/ZZZNOPE/options/exposure/expirations",
            headers=auth_headers,
        )
        assert res.status_code == 404

    def test_dte_is_non_negative(self, client, auth_headers, db, instrument, ohlcv_bars):
        _seed_chain(db, instrument)
        res = client.get(
            f"/api/v1/instruments/{instrument.symbol}/options/exposure/expirations",
            headers=auth_headers,
        )
        for summary in res.json():
            assert summary["dte"] >= 0
