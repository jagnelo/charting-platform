from datetime import UTC, date, datetime, timedelta, timezone

from app.models.ohlcv import Timeframe
from app.models.radar import (
    RadarOutcomeStatus,
    RadarRunStatus,
    RadarSetupType,
    RadarState,
)
from app.routers.calendar import CalendarEvent
from app.routers.indicator_alerts import IndicatorAlertOut as LegacyIndicatorAlertOut
from app.schemas.analysis import (
    AnalysisCell,
    AnalysisPoint,
    BenchmarkFamilyConcentrationHistoryPointOut,
    BenchmarkFamilyCoverageSnapshotOut,
    BenchmarkFamilyMemberBarHistoryTimeframeOut,
    BreadthDefinitionHistoryOccurrenceOut,
    BreadthHistoryPoint,
    CrossFamilyRankingHistoryPoint,
    IndicatorBatchValue,
    MarketGaugeOut,
    RelativeRotationOut,
    RelativeRotationTailPoint,
    RelativeStrengthOut,
    TechnicalSnapshotOut,
)
from app.schemas.basket import BasketMemberOut, BasketOut, BasketSnapshotOut
from app.schemas.dashboard import DashboardOut, DashboardTabOut, DashboardWidgetOut
from app.schemas.drawing import ChartDrawingOut
from app.schemas.market_map import MarketMapCell, MarketMapOut, MarketMapSnapshotSummary
from app.schemas.preset import IndicatorPresetOut
from app.schemas.radar import (
    RadarDetectionSummaryOut,
    RadarRunOut,
    RadarSetupThreadOut,
    RadarThreadEventOut,
)

STAMP = datetime(2026, 1, 2, 5, 4, 5, tzinfo=UTC)
OFFSET_STAMP = datetime(2026, 1, 2, 7, 4, 5, tzinfo=timezone(timedelta(hours=2)))


def _assert_utc_z(payload: dict, *fields: str) -> None:
    for field in fields:
        assert payload[field] == "2026-01-02T05:04:05Z"


def test_saved_tool_and_radar_responses_use_canonical_timestamp_wire_format():
    preset = IndicatorPresetOut(
        id=1,
        name="Momentum",
        indicators=[],
        is_default=False,
        created_at=OFFSET_STAMP,
        updated_at=STAMP,
    )
    drawing = ChartDrawingOut(
        id=2,
        instrument_id=3,
        pin_to_all=False,
        drawing_type="horizontal",
        data={},
        style={},
        is_visible=True,
        is_locked=False,
        created_at=STAMP,
        updated_at=STAMP,
    )
    basket_member = BasketMemberOut(
        id=4,
        instrument_id=3,
        position=0,
        created_at=STAMP,
        updated_at=STAMP,
    )
    basket_snapshot = BasketSnapshotOut(
        id=5,
        basket_id=6,
        composition_date=date(2026, 1, 2),
        known_at=STAMP,
        source_type="provider",
        member_count=1,
        created_at=STAMP,
        updated_at=STAMP,
    )
    basket = BasketOut(
        id=6,
        name="Core",
        source_type="personal",
        weighting_scheme="equal",
        is_system_managed=False,
        is_read_only=False,
        members=[basket_member],
        created_at=STAMP,
        updated_at=STAMP,
    )
    widget = DashboardWidgetOut(
        id=7,
        tab_id=8,
        widget_type="chart",
        created_at=STAMP,
        updated_at=STAMP,
    )
    tab = DashboardTabOut(
        id=8,
        dashboard_id=9,
        name="Overview",
        widgets=[widget],
        created_at=STAMP,
        updated_at=STAMP,
    )
    dashboard = DashboardOut(
        id=9,
        user_id=10,
        name="Dashboard",
        is_default=True,
        position=0,
        settings={},
        tabs=[tab],
        created_at=STAMP,
        updated_at=STAMP,
    )
    radar_run = RadarRunOut(
        id=11,
        timeframe=Timeframe.D1,
        universe_type="all",
        universe_filter=None,
        status=RadarRunStatus.COMPLETED,
        started_at=STAMP,
        completed_at=None,
        evaluated_count=1,
        detection_count=1,
        error_summary=None,
        created_at=STAMP,
        updated_at=STAMP,
    )
    radar_thread = RadarSetupThreadOut(
        id=12,
        instrument_id=3,
        timeframe=Timeframe.D1,
        context_role=None,
        reference_price=100.0,
        current_setup_type=RadarSetupType.BREAKOUT,
        current_state=RadarState.CONFIRMED,
        state_changed_at=STAMP,
        started_at=STAMP,
        last_seen_at=STAMP,
        detection_count=1,
    )
    radar_detection = RadarDetectionSummaryOut(
        id=13,
        run_id=11,
        instrument_id=3,
        instrument_symbol="TEST",
        instrument_name="Test",
        timeframe=Timeframe.D1,
        setup_type=RadarSetupType.BREAKOUT,
        score=0.9,
        observed_at=STAMP,
        signal_at=STAMP,
        context_at=None,
        state=RadarState.CONFIRMED,
        state_reason=None,
        fresh_until=STAMP,
        thread_id=12,
        thread_event_index=0,
        key_level_price=None,
        entry_price=None,
        invalidation_price=None,
        target_price=None,
        outcome_status=RadarOutcomeStatus.OPEN,
        outcome_last_evaluated_at=None,
        bars_since_signal=0,
        max_favorable_excursion_pct=None,
        max_adverse_excursion_pct=None,
        target_hit_at=None,
        invalidated_at=None,
        summary="Breakout",
        invalidation_hint=None,
        score_factors={},
        created_at=STAMP,
        updated_at=STAMP,
    )
    radar_event = RadarThreadEventOut(
        id=14,
        setup_type=RadarSetupType.BREAKOUT,
        score=0.9,
        observed_at=STAMP,
        signal_at=STAMP,
        context_at=None,
        state=RadarState.CONFIRMED,
        state_reason=None,
        thread_event_index=0,
        key_level_price=None,
        entry_price=None,
        invalidation_price=None,
        target_price=None,
        outcome_status=RadarOutcomeStatus.OPEN,
        outcome_last_evaluated_at=None,
        bars_since_signal=0,
        max_favorable_excursion_pct=None,
        max_adverse_excursion_pct=None,
        target_hit_at=None,
        invalidated_at=None,
        summary="Breakout",
        invalidation_hint=None,
        created_at=STAMP,
        updated_at=STAMP,
    )

    _assert_utc_z(preset.model_dump(mode="json"), "created_at", "updated_at")
    _assert_utc_z(drawing.model_dump(mode="json"), "created_at", "updated_at")
    _assert_utc_z(basket_member.model_dump(mode="json"), "created_at", "updated_at")
    _assert_utc_z(basket_snapshot.model_dump(mode="json"), "known_at", "created_at", "updated_at")
    _assert_utc_z(basket.model_dump(mode="json"), "created_at", "updated_at")
    _assert_utc_z(dashboard.model_dump(mode="json"), "created_at", "updated_at")
    _assert_utc_z(dashboard.model_dump(mode="json")["tabs"][0], "created_at", "updated_at")
    _assert_utc_z(
        dashboard.model_dump(mode="json")["tabs"][0]["widgets"][0],
        "created_at",
        "updated_at",
    )
    _assert_utc_z(radar_run.model_dump(mode="json"), "started_at", "created_at", "updated_at")
    _assert_utc_z(
        radar_thread.model_dump(mode="json"),
        "state_changed_at",
        "started_at",
        "last_seen_at",
    )
    _assert_utc_z(
        radar_detection.model_dump(mode="json"),
        "observed_at",
        "signal_at",
        "fresh_until",
        "created_at",
        "updated_at",
    )
    _assert_utc_z(
        radar_event.model_dump(mode="json"), "observed_at", "signal_at", "created_at", "updated_at"
    )


