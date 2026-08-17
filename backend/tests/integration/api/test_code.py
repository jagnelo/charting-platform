import json


def test_code_validation_never_executes_source(client, auth_headers):
    response = client.post(
        "/api/v1/code/validate",
        headers=auth_headers,
        json={"source": "import os\nos.system('touch should-never-run')"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert payload["execution_policy"] == "validation_only_isolated_runner_required"
    assert {item["code"] for item in payload["diagnostics"]} >= {
        "forbidden_syntax",
        "unapproved_namespace",
    }


def test_code_validation_reports_generated_condition_lookback(client, auth_headers):
    response = client.post(
        "/api/v1/code/validate",
        headers=auth_headers,
        json={
            "source": (
                "series = ta.indicator('rsi', {'period': 14}, None)\n"
                "change = market.percent_change(63)\n"
                "output.boolean('match', bool(series and change is not None))"
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["lookback_hint"] == 63


def test_code_assets_are_immutable_versions(client, auth_headers):
    created = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "positive-close-streak",
            "name": "Positive close streak",
            "kind": "study",
            "initial_version": {
                "source": "series = ta.sma(market.close('SPY'), 20)\noutput.series('trend', series)",
                "output_contract": "study",
            },
        },
    )
    assert created.status_code == 201
    asset = created.json()
    assert asset["versions"][0]["version_number"] == 1
    assert asset["versions"][0]["dependencies"] == ["market", "output", "ta"]
    next_version = client.post(
        f"/api/v1/code/assets/{asset['id']}/versions",
        headers=auth_headers,
        json={"source": "output.scalar('n', 1)", "output_contract": "scalar"},
    )
    assert next_version.status_code == 201
    assert next_version.json()["version_number"] == 2


def test_market_map_breadth_definition_preserves_condition_and_source_defaults(client, auth_headers):
    source = (
        "condition = parameters.get('condition', {'kind': 'within_52_week_high', "
        "'params': {'threshold_percent': 1.0}})\n"
        "snapshot = research.breadth_condition(dataset, condition)\n"
        "history = research.breadth_condition(dataset, condition, True)\n"
        "output.scalar('current_percentage', snapshot['percentage'])\n"
        "output.series('percentage_history', [point['percentage'] for point in history['points']])\n"
        "output.table('breadth_members', snapshot['rows'])"
    )
    created = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "market-map-spy-within-highs",
            "name": "SPY within one percent of highs",
            "kind": "study",
            "initial_version": {
                "source": source,
                "output_contract": "study",
                "parameter_schema": {
                    "properties": {
                        "condition": {"type": "object"},
                        "source_id": {"type": "string"},
                    },
                    "required": ["condition", "source_id"],
                },
                "default_parameters": {
                    "condition": {
                        "kind": "within_52_week_high",
                        "params": {"threshold_percent": 1.0},
                    },
                    "source_id": "market-group:sp500",
                    "period": "1D",
                    "timeframe": "D1",
                    "adjustment": "split_adjusted",
                },
            },
        },
    )
    assert created.status_code == 201, created.text
    version = created.json()["versions"][0]
    assert version["output_contract"] == "study"
    assert version["source"] == source
    assert version["default_parameters"]["source_id"] == "market-group:sp500"
    assert version["default_parameters"]["condition"]["kind"] == "within_52_week_high"


def test_code_assets_support_archive_clone_and_round_trip_import(client, auth_headers):
    created = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "exportable-study",
            "name": "Exportable study",
            "kind": "study",
            "initial_version": {"source": "output.scalar('n', 1)", "output_contract": "study"},
        },
    )
    assert created.status_code == 201
    asset = created.json()
    archived = client.post(
        f"/api/v1/code/assets/{asset['id']}/archive",
        headers=auth_headers,
        json={"is_archived": True},
    )
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True
    cloned = client.post(
        f"/api/v1/code/assets/{asset['id']}/clone",
        headers=auth_headers,
        json={"stable_key": "cloned-study", "name": "Cloned study"},
    )
    assert cloned.status_code == 201
    assert cloned.json()["id"] != asset["id"]
    assert cloned.json()["versions"][0]["source"] == asset["versions"][0]["source"]
    imported = client.post(
        "/api/v1/code/assets/import",
        headers=auth_headers,
        json={
            "stable_key": "imported-study",
            "name": "Imported study",
            "kind": "study",
            "versions": [
                {"source": "output.scalar('n', 2)", "output_contract": "study"},
                {"source": "output.scalar('n', 3)", "output_contract": "study"},
            ],
        },
    )
    assert imported.status_code == 201
    assert [version["version_number"] for version in imported.json()["versions"]] == [1, 2]


