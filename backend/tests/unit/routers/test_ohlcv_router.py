from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.config import settings
from app.models.market_data_foundation import AdjustmentBasis, MarketSeries, MarketSeriesDefault
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.distributed_locks import DistributedLockError
from app.services.provider_runtime import ProviderNoDataError


class TestOHLCVRouter:
    def test_local_only_returns_retained_bars_in_consumer_shape(
        self, client, auth_headers, instrument, monkeypatch
    ):
        monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
        ts = datetime(2026, 10, 15, 20, 0, tzinfo=UTC)
        bars = [
            SimpleNamespace(
                ts=ts,
                open=100.0,
                high=105.0,
                low=99.0,
                close=104.0,
                volume=12345.0,
                vwap=102.5,
                is_adjusted=True,
            )
        ]
        calls: list[dict] = []

        async def _local_read(*_args, **kwargs):
            calls.append(kwargs)
            return bars

        monkeypatch.setattr("app.routers.ohlcv.fetch_ohlcv_latest", _local_read)
        response = client.get(
            f"/api/v1/ohlcv/{instrument.symbol}/{Timeframe.D1.value}",
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        assert payload[0] == {
            "ts": "2026-10-15T20:00:00Z",
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 104.0,
            "volume": 12345.0,
            "vwap": 102.5,
            "is_adjusted": True,
            "is_derived": False,
            "source_timeframe": None,
            "derivation_method": None,
            "derived_at": None,
            "source_bar_count": None,
            "source_start": None,
            "source_end": None,
        }
        assert calls == [{"allow_provider_fetch": False}]

        legacy_false_flag = client.get(
            f"/api/v1/ohlcv/{instrument.symbol}/{Timeframe.D1.value}",
            params={"local_only": "false"},
            headers=auth_headers,
        )
        assert legacy_false_flag.status_code == 200, legacy_false_flag.text
        assert calls[-1] == {"allow_provider_fetch": False}

    def test_request_driven_mode_keeps_transformed_cached_get_local_by_default(
        self, client, auth_headers, instrument, monkeypatch
    ):
        monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
        bars = [
            SimpleNamespace(
                ts=datetime(2026, 10, 15, 20, 0, tzinfo=UTC),
                open=100,
                high=105,
                low=99,
                close=104,
                volume=10,
                vwap=102,
                is_adjusted=True,
            )
        ]
        calls: list[dict] = []

        async def _local_read(*_args, **kwargs):
            calls.append(kwargs)
            return bars

        monkeypatch.setattr("app.routers.ohlcv.fetch_ohlcv_latest", _local_read)
        response = client.get(
            f"/api/v1/ohlcv/{instrument.symbol}/{Timeframe.D1.value}/transformed",
            params={"bar_type": "heikin_ashi"},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()
        assert calls == [{"allow_provider_fetch": False}]

    def test_request_driven_ordinary_ohlcv_get_reads_only_selected_default_series(
        self, client, auth_headers, db, instrument, monkeypatch
    ):
        monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
        selected = MarketSeries(
            instrument_id=instrument.id,
            feed_scope="request-driven-selected",
            session_code="regular",
            timeframe="D1",
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            is_canonical=True,
            is_active=True,
        )
        alternate = MarketSeries(
            instrument_id=instrument.id,
            feed_scope="request-driven-alternate",
            session_code="regular",
            timeframe="D1",
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            is_canonical=True,
            is_active=True,
        )
        db.add_all([selected, alternate])
        db.flush()
        db.add(
            MarketSeriesDefault(
                instrument_id=instrument.id,
                timeframe="D1",
                is_adjusted=True,
                market_series_id=selected.id,
                selection_reason="request-driven-local-get-regression",
            )
        )
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    market_series_id=selected.id,
                    timeframe=Timeframe.D1,
                    ts=datetime(2026, 1, 2, tzinfo=UTC),
                    open=Decimal("10"),
                    high=Decimal("11"),
                    low=Decimal("9"),
                    close=Decimal("10"),
                    volume=Decimal("100"),
                    is_adjusted=True,
                    adjustment_basis="split_adjusted",
                    adjustment_version="request-driven-test",
                    scope_key=f"series:{selected.id}:regular",
                ),
                OHLCVBar(
                    instrument_id=instrument.id,
                    market_series_id=alternate.id,
                    timeframe=Timeframe.D1,
                    ts=datetime(2026, 1, 5, tzinfo=UTC),
                    open=Decimal("20"),
                    high=Decimal("21"),
                    low=Decimal("19"),
                    close=Decimal("20"),
                    volume=Decimal("200"),
                    is_adjusted=True,
                    adjustment_basis="split_adjusted",
                    adjustment_version="request-driven-test",
                    scope_key=f"series:{alternate.id}:regular",
                ),
            ]
        )
        db.flush()

        response = client.get(
            f"/api/v1/ohlcv/{instrument.symbol}/{Timeframe.D1.value}",
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert [row["close"] for row in payload] == [10.0]

    def test_transformed_chart_types_return_server_shape(
        self, client, auth_headers, instrument, monkeypatch
    ):
        bars = [
            SimpleNamespace(
                ts=datetime(2024, 1, 2, tzinfo=UTC),
                open=100,
                high=105,
                low=95,
                close=104,
                volume=10,
                is_adjusted=True,
            ),
            SimpleNamespace(
                ts=datetime(2024, 1, 3, tzinfo=UTC),
                open=104,
                high=112,
                low=101,
                close=110,
                volume=12,
                is_adjusted=True,
            ),
        ]

        async def _raw(*_args, **_kwargs):
            return bars

        monkeypatch.setattr("app.routers.ohlcv.fetch_ohlcv_latest", _raw)
        for bar_type in ("heikin_ashi", "renko", "kagi", "point_figure"):
            response = client.get(
                f"/api/v1/ohlcv/{instrument.symbol}/{Timeframe.D1.value}/transformed",
                params={"bar_type": bar_type, "local_only": "true"},
                headers=auth_headers,
            )
            assert response.status_code == 200, (bar_type, response.text)
            payload = response.json()
            assert all(
                set(("ts", "open", "high", "low", "close", "volume")).issubset(row)
                for row in payload
            )

    def test_transformed_chart_ignores_parameters_for_other_types(
        self, client, auth_headers, instrument, monkeypatch
    ):
        bars = [
            SimpleNamespace(
                ts=datetime(2024, 1, 2, tzinfo=UTC),
                open=100,
                high=105,
                low=95,
                close=104,
                volume=10,
                is_adjusted=True,
            ),
        ]

        async def _raw(*_args, **_kwargs):
            return bars

        monkeypatch.setattr("app.routers.ohlcv.fetch_ohlcv_latest", _raw)
        response = client.get(
            f"/api/v1/ohlcv/{instrument.symbol}/{Timeframe.D1.value}/transformed",
            params={"bar_type": "point_figure", "brick_size": 12, "local_only": "true"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text

    def test_no_provider_data_returns_404(self, client, auth_headers, instrument, monkeypatch):
        async def _raise_no_data(*_args, **_kwargs):
            raise ProviderNoDataError("no data")

        monkeypatch.setattr("app.routers.ohlcv.fetch_ohlcv_latest", _raise_no_data)

        res = client.get(
            f"/api/v1/ohlcv/{instrument.symbol}/{Timeframe.D1.value}",
            headers=auth_headers,
        )

        assert res.status_code == 404
        assert res.json() == {
            "detail": f"No OHLCV data available for instrument '{instrument.symbol}' on D1."
        }

    def test_refresh_coordination_failure_returns_retryable_503(
        self, client, auth_headers, instrument, monkeypatch
    ):
        async def _raise_lock_error(*_args, **_kwargs):
            raise DistributedLockError("Redis distributed lock acquisition timed out")

        monkeypatch.setattr("app.routers.ohlcv.fetch_ohlcv_latest", _raise_lock_error)

        res = client.get(
            f"/api/v1/ohlcv/{instrument.symbol}/{Timeframe.D1.value}",
            headers=auth_headers,
        )

        assert res.status_code == 503
        assert res.headers["Retry-After"] == "5"
        assert res.json()["detail"]["code"] == "refresh_coordination_unavailable"

    def test_local_only_skips_provider_hydration(
        self, client, auth_headers, instrument, monkeypatch
    ):
        calls: list[dict] = []

        async def _local_read(*_args, **kwargs):
            calls.append(kwargs)
            return []

        monkeypatch.setattr("app.routers.ohlcv.fetch_ohlcv_latest", _local_read)
        res = client.get(
            f"/api/v1/ohlcv/{instrument.symbol}/{Timeframe.D1.value}",
            params={"local_only": "true"},
            headers=auth_headers,
        )

        assert res.status_code == 200
        assert res.json() == []
        assert calls == [{"allow_provider_fetch": False}]

    def test_transformed_local_only_skips_provider_hydration(
        self, client, auth_headers, instrument, monkeypatch
    ):
        calls: list[dict] = []

        async def _local_read(*_args, **kwargs):
            calls.append(kwargs)
            return []

        monkeypatch.setattr("app.routers.ohlcv.fetch_ohlcv_latest", _local_read)
        res = client.get(
            f"/api/v1/ohlcv/{instrument.symbol}/{Timeframe.D1.value}/transformed",
            params={"bar_type": "heikin_ashi", "local_only": "true"},
            headers=auth_headers,
        )

        assert res.status_code == 200
        assert res.json() == []
        assert calls == [{"allow_provider_fetch": False}]
