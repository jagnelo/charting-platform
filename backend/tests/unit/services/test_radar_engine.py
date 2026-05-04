from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.radar_engine import analyze_instrument


def _make_bars(prices: list[float]) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    base = datetime(2024, 1, 1, tzinfo=UTC)
    for index, price in enumerate(prices):
        bars.append(
            OHLCVBar(
                instrument_id=1,
                timeframe=Timeframe.D1,
                ts=base + timedelta(days=index),
                open=Decimal(str(round(price - 0.6, 4))),
                high=Decimal(str(round(price + 1.2, 4))),
                low=Decimal(str(round(price - 1.2, 4))),
                close=Decimal(str(round(price, 4))),
                volume=Decimal("1000000"),
                is_adjusted=True,
            )
        )
    return bars


def _instrument() -> Instrument:
    return Instrument(id=1, instrument_type_id=1, symbol="AAPL", name="Apple", is_active=True)


class TestRadarEngine:
    def test_approaching_support_detection_is_classified(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        detections = analyze_instrument(_instrument(), _make_bars(prices))
        setup_types = {d.setup_type.value for d in detections}
        assert "approaching_support" in setup_types

    def test_rejection_detection_is_classified(self):
        prices = [100, 104, 108, 111, 108, 104] * 18
        prices += [108, 110.5, 107.5, 106.5, 105.5]
        bars = _make_bars(prices)
        bars[-1].high = Decimal("113.5")
        detections = analyze_instrument(_instrument(), bars)
        setup_types = {d.setup_type.value for d in detections}
        assert "rejection" in setup_types

    def test_candidates_have_normalized_scores_and_freshness(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        detections = analyze_instrument(_instrument(), _make_bars(prices))
        assert detections
        for detection in detections:
            assert 0.0 <= detection.score <= 1.0
            assert detection.fresh_until > detection.observed_at
            assert detection.evidence["overlays"]
