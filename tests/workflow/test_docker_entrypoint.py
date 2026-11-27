from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "backend" / "docker-entrypoint.sh"


def run_entrypoint(tmp_path: Path, argv: list[str], env: dict[str, str] | None = None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    for name in ("alembic", "uvicorn", "gunicorn", "python", "python3", "arq", "sh"):
        stub = bin_dir / name
        stub.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\n')
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    run_env = {"PATH": f"{bin_dir}:/usr/bin:/bin"}
    run_env.update(env or {})
    # Invoke the real sh through an absolute path: the stub dir shadows `sh`
    # for the exec'd command, not for the entrypoint itself.
    proc = subprocess.run(
        ["/bin/sh", str(ENTRYPOINT), *argv],
        env=run_env, capture_output=True, text=True, check=False,
    )
    calls = log.read_text().splitlines() if log.exists() else []
    return proc, calls


@pytest.mark.parametrize(
    "argv",
    [
        ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        ["python", "-m", "uvicorn", "app.main:app"],
        ["gunicorn", "app.main:app"],
    ],
)
def test_api_server_migrates_without_env(tmp_path, argv):
    proc, calls = run_entrypoint(tmp_path, argv)
    assert proc.returncode == 0, proc.stderr
    assert calls[0] == "alembic upgrade head"
    assert calls[1].split()[0] == argv[0]


@pytest.mark.parametrize(
    "argv",
    [
        ["python", "some_script.py"],
        ["python", "-m", "app.workers.arq_worker"],
        ["python", "-m", "app.strategy_lab_v2.worker_entrypoint"],
        ["arq", "app.tasks.worker.WorkerSettings"],
    ],
)
def test_other_commands_skip_migrations_by_default(tmp_path, argv):
    proc, calls = run_entrypoint(tmp_path, argv)
    assert proc.returncode == 0, proc.stderr
    assert "alembic upgrade head" not in calls
    assert len(calls) == 1 and calls[0].split()[0] == argv[0]


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes"])
def test_explicit_opt_in_migrates_any_command(tmp_path, value):
    proc, calls = run_entrypoint(
        tmp_path, ["python", "some_script.py"], {"RUN_MIGRATIONS": value}
    )
    assert proc.returncode == 0, proc.stderr
    assert calls == ["alembic upgrade head", "python some_script.py"]


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no"])
def test_explicit_opt_out_skips_even_for_api_server(tmp_path, value):
    proc, calls = run_entrypoint(
        tmp_path, ["uvicorn", "app.main:app"], {"RUN_MIGRATIONS": value}
    )
    assert proc.returncode == 0, proc.stderr
    assert calls == ["uvicorn app.main:app"]


def test_invalid_value_fails_closed_without_running_command(tmp_path):
    proc, calls = run_entrypoint(
        tmp_path, ["uvicorn", "app.main:app"], {"RUN_MIGRATIONS": "maybe"}
    )
    assert proc.returncode == 64
    assert calls == []


def test_compose_services_keep_migrating_contract():
    """The backend service must keep migrating via the default CMD with no env;
    entrypoint-dependent workers must opt in explicitly."""
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]
    assert "command" not in services["backend"]
    assert "entrypoint" not in services["backend"]
    assert "RUN_MIGRATIONS" not in (services["backend"].get("environment") or {})
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text()
    assert 'CMD ["uvicorn", "app.main:app"' in dockerfile
    assert services["worker"]["depends_on"]["backend"]["condition"] == "service_healthy"
    for name in ("strategy-lab-v2-worker", "strategy-lab-v2-forward-worker"):
        assert str(services[name]["environment"]["RUN_MIGRATIONS"]).lower() == "true"

    rpi = yaml.safe_load((ROOT / "deploy/rpi/compose.yml").read_text())["services"]
    assert "command" not in rpi["backend"]
    assert rpi["worker"]["depends_on"]["backend"]["condition"] == "service_healthy"
