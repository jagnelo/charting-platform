"""add provider symbol and identifiers

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-04-21 00:00:00.000000
"""

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op


revision: str = "f9a0b1c2d3e4"
down_revision: str | Sequence[str] | None = "e8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


identifier_type = postgresql.ENUM(
    "ISIN",
    "FIGI",
    "COMPOSITE_FIGI",
    "CUSIP",
    "SEDOL",
    "LEI",
    "INTERNAL",
    name="instrumentidentifiertype",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    postgresql.ENUM(
        "ISIN",
        "FIGI",
        "COMPOSITE_FIGI",
        "CUSIP",
        "SEDOL",
        "LEI",
        "INTERNAL",
        name="instrumentidentifiertype",
    ).create(bind, checkfirst=True)

    if "instrument" in tables:
        columns = {column["name"] for column in inspector.get_columns("instrument")}
        if "primary_identifier_type" not in columns:
            op.add_column("instrument", sa.Column("primary_identifier_type", sa.String(length=30), nullable=True))
        if "primary_identifier_value" not in columns:
            op.add_column("instrument", sa.Column("primary_identifier_value", sa.String(length=80), nullable=True))
        indexes = {index["name"] for index in inspector.get_indexes("instrument")}
        if "ix_instrument_primary_identifier_type" not in indexes:
            op.create_index("ix_instrument_primary_identifier_type", "instrument", ["primary_identifier_type"])
        if "ix_instrument_primary_identifier_value" not in indexes:
            op.create_index("ix_instrument_primary_identifier_value", "instrument", ["primary_identifier_value"])

    if "instrument_identifier" not in tables:
        op.create_table(
            "instrument_identifier",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("instrument_id", sa.Integer(), nullable=False),
            sa.Column("data_source_id", sa.Integer(), nullable=True),
            sa.Column("identifier_type", identifier_type, nullable=False),
            sa.Column("identifier_value", sa.String(length=80), nullable=False),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("extra_data", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"]),
            sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("identifier_type", "identifier_value", name="uq_instrument_identifier_type_value"),
        )
        op.create_index("ix_instrument_identifier_instrument_id", "instrument_identifier", ["instrument_id"])
        op.create_index("ix_instrument_identifier_data_source_id", "instrument_identifier", ["data_source_id"])
        op.create_index("ix_instrument_identifier_identifier_type", "instrument_identifier", ["identifier_type"])

    if "instrument_provider_symbol" not in tables:
        op.create_table(
            "instrument_provider_symbol",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("instrument_id", sa.Integer(), nullable=False),
            sa.Column("data_source_id", sa.Integer(), nullable=False),
            sa.Column("provider_symbol", sa.String(length=80), nullable=False),
            sa.Column("provider_exchange_code", sa.String(length=30), nullable=True),
            sa.Column("provider_instrument_type", sa.String(length=30), nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("extra_data", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"]),
            sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "data_source_id",
                "provider_symbol",
                "provider_exchange_code",
                name="uq_instrument_provider_symbol",
            ),
        )
        op.create_index("ix_instrument_provider_symbol_instrument_id", "instrument_provider_symbol", ["instrument_id"])
        op.create_index("ix_instrument_provider_symbol_data_source_id", "instrument_provider_symbol", ["data_source_id"])
        op.create_index("ix_instrument_provider_symbol_provider_symbol", "instrument_provider_symbol", ["provider_symbol"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "instrument_provider_symbol" in tables:
        op.drop_index("ix_instrument_provider_symbol_provider_symbol", table_name="instrument_provider_symbol")
        op.drop_index("ix_instrument_provider_symbol_data_source_id", table_name="instrument_provider_symbol")
        op.drop_index("ix_instrument_provider_symbol_instrument_id", table_name="instrument_provider_symbol")
        op.drop_table("instrument_provider_symbol")

    if "instrument_identifier" in tables:
        op.drop_index("ix_instrument_identifier_identifier_type", table_name="instrument_identifier")
        op.drop_index("ix_instrument_identifier_data_source_id", table_name="instrument_identifier")
        op.drop_index("ix_instrument_identifier_instrument_id", table_name="instrument_identifier")
        op.drop_table("instrument_identifier")

    if "instrument" in tables:
        indexes = {index["name"] for index in inspector.get_indexes("instrument")}
        if "ix_instrument_primary_identifier_value" in indexes:
            op.drop_index("ix_instrument_primary_identifier_value", table_name="instrument")
        if "ix_instrument_primary_identifier_type" in indexes:
            op.drop_index("ix_instrument_primary_identifier_type", table_name="instrument")
        columns = {column["name"] for column in inspector.get_columns("instrument")}
        if "primary_identifier_value" in columns:
            op.drop_column("instrument", "primary_identifier_value")
        if "primary_identifier_type" in columns:
            op.drop_column("instrument", "primary_identifier_type")

    identifier_type.drop(bind, checkfirst=True)