def test_code_asset_kind_and_declared_output_contract_must_match(client, auth_headers):
    wrong_kind = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "bad-column-contract",
            "name": "Bad column contract",
            "kind": "column",
            "initial_version": {
                "source": "output.series('trend', [1])",
                "output_contract": "series",
            },
        },
    )
    assert wrong_kind.status_code == 422
    assert wrong_kind.json()["detail"]["code"] == "asset_output_contract_mismatch"

    wrong_source = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "bad-source-contract",
            "name": "Bad source contract",
            "kind": "column",
            "initial_version": {
                "source": "output.series('trend', [1])",
                "output_contract": "scalar",
            },
        },
    )
    assert wrong_source.status_code == 422
    assert wrong_source.json()["detail"] == {
        "code": "declared_output_contract_mismatch",
        "declared": "scalar",
        "observed": ["series"],
    }

    valid_condition = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "qualified-condition",
            "name": "Qualified condition",
            "kind": "condition",
            "initial_version": {
                "source": "output.boolean('qualifies', 2 > 1)",
                "output_contract": "boolean",
            },
        },
    )
    assert valid_condition.status_code == 201

    selected = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "selected-study-series",
            "name": "Selected study series",
            "kind": "plot",
            "initial_version": {
                "source": "output.scalar('sample', 1)\noutput.series('trend', [1, 2])",
                "output_contract": "series",
                "output_name": "trend",
            },
        },
    )
    assert selected.status_code == 201
    assert selected.json()["versions"][0]["output_name"] == "trend"

    invalid_selected = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "selected-study-invalid",
            "name": "Selected study invalid",
            "kind": "plot",
            "initial_version": {
                "source": "output.scalar('sample', 1)",
                "output_contract": "series",
                "output_name": "trend",
            },
        },
    )
    assert invalid_selected.status_code == 422
    assert invalid_selected.json()["detail"]["code"] == "selected_output_contract_mismatch"


def test_code_asset_rejects_defaults_that_violate_its_parameter_schema(client, auth_headers):
    response = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "invalid-default-study",
            "name": "Invalid defaults",
            "kind": "study",
            "initial_version": {
                "source": "output.scalar('lookback', parameters['lookback'])",
                "output_contract": "study",
                "parameter_schema": {"properties": {"lookback": {"type": "integer", "minimum": 1}}},
                "default_parameters": {"lookback": 0},
            },
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "parameter_validation_failed"


def test_research_run_is_queued_for_isolated_runner(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "sample-study",
            "name": "Sample",
            "kind": "study",
            "initial_version": {"source": "output.scalar('n', 1)", "output_contract": "study"},
        },
    ).json()
    response = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "dataset_manifest": {"snapshot": "fixture"},
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert (tmp_path / "jobs" / f"{response.json()['id']}.json").exists()
    canceled = client.post(
        f"/api/v1/research/runs/{response.json()['id']}/cancel", headers=auth_headers
    )
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"


def test_research_run_job_preserves_json_parameters_for_isolated_runner(
    client, auth_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "parameter-study",
            "name": "Parameter study",
            "kind": "study",
            "initial_version": {
                "source": "output.scalar('threshold', parameters['threshold'])",
                "output_contract": "study",
            },
        },
    ).json()
    run = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {"parameters": {"threshold": 42}},
        },
    )
    assert run.status_code == 202
    job = json.loads((tmp_path / "jobs" / f"{run.json()['id']}.json").read_text())
    assert job["parameters"] == {"threshold": 42}


def test_research_run_merges_defaults_and_rejects_schema_invalid_parameters(
    client, auth_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "schema-study",
            "name": "Schema study",
            "kind": "study",
            "initial_version": {
                "source": "output.scalar('lookback', parameters['lookback'])",
                "output_contract": "study",
                "parameter_schema": {
                    "properties": {"lookback": {"type": "integer", "minimum": 1}},
                    "additionalProperties": False,
                },
                "default_parameters": {"lookback": 20},
            },
        },
    ).json()
    valid = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={"code_version_id": asset["versions"][0]["id"], "run_config": {}},
    )
    assert valid.status_code == 202
    assert valid.json()["run_config"]["parameters"] == {"lookback": 20}
    invalid = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {"parameters": {"lookback": 0}},
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "parameter_validation_failed"


