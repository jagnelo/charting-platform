from app.models.ohlcv import Timeframe
from app.services.provider_runtime import ProviderNoDataError


class TestOHLCVRouter:
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
