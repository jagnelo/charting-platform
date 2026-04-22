"""add provider capabilities and field provenance

Revision ID: a5b6c7d8e9f0
Revises: f9a0b1c2d3e4
Create Date: 2026-04-22 17:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "a5b6c7d8e9f0"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    return column_name in columns


def upgrade() -> None:
    additions: list[tuple[str, str, sa.Column]] = [
        (
            "data_source",
            "supported_capabilities",
            sa.Column("supported_capabilities", sa.JSON(), nullable=True),
        ),
        (
            "instrument",
            "field_provenance",
            sa.Column("field_provenance", sa.JSON(), nullable=True),
        ),
        (
            "equity_detail",
            "field_provenance",
            sa.Column("field_provenance", sa.JSON(), nullable=True),
        ),
        (
            "future_detail",
            "field_provenance",
            sa.Column("field_provenance", sa.JSON(), nullable=True),
        ),
        (
            "option_detail",
            "field_provenance",
            sa.Column("field_provenance", sa.JSON(), nullable=True),
        ),
        (
            "forex_detail",
            "field_provenance",
            sa.Column("field_provenance", sa.JSON(), nullable=True),
        ),
        (
            "instrument_stats",
            "field_provenance",
            sa.Column("field_provenance", sa.JSON(), nullable=True),
        ),
    ]

    for table_name, column_name, column in additions:
        if not _has_column(table_name, column_name):
            op.add_column(table_name, column)


def downgrade() -> None:
    removals = [
        ("instrument_stats", "field_provenance"),
        ("forex_detail", "field_provenance"),
        ("option_detail", "field_provenance"),
        ("future_detail", "field_provenance"),
        ("equity_detail", "field_provenance"),
        ("instrument", "field_provenance"),
        ("data_source", "supported_capabilities"),
    ]

    for table_name, column_name in removals:
        if _has_column(table_name, column_name):
            op.drop_column(table_name, column_name)