def test_research_runs_list_is_user_scoped_and_newest_first(
    client, auth_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "list-study",
            "name": "List",
            "kind": "study",
            "initial_version": {"source": "output.scalar('n', 1)", "output_contract": "study"},
        },
    ).json()
    first = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={"code_version_id": asset["versions"][0]["id"]},
    ).json()
    second = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={"code_version_id": asset["versions"][0]["id"]},
    ).json()

    listed = client.get("/api/v1/research/runs?limit=1", headers=auth_headers)

    assert listed.status_code == 200
    assert [run["id"] for run in listed.json()] == [second["id"]]
    assert listed.json()[0]["artifact_count"] == 0
    assert listed.json()[0]["artifacts"] == []
    assert second["id"] > first["id"]

    detailed = client.get(
        "/api/v1/research/runs?limit=1&include_artifacts=true", headers=auth_headers
    )
    assert detailed.status_code == 200
    assert detailed.json()[0]["id"] == second["id"]
    assert detailed.json()[0]["artifacts"] == []


def test_research_rerun_snapshot_retains_manifest(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "rerun-study",
            "name": "Rerun",
            "kind": "study",
            "initial_version": {"source": "output.scalar('n', 1)", "output_contract": "study"},
        },
    ).json()
    original = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "dataset_manifest": {"snapshot": "frozen", "closes": [1]},
        },
    ).json()

    rerun = client.post(
        f"/api/v1/research/runs/{original['id']}/rerun?snapshot=true", headers=auth_headers
    )

    assert rerun.status_code == 202
    assert rerun.json()["id"] != original["id"]
    assert rerun.json()["code_version_id"] == original["code_version_id"]
    assert rerun.json()["dataset_manifest"] == original["dataset_manifest"]


def test_research_result_is_collected_as_structured_artifact(
    client, auth_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "artifact-study",
            "name": "Artifact",
            "kind": "study",
            "initial_version": {"source": "output.scalar('n', 1)", "output_contract": "study"},
        },
    ).json()
    run = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={"code_version_id": asset["versions"][0]["id"]},
    ).json()
    results = tmp_path / "results"
    results.mkdir()
    (results / f"{run['id']}.json").write_text(
        '{"status":"completed","artifacts":{"n":{"type":"scalar","value":1}},"reproducibility_hash":"abc"}'
    )
    collected = client.get(f"/api/v1/research/runs/{run['id']}", headers=auth_headers)
    assert collected.status_code == 200
    assert collected.json()["status"] == "completed"
    assert collected.json()["reproducibility_hash"] == "abc"


def test_research_run_materializes_only_declared_local_symbol_data(
    client, auth_headers, tmp_path, monkeypatch, instrument, ohlcv_bars
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "streak-study",
            "name": "Streak study",
            "kind": "study",
            "initial_version": {
                "source": "streaks = stats.positive_close_streaks(dataset)\noutput.scalar('current', streaks['current'])",
                "output_contract": "study",
            },
        },
    ).json()
    run = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {"symbol": instrument.symbol},
        },
    )
    assert run.status_code == 202
    payload = run.json()
    assert payload["dataset_manifest"]["symbol"] == instrument.symbol
    assert payload["dataset_manifest"]["metadata"]["instrument_id"] == instrument.id
    assert len(payload["dataset_manifest"]["sessions"]) == len(ohlcv_bars)
    assert len(payload["dataset_manifest"]["closes"]) == len(ohlcv_bars)
    assert len(payload["dataset_manifest"]["opens"]) == len(ohlcv_bars)
    assert len(payload["dataset_manifest"]["highs"]) == len(ohlcv_bars)
    assert len(payload["dataset_manifest"]["lows"]) == len(ohlcv_bars)
    assert len(payload["dataset_manifest"]["volumes"]) == len(ohlcv_bars)
    assert payload["dataset_manifest"]["adjustment"] == "split_adjusted"


def test_research_run_materializes_structured_study_universe_with_exclusions(
    client, auth_headers, tmp_path, monkeypatch, instrument, ohlcv_bars
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "universe-study",
            "name": "Universe study",
            "kind": "study",
            "initial_version": {
                "source": "output.table('symbols', [{'symbol': item['symbol']} for item in market.universe()])",
                "output_contract": "study",
            },
        },
    ).json()
    response = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {"symbols": [instrument.symbol, "NOT_A_CANONICAL_SYMBOL"]},
        },
    )
    assert response.status_code == 202
    manifest = response.json()["dataset_manifest"]
    assert manifest["requested_symbols"] == [instrument.symbol, "NOT_A_CANONICAL_SYMBOL"]
    assert [item["symbol"] for item in manifest["datasets"]] == [instrument.symbol]
    assert manifest["exclusions"] == [
        {"symbol": "NOT_A_CANONICAL_SYMBOL", "code": "declared_instrument_not_found"}
    ]


