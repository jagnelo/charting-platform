#!/usr/bin/env python3
"""Run the migration compatibility gate against disposable PostgreSQL.

The integration candidate is a merge commit.  Its first parent is the exact
master baseline, so the gate can build the old schema with the previous
application and then upgrade that same database with the candidate migrations.
The database and the temporary previous-release worktree are always removed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv" / "bin" / "python"
ALEMBIC = BACKEND / ".venv" / "bin" / "alembic"


def run(
    args: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)
    if check and result.returncode:
        print(result.stdout, end="")
        print(result.stderr, end="")
        raise SystemExit(result.returncode)
    return result


def git(*args: str, cwd: Path = ROOT) -> str:
    return run(["git", *args], cwd=cwd).stdout.strip()


def changed_migrations(base: str) -> list[str]:
    output = git(
        "diff", "--name-only", f"{base}..HEAD", "--", "backend/alembic/versions"
    )
    return [line for line in output.splitlines() if line.endswith(".py")]


def wait_for_postgres(port: int) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = run(
            [
                "docker",
                "exec",
                os.environ["MIGRATION_CONTAINER"],
                "pg_isready",
                "-U",
                "postgres",
            ],
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise SystemExit(f"PostgreSQL did not become ready on host port {port}")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def migration_env(port: int) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL_SYNC": f"postgresql+psycopg2://postgres:postgres@127.0.0.1:{port}/chartingdb",
            "DATABASE_URL": f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{port}/chartingdb",
            "SECRET_KEY": "migration-gate-only",
            "APP_ENV": "test",
        }
    )
    return env


def old_head(worktree: Path) -> str:
    return run([str(ALEMBIC), "heads"], cwd=worktree / "backend").stdout.strip()


def smoke_previous_app(worktree: Path, port: int) -> None:
    """Exercise a previous-release app against the upgraded candidate schema."""
    app_port = free_port()
    env = migration_env(port)
    env["REDIS_URL"] = "redis://127.0.0.1:1/0"
    process = subprocess.Popen(
        [
            str(PYTHON),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(app_port),
        ],
        cwd=worktree / "backend",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        # Cold imports and database startup can exceed the old 30-second
        # window when the exhaustive gate is sharing a busy Docker host. Keep
        # the probe bounded, but allow a realistic previous-release startup
        # budget and report early process exits instead of masking them as a
        # generic timeout.
        deadline = time.monotonic() + 90
        url = f"http://127.0.0.1:{app_port}/health"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output, _ = process.communicate()
                raise SystemExit(
                    "previous-release application exited before /health became "
                    f"ready (exit={process.returncode}):\n{output}"
                )
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        print("previous-release application smoke: /health 200")
                        return
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.5)
        process.terminate()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
        raise SystemExit(
            f"previous-release application smoke failed after 90s:\n{output}"
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-sha", default=os.getenv("INTEGRATION_BASE_SHA"))
    args = parser.parse_args()
    base = args.base_sha or git("rev-parse", "HEAD^1")
    migrations = changed_migrations(base)
    if not migrations:
        print(f"migration compatibility: skipped (no migration changes from {base})")
        return 0

    if shutil.which("docker") is None or not PYTHON.exists() or not ALEMBIC.exists():
        raise SystemExit("migration compatibility requires Docker and backend/.venv")

    port = free_port()
    container = f"charting-migration-gate-{uuid.uuid4().hex[:10]}"
    os.environ["MIGRATION_CONTAINER"] = container
    env = migration_env(port)
    previous = Path(tempfile.mkdtemp(prefix="charting-previous-release-"))
    try:
        run(["git", "worktree", "add", "--detach", str(previous), base])
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container,
                "-e",
                "POSTGRES_USER=postgres",
                "-e",
                "POSTGRES_PASSWORD=postgres",
                "-e",
                "POSTGRES_DB=chartingdb",
                "-p",
                f"127.0.0.1:{port}:5432",
                "postgres:16-alpine",
            ]
        )
        wait_for_postgres(port)
        old_env = migration_env(port)
        run([str(ALEMBIC), "upgrade", "head"], cwd=previous / "backend", env=old_env)
        print(f"previous-master schema: {old_head(previous)}")
        run([str(ALEMBIC), "upgrade", "head"], cwd=BACKEND, env=env)
        print(f"candidate schema: {git('rev-parse', 'HEAD')}")
        smoke_previous_app(previous, port)
        print(
            f"migration compatibility: passed ({len(migrations)} changed migration file(s))"
        )
        return 0
    finally:
        run(["docker", "rm", "-f", container], check=False)
        run(["git", "worktree", "remove", "--force", str(previous)], check=False)
        shutil.rmtree(previous, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
