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


def test_code_asset_kind_and_declared_output_contract_must_match(client, auth_headers):
    wrong_kind = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "bad-column-contract",
            "name": "Bad column contract",
            "kind": "column",
            "initial_version": {"source": "output.series('trend', [1])", "output_contract": "series"},
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
            "initial_version": {"source": "output.series('trend', [1])", "output_contract": "scalar"},
        },
    )
    assert wrong_source.status_code == 422
    assert wrong_source.json()["detail"] == {
        "code": "declared_output_contract_mismatch", "declared": "scalar", "observed": ["series"],
    }

    valid_condition = client.post(
        "/api/v1/code/assets",
        headers=auth_headers,
        json={
            "stable_key": "qualified-condition",
            "name": "Qualified condition",
            "kind": "condition",
            "initial_version": {"source": "output.boolean('qualifies', 2 > 1)", "output_contract": "boolean"},
        },
    )
    assert valid_condition.status_code == 201


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
    assert second["id"] > first["id"]


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
    assert len(payload["dataset_manifest"]["closes"]) == len(ohlcv_bars)
    assert payload["dataset_manifest"]["adjustment"] == "split_adjusted"


def test_column_batch_run_materializes_declared_universe_and_returns_typed_cells(
    client, auth_headers, tmp_path, monkeypatch, instrument, ohlcv_bars
):
    monkeypatch.setattr("app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setattr("app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results"))
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
        json={"code_version_id": asset["versions"][0]["id"], "run_config": {"symbols": [instrument.symbol, "MISSING"]}},
    )
    assert run.status_code == 202
    payload = run.json()
    assert [item["symbol"] for item in payload["dataset_manifest"]["datasets"]] == [instrument.symbol]
    assert payload["dataset_manifest"]["exclusions"] == [{"symbol": "MISSING", "code": "declared_instrument_not_found"}]

    result_dir = tmp_path / "results"
    result_dir.mkdir()
    (result_dir / f"{payload['id']}.json").write_text(
        '{"status":"completed","artifacts":{"batch_cells":{"type":"batch","value":{"cells":[{"instrument_id":%d,"symbol":"%s","status":"completed","value":12.5}]}}}}'
        % (instrument.id, instrument.symbol)
    )
    cells = client.get(f"/api/v1/research/runs/{payload['id']}/batch-results", headers=auth_headers)
    assert cells.status_code == 200
    assert cells.json()["output_contract"] == "scalar"
    assert cells.json()["cells"] == [{"instrument_id": instrument.id, "symbol": instrument.symbol, "status": "completed", "value": 12.5, "error": None}]
