"""
Integration tests for background tasks:
  - Full alert engine cycle (price + indicator alerts)
  - Bulk data fetching pipeline
  - Screener task runner

These tests patch provider-facing market data calls and OneSignal while using a real DB.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch


class AsyncSessionAdapter:
    def __init__(self, session):
        self._session = session

    async def execute(self, *args, **kwargs):
        return self._session.execute(*args, **kwargs)

    async def get(self, *args, **kwargs):
        return self._session.get(*args, **kwargs)

    async def commit(self):
        self._session.commit()

    async def rollback(self):
        self._session.rollback()

    async def flush(self, *args, **kwargs):
        self._session.flush(*args, **kwargs)

    async def refresh(self, *args, **kwargs):
        self._session.refresh(*args, **kwargs)

    def add(self, *args, **kwargs):
        return self._session.add(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._session, item)


class AsyncSessionContext:
    def __init__(self, session):
        self._adapter = AsyncSessionAdapter(session)

    async def __aenter__(self):
        return self._adapter

    async def __aexit__(self, exc_type, exc, tb):
        return False

# ── Alert engine ───────────────────────────────────────────────────────────────


class TestAlertEngineFullCycle:
    @patch("app.tasks.alert_tasks.send_alert_notification", new_callable=AsyncMock)
    @patch("app.tasks.alert_tasks.get_current_price_async", new_callable=AsyncMock)
    async def test_price_alert_fires_when_condition_met(
        self, mock_price, mock_notif, db, user, instrument
    ):
        """End-to-end: alert engine fetches price, evaluates condition, fires notification."""
        from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
        from app.tasks.alert_tasks import check_all_alerts

        mock_price.return_value = 210.0  # price crossed above 200
        mock_notif.return_value = "onesignal-notif-123"

        alert = PriceAlert(
            user_id=user.id,
            instrument_id=instrument.id,
            condition=AlertCondition.CROSSES_ABOVE,
            threshold_price=Decimal("200.00"),
            last_known_price=Decimal("195.00"),  # was below
            status=AlertStatus.ACTIVE,
            repeat=False,
        )
        db.add(alert)
        db.flush()

        # Patch DB session creation to use our test session
        with patch(
            "app.tasks.alert_tasks.AsyncSessionLocal",
            return_value=AsyncSessionContext(db),
        ):
            await check_all_alerts({})

        db.refresh(alert)
        assert alert.status == AlertStatus.TRIGGERED
        assert alert.triggered_at is not None
        assert alert.trigger_count == 1
        assert alert.last_notification_id == "onesignal-notif-123"
        mock_notif.assert_called_once()

    @patch("app.tasks.alert_tasks.send_alert_notification", new_callable=AsyncMock)
    @patch("app.tasks.alert_tasks.get_current_price_async", new_callable=AsyncMock)
    async def test_price_alert_does_not_fire_when_not_met(
        self, mock_price, mock_notif, db, user, instrument
    ):
        from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
        from app.tasks.alert_tasks import check_all_alerts

        mock_price.return_value = 195.0  # still below threshold

        alert = PriceAlert(
            user_id=user.id,
            instrument_id=instrument.id,
            condition=AlertCondition.CROSSES_ABOVE,
            threshold_price=Decimal("200.00"),
            last_known_price=Decimal("190.00"),
            status=AlertStatus.ACTIVE,
            repeat=False,
        )
        db.add(alert)
        db.flush()

        with patch(
            "app.tasks.alert_tasks.AsyncSessionLocal",
            return_value=AsyncSessionContext(db),
        ):
            await check_all_alerts({})

        db.refresh(alert)
        assert alert.status == AlertStatus.ACTIVE
        assert alert.triggered_at is None
        mock_notif.assert_not_called()

    @patch("app.tasks.alert_tasks.send_alert_notification", new_callable=AsyncMock)
    @patch("app.tasks.alert_tasks.get_current_price_async", new_callable=AsyncMock)
    async def test_repeat_alert_stays_active_after_trigger(
        self, mock_price, mock_notif, db, user, instrument
    ):
        from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
        from app.tasks.alert_tasks import check_all_alerts

        mock_price.return_value = 210.0
        mock_notif.return_value = "notif-id"

        alert = PriceAlert(
            user_id=user.id,
            instrument_id=instrument.id,
            condition=AlertCondition.CROSSES_ABOVE,
            threshold_price=Decimal("200.00"),
            last_known_price=Decimal("195.00"),
            status=AlertStatus.ACTIVE,
            repeat=True,  # <-- repeat enabled
        )
        db.add(alert)
        db.flush()

        with patch(
            "app.tasks.alert_tasks.AsyncSessionLocal",
            return_value=AsyncSessionContext(db),
        ):
            await check_all_alerts({})

        db.refresh(alert)
        assert alert.status == AlertStatus.ACTIVE  # stays active
        assert alert.trigger_count == 1

    @patch("app.tasks.alert_tasks.send_alert_notification", new_callable=AsyncMock)
    async def test_indicator_alert_fires(self, mock_notif, db, user, instrument, ohlcv_bars):
        """Indicator alert fires when RSI condition is met."""
        from app.models.indicator_alert import IndicatorAlert
        from app.models.ohlcv import Timeframe
        from app.models.price_alert import AlertStatus
        from app.services.indicators import get_latest_value
        from app.tasks.alert_tasks import check_all_alerts

        mock_notif.return_value = "notif-ind-1"

        # Force a late drop so the current RSI crosses below the prior RSI window.
        ohlcv_bars[-2].open = Decimal("110")
        ohlcv_bars[-2].high = Decimal("112")
        ohlcv_bars[-2].low = Decimal("108")
        ohlcv_bars[-2].close = Decimal("111")
        ohlcv_bars[-1].open = Decimal("90")
        ohlcv_bars[-1].high = Decimal("91")
        ohlcv_bars[-1].low = Decimal("70")
        ohlcv_bars[-1].close = Decimal("72")
        db.flush()

        prev_rsi = get_latest_value("rsi", ohlcv_bars[:-1], {"period": 14})
        current_rsi = get_latest_value("rsi", ohlcv_bars, {"period": 14})
        assert prev_rsi is not None
        assert current_rsi is not None
        assert current_rsi < prev_rsi
        threshold = round((prev_rsi + current_rsi) / 2, 2)

        alert = IndicatorAlert(
            user_id=user.id,
            instrument_id=instrument.id,
            timeframe=Timeframe.D1,
            indicator_a_type="rsi",
            indicator_a_params={"period": 14},
            condition="crosses_below",
            threshold_value=Decimal(str(threshold)),
            last_value_a=Decimal(str(round(prev_rsi, 2))),
            status=AlertStatus.ACTIVE,
            repeat=False,
        )
        db.add(alert)
        db.flush()

        with patch(
            "app.tasks.alert_tasks.AsyncSessionLocal",
            return_value=AsyncSessionContext(db),
        ):
            await check_all_alerts({})

        db.refresh(alert)
        assert alert.status == AlertStatus.TRIGGERED
        assert alert.triggered_at is not None

    @patch("app.tasks.alert_tasks.get_current_price_async", new_callable=AsyncMock)
    async def test_engine_handles_price_fetch_failure_gracefully(
        self, mock_price, db, user, instrument
    ):
        """Engine should not crash if the configured provider returns no price."""
        from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
        from app.tasks.alert_tasks import check_all_alerts

        mock_price.return_value = None  # fetch failed

        alert = PriceAlert(
            user_id=user.id,
            instrument_id=instrument.id,
            condition=AlertCondition.CROSSES_ABOVE,
            threshold_price=Decimal("200.00"),
            status=AlertStatus.ACTIVE,
        )
        db.add(alert)
        db.flush()

        with patch(
            "app.tasks.alert_tasks.AsyncSessionLocal",
            return_value=AsyncSessionContext(db),
        ):
            result = await check_all_alerts({})  # must not raise

        assert "price_fired" in result


# ── Data pipeline ──────────────────────────────────────────────────────────────


class TestDataPipeline:
    @patch("app.services.bulk_fetch.bulk_fetch_instrument", new_callable=AsyncMock)
    async def test_fetch_instrument_history_delegates_to_bulk_fetch(
        self, mock_bulk_fetch, db, instrument
    ):
        from app.tasks.data_tasks import fetch_instrument_history

        mock_bulk_fetch.return_value = {"MN": 10, "W1": 20}

        with patch(
            "app.tasks.data_tasks.AsyncSessionLocal",
            return_value=AsyncSessionContext(db),
        ):
            result = await fetch_instrument_history({}, instrument.id)

        assert result["instrument_id"] == instrument.id
        assert result["results"] == {"MN": 10, "W1": 20}
        mock_bulk_fetch.assert_awaited_once()

    @patch("app.tasks.data_tasks.fetch_ohlcv")
    async def test_fetch_instrument_history_unknown_id(self, mock_fetch, db):
        from app.tasks.data_tasks import fetch_instrument_history

        with patch(
            "app.tasks.data_tasks.AsyncSessionLocal",
            return_value=AsyncSessionContext(db),
        ):
            result = await fetch_instrument_history({}, 99999)

        assert "error" in result
        mock_fetch.assert_not_called()

    @patch("app.tasks.data_tasks.fetch_ohlcv")
    async def test_fetch_all_instruments_history(self, mock_fetch, db, instrument, instrument_b):
        from app.tasks.data_tasks import fetch_all_instruments_history

        mock_fetch.return_value = []
        newest = instrument.created_at

        with patch(
            "app.tasks.data_tasks.AsyncSessionLocal",
            return_value=AsyncSessionContext(db),
        ), patch(
            "app.tasks.data_tasks._get_newest_bar_ts",
            new_callable=AsyncMock,
            side_effect=lambda *_args, **_kwargs: newest,
        ):
            result = await fetch_all_instruments_history({})

        assert result["instruments_refreshed"] >= 2
        assert mock_fetch.call_count >= 2
