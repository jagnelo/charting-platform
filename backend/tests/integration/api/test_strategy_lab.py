class TestStrategyLabAPI:
    def test_research_event_artifact_promotes_with_lineage(self, client, auth_headers, db, user):
        import hashlib
        import json

        from app.models.research import CodeAsset, CodeVersion, ResearchArtifact, ResearchRun

        manifest = {
            "source": "canonical_database",
            "instrument_ids": [7],
            "timeframe": "D1",
            "as_of": "2026-01-03T00:00:00Z",
        }
        asset = CodeAsset(
            user_id=user.id,
            stable_key="event-run-promotion",
            name="Breakout Study",
            kind="study",
        )
        db.add(asset)
        db.flush()
        version = CodeVersion(
            code_asset_id=asset.id,
            version_number=1,
            source="output.events('breakout', [])",
            output_contract="events",
            parameter_schema={"lookback": {"type": "integer"}},
            default_parameters={"lookback": 20},
        )
        db.add(version)
        db.flush()
        run = ResearchRun(
            user_id=user.id,
            code_version_id=version.id,
            status="completed",
            run_config={"symbols": ["SPY"], "timeframe": "D1"},
            dataset_manifest=manifest,
            reproducibility_hash="run-hash",
        )
        run.artifacts.append(
            ResearchArtifact(
                artifact_type="events",
                name="breakout_events",
                payload={
                    "value": [
                        {
                            "symbol": "SPY",
                            "timestamp": "2026-01-02T00:00:00Z",
                            "kind": "breakout",
                            "instrument_id": 7,
                        }
                    ]
                },
            )
        )
        db.add(run)
        db.flush()

        response = client.post(
            f"/api/v1/research/runs/{run.id}/promote-event-signal",
            headers=auth_headers,
            json={"name": "Promoted event signal", "description": "Event lineage test"},
        )

        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["name"] == "Promoted event signal"
        assert payload["definition_type"] == "python"
        metadata = payload["metadata"]
        assert metadata["origin"] == "research_run_event_promotion"
        assert metadata["source_run_id"] == run.id
        assert metadata["source_code_asset_id"] == asset.id
        assert metadata["source_code_version_id"] == version.id
        assert metadata["source_artifact_name"] == "breakout_events"
        assert metadata["source_reproducibility_hash"] == "run-hash"
        assert (
            metadata["source_dataset_manifest_sha256"]
            == hashlib.sha256(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
        assert metadata["source_dataset_manifest"] == {
            "source": "canonical_database",
            "timeframe": "D1",
            "as_of": "2026-01-03T00:00:00Z",
        }
        assert metadata["source_run_config"] == {"symbols": ["SPY"], "timeframe": "D1"}
        assert metadata["semantics"] == "re_evaluate_current_data_event_source"
        assert metadata["point_in_time_source_preserved"] is False
        assert payload["versions"][0]["definition_snapshot"] == {
            "kind": "python_event_signal",
            "code_version_id": version.id,
            "output_contract": "events",
            "source_run_id": run.id,
            "source_artifact_name": "breakout_events",
            "source_dataset_manifest_sha256": metadata["source_dataset_manifest_sha256"],
            "semantics": "re_evaluate_current_data_event_source",
        }

    def test_study_code_version_can_be_reused_as_strategy_signal(self, client, auth_headers):
        asset_res = client.post(
            "/api/v1/code/assets",
            headers=auth_headers,
            json={
                "stable_key": "study-signal-reuse",
                "name": "Reusable study signal",
                "kind": "study",
                "initial_version": {
                    "source": "output.boolean('signal', True)",
                    "output_contract": "boolean",
                    "parameter_schema": {},
                    "default_parameters": {},
                },
            },
        )
        assert asset_res.status_code == 201
        version_id = asset_res.json()["versions"][0]["id"]
        promotion_res = client.post(
            f"/api/v1/strategy-lab/signals/from-code/{version_id}",
            headers=auth_headers,
            json={},
        )
        assert promotion_res.status_code == 201
        assert promotion_res.json()["metadata"]["code_version_id"] == version_id

    def test_research_event_artifact_promotes_to_scoped_python_filter(
        self, client, auth_headers, db, user
    ):
        import hashlib
        import json

        from app.models.research import CodeAsset, CodeVersion, ResearchArtifact, ResearchRun

        asset = CodeAsset(
            user_id=user.id,
            stable_key="event-filter-promotion",
            name="Breakout Study",
            kind="study",
        )
        db.add(asset)
        db.flush()
        version = CodeVersion(
            code_asset_id=asset.id,
            version_number=1,
            source="output.events('breakout', [])",
            output_contract="events",
            parameter_schema={},
            default_parameters={},
        )
        db.add(version)
        db.flush()
        run = ResearchRun(
            user_id=user.id,
            code_version_id=version.id,
            status="completed",
            run_config={"symbols": ["SPY", "XLK"], "timeframe": "D1"},
            dataset_manifest={
                "source": "canonical_database",
                "timeframe": "D1",
                "datasets": [
                    {"instrument_id": 7, "symbol": "SPY"},
                    {"instrument_id": 8, "symbol": "XLK"},
                ],
            },
            reproducibility_hash="event-filter-hash",
        )
        run.artifacts.append(
            ResearchArtifact(
                artifact_type="events",
                name="breakout_events",
                payload={
                    "value": [{"symbol": "SPY", "timestamp": "2026-01-02", "kind": "breakout"}]
                },
            )
        )
        db.add(run)
        db.flush()

        response = client.post(
            f"/api/v1/research/runs/{run.id}/promote-event-filter",
            headers=auth_headers,
            json={"name": "Breakout event filter", "description": "Scoped event adapter"},
        )

        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["name"] == "Breakout event filter"
        assert payload["universe_type"] == "custom"
        assert payload["universe_instrument_ids"] == [7, 8]
        assert payload["timeframe"] == "D1"
        assert payload["semantics"] == "event_presence_at_current_observation"
        assert payload["conditions"] == {
            "type": "python_condition",
            "code_version_id": version.id,
            "output_name": "breakout_events",
            "output_adapter": "events_to_boolean",
            "provenance": {
                "origin": "research_run_event_filter_promotion",
                "source_run_id": run.id,
                "source_code_asset_id": asset.id,
                "source_code_version_id": version.id,
                "source_artifact_id": run.artifacts[0].id,
                "source_artifact_name": "breakout_events",
                "source_output_name": "breakout_events",
                "source_reproducibility_hash": "event-filter-hash",
                "source_dataset_manifest_sha256": hashlib.sha256(
                    json.dumps(
                        {
                            "source": "canonical_database",
                            "timeframe": "D1",
                            "datasets": [
                                {"instrument_id": 7, "symbol": "SPY"},
                                {"instrument_id": 8, "symbol": "XLK"},
                            ],
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                "source_dataset_manifest": {
                    "source": "canonical_database",
                    "timeframe": "D1",
                },
                "source_run_config": {"symbols": ["SPY", "XLK"], "timeframe": "D1"},
                "output_contract": "events",
                "output_adapter": "events_to_boolean",
                "semantics": "event_presence_at_current_observation",
                "point_in_time_source_preserved": False,
            },
        }

    def test_multi_output_study_event_artifact_promotes_to_scoped_python_filter(
        self, client, auth_headers, db, user
    ):
        """A named event output from a structured Study Lab run uses the explicit adapter."""
        from app.models.research import CodeAsset, CodeVersion, ResearchArtifact, ResearchRun

        asset = CodeAsset(
            user_id=user.id,
            stable_key="structured-event-filter-promotion",
            name="Structured event study",
            kind="study",
        )
        db.add(asset)
        db.flush()
        version = CodeVersion(
            code_asset_id=asset.id,
            version_number=1,
            source=(
                "output.scalar('sample_size', 1)\n"
                "output.events('signals', [{'symbol': dataset['symbol'], 'timestamp': "
                "market.timestamps()[-1], 'kind': 'signal'}])"
            ),
            output_contract="study",
        )
        db.add(version)
        db.flush()
        run = ResearchRun(
            user_id=user.id,
            code_version_id=version.id,
            status="completed",
            run_config={"symbols": ["SPY"], "timeframe": "D1"},
            dataset_manifest={
                "source": "canonical_database",
                "timeframe": "D1",
                "datasets": [{"instrument_id": 7, "symbol": "SPY"}],
            },
            reproducibility_hash="structured-event-filter-hash",
        )
        run.artifacts.append(
            ResearchArtifact(
                artifact_type="events",
                name="signals",
                payload={
                    "value": [
                        {
                            "symbol": "SPY",
                            "timestamp": "2026-01-02",
                            "kind": "signal",
                            "instrument_id": 7,
                        }
                    ]
                },
            )
        )
        db.add(run)
        db.flush()

        response = client.post(
            f"/api/v1/research/runs/{run.id}/promote-event-filter",
            headers=auth_headers,
            json={"artifact_name": "signals", "name": "Structured event filter"},
        )

        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["universe_instrument_ids"] == [7]
        assert payload["conditions"]["code_version_id"] == version.id
        assert payload["conditions"]["output_name"] == "signals"
        assert payload["conditions"]["output_adapter"] == "events_to_boolean"
        assert payload["conditions"]["provenance"]["output_contract"] == "study"
        assert payload["conditions"]["provenance"]["source_output_name"] == "signals"

        missing_name = client.post(
            f"/api/v1/research/runs/{run.id}/promote-event-filter",
            headers=auth_headers,
            json={"name": "Missing event name"},
        )
        assert missing_name.status_code == 422
        assert (
            missing_name.json()["detail"]["code"]
            == "research_filter_promotion_artifact_name_required"
        )

    def test_multi_output_study_event_output_promotes_to_strategy_signal(
        self, client, auth_headers
    ):
        """A named event output keeps its contract and lineage through both API boundaries."""
        source = (
            "output.scalar('sample_size', 1)\n"
            'output.events(\'occurrences\', [{"symbol": "SPY", '
            '"timestamp": "2026-01-02", "kind": "signal"}])'
        )
        lineage = {
            "type": "study_run_promotion",
            "source_run_id": 37,
            "source_code_version_id": 85,
            "source_reproducibility_hash": "structured-signal-hash",
            "source_dataset_manifest": {
                "source": "canonical_database",
                "timeframe": "D1",
            },
            "source_run_config": {"symbols": ["SPY"], "timeframe": "D1"},
            "source_output_name": "occurrences",
            "target": "signal",
            "output_adapter": "events_to_signal",
            "semantics": "study_event_result_as_strategy_signal",
            "point_in_time_source_preserved": False,
        }

        asset_res = client.post(
            "/api/v1/code/assets",
            headers=auth_headers,
            json={
                "stable_key": "structured-event-strategy-signal",
                "name": "Occurrences Study Signal",
                "kind": "signal",
                "initial_version": {
                    "source": source,
                    "output_contract": "events",
                    "output_name": "occurrences",
                    "parameter_schema": {"lookback": {"type": "integer"}},
                    "default_parameters": {"lookback": 20},
                    "lineage": lineage,
                },
            },
        )
        assert asset_res.status_code == 201, asset_res.text
        version = asset_res.json()["versions"][0]
        assert version["output_contract"] == "events"
        assert version["output_name"] == "occurrences"
        assert any(
            diagnostic["code"] == "promotion_lineage" and diagnostic["lineage"] == lineage
            for diagnostic in version["diagnostics"]
        )

        promotion_res = client.post(
            f"/api/v1/strategy-lab/signals/from-code/{version['id']}",
            headers=auth_headers,
        )
        assert promotion_res.status_code == 201, promotion_res.text
        payload = promotion_res.json()
        assert payload["name"] == "Occurrences Study Signal Strategy Signal"
        assert payload["metadata"] == {
            "origin": "study_lab_promotion",
            "code_asset_id": asset_res.json()["id"],
            "code_version_id": version["id"],
            "output_contract": "events",
        }
        assert payload["versions"][0]["definition_snapshot"] == {
            "kind": "python_signal",
            "code_version_id": version["id"],
            "output_contract": "events",
        }

    def test_study_lab_signal_promotion_creates_strategy_definition_reference(
        self, client, auth_headers
    ):
        asset_res = client.post(
            "/api/v1/code/assets",
            headers=auth_headers,
            json={
                "stable_key": "study-signal-promotion",
                "name": "Positive Close Signal",
                "kind": "signal",
                "initial_version": {
                    "source": "output.boolean('signal', True)",
                    "output_contract": "boolean",
                    "parameter_schema": {},
                    "default_parameters": {},
                },
            },
        )
        assert asset_res.status_code == 201
        version_id = asset_res.json()["versions"][0]["id"]

        promotion_res = client.post(
            f"/api/v1/strategy-lab/signals/from-code/{version_id}",
            headers=auth_headers,
            json={},
        )
        assert promotion_res.status_code == 201
        payload = promotion_res.json()
        assert payload["definition_type"] == "python"
        assert payload["metadata"]["code_version_id"] == version_id
        assert payload["versions"][0]["definition_snapshot"] == {
            "kind": "python_signal",
            "code_version_id": version_id,
            "output_contract": "boolean",
        }

    def test_promoted_python_signal_run_queues_isolated_research(
        self, client, auth_headers, instrument, ohlcv_bars
    ):
        asset_res = client.post(
            "/api/v1/code/assets",
            headers=auth_headers,
            json={
                "stable_key": "study-signal-run-queue",
                "name": "Queued Positive Signal",
                "kind": "signal",
                "initial_version": {
                    "source": "output.boolean('signal', market.close()[-1] > 0)",
                    "output_contract": "boolean",
                    "parameter_schema": {},
                    "default_parameters": {},
                },
            },
        )
        assert asset_res.status_code == 201
        version_id = asset_res.json()["versions"][0]["id"]
        promotion_res = client.post(
            f"/api/v1/strategy-lab/signals/from-code/{version_id}",
            headers=auth_headers,
            json={},
        )
        assert promotion_res.status_code == 201
        strategy = promotion_res.json()
        strategy_version_id = strategy["versions"][0]["id"]

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{strategy_version_id}/runs",
            headers=auth_headers,
            json={
                "timeframe": "D1",
                "universe_config": {"symbols": [instrument.symbol]},
                "benchmark_config": {},
            },
        )
        assert run_res.status_code == 201
        run = run_res.json()
        assert run["status"] == "queued"
        assert run["result_summary"]["result_kind"] == "python_signal_research"
        assert isinstance(run["result_summary"]["research_run_id"], int)
        assert run["result_summary"]["output_contract"] == "boolean"

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

    def test_strategy_lab_can_preview_and_run_basket_universe(
        self, client, auth_headers, instrument, ohlcv_bars
    ):
        basket_res = client.post(
            "/api/v1/baskets",
            headers=auth_headers,
            json={
                "name": "Strategy basket",
                "members": [{"instrument_id": instrument.id}],
            },
        )
        assert basket_res.status_code == 200
        basket_id = basket_res.json()["id"]

        preview_res = client.post(
            "/api/v1/strategy-lab/coverage-preview",
            headers=auth_headers,
            json={
                "universe_config": {"basket_id": basket_id},
                "timeframe": "D1",
                "date_from": ohlcv_bars[0].ts.isoformat(),
                "date_to": ohlcv_bars[-1].ts.isoformat(),
            },
        )
        assert preview_res.status_code == 200
        preview = preview_res.json()
        assert preview["universe"]["preview_mode"] == "resolved"
        assert preview["universe"]["resolved_symbols"] == ["AAPL"]

        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Basket Universe Strategy",
                "source_type": "custom",
                "definition_type": "rules",
                "is_active": True,
                "tags": ["basket"],
                "metadata": {},
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
                    "universe_config": {"basket_id": basket_id},
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                    "notes": "Basket universe",
                },
            },
        )
        assert create_res.status_code == 201
        definition = create_res.json()
        assert definition["versions"][0]["universe_config"] == {"basket_id": basket_id}

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
        assert payload["result_summary"]["coverage"]["resolved_symbols"] == ["AAPL"]

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
        assert (
            "earlier local history may be missing"
            in (payload["universe"]["limiting_instruments"][0]["note"] or "").lower()
        )
        assert payload["benchmark"]["symbol"] == "SPY"
        assert payload["benchmark"]["requested_status"] == "partial"
        assert payload["benchmark"]["requested_first_bar_at"].startswith("2024-03-01")

    def test_strategy_run_can_use_etf_holdings_snapshot_universe(
        self,
        client,
        admin_headers,
        auth_headers,
        instrument,
        ohlcv_bars,
    ):
        ingest_res = client.post(
            "/api/v1/etf-holdings/SPY/ingest",
            headers=admin_headers,
            json={
                "composition_date": "2026-05-31",
                "source_provider": "issuer-test",
                "provenance": "issuer_current_holdings",
                "rows": [
                    {
                        "symbol": instrument.symbol,
                        "name": instrument.name,
                        "weight": "0.05",
                        "shares": "100",
                    }
                ],
            },
        )
        assert ingest_res.status_code == 200

        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "ETF Snapshot Strategy",
                "source_type": "custom",
                "definition_type": "rules",
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
                    "universe_config": {
                        "etf_holdings": {
                            "symbol": "SPY",
                            "snapshot_mode": "latest",
                        }
                    },
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                },
            },
        )
        assert create_res.status_code == 201
        version = create_res.json()["versions"][0]

        preview_res = client.post(
            "/api/v1/strategy-lab/coverage-preview",
            headers=auth_headers,
            json={
                "source_type": "custom",
                "timeframe": "D1",
                "date_from": ohlcv_bars[0].ts.isoformat(),
                "date_to": ohlcv_bars[-1].ts.isoformat(),
                "universe_config": version["universe_config"],
                "benchmark_config": {},
            },
        )
        assert preview_res.status_code == 200
        preview = preview_res.json()
        assert preview["universe"]["instrument_count"] == 1
        assert preview["universe"]["resolved_symbols"] == [instrument.symbol]

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{version['id']}/runs",
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
                },
            },
        )
        assert run_res.status_code == 201
        run = run_res.json()
        assert run["result_summary"]["universe"]["resolved_instrument_count"] == 1
        assert run["result_summary"]["universe"]["resolved_symbols"] == [instrument.symbol]

    def test_strategy_run_can_use_dynamic_etf_holdings_universe(
        self,
        client,
        admin_headers,
        auth_headers,
        db,
        instrument,
        instrument_b,
        ohlcv_bars,
    ):
        from decimal import Decimal

        from app.models.ohlcv import OHLCVBar, Timeframe

        for index, source_bar in enumerate(ohlcv_bars):
            close = Decimal(str(round(320 + index * 0.2, 4)))
            db.add(
                OHLCVBar(
                    instrument_id=instrument_b.id,
                    timeframe=Timeframe.D1,
                    ts=source_bar.ts,
                    open=close,
                    high=close + Decimal("1.0"),
                    low=close - Decimal("1.0"),
                    close=close,
                    volume=Decimal("5000000"),
                    is_adjusted=True,
                )
            )
        db.commit()

        first_snapshot = client.post(
            "/api/v1/etf-holdings/SPY/ingest",
            headers=admin_headers,
            json={
                "composition_date": "2024-01-01",
                "known_at": "2024-01-01T00:00:00Z",
                "source_provider": "issuer-test",
                "provenance": "issuer_self_snapshotted_holdings",
                "rows": [
                    {
                        "symbol": instrument.symbol,
                        "name": instrument.name,
                        "weight": "1.0",
                        "shares": "100",
                    }
                ],
            },
        )
        assert first_snapshot.status_code == 200
        second_snapshot = client.post(
            "/api/v1/etf-holdings/SPY/ingest",
            headers=admin_headers,
            json={
                "composition_date": "2024-03-01",
                "known_at": "2024-03-01T00:00:00Z",
                "source_provider": "issuer-test",
                "provenance": "issuer_self_snapshotted_holdings",
                "rows": [
                    {
                        "symbol": instrument_b.symbol,
                        "name": instrument_b.name,
                        "weight": "1.0",
                        "shares": "100",
                    }
                ],
            },
        )
        assert second_snapshot.status_code == 200

        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Dynamic ETF Universe Strategy",
                "source_type": "custom",
                "definition_type": "rules",
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
                            "stop_loss_pct": 10.0,
                            "take_profit_rr": 0,
                            "max_bars_in_trade": 1,
                        },
                    },
                    "universe_config": {
                        "etf_holdings": {
                            "symbol": "SPY",
                            "snapshot_mode": "dynamic",
                        }
                    },
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                },
            },
        )
        assert create_res.status_code == 201
        version = create_res.json()["versions"][0]

        preview_res = client.post(
            "/api/v1/strategy-lab/coverage-preview",
            headers=auth_headers,
            json={
                "source_type": "custom",
                "timeframe": "D1",
                "date_from": ohlcv_bars[0].ts.isoformat(),
                "date_to": ohlcv_bars[-1].ts.isoformat(),
                "universe_config": version["universe_config"],
                "benchmark_config": {},
            },
        )
        assert preview_res.status_code == 200
        assert set(preview_res.json()["universe"]["resolved_symbols"]) == {
            instrument.symbol,
            instrument_b.symbol,
        }

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{version['id']}/runs",
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
                    "slippage_bps": 0,
                    "close_open_positions_at_end": True,
                },
            },
        )
        assert run_res.status_code == 201
        summary = run_res.json()["result_summary"]
        assert set(summary["universe"]["resolved_symbols"]) == {
            instrument.symbol,
            instrument_b.symbol,
        }
        entries = [event for event in summary["execution_log"] if event["event_type"] == "entry"]
        assert {event["symbol"] for event in entries} == {instrument.symbol, instrument_b.symbol}
        assert {
            event["universe_snapshot_composition_date"]
            for event in entries
            if event["symbol"] == instrument.symbol
        } == {"2024-01-01"}
        assert {
            event["universe_snapshot_composition_date"]
            for event in entries
            if event["symbol"] == instrument_b.symbol
        } == {"2024-03-01"}
        assert all(
            event["ts"] < "2024-03-01T00:00:00+00:00"
            for event in entries
            if event["symbol"] == instrument.symbol
        )
        assert all(
            event["ts"] >= "2024-03-01T00:00:00+00:00"
            for event in entries
            if event["symbol"] == instrument_b.symbol
        )

    def test_dynamic_etf_universe_can_close_positions_on_constituent_removal(
        self,
        client,
        admin_headers,
        auth_headers,
        db,
        instrument,
        instrument_b,
        ohlcv_bars,
    ):
        from decimal import Decimal

        from app.models.ohlcv import OHLCVBar, Timeframe

        for index, source_bar in enumerate(ohlcv_bars):
            close = Decimal(str(round(320 + index * 0.2, 4)))
            db.add(
                OHLCVBar(
                    instrument_id=instrument_b.id,
                    timeframe=Timeframe.D1,
                    ts=source_bar.ts,
                    open=close,
                    high=close + Decimal("1.0"),
                    low=close - Decimal("1.0"),
                    close=close,
                    volume=Decimal("5000000"),
                    is_adjusted=True,
                )
            )
        db.commit()

        first_snapshot = client.post(
            "/api/v1/etf-holdings/SPY/ingest",
            headers=admin_headers,
            json={
                "composition_date": "2024-01-01",
                "known_at": "2024-01-01T00:00:00Z",
                "source_provider": "issuer-test",
                "provenance": "issuer_self_snapshotted_holdings",
                "rows": [
                    {
                        "symbol": instrument.symbol,
                        "name": instrument.name,
                        "weight": "1.0",
                        "shares": "100",
                    }
                ],
            },
        )
        assert first_snapshot.status_code == 200
        second_snapshot = client.post(
            "/api/v1/etf-holdings/SPY/ingest",
            headers=admin_headers,
            json={
                "composition_date": "2024-03-01",
                "known_at": "2024-03-01T00:00:00Z",
                "source_provider": "issuer-test",
                "provenance": "issuer_self_snapshotted_holdings",
                "rows": [
                    {
                        "symbol": instrument_b.symbol,
                        "name": instrument_b.name,
                        "weight": "1.0",
                        "shares": "100",
                    }
                ],
            },
        )
        assert second_snapshot.status_code == 200

        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Dynamic ETF Removal Exit Strategy",
                "source_type": "custom",
                "definition_type": "rules",
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
                            "stop_loss_pct": 50.0,
                            "take_profit_rr": 0,
                            "max_bars_in_trade": 0,
                        },
                    },
                    "universe_config": {
                        "etf_holdings": {
                            "symbol": "SPY",
                            "snapshot_mode": "dynamic",
                        }
                    },
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                },
            },
        )
        assert create_res.status_code == 201
        version = create_res.json()["versions"][0]

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{version['id']}/runs",
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
                    "slippage_bps": 0,
                    "close_open_positions_at_end": False,
                    "dynamic_universe_exit_policy": "close_on_removal",
                },
            },
        )
        assert run_res.status_code == 201
        summary = run_res.json()["result_summary"]
        removal_exits = [
            event
            for event in summary["execution_log"]
            if event["event_type"] == "exit" and event["reason"] == "constituent_removed"
        ]
        assert [event["symbol"] for event in removal_exits] == [instrument.symbol]
        assert removal_exits[0]["universe_membership_status"] == "removed"
        assert removal_exits[0]["universe_snapshot_composition_date"] == "2024-03-01"
        assert all(
            position["instrument_symbol"] != instrument.symbol
            for position in summary["open_positions"]
        )
        assert (
            summary["execution_assumptions"]["dynamic_universe_exit_policy"] == "close_on_removal"
        )
        assert summary["dynamic_universe"]["snapshot_count"] == 2

    def test_strategy_run_can_use_dynamic_etf_derived_basket_universe(
        self,
        client,
        admin_headers,
        auth_headers,
        db,
        instrument,
        instrument_b,
        ohlcv_bars,
    ):
        from decimal import Decimal

        from app.models.ohlcv import OHLCVBar, Timeframe

        for index, source_bar in enumerate(ohlcv_bars):
            close = Decimal(str(round(320 + index * 0.2, 4)))
            db.add(
                OHLCVBar(
                    instrument_id=instrument_b.id,
                    timeframe=Timeframe.D1,
                    ts=source_bar.ts,
                    open=close,
                    high=close + Decimal("1.0"),
                    low=close - Decimal("1.0"),
                    close=close,
                    volume=Decimal("5000000"),
                    is_adjusted=True,
                )
            )
        db.commit()

        first_snapshot = client.post(
            "/api/v1/etf-holdings/SPY/ingest",
            headers=admin_headers,
            json={
                "composition_date": "2024-01-01",
                "known_at": "2024-01-01T00:00:00Z",
                "source_provider": "issuer-test",
                "provenance": "issuer_self_snapshotted_holdings",
                "rows": [
                    {
                        "symbol": instrument.symbol,
                        "name": instrument.name,
                        "weight": "1.0",
                        "shares": "100",
                    }
                ],
            },
        )
        assert first_snapshot.status_code == 200
        basket_res = client.get("/api/v1/etf-holdings/SPY/basket", headers=auth_headers)
        assert basket_res.status_code == 200
        basket_id = basket_res.json()["id"]

        second_snapshot = client.post(
            "/api/v1/etf-holdings/SPY/ingest",
            headers=admin_headers,
            json={
                "composition_date": "2024-03-01",
                "known_at": "2024-03-01T00:00:00Z",
                "source_provider": "issuer-test",
                "provenance": "issuer_self_snapshotted_holdings",
                "rows": [
                    {
                        "symbol": instrument_b.symbol,
                        "name": instrument_b.name,
                        "weight": "1.0",
                        "shares": "100",
                    }
                ],
            },
        )
        assert second_snapshot.status_code == 200

        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Dynamic ETF Basket Strategy",
                "source_type": "custom",
                "definition_type": "rules",
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
                            "stop_loss_pct": 10.0,
                            "take_profit_rr": 0,
                            "max_bars_in_trade": 1,
                        },
                    },
                    "universe_config": {
                        "basket_id": basket_id,
                        "basket_snapshot_mode": "dynamic",
                    },
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                },
            },
        )
        assert create_res.status_code == 201
        version = create_res.json()["versions"][0]

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{version['id']}/runs",
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
                    "slippage_bps": 0,
                    "close_open_positions_at_end": True,
                },
            },
        )
        assert run_res.status_code == 201
        summary = run_res.json()["result_summary"]
        entries = [event for event in summary["execution_log"] if event["event_type"] == "entry"]
        assert {event["symbol"] for event in entries} == {instrument.symbol, instrument_b.symbol}
        assert {
            event["universe_snapshot_composition_date"]
            for event in entries
            if event["symbol"] == instrument_b.symbol
        } == {"2024-03-01"}
        assert summary["dynamic_universe"]["snapshot_count"] == 2

    def test_strategy_run_can_use_dynamic_manual_basket_history(
        self,
        client,
        auth_headers,
        db,
        instrument,
        instrument_b,
        ohlcv_bars,
    ):
        from datetime import UTC, datetime
        from decimal import Decimal

        from sqlalchemy import select

        from app.models.basket import BasketSnapshot
        from app.models.ohlcv import OHLCVBar, Timeframe

        for index, source_bar in enumerate(ohlcv_bars):
            close = Decimal(str(round(320 + index * 0.2, 4)))
            db.add(
                OHLCVBar(
                    instrument_id=instrument_b.id,
                    timeframe=Timeframe.D1,
                    ts=source_bar.ts,
                    open=close,
                    high=close + Decimal("1.0"),
                    low=close - Decimal("1.0"),
                    close=close,
                    volume=Decimal("5000000"),
                    is_adjusted=True,
                )
            )
        db.commit()

        created = client.post(
            "/api/v1/baskets",
            headers=auth_headers,
            json={
                "name": "Manual dynamic basket",
                "members": [{"instrument_id": instrument.id}],
            },
        )
        assert created.status_code == 200
        basket_id = created.json()["id"]

        updated = client.patch(
            f"/api/v1/baskets/{basket_id}",
            headers=auth_headers,
            json={"members": [{"instrument_id": instrument_b.id}]},
        )
        assert updated.status_code == 200
        assert updated.json()["snapshot_count"] == 2

        snapshots = list(
            db.execute(
                select(BasketSnapshot)
                .where(BasketSnapshot.basket_id == basket_id)
                .order_by(BasketSnapshot.id.asc())
            )
            .scalars()
            .all()
        )
        snapshots[0].composition_date = ohlcv_bars[0].ts.date()
        snapshots[0].known_at = datetime.combine(
            snapshots[0].composition_date, datetime.min.time(), tzinfo=UTC
        )
        snapshots[1].composition_date = ohlcv_bars[len(ohlcv_bars) // 2].ts.date()
        snapshots[1].known_at = datetime.combine(
            snapshots[1].composition_date, datetime.min.time(), tzinfo=UTC
        )
        db.commit()

        create_res = client.post(
            "/api/v1/strategy-lab/definitions",
            headers=auth_headers,
            json={
                "name": "Dynamic Manual Basket Strategy",
                "source_type": "custom",
                "definition_type": "rules",
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
                            "stop_loss_pct": 10.0,
                            "take_profit_rr": 0,
                            "max_bars_in_trade": 1,
                        },
                    },
                    "universe_config": {
                        "basket_id": basket_id,
                        "basket_snapshot_mode": "dynamic",
                    },
                    "benchmark_config": {"symbol": "SPY"},
                    "execution_model": {"entry": "next_bar_open"},
                },
            },
        )
        assert create_res.status_code == 201
        version = create_res.json()["versions"][0]

        run_res = client.post(
            f"/api/v1/strategy-lab/versions/{version['id']}/runs",
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
                    "slippage_bps": 0,
                    "close_open_positions_at_end": True,
                },
            },
        )
        assert run_res.status_code == 201
        summary = run_res.json()["result_summary"]
        entries = [event for event in summary["execution_log"] if event["event_type"] == "entry"]
        assert {event["symbol"] for event in entries} == {instrument.symbol, instrument_b.symbol}
        assert summary["dynamic_universe"]["kind"] == "basket"
        assert summary["dynamic_universe"]["basket_id"] == basket_id
        assert summary["dynamic_universe"]["snapshot_count"] == 2
        assert {event["universe_snapshot_source_type"] for event in entries} == {"manual"}

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
                            {
                                "type": "fundamental_filter",
                                "field": "sector",
                                "op": "eq",
                                "value": "Technology",
                            },
                            {
                                "type": "stats_filter",
                                "field": "market_cap",
                                "op": "gt",
                                "value": 1000000,
                            },
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
        excursion = payload["result_summary"]["analytics"]["trade_distributions"]["mae_mfe"]
        assert excursion["sample_size"] >= 0
        assert isinstance(excursion["rows"], list)
        assert isinstance(excursion["mae_histogram"], list)
        assert isinstance(excursion["mfe_histogram"], list)

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
