#!/usr/bin/env python3
"""Run the migration compatibility gate against disposable PostgreSQL.

INTEGRATION_BASE_SHA identifies the prior runnable release. The gate builds
that schema with the previous application, upgrades it with the checked-out
staging or master commit, and then exercises the previous application against
the expanded schema. The temporary database/worktree are always removed.
"""

from __future__ import annotations

import argparse
import difflib
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
    changed = {line for line in output.splitlines() if line.endswith(".py")}
    # During an implementation session the corrective migration is often
    # intentionally uncommitted. Include tracked/untracked worktree paths so
    # the gate cannot report a false “no migration changes” skip.
    status = git("status", "--short")
    for line in status.splitlines():
        path = line[3:] if len(line) > 3 else ""
        if path.startswith("backend/alembic/versions/") and path.endswith(".py"):
            changed.add(path)
    return sorted(changed)


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


def migration_env(port: int, database: str = "chartingdb") -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL_SYNC": f"postgresql+psycopg2://postgres:postgres@127.0.0.1:{port}/{database}",
            "DATABASE_URL": f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{port}/{database}",
            "SECRET_KEY": "migration-gate-only",
            "APP_ENV": "test",
        }
    )
    return env


def postgres_scalar(database: str, query: str) -> str:
    return run(
        [
            "docker",
            "exec",
            os.environ["MIGRATION_CONTAINER"],
            "psql",
            "-U",
            "postgres",
            "-d",
            database,
            "-qAtc",
            query,
        ]
    ).stdout.strip()


def provider_quota_schema(database: str) -> str:
    return postgres_scalar(
        database,
        """
        SELECT table_name || '.' || column_name || '|' || data_type || '|' || is_nullable
               || '|' || COALESCE(column_default, '<none>')
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND ((table_name = 'provider_policy' AND column_name IN (
                   'max_concurrency', 'tokens_per_minute', 'burst_capacity',
                   'cooldown_seconds', 'quota_contract', 'quota_scope',
                   'quota_source', 'quota_verified_at'))
            OR (table_name = 'provider_quota_window' AND column_name = 'dimension'))
        ORDER BY table_name, column_name
        """,
    )


def provider_recurring_cost_schema(database: str) -> str:
    """Compare the new shared cost-governance schema on both install paths."""
    tables = (
        "'provider_recurring_cost_budget', "
        "'provider_recurring_cost_budget_revision', "
        "'provider_recurring_cost_commitment', "
        "'provider_recurring_cost_commitment_revision'"
    )
    columns = postgres_scalar(
        database,
        "SELECT table_name || '.' || column_name || '|' || data_type || '|' || is_nullable "
        "|| '|' || COALESCE(column_default, '<none>') || '|' "
        "|| COALESCE(character_maximum_length::text, '') || '|' "
        "|| COALESCE(numeric_precision::text, '') || '|' "
        "|| COALESCE(numeric_scale::text, '') "
        "FROM information_schema.columns WHERE table_schema = 'public' "
        f"AND table_name IN ({tables}) ORDER BY table_name, ordinal_position",
    )
    constraints = postgres_scalar(
        database,
        "SELECT tc.table_name || '.' || tc.constraint_name || '|' || tc.constraint_type "
        "|| '|' || COALESCE(string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position), '') "
        "|| '|' || COALESCE(cc.check_clause, '') "
        "FROM information_schema.table_constraints tc "
        "LEFT JOIN information_schema.key_column_usage kcu "
        "ON tc.constraint_catalog = kcu.constraint_catalog "
        "AND tc.constraint_schema = kcu.constraint_schema "
        "AND tc.constraint_name = kcu.constraint_name "
        "AND tc.table_name = kcu.table_name "
        "LEFT JOIN information_schema.check_constraints cc "
        "ON tc.constraint_catalog = cc.constraint_catalog "
        "AND tc.constraint_schema = cc.constraint_schema "
        "AND tc.constraint_name = cc.constraint_name "
        "WHERE tc.table_schema = 'public' "
        "AND (tc.constraint_type != 'CHECK' OR cc.check_clause NOT LIKE '%IS NOT NULL%') "
        f"AND tc.table_name IN ({tables}) "
        "GROUP BY tc.table_name, tc.constraint_name, tc.constraint_type, cc.check_clause "
        "ORDER BY tc.table_name, tc.constraint_name",
    )
    indexes = postgres_scalar(
        database,
        "SELECT tablename || '.' || indexname || '|' || indexdef "
        "FROM pg_indexes WHERE schemaname = 'public' "
        f"AND tablename IN ({tables}) ORDER BY tablename, indexname",
    )
    if not columns or not constraints:
        return ""
    return "\n".join(
        (columns, "-- constraints --", constraints, "-- indexes --", indexes)
    )


