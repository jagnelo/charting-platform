from datetime import UTC, datetime
from types import SimpleNamespace

from app.models.ohlcv import Timeframe
from app.services.provider_runtime import ProviderNoDataError


class TestOHLCVRouter:
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
        assert "No OHLCV data available" in res.json()["detail"]

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
        assert isinstance(res.json(), list)
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
