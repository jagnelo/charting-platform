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
            "POSTGRES_HOST_PORT": 15432,
            "REDIS_HOST_PORT": 16379,
            "BACKEND_HOST_PORT": 18000,
            "FRONTEND_HOST_PORT": 18080,
        },
    }
    env = runtime.environment(allocation)
    assert env["STACK_COMPOSE_PROJECT"].startswith("charting-stack-")
    assert env["DATABASE_URL"].endswith("@127.0.0.1:15432/chartingdb")
    assert env["VITE_API_PROXY_TARGET"] == "http://127.0.0.1:18000"
    assert "18080" in env["STACK_URL"]
