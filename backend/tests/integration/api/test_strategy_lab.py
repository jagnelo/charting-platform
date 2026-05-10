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
                    "engine_type": "platform",
                    "definition_snapshot": {"timeframe": "D1", "logic": "close > sma20"},
                    "parameter_schema": {"lookback": {"type": "integer", "default": 20}},
                    "default_parameters": {"lookback": 20},
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
        assert created["versions"][0]["engine_type"] == "platform"

        list_res = client.get("/api/v1/strategy-lab/definitions", headers=auth_headers)
        assert list_res.status_code == 200
        assert any(item["id"] == created["id"] for item in list_res.json())

        version_res = client.post(
            f"/api/v1/strategy-lab/definitions/{created['id']}/versions",
            headers=auth_headers,
            json={
                "engine_type": "platform",
                "definition_snapshot": {"timeframe": "D1", "logic": "close > ema50"},
                "parameter_schema": {"ema_period": {"type": "integer", "default": 50}},
                "default_parameters": {"ema_period": 50},
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
                "parameter_values": {"ema_period": 50},
                "universe_config": {"symbols": ["AAPL"]},
                "execution_assumptions": {"slippage_bps": 5},
            },
        )
        assert run_res.status_code == 201
        run_payload = run_res.json()
        assert run_payload["run"]["status"] == "completed"
        assert run_payload["run"]["engine_type"] == "platform"
        assert run_payload["run"]["result_summary"]["coverage"]["instrument_count"] == 1
        assert run_payload["run"]["result_summary"]["coverage"]["total_bars"] >= 1
        assert run_payload["run"]["result_summary"]["readiness"]["has_coverage"] is True
        assert run_payload["engine"]["is_available"] is True

        detail_res = client.get(
            f"/api/v1/strategy-lab/definitions/{created['id']}",
            headers=auth_headers,
        )
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["runs"]
        assert detail["runs"][0]["id"] == run_payload["run"]["id"]

        runs_res = client.get("/api/v1/strategy-lab/runs", headers=auth_headers)
        assert runs_res.status_code == 200
        assert any(item["id"] == run_payload["run"]["id"] for item in runs_res.json())

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
                "engine_type": "platform",
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
