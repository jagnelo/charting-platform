"""add basket composition snapshots

Revision ID: f0a1b2c3d4e5
Revises: e0f1a2b3c4d5
Create Date: 2026-06-06 17:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "e0f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_once(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "basket_snapshot" not in tables:
        op.create_table(
            "basket_snapshot",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("basket_id", sa.Integer(), nullable=False),
            sa.Column("composition_date", sa.Date(), nullable=False),
            sa.Column("known_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_type", sa.String(length=40), nullable=False),
            sa.Column("source_snapshot_id", sa.Integer(), nullable=True),
            sa.Column("member_count", sa.Integer(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["basket_id"], ["basket.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["source_snapshot_id"],
                ["etf_holdings_snapshot.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    for name, cols in [
        ("ix_basket_snapshot_basket_id", ["basket_id"]),
        ("ix_basket_snapshot_composition_date", ["composition_date"]),
        ("ix_basket_snapshot_known_at", ["known_at"]),
        ("ix_basket_snapshot_source_snapshot_id", ["source_snapshot_id"]),
        ("ix_basket_snapshot_basket_date", ["basket_id", "composition_date"]),
        ("ix_basket_snapshot_source", ["basket_id", "source_snapshot_id"]),
    ]:
        _create_index_once(name, "basket_snapshot", cols)

    tables = set(sa.inspect(bind).get_table_names())
    if "basket_snapshot_member" not in tables:
        op.create_table(
            "basket_snapshot_member",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("basket_snapshot_id", sa.Integer(), nullable=False),
            sa.Column("instrument_id", sa.Integer(), nullable=False),
            sa.Column("source_holding_id", sa.Integer(), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("weight", sa.Numeric(precision=18, scale=8), nullable=True),
            sa.Column("label", sa.String(length=120), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["basket_snapshot_id"],
                ["basket_snapshot.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_holding_id"], ["etf_holding.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "basket_snapshot_id",
                "instrument_id",
                name="uq_basket_snapshot_member_instrument",
            ),
        )
    for name, cols in [
        ("ix_basket_snapshot_member_basket_snapshot_id", ["basket_snapshot_id"]),
        ("ix_basket_snapshot_member_instrument_id", ["instrument_id"]),
        ("ix_basket_snapshot_member_source_holding_id", ["source_holding_id"]),
        ("ix_basket_snapshot_member_weight", ["basket_snapshot_id", "weight"]),
    ]:
        _create_index_once(name, "basket_snapshot_member", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ["basket_snapshot_member", "basket_snapshot"]:
        if inspector.has_table(table):
            op.drop_table(table)
