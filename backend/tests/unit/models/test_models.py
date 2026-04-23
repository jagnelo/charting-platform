"""
Unit tests for DB model constraints and relationships.
Verifies FK cascades, unique constraints, and nullable rules
against the real Postgres schema.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError


class TestUserModel:
    def test_username_unique_constraint(self, db, user):
        from app.models.user import User
        from app.services.auth import hash_password

        dup = User(username="testuser", email="other@test.com", hashed_password=hash_password("x"))
        db.add(dup)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_email_unique_constraint(self, db, user):
        from app.models.user import User
        from app.services.auth import hash_password

        dup = User(
            username="other_user", email="test@example.com", hashed_password=hash_password("x")
        )
        db.add(dup)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_user_defaults(self, db):
        from app.models.user import User
        from app.services.auth import hash_password

        u = User(username="defaulttest", email="dt@test.com", hashed_password=hash_password("x"))
        db.add(u)
        db.flush()
        assert u.is_active is True
        assert u.is_admin is False
        assert u.last_login_at is None

    def test_user_cascade_deletes_drawings(self, db, user, instrument):
        from app.models.chart_drawing import ChartDrawing
        from app.models.ohlcv import Timeframe

        drawing = ChartDrawing(
            user_id=user.id,
            instrument_id=instrument.id,
            timeframe=Timeframe.D1,
            drawing_type="trendline",
            data={},
            style={},
            is_visible=True,
            is_locked=False,
        )
        db.add(drawing)
        db.flush()
        drawing_id = drawing.id

        db.delete(user)
        db.flush()

        result = db.get(ChartDrawing, drawing_id)
        assert result is None

    def test_user_cascade_deletes_alerts(self, db, user, instrument):
        from app.models.price_alert import AlertCondition, PriceAlert

        alert = PriceAlert(
            user_id=user.id,
            instrument_id=instrument.id,
            condition=AlertCondition.CROSSES_ABOVE,
            threshold_price=Decimal("200"),
        )
        db.add(alert)
        db.flush()
        alert_id = alert.id

        db.delete(user)
        db.flush()

        result = db.get(PriceAlert, alert_id)
        assert result is None


class TestOHLCVBarModel:
    def test_unique_constraint(self, db, instrument, ohlcv_bars):
        """Inserting a duplicate (instrument, timeframe, ts, is_adjusted) should fail."""

        from app.models.ohlcv import OHLCVBar, Timeframe

        duplicate = OHLCVBar(
            instrument_id=instrument.id,
            timeframe=Timeframe.D1,
            ts=ohlcv_bars[0].ts,  # same timestamp
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("95"),
            close=Decimal("102"),
            volume=Decimal("1000000"),
            is_adjusted=ohlcv_bars[0].is_adjusted,
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_high_gte_low_data_integrity(self, db, ohlcv_bars):
        for bar in ohlcv_bars:
            assert bar.high >= bar.low, f"Bar {bar.ts}: high < low"

    def test_bars_ordered_by_ts(self, db, instrument, ohlcv_bars):
        from sqlalchemy import select

        from app.models.ohlcv import OHLCVBar, Timeframe

        bars = (
            db.execute(
                select(OHLCVBar)
                .where(OHLCVBar.instrument_id == instrument.id, OHLCVBar.timeframe == Timeframe.D1)
                .order_by(OHLCVBar.ts)
            )
            .scalars()
            .all()
        )
        tss = [b.ts for b in bars]
        assert tss == sorted(tss)


class TestScreenerModel:
    def test_screener_conditions_tree_stored(self, db, user):
        """ScreenerDefinition persists a JSON conditions tree correctly."""
        from app.models.screener import ScreenerDefinition

        tree = {
            "operator": "AND",
            "conditions": [
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 50}
            ],
        }
        s = ScreenerDefinition(
            user_id=user.id,
            name="TreeTest",
            conditions=tree,
            universe_type="all",
            timeframe="D1",
        )
        db.add(s)
        db.flush()
        db.refresh(s)
        assert s.conditions["operator"] == "AND"
        assert len(s.conditions["conditions"]) == 1

    def test_screener_result_cascade_delete(self, db, screener):
        from app.models.screener import ScreenerResult

        result = ScreenerResult(
            screener_id=screener.id,
            run_at=datetime.now(UTC),
            matched_ids=[1, 2, 3],
            result_data={"1": {"close": 145.2}},
        )
        db.add(result)
        db.flush()
        result_id = result.id

        db.delete(screener)
        db.flush()

        assert db.get(ScreenerResult, result_id) is None

    def test_screener_cascade_deletes_on_user_delete(self, db, user):
        """Deleting a user cascades to their screener definitions."""
        from sqlalchemy import select

        from app.models.screener import ScreenerDefinition

        s = ScreenerDefinition(
            user_id=user.id,
            name="UserCascadeTest",
            conditions={"operator": "AND", "conditions": []},
            universe_type="all",
            timeframe="D1",
        )
        db.add(s)
        db.flush()
        s_id = s.id

        db.delete(user)
        db.flush()

        assert db.execute(
            select(ScreenerDefinition).where(ScreenerDefinition.id == s_id)
        ).scalar_one_or_none() is None


class TestWatchlistModel:
    def test_watchlist_item_unique_constraint(self, db, user, instrument, watchlist):
        from sqlalchemy.exc import IntegrityError

        from app.models.watchlist import WatchlistItem

        item1 = WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id)
        db.add(item1)
        db.flush()

        item2 = WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id)
        db.add(item2)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_watchlist_cascade_deletes_items(self, db, user, instrument, watchlist):
        from app.models.watchlist import WatchlistItem

        item = WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id)
        db.add(item)
        db.flush()
        item_id = item.id

        db.delete(watchlist)
        db.flush()

        assert db.get(WatchlistItem, item_id) is None


class TestPriceAlertModel:
    def test_alert_default_status_is_active(self, db, user, instrument):
        from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert

        a = PriceAlert(
            user_id=user.id,
            instrument_id=instrument.id,
            condition=AlertCondition.TOUCHES,
            threshold_price=Decimal("150"),
        )
        db.add(a)
        db.flush()
        assert a.status == AlertStatus.ACTIVE

    def test_alert_trigger_count_default_zero(self, db, user, instrument):
        from app.models.price_alert import AlertCondition, PriceAlert

        a = PriceAlert(
            user_id=user.id,
            instrument_id=instrument.id,
            condition=AlertCondition.TOUCHES,
            threshold_price=Decimal("150"),
        )
        db.add(a)
        db.flush()
        assert a.trigger_count == 0