def test_research_run_materializes_a_canonical_watchlist_source(
    client, auth_headers, tmp_path, monkeypatch, instrument, ohlcv_bars
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    created = client.post(
        "/api/v1/watchlists",
        headers=auth_headers,
        json={"name": "Study source watchlist"},
    )
    assert created.status_code == 200
    watchlist_id = created.json()["id"]
    added = client.post(
        f"/api/v1/watchlists/{watchlist_id}/items",
        headers=auth_headers,
        json={"instrument_id": instrument.id},
    )
    assert added.status_code == 200
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "watchlist-source-study",
            "name": "Watchlist source study",
            "kind": "study",
            "initial_version": {
                "source": "output.scalar('member_count', len(market.universe()))",
                "output_contract": "study",
            },
        },
    ).json()

    response = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {"universe_source_id": f"watchlist:{watchlist_id}"},
        },
    )

    assert response.status_code == 202
    manifest = response.json()["dataset_manifest"]
    assert manifest["universe_source_id"] == f"watchlist:{watchlist_id}"
    assert manifest["universe_source"]["watchlist_id"] == watchlist_id
    assert manifest["universe_source"]["source_kind"] == "personal"
    assert manifest["requested_symbols"] == [instrument.symbol]
    assert [item["symbol"] for item in manifest["datasets"]] == [instrument.symbol]


def test_research_run_honors_study_dataset_controls_and_records_them(
    client, auth_headers, db, tmp_path, monkeypatch, instrument, ohlcv_bars
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "controlled-study",
            "name": "Controlled study",
            "kind": "study",
            "initial_version": {
                "source": "output.scalar('current', 1)",
                "output_contract": "study",
            },
        },
    ).json()
    response = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {
                "symbol": instrument.symbol,
                "timeframe": "D1",
                "adjustment": "split_adjusted",
                "session": "regular",
                "benchmark": "SPY",
                "start_date": "2024-02-01",
                "end_date": "2024-02-05",
            },
        },
    )
    assert response.status_code == 202
    manifest = response.json()["dataset_manifest"]
    assert manifest["timeframe"] == "D1"
    assert manifest["adjustment"] == "split_adjusted"
    assert manifest["session"] == "regular"
    assert manifest["benchmark"] == "SPY"
    assert manifest["start_date"] == "2024-02-01"
    assert manifest["end_date"] == "2024-02-05"
    assert len(manifest["timestamps"]) == 5
    assert manifest["timestamps"][0].startswith("2024-02-01")
    assert manifest["timestamps"][-1].startswith("2024-02-05")
    assert manifest["benchmark_coverage"] == {
        "status": "unavailable",
        "symbol": "SPY",
        "reason": "benchmark_instrument_not_found",
    }

    ready_response = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {
                "symbol": instrument.symbol,
                "benchmark": instrument.symbol,
                "start_date": "2024-02-01",
                "end_date": "2024-02-05",
            },
        },
    )
    assert ready_response.status_code == 202
    ready_manifest = ready_response.json()["dataset_manifest"]
    assert ready_manifest["benchmark_coverage"]["status"] == "ready"
    assert ready_manifest["benchmark_dataset"]["symbol"] == instrument.symbol
    assert len(ready_manifest["benchmark_dataset"]["timestamps"]) == 5

    from datetime import timedelta

    from app.models.ohlcv import OHLCVBar

    pre_market = OHLCVBar(
        instrument_id=instrument.id,
        timeframe=ohlcv_bars[-1].timeframe,
        ts=ohlcv_bars[-1].ts + timedelta(days=1),
        open=ohlcv_bars[-1].open,
        high=ohlcv_bars[-1].high,
        low=ohlcv_bars[-1].low,
        close=ohlcv_bars[-1].close,
        volume=ohlcv_bars[-1].volume,
        is_adjusted=True,
        session="pre_market",
    )
    db.add(pre_market)
    db.flush()
    session_range = {
        "symbol": instrument.symbol,
        "start_date": ohlcv_bars[-1].ts.date().isoformat(),
        "end_date": pre_market.ts.date().isoformat(),
    }
    regular_response = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {**session_range, "session": "regular"},
        },
    )
    all_response = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {**session_range, "session": "all"},
        },
    )
    assert regular_response.status_code == 202
    assert all_response.status_code == 202
    assert len(regular_response.json()["dataset_manifest"]["timestamps"]) == 1
    assert len(all_response.json()["dataset_manifest"]["timestamps"]) == 2


def test_research_run_rejects_unsupported_study_dataset_controls(client, auth_headers, instrument):
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "invalid-study-controls",
            "name": "Invalid study controls",
            "kind": "study",
            "initial_version": {
                "source": "output.scalar('current', 1)",
                "output_contract": "study",
            },
        },
    ).json()
    response = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {
                "symbol": instrument.symbol,
                "timeframe": "D1",
                "adjustment": "total_return",
            },
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_dataset_adjustment"


