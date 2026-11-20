"""The refresh claim query must use the partial index on real PostgreSQL.

Production (2026-11-20): ~232k market_refresh_job rows of which ~100k were open;
each single-job claim cost ~105 ms because the planner walked the whole
priority index and filtered.  The partial claim index covers only open rows.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

pytestmark = pytest.mark.integration

INDEX_NAME = "ix_market_refresh_job_claimable"
_MIGRATION = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "a7c3e5f9b2d4_add_refresh_job_claim_index.py"
)


def _sync_url(raw_url: str) -> str:
    return raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)


def _engine(request, test_database_url):
    raw_url = test_database_url
    if not raw_url:
        raw_url = request.getfixturevalue("pg_container").get_connection_url()
    return sa.create_engine(_sync_url(raw_url), pool_pre_ping=True)


def test_claim_query_uses_partial_index_and_returns_first_due_row(request, test_database_url):
    import app.models  # noqa: F401
    from app.database import Base
    from app.models.market_data_foundation import MarketRefreshJob
    from app.services.market_refresh_queue import claimable_jobs_query

    engine = _engine(request, test_database_url)
    schema = f"claim_index_{uuid4().hex[:12]}"
    now = datetime.now(UTC)
    past = now - timedelta(hours=1)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            Base.metadata.create_all(
                connection.execution_options(schema_translate_map={None: schema})
            )

            def row(key, status, priority, next_attempt_at):
                return {
                    "request_key": key,
                    "capability": "history",
                    "priority": priority,
                    "status": status,
                    "attempts": 0,
                    "next_attempt_at": next_attempt_at,
                    "metadata_payload": {},
                    "created_at": now,
                    "updated_at": now,
                }

            rows = [
                row(f"done-{i}", "completed" if i % 2 else "tracking", 100 + i % 5, past)
                for i in range(4000)
            ]
            # A deep open backlog, as in production, so the ordered partial index
            # beats bitmap-scanning the status index and sorting.
            rows += [
                row(
                    f"open-{i}",
                    ("queued", "retry", "deferred")[i % 3],
                    100 + i % 7,
                    past + timedelta(seconds=i),
                )
                for i in range(6000)
            ]
            rows += [
                row("open-late", "queued", 100, past + timedelta(minutes=5)),
                row("open-first", "queued", 10, past),
                row("open-deferred", "deferred", 50, past),
                row("open-future", "retry", 1, now + timedelta(hours=1)),
            ]
            connection.execute(sa.insert(MarketRefreshJob.__table__), rows)
            connection.execute(sa.text("ANALYZE market_refresh_job"))

            statement = claimable_jobs_query(now, 1)
            compiled = statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
            plan = "\n".join(
                r[0] for r in connection.execute(sa.text(f"EXPLAIN {compiled}")).fetchall()
            )
            assert f"Index Scan using {INDEX_NAME}" in plan

            claimed = connection.execute(statement).mappings().all()
            assert [job["request_key"] for job in claimed] == ["open-first"]
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_claim_index_migration_roundtrip_on_postgres(request, test_database_url):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    spec = importlib.util.spec_from_file_location("refresh_job_claim_index_pg", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = _engine(request, test_database_url)
    schema = f"claim_index_mig_{uuid4().hex[:12]}"
    indexdef_sql = sa.text(
        "SELECT indexdef FROM pg_indexes WHERE schemaname = :schema AND indexname = :name"
    )
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            connection.exec_driver_sql(
                "CREATE TABLE market_refresh_job (id BIGINT PRIMARY KEY, priority INTEGER NOT NULL,"
                " status VARCHAR(24) NOT NULL, next_attempt_at TIMESTAMPTZ NOT NULL)"
            )
            module.op = Operations(MigrationContext.configure(connection))
            module.upgrade()
            indexdef = connection.execute(
                indexdef_sql, {"schema": schema, "name": INDEX_NAME}
            ).scalar_one()
            assert "(priority, next_attempt_at, id)" in indexdef
            assert "WHERE" in indexdef
            for status in ("queued", "retry", "deferred", "leased"):
                assert f"'{status}'" in indexdef
            module.downgrade()
            assert (
                connection.execute(indexdef_sql, {"schema": schema, "name": INDEX_NAME}).first()
                is None
            )
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
