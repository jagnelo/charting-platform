"""
Integration tests for background tasks:
  - Full alert engine cycle (price + indicator alerts)
  - Bulk data fetching pipeline
  - Screener task runner

These tests patch yfinance and OneSignal but use a real DB.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

# ── Alert engine ───────────────────────────────────────────────────────────────


class TestAlertEngineFullCycle:
    @patch("app.tasks.alert_tasks.send_alert_notification", new_callable=AsyncMock)
    @patch("app.tasks.alert_tasks.get_current_price")
    @patch("app.tasks.alert_tasks._ticker_for_instrument")
    async def test_price_alert_fires_when_condition_met(
        self, mock_ticker, mock_price, mock_notif, db, user, instrument
    ):
        """End-to-end: alert engine fetches price, evaluates condition, fires notification."""
        from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
        from app.tasks.alert_tasks import check_all_alerts

        mock_ticker.return_value = "AAPL"
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
        with patch("app.tasks.alert_tasks.SessionLocal", return_value=db):
            await check_all_alerts({})

        db.refresh(alert)
        assert alert.status == AlertStatus.TRIGGERED
        assert alert.triggered_at is not None
        assert alert.trigger_count == 1
        assert alert.last_notification_id == "onesignal-notif-123"
        mock_notif.assert_called_once()

    @patch("app.tasks.alert_tasks.send_alert_notification", new_callable=AsyncMock)
    @patch("app.tasks.alert_tasks.get_current_price")
    @patch("app.tasks.alert_tasks._ticker_for_instrument")
    async def test_price_alert_does_not_fire_when_not_met(
        self, mock_ticker, mock_price, mock_notif, db, user, instrument
    ):
        from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
        from app.tasks.alert_tasks import check_all_alerts

        mock_ticker.return_value = "AAPL"
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

        with patch("app.tasks.alert_tasks.SessionLocal", return_value=db):
            await check_all_alerts({})

        db.refresh(alert)
        assert alert.status == AlertStatus.ACTIVE
        assert alert.triggered_at is None
        mock_notif.assert_not_called()

    @patch("app.tasks.alert_tasks.send_alert_notification", new_callable=AsyncMock)
    @patch("app.tasks.alert_tasks.get_current_price")
    @patch("app.tasks.alert_tasks._ticker_for_instrument")
    async def test_repeat_alert_stays_active_after_trigger(
        self, mock_ticker, mock_price, mock_notif, db, user, instrument
    ):
        from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
        from app.tasks.alert_tasks import check_all_alerts

        mock_ticker.return_value = "AAPL"
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

        with patch("app.tasks.alert_tasks.SessionLocal", return_value=db):
            await check_all_alerts({})

        db.refresh(alert)
        assert alert.status == AlertStatus.ACTIVE  # stays active
        assert alert.trigger_count == 1

    @patch("app.tasks.alert_tasks.send_alert_notification", new_callable=AsyncMock)
    async def test_indicator_alert_fires(self, mock_notif, db, user, instrument, ohlcv_bars):
        """Indicator alert fires when RSI condition is met."""
        from app.models.indicator_alert import IndicatorAlert
        from app.models.ohlcv import Timeframe
        from app.models.price_alert import AlertCondition, AlertStatus
        from app.services.indicators import get_last_value
        from app.tasks.alert_tasks import check_all_alerts

        mock_notif.return_value = "notif-ind-1"

        # Find actual RSI value so we can set threshold to guarantee trigger
        rsi_val = get_last_value("rsi", ohlcv_bars, {"period": 14})
        assert rsi_val is not None

        # Set threshold just above current RSI → condition CROSSES_BELOW will fire
        # next time if we set last_indicator_value above threshold
        alert = IndicatorAlert(
            user_id=user.id,
            instrument_id=instrument.id,
            timeframe=Timeframe.D1,
            indicator_type="rsi",
            indicator_params={"period": 14},
            condition=AlertCondition.CROSSES_BELOW,
            threshold_value=Decimal(str(round(rsi_val + 5, 2))),  # threshold above current
            last_indicator_value=Decimal(str(round(rsi_val + 6, 2))),  # prev was even higher
            status=AlertStatus.ACTIVE,
            repeat=False,
        )
        db.add(alert)
        db.flush()

        with patch("app.tasks.alert_tasks.SessionLocal", return_value=db):
            await check_all_alerts({})

        db.refresh(alert)
        assert alert.status == AlertStatus.TRIGGERED
        assert alert.triggered_at is not None

    @patch("app.tasks.alert_tasks.get_current_price")
    @patch("app.tasks.alert_tasks._ticker_for_instrument")
    async def test_engine_handles_price_fetch_failure_gracefully(
        self, mock_ticker, mock_price, db, user, instrument
    ):
        """Engine should not crash if yfinance returns None."""
        from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
        from app.tasks.alert_tasks import check_all_alerts

        mock_ticker.return_value = "AAPL"
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

        with patch("app.tasks.alert_tasks.SessionLocal", return_value=db):
            result = await check_all_alerts({})  # must not raise

        assert "price_fired" in result


# ── Data pipeline ──────────────────────────────────────────────────────────────


class TestDataPipeline:
    @patch("app.tasks.data_tasks.fetch_ohlcv")
    async def test_fetch_instrument_history_calls_all_timeframes(self, mock_fetch, db, instrument):
        from app.tasks.data_tasks import FULL_HISTORY_TIMEFRAMES, fetch_instrument_history

        mock_fetch.return_value = []

        with patch("app.tasks.data_tasks.SessionLocal", return_value=db):
            result = await fetch_instrument_history({}, instrument.id)

        assert result["instrument_id"] == instrument.id
        assert mock_fetch.call_count == len(FULL_HISTORY_TIMEFRAMES)

    @patch("app.tasks.data_tasks.fetch_ohlcv")
    async def test_fetch_instrument_history_unknown_id(self, mock_fetch, db):
        from app.tasks.data_tasks import fetch_instrument_history

        with patch("app.tasks.data_tasks.SessionLocal", return_value=db):
            result = await fetch_instrument_history({}, 99999)

        assert "error" in result
        mock_fetch.assert_not_called()

    @patch("app.tasks.data_tasks.fetch_ohlcv")
    async def test_fetch_all_instruments_history(self, mock_fetch, db, instrument, instrument_b):
        from app.tasks.data_tasks import fetch_all_instruments_history

        mock_fetch.return_value = []

        with patch("app.tasks.data_tasks.SessionLocal", return_value=db):
            result = await fetch_all_instruments_history({})

        assert result["instruments_refreshed"] >= 2
        assert mock_fetch.call_count >= 2  # at least one call per instrument
