from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.radar import (
    RadarDetection,
    RadarOutcomeStatus,
    RadarSetupThread,
    RadarSetupType,
    RadarState,
)
from app.services.radar_engine import (
    _apply_candidate_to_thread,
    _evaluate_detection_outcome,
    _find_duplicate_thread_detection,
    _find_matching_thread,
    _invalidation_price,
    analyze_instrument,
)


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


_EXPECTED_SCORE_FACTOR_KEYS = {
    "distance_to_level",
    "touch_count",
    "recency",
    "structure_age",
    "overlap_confluence",
    "multi_timeframe_alignment",
    "trend_pattern_quality",
    "gap_context",
    "avwap_anchor_quality",
    "recent_reaction_quality",
    "timeframe_importance",
    "normalized_score",
}


class TestInvalidationPrice:
    def _zone(self, low: float = 95.0, high: float = 105.0) -> SimpleNamespace:
        return SimpleNamespace(low=low, high=high)

    def test_support_setups_use_zone_low(self):
        zone = self._zone()
        for st in (
            RadarSetupType.APPROACHING_SUPPORT,
            RadarSetupType.RECLAIM,
            RadarSetupType.BREAKOUT,
        ):
            assert _invalidation_price(st, zone) == round(zone.low, 4)

    def test_resistance_setups_use_zone_high(self):
        zone = self._zone()
        for st in (
            RadarSetupType.APPROACHING_RESISTANCE,
            RadarSetupType.REJECTION,
            RadarSetupType.BREAKDOWN,
        ):
            assert _invalidation_price(st, zone) == round(zone.high, 4)


