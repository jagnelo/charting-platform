"""A PostgreSQL quota ledger gains the admission indexes in place on first use."""

from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from app.config import settings
from app.services.provider_quota_coordinator import (
    _HOT_PATH_INDEXES,
    _engine_for,
    _upgrade_hot_path_indexes,
    metadata,
)

pytestmark = pytest.mark.integration

EXPECTED_COLUMNS = {
    "ix_provider_quota_ledger_baseline_dimension_observed": (
        "(account_scope, quota_group, dimension, window_seconds, observed_at)"
    ),
    "ix_provider_quota_ledger_reservation_dimension_created": (
        "(account_scope, quota_group, dimension, created_at)"
    ),
    "ix_provider_quota_ledger_reservation_dimension_window": (
        "(account_scope, quota_group, dimension, window_started_at)"
    ),
    "ix_provider_quota_ledger_reservation_scope_state_lease": (
        "(account_scope, state, lease_expires_at)"
    ),
}


def _schema_url(raw_url: str, schema: str) -> str:
    url = make_url(raw_url).set(
        drivername="postgresql+psycopg2", query={"options": f"-csearch_path={schema}"}
    )
    return url.render_as_string(hide_password=False)


def _ledger_indexes(connection, schema: str) -> dict[str, str]:
    rows = connection.execute(
        sa.text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = :schema AND indexname LIKE 'ix_provider_quota_ledger_%'"
        ),
        {"schema": schema},
    ).all()
    return {name: definition for name, definition in rows}


def test_existing_postgres_ledger_gains_indexes_on_first_use(
    request, test_database_url, monkeypatch
):
    raw_url = test_database_url or request.getfixturevalue("pg_container").get_connection_url()
    schema = f"quota_ledger_{uuid4().hex[:12]}"
    url = _schema_url(raw_url, schema)
    admin = sa.create_engine(_schema_url(raw_url, "public"))
    _engine_for.cache_clear()
    try:
        with admin.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        # A ledger written before these indexes existed, with a row in it.
        legacy = sa.create_engine(url)
        with legacy.begin() as connection:
            metadata.create_all(connection)
            for index in _HOT_PATH_INDEXES:
                connection.execute(sa.text(f'DROP INDEX "{index.name}"'))
            connection.execute(
                sa.text(
                    "INSERT INTO provider_quota_ledger_scope_lock (provider_name, account_scope) "
                    "VALUES ('__account_scope__', 'fixture')"
                )
            )
            assert _ledger_indexes(connection, schema) == {}
        legacy.dispose()

        monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", url)
        engine = _engine_for(url)

        with engine.connect() as connection:
            indexes = _ledger_indexes(connection, schema)
            assert set(indexes) == set(EXPECTED_COLUMNS)
            for name, columns in EXPECTED_COLUMNS.items():
                assert indexes[name].endswith(columns), indexes[name]
            assert (
                connection.execute(
                    sa.text("SELECT count(*) FROM provider_quota_ledger_scope_lock")
                ).scalar_one()
                == 1
            )

        # Re-running the upgrade (another process's first use) is a no-op.
        _upgrade_hot_path_indexes(engine)
        with engine.connect() as connection:
            assert _ledger_indexes(connection, schema) == indexes
    finally:
        _engine_for.cache_clear()
        with admin.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()
