"""add radar setup threads

Revision ID: f1e2d3c4b5a6
Revises: 40b528649be0
Create Date: 2026-05-06 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgEnum


revision: str = "f1e2d3c4b5a6"
down_revision: str | None = "40b528649be0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    timeframe_enum = PgEnum(
        "M1",
        "M5",
        "M15",
        "M30",
        "H1",
        "H2",
        "H4",
        "H12",
        "D1",
        "W1",
        "MN",
        name="timeframe",
        create_type=False,
    )
    radar_setup_type = PgEnum(
        "APPROACHING_SUPPORT",
        "APPROACHING_RESISTANCE",
        "BREAKOUT",
        "BREAKDOWN",
        "RECLAIM",
        "REJECTION",
        name="radarsetuptype",
        create_type=False,
    )

    op.create_table(
        "radar_setup_thread",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instrument.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("timeframe", timeframe_enum, nullable=False),
        sa.Column("context_role", sa.String(length=32), nullable=True),
        sa.Column("reference_price", sa.Float(), nullable=False),
        sa.Column("current_setup_type", radar_setup_type, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detection_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_radar_setup_thread_instrument_id", "radar_setup_thread", ["instrument_id"]
    )
    op.create_index(
        "ix_radar_setup_thread_context_role", "radar_setup_thread", ["context_role"]
    )
    op.create_index(
        "ix_radar_setup_thread_current_setup_type",
        "radar_setup_thread",
        ["current_setup_type"],
    )
    op.create_index("ix_radar_setup_thread_last_seen_at", "radar_setup_thread", ["last_seen_at"])

    op.add_column("radar_detection", sa.Column("thread_id", sa.Integer(), nullable=True))
    op.add_column(
        "radar_detection",
        sa.Column("signal_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "radar_detection",
        sa.Column("context_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "radar_detection",
        sa.Column("thread_event_index", sa.Integer(), nullable=True),
    )

    op.create_foreign_key(
        "fk_radar_detection_thread_id_radar_setup_thread",
        "radar_detection",
        "radar_setup_thread",
        ["thread_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_radar_detection_thread_id", "radar_detection", ["thread_id"])
    op.create_index("ix_radar_detection_signal_at", "radar_detection", ["signal_at"])

    op.execute(
        sa.text(
            """
            UPDATE radar_detection
            SET signal_at = COALESCE(
                to_timestamp((evidence_json -> 'metrics' ->> 'signal_time')::double precision),
                observed_at
            ),
            context_at = CASE
                WHEN evidence_json -> 'metrics' ->> 'context_time' IS NOT NULL
                    THEN to_timestamp((evidence_json -> 'metrics' ->> 'context_time')::double precision)
                ELSE NULL
            END
            """
        )
    )
    op.alter_column("radar_detection", "signal_at", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_radar_detection_signal_at", table_name="radar_detection")
    op.drop_index("ix_radar_detection_thread_id", table_name="radar_detection")
    op.drop_constraint(
        "fk_radar_detection_thread_id_radar_setup_thread",
        "radar_detection",
        type_="foreignkey",
    )
    op.drop_column("radar_detection", "thread_event_index")
    op.drop_column("radar_detection", "context_at")
    op.drop_column("radar_detection", "signal_at")
    op.drop_column("radar_detection", "thread_id")

    op.drop_index("ix_radar_setup_thread_last_seen_at", table_name="radar_setup_thread")
    op.drop_index("ix_radar_setup_thread_current_setup_type", table_name="radar_setup_thread")
    op.drop_index("ix_radar_setup_thread_context_role", table_name="radar_setup_thread")
    op.drop_index("ix_radar_setup_thread_instrument_id", table_name="radar_setup_thread")
    op.drop_table("radar_setup_thread")
