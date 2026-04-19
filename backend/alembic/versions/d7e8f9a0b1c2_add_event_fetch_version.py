"""add event fetch state version

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-04-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: str | None = "c6d7e8f9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "instrument_event_fetch_state" not in tables:
        return

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
    if "instrument_event_fetch_state" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("instrument_event_fetch_state")}
    if "fetch_version" in columns:
        op.drop_column("instrument_event_fetch_state", "fetch_version")
