from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "alembic"
    / "versions"
    / "ff6a7b8c9d0e_bind_forward_dispatch_checkpoint.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "strategy_lab_v2_forward_dispatch_admission_migration",
        _MIGRATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load the forward dispatch admission migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.integration
def test_forward_dispatch_admission_migration_enforces_complete_context(
    pg_container,
    test_database_url: str | None,
) -> None:
    if test_database_url is not None:
        pytest.skip("migration DDL test requires its own disposable PostgreSQL container")

    migration = _migration_module()
    raw_url = pg_container.get_connection_url()
    engine = sa.create_engine(raw_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    CREATE TABLE strategy_lab_v2_forward_event_dispatches (
                        owner_id TEXT NOT NULL,
                        instance_id TEXT NOT NULL,
                        event_fingerprint TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        request_fingerprint TEXT NOT NULL,
                        attempt_id TEXT NOT NULL,
                        payload_digest TEXT NOT NULL,
                        queue_name TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        replay_plan_fingerprint TEXT NULL,
                        dispatch_fingerprint TEXT NOT NULL,
                        PRIMARY KEY (owner_id, idempotency_key),
                        UNIQUE (owner_id, instance_id, event_fingerprint),
                        UNIQUE (owner_id, request_fingerprint)
                    )
                    """
                )
            )
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()

            columns = {
                column["name"]
                for column in sa.inspect(connection).get_columns(
                    "strategy_lab_v2_forward_event_dispatches"
                )
            }
            assert {
                "pre_event_checkpoint_fingerprint",
                "warmup_receipt_fingerprint",
                "admission_decision",
            }.issubset(columns)

            connection.execute(
                sa.text(
                    """
                    INSERT INTO strategy_lab_v2_forward_event_dispatches (
                        owner_id, instance_id, event_fingerprint, idempotency_key,
                        request_fingerprint, attempt_id, payload_digest, queue_name,
                        created_at, replay_plan_fingerprint, dispatch_fingerprint
                    ) VALUES (
                        'owner-legacy', 'instance-legacy', 'event-legacy', 'legacy-key',
                        'request-legacy', 'instance-legacy', 'payload-legacy', 'forward-events',
                        '2026-10-05T00:00:00Z', NULL, 'dispatch-legacy'
                    )
                    """
                )
            )
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            """
                            INSERT INTO strategy_lab_v2_forward_event_dispatches (
                                owner_id, instance_id, event_fingerprint, idempotency_key,
                                request_fingerprint, attempt_id, payload_digest, queue_name,
                                created_at, replay_plan_fingerprint,
                                pre_event_checkpoint_fingerprint, admission_decision,
                                dispatch_fingerprint
                            ) VALUES (
                                'owner-partial', 'instance-partial', 'event-partial', 'partial-key',
                                'request-partial', 'instance-partial', 'payload-partial',
                                'forward-events', '2026-10-05T00:00:00Z', NULL,
                                'checkpoint-partial', 'enqueue', 'dispatch-partial'
                            )
                            """
                        )
                    )
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            """
                            INSERT INTO strategy_lab_v2_forward_event_dispatches (
                                owner_id, instance_id, event_fingerprint, idempotency_key,
                                request_fingerprint, attempt_id, payload_digest, queue_name,
                                created_at, replay_plan_fingerprint,
                                pre_event_checkpoint_fingerprint,
                                warmup_receipt_fingerprint, dispatch_fingerprint
                            ) VALUES (
                                'owner-missing-decision', 'instance-missing-decision',
                                'event-missing-decision', 'missing-decision-key',
                                'request-missing-decision', 'instance-missing-decision',
                                'payload-missing-decision', 'forward-events',
                                '2026-10-05T00:00:00Z', NULL, 'checkpoint-current',
                                'warmup-current', 'dispatch-missing-decision'
                            )
                            """
                        )
                    )
            connection.execute(
                sa.text(
                    """
                    INSERT INTO strategy_lab_v2_forward_event_dispatches (
                        owner_id, instance_id, event_fingerprint, idempotency_key,
                        request_fingerprint, attempt_id, payload_digest, queue_name,
                        created_at, replay_plan_fingerprint,
                        pre_event_checkpoint_fingerprint, warmup_receipt_fingerprint,
                        admission_decision, dispatch_fingerprint
                    ) VALUES (
                        'owner-current', 'instance-current', 'event-current', 'current-key',
                        'request-current', 'instance-current', 'payload-current', 'forward-events',
                        '2026-10-05T00:00:00Z', NULL, 'checkpoint-current', 'warmup-current',
                        'enqueue', 'dispatch-current'
                    )
                    """
                )
            )
            migration.downgrade()
            remaining_columns = {
                column["name"]
                for column in sa.inspect(connection).get_columns(
                    "strategy_lab_v2_forward_event_dispatches"
                )
            }
            assert "pre_event_checkpoint_fingerprint" not in remaining_columns
    finally:
        with engine.begin() as connection:
            connection.execute(
                sa.text("DROP TABLE IF EXISTS strategy_lab_v2_forward_event_dispatches CASCADE")
            )
        engine.dispose()
