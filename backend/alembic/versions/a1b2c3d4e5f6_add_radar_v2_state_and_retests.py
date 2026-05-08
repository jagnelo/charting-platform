"""add radar v2 state and retests

Revision ID: a1b2c3d4e5f6
Revises: f1e2d3c4b5a6
Create Date: 2026-05-07 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f1e2d3c4b5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_enum_if_missing(name: str, values: tuple[str, ...]) -> None:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = '{name}'
                  AND n.nspname = current_schema()
            ) THEN
                EXECUTE format($ddl$CREATE TYPE %I AS ENUM ({quoted_values})$ddl$, '{name}');
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    op.execute("ALTER TYPE radarsetuptype ADD VALUE IF NOT EXISTS 'BREAKOUT_RETEST'")
    op.execute("ALTER TYPE radarsetuptype ADD VALUE IF NOT EXISTS 'BREAKDOWN_RETEST'")
    op.execute("ALTER TYPE radarsetuptype ADD VALUE IF NOT EXISTS 'FAKEOUT'")
    op.execute("ALTER TYPE radarsetuptype ADD VALUE IF NOT EXISTS 'FAKEDOWN'")
    op.execute("ALTER TYPE radarsetuptype ADD VALUE IF NOT EXISTS 'FAILED_RECLAIM'")
    op.execute(
        "ALTER TYPE radarsetuptype ADD VALUE IF NOT EXISTS 'FAILED_BREAKDOWN_RECOVERY'"
    )
    op.execute("ALTER TYPE radarsetuptype ADD VALUE IF NOT EXISTS 'COMPRESSION_SUPPORT'")
    op.execute(
        "ALTER TYPE radarsetuptype ADD VALUE IF NOT EXISTS 'COMPRESSION_RESISTANCE'"
    )

    radar_state = PgEnum(
        "DEVELOPING",
        "CONFIRMED",
        "INVALIDATED",
        "EXPIRED",
        name="radarstate",
        create_type=False,
    )
    _create_enum_if_missing(
        "radarstate",
        ("DEVELOPING", "CONFIRMED", "INVALIDATED", "EXPIRED"),
    )

    radar_outcome_status = PgEnum(
        "OPEN",
        "TARGET_HIT",
        "INVALIDATED",
        "EXPIRED",
        name="radaroutcomestatus",
        create_type=False,
    )
    _create_enum_if_missing(
        "radaroutcomestatus",
        ("OPEN", "TARGET_HIT", "INVALIDATED", "EXPIRED"),
    )

    op.add_column(
        "radar_setup_thread",
        sa.Column(
            "current_state",
            radar_state,
            nullable=False,
            server_default="DEVELOPING",
        ),
    )
    op.add_column(
        "radar_setup_thread",
        sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_radar_setup_thread_current_state",
        "radar_setup_thread",
        ["current_state"],
    )

    op.add_column(
        "radar_detection",
        sa.Column(
            "state",
            radar_state,
            nullable=False,
            server_default="DEVELOPING",
        ),
    )
    op.add_column("radar_detection", sa.Column("state_reason", sa.Text(), nullable=True))
    op.add_column("radar_detection", sa.Column("entry_price", sa.Float(), nullable=True))
    op.add_column("radar_detection", sa.Column("invalidation_price", sa.Float(), nullable=True))
    op.add_column("radar_detection", sa.Column("target_price", sa.Float(), nullable=True))
    op.add_column(
        "radar_detection",
        sa.Column(
            "outcome_status",
            radar_outcome_status,
            nullable=False,
            server_default="OPEN",
        ),
    )
    op.add_column(
        "radar_detection",
        sa.Column("outcome_last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "radar_detection",
        sa.Column("bars_since_signal", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "radar_detection",
        sa.Column("max_favorable_excursion_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "radar_detection",
        sa.Column("max_adverse_excursion_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "radar_detection",
        sa.Column("target_hit_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "radar_detection",
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_radar_detection_state", "radar_detection", ["state"])
    op.create_index("ix_radar_detection_outcome_status", "radar_detection", ["outcome_status"])

    op.execute(
        sa.text(
            """
            UPDATE radar_setup_thread
            SET current_state = CASE
                    WHEN current_setup_type IN ('APPROACHING_SUPPORT', 'APPROACHING_RESISTANCE')
                        THEN 'DEVELOPING'::radarstate
                    ELSE 'CONFIRMED'::radarstate
                END,
                state_changed_at = last_seen_at
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE radar_detection
            SET state = CASE
                    WHEN setup_type IN ('APPROACHING_SUPPORT', 'APPROACHING_RESISTANCE')
                        THEN 'DEVELOPING'::radarstate
                    ELSE 'CONFIRMED'::radarstate
                END,
                entry_price = key_level_price,
                invalidation_price = CASE
                    WHEN evidence_json -> 'metrics' ->> 'invalidation_price' IS NOT NULL
                        THEN (evidence_json -> 'metrics' ->> 'invalidation_price')::double precision
                    ELSE NULL
                END,
                target_price = CASE
                    WHEN evidence_json -> 'metrics' ->> 'target_price' IS NOT NULL
                        THEN (evidence_json -> 'metrics' ->> 'target_price')::double precision
                    ELSE NULL
                END,
                outcome_last_evaluated_at = observed_at,
                bars_since_signal = 0
            """
        )
    )
    op.alter_column("radar_setup_thread", "state_changed_at", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_radar_detection_state", table_name="radar_detection")
    op.drop_column("radar_detection", "target_price")
    op.drop_column("radar_detection", "invalidation_price")
    op.drop_column("radar_detection", "entry_price")
    op.drop_index("ix_radar_detection_outcome_status", table_name="radar_detection")
    op.drop_column("radar_detection", "invalidated_at")
    op.drop_column("radar_detection", "target_hit_at")
    op.drop_column("radar_detection", "max_adverse_excursion_pct")
    op.drop_column("radar_detection", "max_favorable_excursion_pct")
    op.drop_column("radar_detection", "bars_since_signal")
    op.drop_column("radar_detection", "outcome_last_evaluated_at")
    op.drop_column("radar_detection", "outcome_status")
    op.drop_column("radar_detection", "state_reason")
    op.drop_column("radar_detection", "state")

    op.drop_index("ix_radar_setup_thread_current_state", table_name="radar_setup_thread")
    op.drop_column("radar_setup_thread", "state_changed_at")
    op.drop_column("radar_setup_thread", "current_state")

    bind = op.get_bind()
    sa.Enum(name="radaroutcomestatus").drop(bind, checkfirst=True)
    sa.Enum(name="radarstate").drop(bind, checkfirst=True)
    # `radarsetuptype` is intentionally left with the added values because
    # PostgreSQL does not support removing enum labels in a simple downgrade.
