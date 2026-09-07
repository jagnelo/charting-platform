import importlib.util
from pathlib import Path

import pytest


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
    runtime.remove_unregistered_env_files({"allocations": {"active": {"id": "active-id"}}})
    assert (runtime_dir / "active-id.env").exists()
    assert not (runtime_dir / "stale-id.env").exists()


def test_shared_env_is_linked_into_ignored_worktree_paths(tmp_path, monkeypatch):
    runtime = _load_runtime()
    checkout = tmp_path / "checkout"
    (checkout / "backend").mkdir(parents=True)
    source = tmp_path / "operator" / "app.env"
    source.parent.mkdir()
    source.write_text("PROVIDER_KEY=secret\n")
    source.chmod(0o600)
    monkeypatch.setenv(runtime.SHARED_ENV_OVERRIDE, str(source))
    monkeypatch.setattr(runtime, "root", lambda: checkout)

    assert runtime.install_shared_env_links() == source.resolve()
    for relative_target in runtime.SHARED_ENV_TARGETS:
        target = checkout / relative_target
        assert target.is_symlink()
        assert target.resolve() == source.resolve()

    # Re-running is idempotent and never copies secret bytes into the checkout.
    assert runtime.install_shared_env_links() == source.resolve()


def test_shared_env_rejects_unsafe_permissions(tmp_path, monkeypatch):
    runtime = _load_runtime()
    source = tmp_path / "app.env"
    source.write_text("PROVIDER_KEY=secret\n")
    source.chmod(0o640)
    monkeypatch.setenv(runtime.SHARED_ENV_OVERRIDE, str(source))
    monkeypatch.setattr(runtime, "root", lambda: tmp_path / "checkout")

    with pytest.raises(SystemExit, match="chmod 600"):
        runtime.install_shared_env_links()


def test_shared_env_never_replaces_existing_file_or_other_link(tmp_path, monkeypatch):
    runtime = _load_runtime()
    checkout = tmp_path / "checkout"
    (checkout / "backend").mkdir(parents=True)
    source = tmp_path / "app.env"
    source.write_text("PROVIDER_KEY=secret\n")
    source.chmod(0o600)
    monkeypatch.setenv(runtime.SHARED_ENV_OVERRIDE, str(source))
    monkeypatch.setattr(runtime, "root", lambda: checkout)

    (checkout / ".env").write_text("LOCAL=keep\n")
    with pytest.raises(SystemExit, match="refusing to replace existing env file"):
        runtime.install_shared_env_links()

    (checkout / ".env").unlink()
    elsewhere = tmp_path / "elsewhere.env"
    elsewhere.write_text("OTHER=keep\n")
    elsewhere.chmod(0o600)
    (checkout / ".env").symlink_to(elsewhere)
    with pytest.raises(SystemExit, match="pointing elsewhere"):
        runtime.install_shared_env_links()