def test_market_map_responses_use_canonical_timestamp_wire_format():
    source = {
        "source_id": "index:sp500",
        "source_kind": "index",
        "name": "S&P 500",
        "locked": True,
        "can_follow": True,
        "can_clone": False,
        "can_edit_membership": False,
    }
    cell = MarketMapCell(
        instrument_id=1,
        symbol="TEST",
        name="Test",
        observation_time=OFFSET_STAMP,
        coverage=1.0,
    )
    market_map = MarketMapOut(
        source=source,
        group_by="sector_industry",
        period="1D",
        period_start=OFFSET_STAMP,
        period_end=STAMP,
        timeframe="D1",
        adjustment="adjusted",
        area_metric="market_cap",
        color_metric="return",
        cache_key="a" * 64,
        cached_at=STAMP,
        freshness="fresh",
        coverage=1.0,
        cells=[cell],
    )
    snapshot = MarketMapSnapshotSummary(
        id=2,
        name="S&P snapshot",
        source_id="index:sp500",
        cache_key="a" * 64,
        snapshot_hash="b" * 64,
        created_at=STAMP,
        updated_at=STAMP,
    )

    market_map_payload = market_map.model_dump(mode="json")
    _assert_utc_z(market_map_payload, "period_start", "period_end", "cached_at")
    _assert_utc_z(market_map_payload["cells"][0], "observation_time")
    _assert_utc_z(snapshot.model_dump(mode="json"), "created_at", "updated_at")


def test_calendar_and_legacy_indicator_alert_responses_use_canonical_timestamps():
    calendar_event = CalendarEvent(
        id=1,
        date="2026-01-02",
        event_time=OFFSET_STAMP,
        fetched_at=STAMP,
        event_type="earnings",
        symbol="TEST",
        title="Earnings",
        time_hint="before_open",
        source="provider",
    )
    indicator_alert = LegacyIndicatorAlertOut(
        id=2,
        instrument_id=3,
        timeframe=Timeframe.D1,
        indicator_type="rsi",
        indicator_params={},
        condition="crosses_above",
        threshold_value=None,
        compare_indicator_type=None,
        compare_indicator_params=None,
        status="active",
        repeat=False,
        notes=None,
        triggered_at=OFFSET_STAMP,
        trigger_count=0,
        last_indicator_value=None,
        created_at=STAMP,
    )

    _assert_utc_z(calendar_event.model_dump(mode="json"), "event_time", "fetched_at")
    _assert_utc_z(indicator_alert.model_dump(mode="json"), "triggered_at", "created_at")


