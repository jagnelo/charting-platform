class TestStrategyLabAPI:
    def test_create_list_version_and_run_strategy(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        date_from = ohlcv_bars[0].ts.isoformat()
        date_to = ohlcv_bars[-1].ts.isoformat()
        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Momentum Pilot",
                "description": "Initial strategy lab foundation test",
                "source_type": "custom",
                "definition_type": "rules",
                "is_active": True,
                "tags": ["momentum", "swing"],
                "metadata": {"owner": "test"},
                "initial_version": {
                    "definition_snapshot": {
                        "timeframe": "D1",
                        "direction": "long",
                        "entry_logic": "all",
                        "conditions": [
                            {
                                "type": "price_threshold",
                                "field": "close",
                                "op": "gt",
                                "value": 0,
                            }
                        ],
                        "risk": {
                            "stop_loss_pct": 2.0,
                            "take_profit_rr": 1.5,
                            "max_bars_in_trade": 5,
                        },
                    },
                    "parameter_schema": {},
                    "default_parameters": {},
                    "universe_config": {"symbols": ["AAPL"]},
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                    "notes": "Seed version",
                },
            },
        )
        assert create_res.status_code == 201
        created = create_res.json()
        assert created["name"] == "Momentum Pilot"
        assert created["versions"][0]["version_number"] == 1
        assert created["versions"][0]["definition_snapshot"]["timeframe"] == "D1"

        list_res = client.get("/api/v1/strategy-lab/definitions", headers=auth_headers)
        assert list_res.status_code == 200
        assert any(item["id"] == created["id"] for item in list_res.json())

        version_res = client.post(
            f"/api/v1/strategy-lab/definitions/{created['id']}/versions",
            headers=auth_headers,
            json={
                "definition_snapshot": {
                    "timeframe": "D1",
                    "direction": "long",
                    "entry_logic": "all",
                    "conditions": [
                        {
                            "type": "price_indicator",
                            "field": "close",
                            "op": "gt",
                            "indicator": "sma",
                            "params": {"period": 5},
                        }
                    ],
                    "risk": {
                        "stop_loss_pct": 2.0,
                        "take_profit_rr": 1.2,
                        "max_bars_in_trade": 7,
                    },
                },
                "parameter_schema": {},
                "default_parameters": {},
                "universe_config": {"symbols": ["AAPL"]},
                "benchmark_config": {"symbol": "QQQ"},
                "execution_model": {"entry": "close_confirmation"},
                "notes": "Published version two",
            },
        )
        assert version_res.status_code == 201
        version = version_res.json()
        assert version["version_number"] == 2
        assert version["is_current"] is True

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{version['id']}/runs",
            headers=auth_headers,
            json={
                "test_mode": "backtest",
                "timeframe": "D1",
                "date_from": date_from,
                "date_to": date_to,
                "parameter_values": {},
                "universe_config": {"symbols": ["AAPL"]},
                "execution_assumptions": {
                    "initial_capital": 100000,
                    "risk_per_trade_pct": 1.0,
                    "slippage_bps": 5,
                    "commission_per_trade": 1.0,
                },
            },
        )
        assert run_res.status_code == 201
        run_payload = run_res.json()
        assert run_payload["status"] == "completed"
        assert run_payload["result_summary"]["result_kind"] == "rules_backtest"
        assert run_payload["result_summary"]["coverage"]["instrument_count"] == 1
        assert run_payload["result_summary"]["coverage"]["total_bars"] >= 1
        assert run_payload["result_summary"]["performance"]["trade_count"] is not None
        assert len(run_payload["result_summary"]["equity_curve"]) >= len(ohlcv_bars)
        assert len(run_payload["result_summary"]["portfolio_timeline"]) >= len(ohlcv_bars)
        assert run_payload["artifact_manifest"]["supports_execution_stats"] is True

        detail_res = client.get(
            f"/api/v1/strategy-lab/definitions/{created['id']}",
            headers=auth_headers,
        )
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["runs"]
        assert detail["runs"][0]["id"] == run_payload["id"]

        runs_res = client.get("/api/v1/strategy-lab/runs", headers=auth_headers)
        assert runs_res.status_code == 200
        assert any(item["id"] == run_payload["id"] for item in runs_res.json())

    def test_preview_strategy_coverage_summarizes_universe_and_benchmark(
        self,
        client,
        auth_headers,
        db,
        instrument,
        instrument_b,
        instrument_type,
        ohlcv_bars,
    ):
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal

        from app.models.instrument import Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe

        benchmark = Instrument(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(benchmark)
        db.flush()

        msft_start = datetime(2024, 2, 15, tzinfo=UTC)
        for index in range(50):
            close = Decimal(str(round(410 + index * 0.5, 4)))
            db.add(
                OHLCVBar(
                    instrument_id=instrument_b.id,
                    timeframe=Timeframe.D1,
                    ts=msft_start + timedelta(days=index),
                    open=close,
                    high=close + Decimal("1.0"),
                    low=close - Decimal("1.0"),
                    close=close,
                    volume=Decimal("5000000"),
                    is_adjusted=True,
                )
            )

        benchmark_start = datetime(2024, 3, 1, tzinfo=UTC)
        for index in range(35):
            close = Decimal(str(round(500 + index * 1.25, 4)))
            db.add(
                OHLCVBar(
                    instrument_id=benchmark.id,
                    timeframe=Timeframe.D1,
                    ts=benchmark_start + timedelta(days=index),
                    open=close,
                    high=close + Decimal("1.0"),
                    low=close - Decimal("1.0"),
                    close=close,
                    volume=Decimal("8000000"),
                    is_adjusted=True,
                )
            )
        db.flush()

        preview_res = client.post(
            "/api/v1/strategy-lab/coverage-preview",
            headers=auth_headers,
            json={
                "source_type": "custom",
                "timeframe": "D1",
                "date_from": ohlcv_bars[9].ts.isoformat(),
                "date_to": ohlcv_bars[90].ts.isoformat(),
                "universe_config": {"symbols": ["AAPL", "MSFT"]},
                "benchmark_config": {"symbol": "SPY"},
            },
        )

        assert preview_res.status_code == 200
        payload = preview_res.json()
        assert payload["timeframe"] == "D1"
        assert payload["universe"]["instrument_count"] == 2
        assert payload["universe"]["instruments_with_full_requested_coverage"] == 1
        assert payload["universe"]["instruments_with_partial_requested_coverage"] == 1
        assert payload["universe"]["requested_fits_collective_range"] is False
        assert payload["universe"]["collective_coverage_from"].startswith("2024-02-15")
        assert payload["universe"]["limiting_instruments"][0]["symbol"] == "MSFT"
        assert "earlier local history may be missing" in (
            payload["universe"]["limiting_instruments"][0]["note"] or ""
        ).lower()
        assert payload["benchmark"]["symbol"] == "SPY"
        assert payload["benchmark"]["requested_status"] == "partial"
        assert payload["benchmark"]["requested_first_bar_at"].startswith("2024-03-01")

    def test_delete_definition_removes_strategy(self, client, auth_headers):
        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Delete Me",
                "description": None,
                "source_type": "custom",
                "definition_type": "rules",
                "is_active": True,
                "tags": ["tmp"],
                "metadata": {},
                "initial_version": {
                    "definition_snapshot": {
                        "timeframe": "D1",
                        "direction": "long",
                        "entry_logic": "all",
                        "conditions": [
                            {
                                "type": "indicator_threshold",
                                "indicator": "rsi",
                                "params": {"period": 14},
                                "op": "lt",
                                "value": 30,
                            }
                        ],
                        "risk": {
                            "stop_loss_pct": 2.0,
                            "take_profit_rr": 1.5,
                            "max_bars_in_trade": 5,
                        },
                    },
                    "parameter_schema": {},
                    "default_parameters": {},
                    "universe_config": {"symbols": ["AAPL"]},
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                    "notes": None,
                },
            },
        )
        assert create_res.status_code == 201
        strategy_id = create_res.json()["id"]

        delete_res = client.delete(
            f"/api/v1/strategy-lab/definitions/{strategy_id}",
            headers=auth_headers,
        )
        assert delete_res.status_code == 204

        fetch_res = client.get(
            f"/api/v1/strategy-lab/definitions/{strategy_id}",
            headers=auth_headers,
        )
        assert fetch_res.status_code == 404

    def test_update_version_persists_strategy_draft_defaults(self, client, auth_headers):
        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Save Draft",
                "description": None,
                "source_type": "custom",
                "definition_type": "rules",
                "is_active": True,
                "tags": ["draft"],
                "metadata": {},
                "initial_version": {
                    "definition_snapshot": {
                        "timeframe": "D1",
                        "direction": "long",
                        "entry_logic": "all",
                        "conditions": [],
                        "risk": {
                            "stop_loss_pct": 2.0,
                            "take_profit_rr": 1.5,
                            "max_bars_in_trade": 5,
                        },
                    },
                    "parameter_schema": {},
                    "default_parameters": {},
                    "universe_config": {"symbols": ["AAPL"]},
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                    "notes": None,
                },
            },
        )
        assert create_res.status_code == 201
        version_id = create_res.json()["versions"][0]["id"]

        update_res = client.patch(
            f"/api/v1/strategy-lab/versions/{version_id}",
            headers=auth_headers,
            json={
                "definition_snapshot": {
                    "timeframe": "D1",
                    "direction": "long",
                    "entry_logic": "all",
                    "condition_tree": {
                        "type": "all",
                        "conditions": [
                            {"type": "price_threshold", "field": "close", "op": "gt", "value": 0}
                        ],
                    },
                    "conditions": [
                        {"type": "price_threshold", "field": "close", "op": "gt", "value": 0}
                    ],
                    "risk": {
                        "stop_loss_pct": 2.0,
                        "take_profit_rr": 1.5,
                        "max_bars_in_trade": 5,
                    },
                },
                "parameter_schema": {},
                "default_parameters": {},
                "universe_config": {"symbols": ["AAPL"]},
                "benchmark_config": {"symbol": "QQQ"},
                "execution_model": {
                    "entry": "next_bar_open",
                    "run_defaults": {
                        "date_from": "2026-02-01",
                        "date_to": "2026-04-30",
                        "initial_capital": 250000,
                    },
                },
                "notes": "Saved draft defaults",
            },
        )
        assert update_res.status_code == 200
        payload = update_res.json()
        assert payload["definition_snapshot"]["conditions"]
        assert payload["benchmark_config"]["symbol"] == "QQQ"
        assert payload["execution_model"]["run_defaults"]["date_from"] == "2026-02-01"
        assert payload["execution_model"]["run_defaults"]["date_to"] == "2026-04-30"
        assert payload["execution_model"]["run_defaults"]["initial_capital"] == 250000

    def test_duplicate_definition_name_is_rejected(self, client, auth_headers):
        payload = {
            "name": "Shared Name",
            "description": None,
            "source_type": "custom",
            "definition_type": "rules",
            "is_active": True,
            "tags": [],
            "metadata": {},
            "initial_version": {
                "definition_snapshot": {},
                "parameter_schema": {},
                "default_parameters": {},
                "universe_config": {},
                "benchmark_config": {},
                "execution_model": {},
                "notes": None,
            },
        }
        assert (
            client.post(
                "/api/v1/strategy-lab/definitions", headers=auth_headers, json=payload
            ).status_code
            == 201
        )
        duplicate = client.post(
            "/api/v1/strategy-lab/definitions", headers=auth_headers, json=payload
        )
        assert duplicate.status_code == 409

    def test_strategy_lab_supports_fundamental_stats_and_performance_conditions(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        from decimal import Decimal

        from app.models.instrument import EquityDetail
        from app.models.instrument_stats import InstrumentStats

        db.add(
            EquityDetail(
                instrument_id=instrument.id,
                sector="Technology",
                industry="Consumer Electronics",
                country="US",
                exchange_mic="XNAS",
                market_cap_tier="mega",
                employees=120000,
            )
        )
        db.add(
            InstrumentStats(
                instrument_id=instrument.id,
                market_cap=Decimal("2500000000000"),
                avg_volume_30d=Decimal("80000000"),
                pe_ratio=Decimal("28"),
                beta=Decimal("1.1"),
                dividend_yield=Decimal("0.005"),
            )
        )
        db.commit()

        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Broad Filter Strategy",
                "source_type": "custom",
                "definition_type": "rules",
                "is_active": True,
                "tags": ["broad"],
                "metadata": {},
                "initial_version": {
                    "definition_snapshot": {
                        "timeframe": "D1",
                        "direction": "long",
                        "entry_logic": "all",
                        "conditions": [
                            {"type": "fundamental_filter", "field": "sector", "op": "eq", "value": "Technology"},
                            {"type": "stats_filter", "field": "market_cap", "op": "gt", "value": 1000000},
                            {"type": "performance", "period": "1M", "op": "gt", "value": -1.0},
                        ],
                        "risk": {
                            "stop_loss_pct": 2.0,
                            "take_profit_rr": 1.5,
                            "max_bars_in_trade": 8,
                        },
                    },
                    "parameter_schema": {},
                    "default_parameters": {},
                    "universe_config": {"symbols": [instrument.symbol]},
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                    "notes": "Full screener condition coverage",
                },
            },
        )
        assert create_res.status_code == 201
        definition = create_res.json()

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{definition['versions'][0]['id']}/runs",
            headers=auth_headers,
            json={
                "test_mode": "backtest",
                "timeframe": "D1",
                "date_from": ohlcv_bars[0].ts.isoformat(),
                "date_to": ohlcv_bars[-1].ts.isoformat(),
                "parameter_values": {},
                "execution_assumptions": {
                    "initial_capital": 100000,
                    "risk_per_trade_pct": 1.0,
                    "slippage_bps": 5,
                    "commission_per_trade": 1.0,
                },
            },
        )
        assert run_res.status_code == 201
        payload = run_res.json()
        assert payload["status"] == "completed"
        assert payload["result_summary"]["result_kind"] == "rules_backtest"

    def test_walk_forward_run_supports_watchlist_universe(
        self, client, auth_headers, db, instrument, instrument_b, ohlcv_bars, watchlist
    ):
        from app.models.watchlist import WatchlistItem

        db.add(WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id, position=0))
        db.add(WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument_b.id, position=1))
        db.commit()

        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Watchlist WFO",
                "source_type": "custom",
                "definition_type": "rules",
                "is_active": True,
                "tags": ["wfo"],
                "metadata": {},
                "initial_version": {
                    "definition_snapshot": {
                        "timeframe": "D1",
                        "direction": "long",
                        "entry_logic": "all",
                        "conditions": [
                            {
                                "left_source": "price",
                                "operator": "gt",
                                "right_source": "indicator",
                                "right_indicator": "sma",
                                "right_period": 5,
                            }
                        ],
                        "risk": {
                            "stop_loss_pct": 2.0,
                            "take_profit_rr": 1.5,
                            "max_bars_in_trade": 8,
                        },
                    },
                    "parameter_schema": {},
                    "default_parameters": {},
                    "universe_config": {"watchlist_id": watchlist.id},
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                    "notes": "Walk-forward watchlist test",
                },
            },
        )
        assert create_res.status_code == 201
        definition = create_res.json()
        version_id = definition["versions"][0]["id"]

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{version_id}/runs",
            headers=auth_headers,
            json={
                "test_mode": "walk_forward",
                "timeframe": "D1",
                "date_from": ohlcv_bars[0].ts.isoformat(),
                "date_to": ohlcv_bars[-1].ts.isoformat(),
                "parameter_values": {},
                "execution_assumptions": {
                    "initial_capital": 100000,
                    "risk_per_trade_pct": 1.0,
                    "slippage_bps": 5,
                    "commission_per_trade": 1.0,
                    "walk_forward_segments": 3,
                    "walk_forward_training_share": 0.6,
                    "optimization": {
                        "enabled": True,
                        "stop_loss_pct_values": [1.5, 2.0],
                        "take_profit_rr_values": [1.5, 2.0],
                        "max_bars_in_trade_values": [5, 8],
                    },
                },
            },
        )
        assert run_res.status_code == 201
        payload = run_res.json()
        assert payload["status"] == "completed"
        assert payload["result_summary"]["result_kind"] == "rules_walk_forward"
        assert payload["result_summary"]["walk_forward"]["segment_count"] == 3
        assert payload["result_summary"]["analytics"]["drawdown_curve"] is not None
        assert payload["result_summary"]["optimization"]["leaderboard"] is not None

    def test_radar_source_run_replays_historical_detections(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        from app.models.ohlcv import Timeframe
        from app.models.radar import (
            RadarDetection,
            RadarOutcomeStatus,
            RadarRun,
            RadarRunStatus,
            RadarSetupType,
            RadarState,
        )

        radar_run = RadarRun(
            timeframe=Timeframe.D1,
            universe_type="all",
            status=RadarRunStatus.COMPLETED,
            started_at=ohlcv_bars[0].ts,
            completed_at=ohlcv_bars[-1].ts,
            evaluated_count=1,
            detection_count=2,
        )
        db.add(radar_run)
        db.flush()
        entry_price = float(ohlcv_bars[3].close)
        stop_price = entry_price * 0.98
        target_price = entry_price + (entry_price - stop_price) * 2.0
        db.add(
            RadarDetection(
                run_id=radar_run.id,
                instrument_id=instrument.id,
                timeframe=Timeframe.D1,
                setup_type=RadarSetupType.BREAKOUT,
                score=0.81,
                observed_at=ohlcv_bars[3].ts,
                signal_at=ohlcv_bars[3].ts,
                context_at=ohlcv_bars[2].ts,
                state=RadarState.CONFIRMED,
                fresh_until=ohlcv_bars[-1].ts,
                entry_price=entry_price,
                invalidation_price=stop_price,
                target_price=target_price,
                outcome_status=RadarOutcomeStatus.OPEN,
                bars_since_signal=0,
                summary="Breakout signal",
                invalidation_hint="Lose breakout level",
                evidence_json={},
                score_factors={},
            )
        )
        db.commit()

        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Radar Breakout Replay",
                "source_type": "radar",
                "definition_type": "signal_source",
                "is_active": True,
                "tags": ["radar"],
                "metadata": {},
                "initial_version": {
                    "definition_snapshot": {
                        "timeframe": "D1",
                        "radar_filters": {
                            "timeframe": "D1",
                            "setup_types": ["breakout"],
                            "states": ["confirmed"],
                            "min_score": 0.7,
                        },
                        "risk": {
                            "stop_loss_pct": 2.0,
                            "take_profit_rr": 2.0,
                            "max_bars_in_trade": 10,
                        },
                    },
                    "parameter_schema": {},
                    "default_parameters": {},
                    "universe_config": {"symbols": [instrument.symbol]},
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "signal_replay"},
                    "notes": "Replay radar breakout detections",
                },
            },
        )
        assert create_res.status_code == 201
        definition = create_res.json()
        version_id = definition["versions"][0]["id"]

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{version_id}/runs",
            headers=auth_headers,
            json={
                "test_mode": "backtest",
                "timeframe": "D1",
                "date_from": ohlcv_bars[0].ts.isoformat(),
                "date_to": ohlcv_bars[-1].ts.isoformat(),
                "parameter_values": {},
                "execution_assumptions": {
                    "initial_capital": 100000,
                    "risk_per_trade_pct": 1.0,
                    "slippage_bps": 5,
                    "commission_per_trade": 1.0,
                },
            },
        )
        assert run_res.status_code == 201
        payload = run_res.json()
        assert payload["status"] == "completed"
        assert payload["result_summary"]["result_kind"] == "radar_replay"
        assert payload["result_summary"]["signal_summary"]["signal_count"] == 1
        assert payload["artifact_manifest"]["supports_execution_stats"] is True

    def test_backtest_supports_screener_latest_result_universe(
        self, client, auth_headers, db, instrument, instrument_b, ohlcv_bars, watchlist
    ):
        from app.models.ohlcv import Timeframe
        from app.models.screener import ScreenerDefinition, ScreenerResult

        screener = ScreenerDefinition(
            user_id=watchlist.user_id,
            name="Momentum Universe",
            universe_type="all",
            timeframe=Timeframe.D1,
            conditions={"operator": "AND", "conditions": []},
            is_active=True,
        )
        db.add(screener)
        db.flush()
        db.add(
            ScreenerResult(
                screener_id=screener.id,
                run_at=ohlcv_bars[-1].ts,
                matched_ids=[instrument.id, instrument_b.id],
                result_data={str(instrument.id): {"close": float(ohlcv_bars[-1].close)}},
            )
        )
        db.commit()

        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Screener Universe Strategy",
                "source_type": "custom",
                "definition_type": "rules",
                "is_active": True,
                "tags": ["screener"],
                "metadata": {},
                "initial_version": {
                    "definition_snapshot": {
                        "timeframe": "D1",
                        "direction": "long",
                        "entry_logic": "all",
                        "conditions": [
                            {
                                "left_source": "price",
                                "operator": "gt",
                                "right_source": "indicator",
                                "right_indicator": "sma",
                                "right_period": 5,
                            }
                        ],
                        "risk": {
                            "stop_loss_pct": 2.0,
                            "take_profit_rr": 1.5,
                            "max_bars_in_trade": 8,
                        },
                    },
                    "parameter_schema": {},
                    "default_parameters": {},
                    "universe_config": {"screener_id": screener.id},
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                    "notes": "Use latest screener result as the run universe",
                },
            },
        )
        assert create_res.status_code == 201
        definition = create_res.json()
        version_id = definition["versions"][0]["id"]

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{version_id}/runs",
            headers=auth_headers,
            json={
                "test_mode": "backtest",
                "timeframe": "D1",
                "date_from": ohlcv_bars[0].ts.isoformat(),
                "date_to": ohlcv_bars[-1].ts.isoformat(),
                "parameter_values": {},
                "execution_assumptions": {
                    "initial_capital": 100000,
                    "risk_per_trade_pct": 1.0,
                    "slippage_bps": 5,
                    "commission_per_trade": 1.0,
                },
            },
        )
        assert run_res.status_code == 201
        payload = run_res.json()
        assert payload["status"] == "completed"
        assert payload["result_summary"]["universe"]["requested"]["screener_id"] == screener.id
        assert payload["result_summary"]["universe"]["resolved_instrument_count"] == 2

    def test_nested_condition_tree_and_portfolio_controls_are_persisted_in_run_results(
        self, client, auth_headers, instrument, instrument_b, ohlcv_bars
    ):
        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Grouped Logic Strategy",
                "source_type": "custom",
                "definition_type": "rules",
                "is_active": True,
                "tags": ["groups"],
                "metadata": {},
                "initial_version": {
                    "definition_snapshot": {
                        "timeframe": "D1",
                        "direction": "long",
                        "entry_logic": "all",
                        "condition_tree": {
                            "type": "all",
                            "conditions": [
                                {
                                    "left_source": "indicator",
                                    "left_indicator": "ema",
                                    "left_period": 3,
                                    "operator": "gt",
                                    "right_source": "indicator",
                                    "right_indicator": "sma",
                                    "right_period": 5,
                                },
                                {
                                    "type": "not",
                                    "condition": {
                                        "left_source": "indicator",
                                        "left_indicator": "rsi",
                                        "left_period": 5,
                                        "operator": "gt",
                                        "right_source": "value",
                                        "right_value": 90,
                                    },
                                },
                            ],
                        },
                        "conditions": [
                            {
                                "left_source": "indicator",
                                "left_indicator": "ema",
                                "left_period": 3,
                                "operator": "gt",
                                "right_source": "indicator",
                                "right_indicator": "sma",
                                "right_period": 5,
                            }
                        ],
                        "risk": {
                            "stop_loss_pct": 2.0,
                            "take_profit_rr": 1.5,
                            "max_bars_in_trade": 8,
                        },
                    },
                    "parameter_schema": {},
                    "default_parameters": {},
                    "universe_config": {"symbols": [instrument.symbol, instrument_b.symbol]},
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {
                        "entry": "next_bar_open",
                        "max_concurrent_positions": 1,
                        "max_portfolio_risk_pct": 1.0,
                        "max_symbol_allocation_pct": 60.0,
                    },
                    "notes": "Grouped rule tree",
                },
            },
        )
        assert create_res.status_code == 201
        version_id = create_res.json()["versions"][0]["id"]

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{version_id}/runs",
            headers=auth_headers,
            json={
                "test_mode": "backtest",
                "timeframe": "D1",
                "date_from": ohlcv_bars[0].ts.isoformat(),
                "date_to": ohlcv_bars[-1].ts.isoformat(),
                "parameter_values": {},
                "execution_assumptions": {
                    "initial_capital": 100000,
                    "risk_per_trade_pct": 1.0,
                    "slippage_bps": 5,
                    "commission_per_trade": 1.0,
                    "max_concurrent_positions": 1,
                    "max_portfolio_risk_pct": 1.0,
                    "max_symbol_allocation_pct": 60.0,
                },
            },
        )
        assert run_res.status_code == 201
        payload = run_res.json()
        assert payload["result_summary"]["result_kind"] == "rules_backtest"
        assert payload["result_summary"]["portfolio"]["accepted_trade_count"] >= 0
        assert payload["result_summary"]["execution_assumptions"]["max_concurrent_positions"] == 1
        assert isinstance(payload["result_summary"]["position_timelines"], list)
        assert isinstance(payload["result_summary"]["execution_log"], list)
        assert isinstance(payload["result_summary"]["portfolio_timeline"], list)
        if payload["result_summary"]["trades"]:
            assert payload["result_summary"]["position_timelines"]
            first_timeline = payload["result_summary"]["position_timelines"][0]
            assert "points" in first_timeline
            assert len(first_timeline["points"]) >= 2
            assert payload["result_summary"]["execution_log"]
            assert payload["result_summary"]["portfolio_timeline"]

    def test_paper_forward_runs_can_be_refreshed_and_append_monitor_snapshots(
        self, client, auth_headers, instrument, ohlcv_bars
    ):
        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Paper Forward Monitor",
                "source_type": "custom",
                "definition_type": "rules",
                "is_active": True,
                "tags": ["paper"],
                "metadata": {},
                "initial_version": {
                    "definition_snapshot": {
                        "timeframe": "D1",
                        "direction": "long",
                        "entry_logic": "all",
                        "conditions": [
                            {
                                "left_source": "price",
                                "operator": "gt",
                                "right_source": "indicator",
                                "right_indicator": "sma",
                                "right_period": 5,
                            }
                        ],
                        "risk": {
                            "stop_loss_pct": 2.0,
                            "take_profit_rr": 1.5,
                            "max_bars_in_trade": 8,
                        },
                    },
                    "parameter_schema": {},
                    "default_parameters": {},
                    "universe_config": {"symbols": [instrument.symbol]},
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                    "notes": "Paper forward strategy",
                },
            },
        )
        assert create_res.status_code == 201
        version_id = create_res.json()["versions"][0]["id"]

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{version_id}/runs",
            headers=auth_headers,
            json={
                "test_mode": "paper_forward",
                "timeframe": "D1",
                "date_from": ohlcv_bars[0].ts.isoformat(),
                "date_to": ohlcv_bars[-1].ts.isoformat(),
                "parameter_values": {},
                "execution_assumptions": {
                    "initial_capital": 100000,
                    "risk_per_trade_pct": 1.0,
                    "slippage_bps": 5,
                    "commission_per_trade": 1.0,
                    "paper_forward_bars": 10,
                },
            },
        )
        assert run_res.status_code == 201
        run_payload = run_res.json()
        assert run_payload["result_summary"]["result_kind"] == "rules_paper_forward"
        assert len(run_payload["result_summary"]["paper_forward"]["monitor_snapshots"]) == 1

        refresh_res = client.post(
            f"/api/v1/strategy-lab/runs/{run_payload['id']}/refresh",
            headers=auth_headers,
            json={},
        )
        assert refresh_res.status_code == 200
        refreshed = refresh_res.json()
        assert refreshed["result_summary"]["result_kind"] == "rules_paper_forward"
        assert len(refreshed["result_summary"]["paper_forward"]["monitor_snapshots"]) == 2
