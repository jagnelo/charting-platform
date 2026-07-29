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
    assert {item["code"] for item in payload["diagnostics"]} >= {"forbidden_syntax", "unapproved_namespace"}


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


def test_research_run_is_queued_for_isolated_runner(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setattr("app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results"))
    asset = client.post(
        "/api/v1/code/assets", headers=auth_headers,
        json={"stable_key": "sample-study", "name": "Sample", "kind": "study", "initial_version": {"source": "output.scalar('n', 1)", "output_contract": "study"}},
    ).json()
    response = client.post(
        "/api/v1/research/runs", headers=auth_headers,
        json={"code_version_id": asset["versions"][0]["id"], "dataset_manifest": {"snapshot": "fixture"}},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert (tmp_path / "jobs" / f"{response.json()['id']}.json").exists()
    canceled = client.post(f"/api/v1/research/runs/{response.json()['id']}/cancel", headers=auth_headers)
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"


def test_research_result_is_collected_as_structured_artifact(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setattr("app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results"))
    asset = client.post("/api/v1/code/assets", headers=auth_headers, json={"stable_key": "artifact-study", "name": "Artifact", "kind": "study", "initial_version": {"source": "output.scalar('n', 1)", "output_contract": "study"}}).json()
    run = client.post("/api/v1/research/runs", headers=auth_headers, json={"code_version_id": asset["versions"][0]["id"]}).json()
    results = tmp_path / "results"
    results.mkdir()
    (results / f"{run['id']}.json").write_text('{"status":"completed","artifacts":{"n":{"type":"scalar","value":1}},"reproducibility_hash":"abc"}')
    collected = client.get(f"/api/v1/research/runs/{run['id']}", headers=auth_headers)
    assert collected.status_code == 200
    assert collected.json()["status"] == "completed"
    assert collected.json()["reproducibility_hash"] == "abc"
