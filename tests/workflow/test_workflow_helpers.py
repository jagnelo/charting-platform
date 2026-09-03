"""Focused behavioral checks for the branch-session helpers."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[2]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_environment_exposes_path_scoped_session_state(monkeypatch):
    runtime = load("runtime", "scripts/worktree-runtime.py")
    monkeypatch.setattr(runtime, "common_root", lambda: Path("/repo"))
    allocation = {
        "worktree": "/repo/.ai/worktrees/feat-demo",
        "id": "feat-demo-123",
        "branch": "feat/demo",
        "slug": "feat-demo",
        "projects": {"dev": "dev", "stack": "stack"},
        "builder": "builder",
        "ports": {key: 10000 + index for index, key in enumerate(runtime.PORT_KEYS)},
    }
    env = runtime.environment(allocation)
    assert env["WORKTREE_RUNTIME_STATE"] == "/repo/.ai/runtime/feat-demo-123"
    assert env["WORKTREE_BUILDER"] == "builder"


def test_docker_status_accounts_unique_images_volumes_and_builder(monkeypatch):
    session = load("agent_session", "scripts/agent-session.py")
    monkeypatch.setattr(session.shutil, "which", lambda command: "/usr/bin/docker")

    def fake_run(*args, **kwargs):
        if args[:2] == ("docker", "info"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:3] == ("docker", "ps", "-aq"):
            return SimpleNamespace(returncode=0, stdout="container-id\n", stderr="")
        if args[:2] == ("docker", "inspect"):
            payload = {
                "Id": "container-id",
                "Name": "/owned",
                "SizeRw": 100,
                "Config": {"Labels": {"charting.worktree.id": "feat-demo-123"}},
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        if args[:3] == ("docker", "image", "inspect"):
            payload = {"Config": {"Labels": {"charting.worktree.id": "feat-demo-123"}}}
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        if args[:2] == ("docker", "volume"):
            return SimpleNamespace(returncode=0, stdout="owned-volume\n", stderr="")
        if args[:3] == ("docker", "buildx", "du"):
            return SimpleNamespace(returncode=0, stdout="Total: 3GB\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(session, "run", fake_run)
    monkeypatch.setattr(
        session,
        "docker_json",
        lambda *args: [{"ID": "image-id", "Labels": "feat-demo-123"}],
    )
    monkeypatch.setattr(
        session,
        "docker_system_df",
        lambda: {
            "Images": [{"ID": "image-id", "UniqueSize": 200}],
            "Volumes": [{"Name": "owned-volume", "Size": 300}],
        },
    )
    monkeypatch.setattr(
        session, "builder_name_from_projects", lambda projects: "builder"
    )
    result = session.docker_status("feat-demo-123", {"dev"})
    assert result["unique_image_bytes"] == 200
    assert result["volume_bytes"] == 300
    assert result["build_cache_bytes"] == 3_000_000_000
    assert result["known_bytes"] == 3_000_000_600


def test_exact_ci_does_not_treat_missing_run_as_green(monkeypatch):
    queue = load("integration_queue", "scripts/integration_queue.py")
    monkeypatch.setattr(queue.shutil, "which", lambda command: "/usr/bin/gh")
    monkeypatch.setattr(
        queue.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="[]", stderr=""),
    )
    state, reason = queue.exact_ci("feat/demo", "a" * 40)
    assert state == "missing"
    assert "no exact" in reason


def test_goal_budget_requires_exact_human_authorization():
    session = load("agent_session_budget", "scripts/agent-session.py")
    assert (
        session.authorized_goal_budget({"human_goal_budget_authorization": "none"})
        is None
    )
    assert (
        session.authorized_goal_budget(
            {"human_goal_budget_authorization": "authorized: 1234"}
        )
        == 1234
    )
    assert (
        session.authorized_goal_budget({"human_goal_budget_authorization": "1234"})
        is None
    )