def seed_legacy_quota_fixture() -> None:
    source_id = postgres_scalar(
        "chartingdb",
        "INSERT INTO data_source (name, is_active) "
        "VALUES ('migration-compatibility-provider-limit-fixture', true) "
        "RETURNING id",
    )
    if not source_id.isdigit():
        raise SystemExit("could not create existing-database provider quota fixture")
    defaulted_limit_columns = int(
        postgres_scalar(
            "chartingdb",
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'provider_policy' "
            "AND column_name IN ('max_concurrency', 'tokens_per_minute', "
            "'burst_capacity', 'cooldown_seconds') AND column_default IS NOT NULL",
        )
    )
    if defaulted_limit_columns == 4:
        # Exercise the old generic-default upgrade path only when the actual
        # previous-release schema still has those defaults.
        statement = (
            "INSERT INTO provider_policy "
            "(data_source_id, capability, max_concurrency, tokens_per_minute, "
            "burst_capacity, cooldown_seconds) "
            f"VALUES ({source_id}, 'PRICE_HISTORY', 2, 60, 15, 30)"
        )
    elif defaulted_limit_columns == 0:
        # A newer previous release has already removed the unsafe defaults;
        # create its real fail-closed state instead of injecting legacy values
        # after the migration that was meant to remove them has run.
        statement = (
            "INSERT INTO provider_policy (data_source_id, capability) "
            f"VALUES ({source_id}, 'PRICE_HISTORY')"
        )
    else:
        raise SystemExit(
            "previous-release provider quota schema has only some generic defaults; "
            "refusing to synthesize an ambiguous fixture"
        )
    run(
        [
            "docker",
            "exec",
            os.environ["MIGRATION_CONTAINER"],
            "psql",
            "-U",
            "postgres",
            "-d",
            "chartingdb",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            statement,
        ]
    )


def seed_fresh_quota_fixture() -> None:
    source_id = postgres_scalar(
        "chartingfresh",
        "INSERT INTO data_source (name, is_active) "
        "VALUES ('migration-compatibility-provider-limit-fixture', true) "
        "RETURNING id",
    )
    if not source_id.isdigit():
        raise SystemExit("could not create fresh-install provider quota fixture")
    run(
        [
            "docker",
            "exec",
            os.environ["MIGRATION_CONTAINER"],
            "psql",
            "-U",
            "postgres",
            "-d",
            "chartingfresh",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "INSERT INTO provider_policy (data_source_id, capability) "
            f"VALUES ({source_id}, 'PRICE_HISTORY')",
        ]
    )


def assert_provider_quota_equivalence() -> None:
    existing = provider_quota_schema("chartingdb")
    fresh = provider_quota_schema("chartingfresh")
    if not existing or existing != fresh:
        raise SystemExit(
            "provider quota schema differs between fresh install and existing-database upgrade"
        )
    for database in ("chartingdb", "chartingfresh"):
        remaining = postgres_scalar(
            database,
            "SELECT count(*) FROM provider_policy p JOIN data_source d "
            "ON d.id = p.data_source_id "
            "WHERE d.name = 'migration-compatibility-provider-limit-fixture' "
            "AND p.capability = 'PRICE_HISTORY' "
            "AND p.max_concurrency IS NULL AND p.tokens_per_minute IS NULL "
            "AND p.burst_capacity IS NULL AND p.cooldown_seconds IS NULL "
            "AND p.quota_contract IS NULL AND p.quota_source IS NULL",
        )
        if remaining != "1":
            raise SystemExit(
                f"{database} did not preserve fail-closed provider quota state: {remaining} rows"
            )
    print("provider quota schema/data equivalence: fresh and existing paths passed")
    existing_cost_schema = provider_recurring_cost_schema("chartingdb")
    fresh_cost_schema = provider_recurring_cost_schema("chartingfresh")
    if not existing_cost_schema or existing_cost_schema != fresh_cost_schema:
        print(
            "\n".join(
                difflib.unified_diff(
                    existing_cost_schema.splitlines(),
                    fresh_cost_schema.splitlines(),
                    fromfile="existing-database-upgrade",
                    tofile="fresh-install",
                    lineterm="",
                )
            )
        )
        raise SystemExit(
            "provider recurring-cost schema differs between fresh install and "
            "existing-database upgrade"
        )
    print("provider recurring-cost schema equivalence: fresh and existing paths passed")
    for database in ("chartingdb", "chartingfresh"):
        negative = run(
            [
                "docker",
                "exec",
                os.environ["MIGRATION_CONTAINER"],
                "psql",
                "-U",
                "postgres",
                "-d",
                database,
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "INSERT INTO provider_recurring_cost_budget "
                "(id, currency, monthly_ceiling, evidence_source, evidence_version, "
                "reviewed_at, revision) VALUES "
                "(1, 'USD', -0.0001, 'migration constraint test', 'negative', now(), 1)",
            ],
            check=False,
        )
        if negative.returncode == 0 or (
            "ck_provider_recurring_cost_budget_nonnegative"
            not in negative.stderr + negative.stdout
        ):
            raise SystemExit(
                f"{database} did not reject a negative recurring-cost ceiling via its named check"
            )
        run(
            [
                "docker",
                "exec",
                os.environ["MIGRATION_CONTAINER"],
                "psql",
                "-U",
                "postgres",
                "-d",
                database,
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "INSERT INTO provider_recurring_cost_budget "
                "(id, currency, monthly_ceiling, evidence_source, evidence_version, "
                "reviewed_at, revision) VALUES "
                "(1, 'USD', 0, 'migration constraint test', 'zero', now(), 1)",
            ]
        )
    print("provider recurring-cost budget constraint: zero accepted, negative rejected")


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
        print(f"previous-release schema: {old_head(previous)}")
        seed_legacy_quota_fixture()
        run([str(ALEMBIC), "upgrade", "head"], cwd=BACKEND, env=env)
        print(f"checked-out schema: {git('rev-parse', 'HEAD')}")
        run(
            ["docker", "exec", container, "createdb", "-U", "postgres", "chartingfresh"]
        )
        fresh_env = migration_env(port, "chartingfresh")
        run([str(ALEMBIC), "upgrade", "head"], cwd=BACKEND, env=fresh_env)
        seed_fresh_quota_fixture()
        assert_provider_quota_equivalence()
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
