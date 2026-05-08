"""add persisted instrument economic events

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-04-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: str | None = "b5c6d7e8f9a0"
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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    event_type = postgresql.ENUM(
        "EARNINGS",
        "EARNINGS_ESTIMATE",
        "DIVIDEND",
        "EX_DIVIDEND",
        "SPLIT",
        name="instrumenteventtype",
        create_type=False,
    )
    time_hint = postgresql.ENUM(
        "PRE_MARKET",
        "POST_MARKET",
        "DURING_MARKET",
        "UNKNOWN",
        name="eventtimehint",
        create_type=False,
    )

    if "instrument_event" not in tables:
        _create_enum_if_missing(
            "instrumenteventtype",
            ("EARNINGS", "EARNINGS_ESTIMATE", "DIVIDEND", "EX_DIVIDEND", "SPLIT"),
        )
        _create_enum_if_missing(
            "eventtimehint",
            ("PRE_MARKET", "POST_MARKET", "DURING_MARKET", "UNKNOWN"),
        )
        op.create_table(
            "instrument_event",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("instrument_id", sa.Integer(), nullable=False),
            sa.Column("event_type", event_type, nullable=False),
            sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("time_hint", time_hint, nullable=False),
            sa.Column("title", sa.String(length=240), nullable=False),
            sa.Column("value", sa.Numeric(20, 8), nullable=True),
            sa.Column("actual", sa.Numeric(20, 8), nullable=True),
            sa.Column("eps_estimate", sa.Numeric(20, 8), nullable=True),
            sa.Column("eps_actual", sa.Numeric(20, 8), nullable=True),
            sa.Column("eps_surprise", sa.Numeric(20, 8), nullable=True),
            sa.Column("eps_surprise_pct", sa.Numeric(20, 8), nullable=True),
            sa.Column("dividend_amount", sa.Numeric(20, 8), nullable=True),
            sa.Column("split_ratio", sa.Numeric(20, 8), nullable=True),
            sa.Column("currency", sa.String(length=10), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=False),
            sa.Column("source_event_key", sa.String(length=240), nullable=False),
            sa.Column("raw_payload", sa.Text(), nullable=True),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("instrument_id", "source", "source_event_key", name="uq_instrument_event_source_key"),
        )
        op.create_index("ix_instrument_event_instrument_id", "instrument_event", ["instrument_id"])
        op.create_index("ix_instrument_event_event_time", "instrument_event", ["event_time"])
        op.create_index("ix_instrument_event_event_type", "instrument_event", ["event_type"])
        op.create_index(
            "ix_instrument_event_inst_time_type",
            "instrument_event",
            ["instrument_id", "event_time", "event_type"],
        )

    if "instrument_event_fetch_state" not in tables:
        op.create_table(
            "instrument_event_fetch_state",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("instrument_id", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=50), nullable=False),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("event_count", sa.Integer(), nullable=False),
            sa.Column("earnings_count", sa.Integer(), nullable=False),
            sa.Column("fetch_version", sa.Integer(), server_default="2", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("instrument_id", "source", name="uq_instrument_event_fetch_state_source"),
        )
        op.create_index(
            "ix_instrument_event_fetch_state_instrument_id",
            "instrument_event_fetch_state",
            ["instrument_id"],
        )
    else:
        columns = {column["name"] for column in inspector.get_columns("instrument_event_fetch_state")}
        if "fetch_version" not in columns:
            op.add_column(
                "instrument_event_fetch_state",
                sa.Column("fetch_version", sa.Integer(), server_default="1", nullable=False),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "instrument_event_fetch_state" in tables:
        columns = {column["name"] for column in inspector.get_columns("instrument_event_fetch_state")}
        if "fetch_version" in columns:
            op.drop_column("instrument_event_fetch_state", "fetch_version")
        op.drop_index("ix_instrument_event_fetch_state_instrument_id", table_name="instrument_event_fetch_state")
        op.drop_table("instrument_event_fetch_state")

    if "instrument_event" in tables:
        op.drop_index("ix_instrument_event_inst_time_type", table_name="instrument_event")
        op.drop_index("ix_instrument_event_event_type", table_name="instrument_event")
        op.drop_index("ix_instrument_event_event_time", table_name="instrument_event")
        op.drop_index("ix_instrument_event_instrument_id", table_name="instrument_event")
        op.drop_table("instrument_event")

    postgresql.ENUM(name="eventtimehint").drop(bind, checkfirst=True)
    postgresql.ENUM(name="instrumenteventtype").drop(bind, checkfirst=True)