def test_column_batch_run_materializes_declared_universe_and_returns_typed_cells(
    client, auth_headers, tmp_path, monkeypatch, instrument, ohlcv_bars
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "batch-last-close",
            "name": "Batch last close",
            "kind": "column",
            "initial_version": {
                "source": "output.scalar('last_close', market.close()[-1])",
                "output_contract": "scalar",
            },
        },
    ).json()
    run = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {"symbols": [instrument.symbol, "MISSING"]},
        },
    )
    assert run.status_code == 202
    payload = run.json()
    assert [item["symbol"] for item in payload["dataset_manifest"]["datasets"]] == [
        instrument.symbol
    ]
    assert payload["dataset_manifest"]["exclusions"] == [
        {"symbol": "MISSING", "code": "declared_instrument_not_found"}
    ]

    result_dir = tmp_path / "results"
    result_dir.mkdir()
    (result_dir / f"{payload['id']}.json").write_text(
        '{"status":"completed","artifacts":{"batch_cells":{"type":"batch","value":{"cells":[{"instrument_id":%d,"symbol":"%s","status":"completed","value":12.5}]}}}}'
        % (instrument.id, instrument.symbol)
    )
    cells = client.get(f"/api/v1/research/runs/{payload['id']}/batch-results", headers=auth_headers)
    assert cells.status_code == 200
    assert cells.json()["output_contract"] == "scalar"
    assert cells.json()["cells"] == [
        {
            "instrument_id": instrument.id,
            "symbol": instrument.symbol,
            "status": "completed",
            "value": 12.5,
            "error": None,
        }
    ]


def test_prepared_universe_batch_accepts_workstation_scale_and_rejects_only_above_ten_thousand(
    client, auth_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "large-batch-column",
            "name": "Large batch column",
            "kind": "column",
            "initial_version": {
                "source": "output.scalar('constant', 1)",
                "output_contract": "scalar",
            },
        },
    ).json()
    accepted = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {"symbols": [f"TEST{i:04d}" for i in range(1001)]},
        },
    )
    assert accepted.status_code == 202
    assert accepted.json()["dataset_manifest"]["batch_history_limit"] == 500
    assert len(accepted.json()["dataset_manifest"]["exclusions"]) == 1001

    rejected = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {"symbols": [f"OVER{i:05d}" for i in range(25001)]},
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == {"code": "batch_universe_too_large", "maximum": 25000}


def test_research_materialization_expands_batch_history_for_code_lookback(
    client, auth_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "lookback-aware-batch-column",
            "name": "Lookback-aware batch column",
            "kind": "column",
            "initial_version": {
                "source": "series = ta.sma(market.close(), 600)\noutput.scalar('value', series[-1])",
                "output_contract": "scalar",
            },
        },
    ).json()
    response = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {"symbols": ["MISSING"]},
        },
    )
    assert response.status_code == 202
    assert response.json()["dataset_manifest"]["batch_history_limit"] == 601


def test_research_materialization_rejects_unbounded_code_lookback(
    client, auth_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "unbounded-lookback-column",
            "name": "Unbounded lookback column",
            "kind": "column",
            "initial_version": {
                "source": "series = ta.sma(market.close(), 5000)\noutput.scalar('value', series[-1])",
                "output_contract": "scalar",
            },
        },
    ).json()
    response = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {"symbols": ["MISSING"]},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "code_lookback_exceeds_dataset_limit",
        "lookback": 5000,
        "maximum": 4999,
    }


def test_batch_results_expose_runner_owned_durable_progress(
    client, auth_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
    )
    monkeypatch.setattr(
        "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
    )
    asset = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "progress-column",
            "name": "Progress column",
            "kind": "column",
            "initial_version": {
                "source": "output.scalar('constant', 1)",
                "output_contract": "scalar",
            },
        },
    ).json()
    run = client.post(
        "/api/v1/research/runs",
        headers=auth_headers,
        json={
            "code_version_id": asset["versions"][0]["id"],
            "run_config": {"symbols": ["MISSING"]},
        },
    ).json()
    result_dir = tmp_path / "results"
    result_dir.mkdir()
    (result_dir / f"{run['id']}.progress.json").write_text(
        '{"completed_cells":150,"total_cells":1000,"status":"running"}'
    )
    response = client.get(f"/api/v1/research/runs/{run['id']}/batch-results", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["progress"] == {
        "completed_cells": 150,
        "total_cells": 1000,
        "status": "running",
    }