class TestRadarEngine:
    def _support_detections(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        return analyze_instrument(_instrument(), _make_bars(prices))

    def _resistance_detections(self):
        prices = [100, 104, 108, 111, 108, 104] * 18
        prices += [108, 110.5, 107.5, 106.5, 105.5]
        bars = _make_bars(prices)
        bars[-1].high = Decimal("113.5")
        return analyze_instrument(_instrument(), bars)

    def test_approaching_support_detection_is_classified(self):
        detections = self._support_detections()
        setup_types = {d.setup_type.value for d in detections}
        assert "approaching_support" in setup_types

    def test_rejection_detection_is_classified(self):
        detections = self._resistance_detections()
        setup_types = {d.setup_type.value for d in detections}
        assert "rejection" in setup_types

    def test_breakout_retest_detection_is_classified(self):
        prices = [100, 104, 108, 111, 108, 104] * 18
        prices += [109, 112.5, 114.5, 112.2, 114.1]
        bars = _make_bars(prices)
        bars[-2].close = Decimal("112.6")
        bars[-1].low = Decimal("111.8")
        detections = analyze_instrument(_instrument(), bars)
        setup_types = {d.setup_type.value for d in detections}
        assert "breakout_retest" in setup_types

    def test_breakdown_retest_detection_is_classified(self):
        prices = [95, 100, 95, 100, 95, 100] * 18
        prices += [96.5, 93.5, 91.8, 93.4, 91.7]
        bars = _make_bars(prices)
        bars[-2].close = Decimal("93.2")
        bars[-1].high = Decimal("94.4")
        detections = analyze_instrument(_instrument(), bars)
        setup_types = {d.setup_type.value for d in detections}
        assert "breakdown_retest" in setup_types

    def test_candidates_have_normalized_scores_and_freshness(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        detections = analyze_instrument(_instrument(), _make_bars(prices))
        assert detections
        for detection in detections:
            assert 0.0 <= detection.score <= 1.0
            assert detection.fresh_until > detection.observed_at
            assert detection.evidence["overlays"]

    def test_fakeout_detection_is_classified(self):
        prices = [100, 104, 108, 111, 108, 104] * 18
        prices += [109.5, 111.8, 114.2, 112.1, 111.2]
        bars = _make_bars(prices)
        bars[-1].high = Decimal("114.8")
        bars[-1].close = Decimal("111.0")
        detections = analyze_instrument(_instrument(), bars)
        setup_types = {d.setup_type.value for d in detections}
        assert "fakeout" in setup_types

    def test_richer_structure_evidence_is_present(self):
        detections = self._support_detections()
        assert detections
        detection = detections[0]
        structure_types = {structure.get("type") for structure in detection.evidence["structures"]}
        assert "horizontal_zone" in structure_types
        assert "trendline" in structure_types
        assert detection.evidence["metrics"]["avwap_anchor_type"]
        assert "multi_timeframe_hits" in detection.evidence["metrics"]

    def test_evidence_metrics_contain_invalidation_price(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        detections = analyze_instrument(_instrument(), _make_bars(prices))
        assert detections
        for det in detections:
            assert "invalidation_price" in det.evidence["metrics"]
            assert isinstance(det.evidence["metrics"]["invalidation_price"], float)

    def test_evidence_metrics_contain_week52_occurrence_timestamps(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        detections = analyze_instrument(_instrument(), _make_bars(prices))
        assert detections
        for det in detections:
            assert "week52_high_time" in det.evidence["metrics"]
            assert "week52_low_time" in det.evidence["metrics"]
            assert isinstance(det.evidence["metrics"]["week52_high_time"], int)
            assert isinstance(det.evidence["metrics"]["week52_low_time"], int)

    def test_evidence_metrics_contain_signal_and_context_timestamps(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        detections = analyze_instrument(_instrument(), _make_bars(prices))
        assert detections
        for det in detections:
            assert "signal_time" in det.evidence["metrics"]
            assert "context_time" in det.evidence["metrics"]
            assert isinstance(det.evidence["metrics"]["signal_time"], int)
            assert isinstance(det.evidence["metrics"]["context_time"], int)

    def test_candidates_expose_signal_context_and_role_fields(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        detections = analyze_instrument(_instrument(), _make_bars(prices))
        assert detections
        for det in detections:
            assert det.signal_at.tzinfo is not None
            assert det.context_role in {"support", "resistance"}
            if det.context_at is not None:
                assert det.context_at.tzinfo is not None
                assert det.context_at <= det.observed_at

    def test_candidates_expose_state_and_action_levels(self):
        detections = analyze_instrument(
            _instrument(),
            _make_bars([95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98]),
        )
        assert detections
        for det in detections:
            assert det.state in {RadarState.DEVELOPING, RadarState.CONFIRMED}
            assert det.state_reason
            assert det.entry_price > 0
            assert det.invalidation_price > 0
            assert det.target_price > 0
            assert "entry_price" in det.evidence["metrics"]
            assert "target_price" in det.evidence["metrics"]
            assert "risk_reward" in det.evidence["metrics"]
            overlay_roles = {overlay.get("role") for overlay in det.evidence["overlays"]}
            assert {"entry", "invalidation", "target"}.issubset(overlay_roles)

    def test_evidence_overlays_contain_invalidation_line(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        detections = analyze_instrument(_instrument(), _make_bars(prices))
        assert detections
        for det in detections:
            inv_overlays = [o for o in det.evidence["overlays"] if o.get("role") == "invalidation"]
            assert inv_overlays, f"No invalidation overlay for {det.setup_type}"
            ov = inv_overlays[0]
            assert ov["kind"] == "line"
            assert ov["label"] == "Invalidation"
            assert len(ov["points"]) == 2

    def test_invalidation_price_matches_overlay_price(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        detections = analyze_instrument(_instrument(), _make_bars(prices))
        assert detections
        for det in detections:
            inv_price = det.evidence["metrics"]["invalidation_price"]
            inv_overlay = next(
                o for o in det.evidence["overlays"] if o.get("role") == "invalidation"
            )
            assert inv_overlay["points"][0]["price"] == inv_price
            assert inv_overlay["points"][1]["price"] == inv_price

    def test_score_factors_have_all_expected_keys(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        detections = analyze_instrument(_instrument(), _make_bars(prices))
        assert detections
        for det in detections:
            assert _EXPECTED_SCORE_FACTOR_KEYS == set(det.score_factors.keys())

    def test_matching_thread_continues_same_role_and_level_story(self):
        prices = [95, 100, 95, 100, 95, 100] * 20
        prices += [98, 97, 96, 97, 98]
        detections = analyze_instrument(_instrument(), _make_bars(prices))
        candidate = next(
            det for det in detections if det.setup_type == RadarSetupType.APPROACHING_SUPPORT
        )
        thread = RadarSetupThread(
            instrument_id=1,
            timeframe=Timeframe.D1,
            context_role="support",
            reference_price=candidate.key_level_price + 0.4,
            current_setup_type=RadarSetupType.APPROACHING_SUPPORT,
            current_state=RadarState.DEVELOPING,
            state_changed_at=candidate.signal_at - timedelta(days=1),
            started_at=candidate.signal_at - timedelta(days=3),
            last_seen_at=candidate.signal_at - timedelta(days=1),
            detection_count=2,
        )

        matched = _find_matching_thread(candidate, [thread])

        assert matched is thread

        event_index = _apply_candidate_to_thread(candidate, thread)

        assert event_index == 3
        assert thread.detection_count == 3
        assert thread.current_setup_type == candidate.setup_type
        assert thread.current_state == candidate.state
        assert thread.last_seen_at == candidate.signal_at

    def test_duplicate_thread_detection_is_reused_instead_of_incremented(self):
        candidate = next(
            det
            for det in self._support_detections()
            if det.setup_type == RadarSetupType.APPROACHING_SUPPORT
        )
        existing_detection = RadarDetection(
            id=55,
            run_id=1,
            instrument_id=1,
            timeframe=Timeframe.D1,
            setup_type=candidate.setup_type,
            state=candidate.state,
            state_reason=candidate.state_reason,
            score=candidate.score,
            summary=candidate.summary,
            invalidation_hint=candidate.invalidation_hint,
            evidence_json=candidate.evidence,
            score_factors=candidate.score_factors,
            signal_at=candidate.signal_at,
            context_at=candidate.context_at,
            key_level_price=candidate.key_level_price,
            entry_price=candidate.entry_price,
            invalidation_price=candidate.invalidation_price,
            target_price=candidate.target_price,
            thread_event_index=2,
            observed_at=candidate.observed_at,
            fresh_until=candidate.fresh_until,
        )
        thread = RadarSetupThread(
            instrument_id=1,
            timeframe=Timeframe.D1,
            context_role="support",
            reference_price=candidate.key_level_price,
            current_setup_type=RadarSetupType.APPROACHING_SUPPORT,
            current_state=RadarState.DEVELOPING,
            state_changed_at=candidate.signal_at,
            started_at=candidate.signal_at - timedelta(days=2),
            last_seen_at=candidate.signal_at,
            detection_count=2,
        )
        thread.detections = [existing_detection]

        duplicate = _find_duplicate_thread_detection(candidate, thread)

        assert duplicate is existing_detection

    def test_support_avwap_is_anchored_to_latest_zone_touch(self):
        detection = next(
            det
            for det in self._support_detections()
            if det.setup_type == RadarSetupType.APPROACHING_SUPPORT
        )

        avwap_overlay = next(
            overlay
            for overlay in detection.evidence["overlays"]
            if overlay.get("role") == "avwap_primary"
        )

        assert detection.evidence["metrics"]["avwap"] is not None
        assert avwap_overlay["label"].startswith("AVWAP")
        assert avwap_overlay["points"]
        assert (
            detection.evidence["metrics"]["avwap_anchor_time"] == avwap_overlay["points"][0]["time"]
        )

    def test_resistance_avwap_is_anchored_to_latest_zone_touch(self):
        detection = next(
            det
            for det in self._resistance_detections()
            if det.setup_type == RadarSetupType.REJECTION
        )

        avwap_overlay = next(
            overlay
            for overlay in detection.evidence["overlays"]
            if overlay.get("role") == "avwap_primary"
        )

        assert detection.evidence["metrics"]["avwap"] is not None
        assert avwap_overlay["label"].startswith("AVWAP")
        assert avwap_overlay["points"]
        assert (
            detection.evidence["metrics"]["avwap_anchor_time"] == avwap_overlay["points"][0]["time"]
        )

    def test_long_outcome_marks_target_hit(self):
        bars = _make_bars([100, 102, 104, 107])
        detection = RadarDetection(
            run_id=1,
            instrument_id=1,
            timeframe=Timeframe.D1,
            setup_type=RadarSetupType.BREAKOUT,
            state=RadarState.CONFIRMED,
            state_reason="Confirmed breakout",
            score=0.9,
            summary="AAPL breakout",
            invalidation_hint="Close below support",
            evidence_json={},
            score_factors={},
            observed_at=bars[-1].ts,
            signal_at=bars[1].ts,
            context_at=bars[0].ts,
            fresh_until=bars[-1].ts + timedelta(days=5),
            key_level_price=101.0,
            entry_price=102.0,
            invalidation_price=99.5,
            target_price=106.0,
        )

        _evaluate_detection_outcome(detection, bars)

        assert detection.outcome_status == RadarOutcomeStatus.TARGET_HIT
        assert detection.target_hit_at == bars[3].ts
        assert detection.invalidated_at is None
        assert detection.bars_since_signal == 2
        assert detection.max_favorable_excursion_pct is not None

    def test_short_outcome_marks_invalidated(self):
        bars = _make_bars([100, 98, 97, 101])
        detection = RadarDetection(
            run_id=1,
            instrument_id=1,
            timeframe=Timeframe.D1,
            setup_type=RadarSetupType.BREAKDOWN,
            state=RadarState.CONFIRMED,
            state_reason="Confirmed breakdown",
            score=0.88,
            summary="AAPL breakdown",
            invalidation_hint="Close back above resistance",
            evidence_json={},
            score_factors={},
            observed_at=bars[-1].ts,
            signal_at=bars[1].ts,
            context_at=bars[0].ts,
            fresh_until=bars[-1].ts + timedelta(days=5),
            key_level_price=99.0,
            entry_price=98.0,
            invalidation_price=100.0,
            target_price=94.0,
        )

        _evaluate_detection_outcome(detection, bars)

        assert detection.outcome_status == RadarOutcomeStatus.INVALIDATED
        assert detection.invalidated_at == bars[3].ts
        assert detection.target_hit_at is None
        assert detection.bars_since_signal == 2
        assert detection.max_adverse_excursion_pct is not None
