import importlib.util
from pathlib import Path


def _load_runtime():
    path = Path(__file__).parents[3] / "scripts" / "worktree-runtime.py"
    spec = importlib.util.spec_from_file_location("worktree_runtime", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_environment_is_path_scoped_and_explicit():
    runtime = _load_runtime()
    allocation = {
        "worktree": "/tmp/a",
        "branch": "feat/a",
        "id": "feat-a-abc",
        "slug": "feat-a",
        "projects": {"dev": "charting-dev-feat-a-x", "stack": "charting-stack-feat-a-x"},
        "ports": {
            "DEV_POSTGRES_HOST_PORT": 15432,
            "DEV_REDIS_HOST_PORT": 16379,
            "DEV_BACKEND_PORT": 18000,
            "VITE_PORT": 19000,
            "POSTGRES_HOST_PORT": 25432,
            "REDIS_HOST_PORT": 26379,
            "BACKEND_HOST_PORT": 28000,
            "FRONTEND_HOST_PORT": 28080,
        },
    }
    env = runtime.environment(allocation)
    assert env["STACK_COMPOSE_PROJECT"].startswith("charting-stack-")
    assert env["DATABASE_URL"].endswith("@127.0.0.1:15432/chartingdb")
    assert env["VITE_API_PROXY_TARGET"] == "http://127.0.0.1:18000"
    assert env["VITE_PORT"] == "19000"
    assert "28080" in env["STACK_URL"]


def test_stale_runtime_allocation_requires_git_and_docker_proof(monkeypatch):
    runtime = _load_runtime()
    monkeypatch.setattr(runtime, "active_worktree_paths", lambda: {Path("/active")})
    monkeypatch.setattr(runtime, "running_managed_projects", lambda projects: False)
    data = {
        "version": 1,
        "allocations": {
            "stale": {
                "worktree": "/stale",
                "projects": {"dev": "charting-dev-stale", "stack": "charting-stack-stale"},
            },
            "active": {
                "worktree": "/active",
                "projects": {"dev": "charting-dev-active", "stack": "charting-stack-active"},
            },
        },
    }
    runtime.reclaim_stale_allocations(data, "current")
    assert set(data["allocations"]) == {"active"}

    monkeypatch.setattr(runtime, "running_managed_projects", lambda projects: None)
    data["allocations"]["stale"] = {"worktree": "/stale", "projects": {}}
    runtime.reclaim_stale_allocations(data, "current")
    assert "stale" in data["allocations"]


def test_unregistered_generated_env_files_are_removed(tmp_path, monkeypatch):
    runtime = _load_runtime()
    runtime_dir = tmp_path / ".ai" / "runtime"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "active-id.env").write_text("ACTIVE=1\n")
    (runtime_dir / "stale-id.env").write_text("STALE=1\n")
    monkeypatch.setattr(runtime, "common_root", lambda: tmp_path)
    runtime.remove_unregistered_env_files(
        {"allocations": {"active": {"id": "active-id"}}}
    )
    assert (runtime_dir / "active-id.env").exists()
    assert not (runtime_dir / "stale-id.env").exists()
