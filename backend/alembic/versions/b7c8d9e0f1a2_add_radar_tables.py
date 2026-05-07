"""add radar tables

Revision ID: b7c8d9e0f1a2
Revises: a7b8c9d0e1f2
Create Date: 2026-05-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgEnum


revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PgEnum with create_type=False suppresses the automatic CREATE TYPE that
    # op.create_table fires via before_create. Lifecycle is managed explicitly
    # below via .create(checkfirst=True), except for timeframe which already
    # exists from the initial_schema migration and must never be recreated.
    radar_run_status = PgEnum("RUNNING", "COMPLETED", "FAILED", name="radarrunstatus", create_type=False)
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
    timeframe_enum = PgEnum(
        "M1", "M5", "M15", "M30", "H1", "H2", "H4", "H12", "D1", "W1", "MN",
        name="timeframe",
        create_type=False,
    )
    bind = op.get_bind()
    radar_run_status.create(bind, checkfirst=True)
    radar_setup_type.create(bind, checkfirst=True)

    op.create_table(
        "radar_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timeframe", timeframe_enum, nullable=False),
        sa.Column("universe_type", sa.String(length=32), nullable=False),
        sa.Column("universe_filter", sa.JSON(), nullable=True),
        sa.Column("status", radar_run_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detection_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "radar_detection",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("radar_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timeframe", timeframe_enum, nullable=False),
        sa.Column("setup_type", radar_setup_type, nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fresh_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("key_level_price", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("invalidation_hint", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("score_factors", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_radar_detection_run_id", "radar_detection", ["run_id"])
    op.create_index("ix_radar_detection_instrument_id", "radar_detection", ["instrument_id"])
    op.create_index("ix_radar_detection_setup_type", "radar_detection", ["setup_type"])
    op.create_index("ix_radar_detection_fresh_until", "radar_detection", ["fresh_until"])


def downgrade() -> None:
    op.drop_index("ix_radar_detection_fresh_until", table_name="radar_detection")
    op.drop_index("ix_radar_detection_setup_type", table_name="radar_detection")
    op.drop_index("ix_radar_detection_instrument_id", table_name="radar_detection")
    op.drop_index("ix_radar_detection_run_id", table_name="radar_detection")
    op.drop_table("radar_detection")
    op.drop_table("radar_run")

    bind = op.get_bind()
    sa.Enum(name="radarsetuptype").drop(bind, checkfirst=True)
    sa.Enum(name="radarrunstatus").drop(bind, checkfirst=True)