def test_analysis_responses_use_canonical_timestamp_wire_format():
    point = AnalysisPoint(timestamp=OFFSET_STAMP, value=1.0)
    strength = RelativeStrengthOut(
        symbol="SPY",
        benchmark="QQQ",
        timeframe="D1",
        adjustment="split_adjusted",
        refreshed_at=OFFSET_STAMP,
        points=[point],
        overlap_start=OFFSET_STAMP,
        overlap_end=STAMP,
        coverage=1.0,
        as_of=STAMP,
    )
    rotation = RelativeRotationOut(
        group_key="sp500-sectors",
        benchmark="SPY",
        timeframe="D1",
        adjustment="split_adjusted",
        refreshed_at=OFFSET_STAMP,
        as_of=STAMP,
        lookback=20,
        tail_length=10,
        history_length=20,
        membership_version=3,
        rows=[
            {
                "instrument_id": 1,
                "symbol": "XLK",
                "name": "Technology",
                "coverage": 1.0,
                "tail": [
                    RelativeRotationTailPoint(timestamp=OFFSET_STAMP, trend=1.0, momentum=2.0)
                ],
            }
        ],
    )
    concentration_point = BenchmarkFamilyConcentrationHistoryPointOut(
        timestamp=OFFSET_STAMP,
        composition_date=date(2026, 1, 1),
        known_at=STAMP,
        membership_version=3,
        coverage=1.0,
    )
    coverage_snapshot = BenchmarkFamilyCoverageSnapshotOut(
        snapshot_id=4,
        composition_date=date(2026, 1, 1),
        as_of_date=date(2026, 1, 2),
        known_at=OFFSET_STAMP,
        published_at=STAMP,
        provenance="sec",
        source_provider="sec",
        source_quality="verified",
        completeness_status="complete",
        row_count=10,
        resolved_count=10,
        unresolved_count=0,
    )
    member_history = BenchmarkFamilyMemberBarHistoryTimeframeOut(
        timeframe="D1",
        oldest=OFFSET_STAMP,
        newest=STAMP,
    )
    analysis_cell = AnalysisCell(value=1.0, observation_time=OFFSET_STAMP)
    breadth_point = BreadthHistoryPoint(
        timestamp=STAMP,
        above_ma={"20": 0.5},
        coverage={"20": 1.0},
    )
    breadth_occurrence = BreadthDefinitionHistoryOccurrenceOut(
        occurrence_id="occ-1",
        timestamp=OFFSET_STAMP,
        kind="member_entered",
        instrument_id=1,
        symbol="SPY",
        name="SPDR S&P 500 ETF Trust",
        value=True,
        pass_count=1,
        eligible_count=1,
    )
    ranking_point = CrossFamilyRankingHistoryPoint(timestamp=STAMP, rank=1)
    indicator_value = IndicatorBatchValue(value=1.0, observation_time=OFFSET_STAMP)
    technical = TechnicalSnapshotOut(
        symbol="SPY",
        timeframe="D1",
        refreshed_at=OFFSET_STAMP,
        as_of=OFFSET_STAMP,
        adjustment="split_adjusted",
        last=100.0,
        rsi14=50.0,
        sma20=99.0,
        sma50=98.0,
        sma200=95.0,
        position_52w=0.8,
        volume_ratio_50=1.2,
    )
    gauge = MarketGaugeOut(
        screener_id=7,
        screener_name="Breadth",
        refreshed_at=OFFSET_STAMP,
        run_at=STAMP,
        matched_count=1,
        evaluated_count=1,
        universe_count=1,
        percentage=1.0,
    )

    _assert_utc_z(
        strength.model_dump(mode="json"), "refreshed_at", "as_of", "overlap_start", "overlap_end"
    )
    _assert_utc_z(strength.model_dump(mode="json")["points"][0], "timestamp")
    _assert_utc_z(rotation.model_dump(mode="json"), "refreshed_at", "as_of")
    _assert_utc_z(rotation.model_dump(mode="json")["rows"][0]["tail"][0], "timestamp")
    _assert_utc_z(concentration_point.model_dump(mode="json"), "timestamp", "known_at")
    _assert_utc_z(coverage_snapshot.model_dump(mode="json"), "known_at", "published_at")
    _assert_utc_z(member_history.model_dump(mode="json"), "oldest", "newest")
    _assert_utc_z(analysis_cell.model_dump(mode="json"), "observation_time")
    _assert_utc_z(breadth_point.model_dump(mode="json"), "timestamp")
    _assert_utc_z(breadth_occurrence.model_dump(mode="json"), "timestamp")
    _assert_utc_z(ranking_point.model_dump(mode="json"), "timestamp")
    _assert_utc_z(indicator_value.model_dump(mode="json"), "observation_time")
    _assert_utc_z(technical.model_dump(mode="json"), "refreshed_at", "as_of")
    _assert_utc_z(gauge.model_dump(mode="json"), "refreshed_at", "run_at")
