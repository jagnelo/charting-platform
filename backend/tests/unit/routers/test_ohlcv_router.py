from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.provider_runtime import ProviderNoDataError


class TestOHLCVRouter:
    def test_local_shape_exposes_derived_lineage(self, client, auth_headers, db, instrument):
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.W1,
                ts=datetime(2025, 1, 2, tzinfo=UTC),
                open=Decimal("10"),
                high=Decimal("12"),
                low=Decimal("9"),
                close=Decimal("11"),
                is_adjusted=True,
                is_derived=True,
                source_timeframe="D1",
                derivation_method="d1_ohlcv_xnys_calendar_aggregation",
                source_bar_count=4,
                source_start=datetime(2024, 12, 30, tzinfo=UTC),
                source_end=datetime(2025, 1, 2, tzinfo=UTC),
            )
        )
        db.flush()

        response = client.get(f"/api/v1/ohlcv/local/{instrument.symbol}/W1", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()[0]["is_derived"] is True
        assert response.json()[0]["source_timeframe"] == "D1"
        assert response.json()[0]["source_bar_count"] == 4

    def test_local_coarse_read_materializes_from_canonical_d1(
        self, client, auth_headers, instrument, ohlcv_bars
    ):
        """Provider-free local reads derive W1 from persisted D1 evidence."""
        response = client.get(
            f"/api/v1/ohlcv/local/{instrument.symbol}/W1",
            headers=auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload
        assert all(row["is_derived"] is True for row in payload)
        assert all(row["source_timeframe"] == "D1" for row in payload)

    def test_local_coarse_read_merges_partial_provider_rows_with_derived_periods(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        """A partial provider series must not hide D1-derived coarse periods."""
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.W1,
                ts=datetime(2024, 1, 1, tzinfo=UTC),
                open=Decimal("999"),
                high=Decimal("1001"),
                low=Decimal("998"),
                close=Decimal("1000"),
                volume=Decimal("1"),
                is_adjusted=True,
                is_derived=False,
            )
        )
        db.flush()

        response = client.get(
            f"/api/v1/ohlcv/local/{instrument.symbol}/W1",
            headers=auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert any(row["is_derived"] is False and row["close"] == 1000.0 for row in payload)
        assert any(row["is_derived"] is True for row in payload)

    def test_local_view_selector_isolates_persisted_provider_and_derived_lineage(
        self, client, auth_headers, db, instrument
    ):
        """The explicit view contract must not conflate persisted lineage."""
        timestamp = datetime(2025, 1, 2, tzinfo=UTC)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.W1,
                    ts=timestamp,
                    open=Decimal("10"),
                    high=Decimal("12"),
                    low=Decimal("9"),
                    close=Decimal("11"),
                    is_adjusted=True,
                    is_derived=False,
                    data_source_id=None,
                ),
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.W1,
                    ts=timestamp + timedelta(days=7),
                    open=Decimal("20"),
                    high=Decimal("22"),
                    low=Decimal("19"),
                    close=Decimal("21"),
                    is_adjusted=True,
                    is_derived=True,
                    source_timeframe="D1",
                    derivation_method="d1_ohlcv_xnys_calendar_aggregation",
                ),
            ]
        )
        db.flush()

        provider = client.get(
            f"/api/v1/ohlcv/local/{instrument.symbol}/W1",
            params={"view": "provider"},
            headers=auth_headers,
        )
        derived = client.get(
            f"/api/v1/ohlcv/local/{instrument.symbol}/W1",
            params={"view": "derived"},
            headers=auth_headers,
        )

        assert provider.status_code == 200
        assert provider.json() and all(row["is_derived"] is False for row in provider.json())
        assert derived.status_code == 200
        assert derived.json() and all(row["is_derived"] is True for row in derived.json())

    def test_chart_coarse_local_read_merges_partial_provider_rows(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        """The chart service path applies the same mixed-source contract."""
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.W1,
                ts=datetime(2024, 1, 1, tzinfo=UTC),
                open=Decimal("999"),
                high=Decimal("1001"),
                low=Decimal("998"),
                close=Decimal("1000"),
                volume=Decimal("1"),
                is_adjusted=True,
                is_derived=False,
            )
        )
        db.flush()

        response = client.get(
            f"/api/v1/ohlcv/{instrument.symbol}/W1",
            params={"local_only": "true"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert any(row["is_derived"] is False and row["close"] == 1000.0 for row in payload)
        assert any(row["is_derived"] is True for row in payload)

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

    def test_transformed_local_coarse_read_materializes_from_canonical_d1(
        self, client, auth_headers, instrument, ohlcv_bars
    ):
        """Transformed local reads use the same provider-free coarse seam."""
        response = client.get(
            f"/api/v1/ohlcv/{instrument.symbol}/W1/transformed",
            params={"bar_type": "heikin_ashi", "local_only": "true"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload
        assert all(set(("ts", "open", "high", "low", "close")).issubset(row) for row in payload)

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
