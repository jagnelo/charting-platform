import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.config import settings
from app.models.data_source import DataSource
from app.models.market_data_foundation import AdjustmentBasis, MarketSeries, MarketSeriesDefault
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.services.derived_timeframes import materialize_derived_timeframes
from app.services.distributed_locks import DistributedLockError
from app.services.provider_runtime import ProviderNoDataError
from tests.unit.conftest import AsyncSessionAdapter


class TestOHLCVRouter:
    def test_local_weekly_monthly_read_refreshes_stale_derived_history_once(
        self, client, auth_headers, db, instrument, monkeypatch
    ):
        monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", False)
        source = DataSource(name="derived-history-refresh-source")
        db.add(source)
        db.flush()
        recent_start = datetime(2026, 5, 11, tzinfo=UTC)
        recent_end = datetime(2026, 11, 5, tzinfo=UTC)
        daily_bars = []
        cursor = recent_start
        close_value = 100
        while cursor <= recent_end:
            if cursor.weekday() < 5:
                daily_bars.append(
                    OHLCVBar(
                        instrument_id=instrument.id,
                        data_source_id=source.id,
                        timeframe=Timeframe.D1,
                        ts=cursor,
                        open=Decimal(close_value - 1),
                        high=Decimal(close_value + 2),
                        low=Decimal(close_value - 2),
                        close=Decimal(close_value),
                        volume=Decimal("100"),
                        is_adjusted=True,
                    )
                )
                close_value += 1
            cursor += timedelta(days=1)
        db.add_all(daily_bars)
        d1_state = InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=source.id,
            dataset_type="ohlcv",
            dataset_key="D1:adj",
            status=DatasetStatus.FRESH,
            fetched_at=recent_end,
            coverage_start=recent_start,
            coverage_end=recent_end,
            extra_data={
                "adjustment_provenance": {
                    "factor_status": "rebuildable_provider_factors",
                    "factor_version": "daily-backfill-test-v1",
                }
            },
        )
        db.add(d1_state)

        weekly_series = MarketSeries(
            instrument_id=instrument.id,
            data_source_id=source.id,
            feed_scope="provider_authoritative",
            session_code="regular",
            timeframe=Timeframe.W1.value,
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="provider-v1",
            is_canonical=True,
            is_active=True,
        )
        monthly_series = MarketSeries(
            instrument_id=instrument.id,
            data_source_id=source.id,
            feed_scope="provider_authoritative",
            session_code="regular",
            timeframe=Timeframe.MN.value,
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="provider-v1",
            is_canonical=True,
            is_active=True,
        )
        db.add_all([weekly_series, monthly_series])
        db.flush()
        provider_week = OHLCVBar(
            instrument_id=instrument.id,
            data_source_id=source.id,
            market_series_id=weekly_series.id,
            timeframe=Timeframe.W1,
            ts=datetime(2026, 6, 8, tzinfo=UTC),
            open=Decimal("998"),
            high=Decimal("1001"),
            low=Decimal("997"),
            close=Decimal("999"),
            volume=Decimal("200"),
            is_adjusted=True,
            scope_key=f"series:{weekly_series.id}:regular",
        )
        provider_month = OHLCVBar(
            instrument_id=instrument.id,
            data_source_id=source.id,
            market_series_id=monthly_series.id,
            timeframe=Timeframe.MN,
            ts=datetime(2026, 6, 1, tzinfo=UTC),
            open=Decimal("998"),
            high=Decimal("1001"),
            low=Decimal("997"),
            close=Decimal("999"),
            volume=Decimal("200"),
            is_adjusted=True,
            scope_key=f"series:{monthly_series.id}:regular",
        )
        raw_derived = OHLCVBar(
            instrument_id=instrument.id,
            timeframe=Timeframe.W1,
            ts=datetime(2026, 6, 8, tzinfo=UTC),
            open=Decimal("49"),
            high=Decimal("52"),
            low=Decimal("48"),
            close=Decimal("51"),
            volume=Decimal("100"),
            is_adjusted=False,
            is_derived=True,
            source_timeframe=Timeframe.D1.value,
            derivation_method="raw-view-preservation-test",
        )
        db.add_all([provider_week, provider_month, raw_derived])
        db.flush()
        provider_week_id = provider_week.id
        provider_month_id = provider_month.id
        raw_derived_id = raw_derived.id

        adapter = AsyncSessionAdapter(db)
        asyncio.run(materialize_derived_timeframes(adapter, instrument.id, adjusted=True))
        db.commit()
        old_weekly = (
            db.query(OHLCVBar)
            .filter(
                OHLCVBar.instrument_id == instrument.id,
                OHLCVBar.timeframe == Timeframe.W1,
                OHLCVBar.is_adjusted.is_(True),
                OHLCVBar.is_derived.is_(True),
            )
            .order_by(OHLCVBar.ts)
            .first()
        )
        assert old_weekly is not None
        assert old_weekly.ts.replace(tzinfo=UTC) == datetime(2026, 5, 11, tzinfo=UTC)

        # Simulate the deployed legacy derived rows, which predate the source
        # signature and need the bounded coverage comparison to notice a backfill.
        weekly_state = (
            db.query(InstrumentDatasetState)
            .filter(
                InstrumentDatasetState.instrument_id == instrument.id,
                InstrumentDatasetState.data_source_id.is_(None),
                InstrumentDatasetState.dataset_key == "W1:adj",
            )
            .one()
        )
        weekly_state.extra_data.pop("source_d1_signature")

        historical_bars = [
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=datetime(2024, 11, 11, tzinfo=UTC),
                open=Decimal("11"),
                high=Decimal("14"),
                low=Decimal("10"),
                close=Decimal("12"),
                volume=Decimal("100"),
                is_adjusted=True,
            ),
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=datetime(2024, 11, 12, tzinfo=UTC),
                open=Decimal("12"),
                high=Decimal("15"),
                low=Decimal("11"),
                close=Decimal("13"),
                volume=Decimal("120"),
                is_adjusted=True,
            ),
        ]
        db.add_all(historical_bars)
        d1_state.coverage_start = historical_bars[0].ts
        d1_state.fetched_at = datetime.now(UTC) + timedelta(seconds=1)
        db.flush()

        provider_calls = []

        def _unexpected_provider_call(*_args, **_kwargs):
            provider_calls.append(True)
            raise AssertionError("local derived history reads must not call a provider")

        monkeypatch.setattr(
            "app.services.market_data.execute_provider_call", _unexpected_provider_call
        )
        real_materialize = materialize_derived_timeframes
        materialize_calls = []

        async def _count_materialize(*args, **kwargs):
            materialize_calls.append(True)
            return await real_materialize(*args, **kwargs)

        monkeypatch.setattr("app.routers.ohlcv.materialize_derived_timeframes", _count_materialize)

        weekly_response = client.get(
            f"/api/v1/ohlcv/local/{instrument.symbol}/{Timeframe.W1.value}",
            params={"limit": 5000},
            headers=auth_headers,
        )
        monthly_response = client.get(
            f"/api/v1/ohlcv/local/{instrument.symbol}/{Timeframe.MN.value}",
            params={"limit": 5000},
            headers=auth_headers,
        )
        assert weekly_response.status_code == 200, weekly_response.text
        assert monthly_response.status_code == 200, monthly_response.text
        weekly = weekly_response.json()
        monthly = monthly_response.json()
        assert weekly[0]["ts"] == "2024-11-11T00:00:00Z"
        assert weekly[0]["close"] == 13.0
        assert monthly[0]["ts"] == "2024-11-11T00:00:00Z"
        assert monthly[0]["close"] == 13.0
        latest_close = float(close_value - 1)
        assert weekly[-1]["close"] == latest_close
        assert monthly[-1]["close"] == latest_close
        assert materialize_calls == [True]
        assert provider_calls == []

        preserved_rows = {
            row.id: row
            for row in db.query(OHLCVBar)
            .filter(OHLCVBar.id.in_((provider_week_id, provider_month_id, raw_derived_id)))
            .all()
        }
        assert preserved_rows[provider_week_id].close == Decimal("999")
        assert preserved_rows[provider_week_id].market_series_id == weekly_series.id
        assert preserved_rows[provider_month_id].close == Decimal("999")
        assert preserved_rows[provider_month_id].market_series_id == monthly_series.id
        assert preserved_rows[raw_derived_id].close == Decimal("51")
        assert preserved_rows[raw_derived_id].is_adjusted is False

        async def _must_not_rematerialize(*_args, **_kwargs):
            raise AssertionError("current derived history should not be rebuilt on each read")

        monkeypatch.setattr(
            "app.routers.ohlcv.materialize_derived_timeframes", _must_not_rematerialize
        )
        for timeframe in (Timeframe.W1, Timeframe.MN):
            response = client.get(
                f"/api/v1/ohlcv/local/{instrument.symbol}/{timeframe.value}",
                params={"limit": 5000},
                headers=auth_headers,
            )
            assert response.status_code == 200, response.text
        assert provider_calls == []

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
