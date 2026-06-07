"""add baskets

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-05 18:58:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "basket" not in tables:
        op.create_table(
            "basket",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source_type", sa.String(length=40), nullable=False),
            sa.Column("weighting_scheme", sa.String(length=40), nullable=False),
            sa.Column("rebalance_frequency", sa.String(length=40), nullable=True),
            sa.Column("classification_mode", sa.String(length=40), nullable=True),
            sa.Column("sector", sa.String(length=120), nullable=True),
            sa.Column("industry", sa.String(length=160), nullable=True),
            sa.Column("source_etf_profile_id", sa.Integer(), nullable=True),
            sa.Column("source_snapshot_id", sa.Integer(), nullable=True),
            sa.Column("composition_date", sa.Date(), nullable=True),
            sa.Column("is_system_managed", sa.Boolean(), nullable=False),
            sa.Column("is_read_only", sa.Boolean(), nullable=False),
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
            sa.ForeignKeyConstraint(["source_etf_profile_id"], ["etf_profile.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["source_snapshot_id"],
                ["etf_holdings_snapshot.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_snapshot_id"),
            sa.UniqueConstraint("user_id", "name", name="uq_basket_user_name"),
        )
        op.create_index("ix_basket_composition_date", "basket", ["composition_date"], unique=False)
        op.create_index("ix_basket_industry", "basket", ["industry"], unique=False)
        op.create_index("ix_basket_sector", "basket", ["sector"], unique=False)
        op.create_index("ix_basket_source_etf_profile_id", "basket", ["source_etf_profile_id"], unique=False)
        op.create_index("ix_basket_source_type", "basket", ["source_type"], unique=False)
        op.create_index("ix_basket_user_id", "basket", ["user_id"], unique=False)
        op.create_index("ix_basket_user_source", "basket", ["user_id", "source_type"], unique=False)
        op.create_index("ix_basket_weighting_scheme", "basket", ["weighting_scheme"], unique=False)

    tables = set(sa.inspect(bind).get_table_names())
    if "basket_member" not in tables:
        op.create_table(
            "basket_member",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("basket_id", sa.Integer(), nullable=False),
            sa.Column("instrument_id", sa.Integer(), nullable=False),
            sa.Column("source_holding_id", sa.Integer(), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("weight", sa.Numeric(precision=18, scale=8), nullable=True),
            sa.Column("label", sa.String(length=120), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
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
            sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_holding_id"], ["etf_holding.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("basket_id", "instrument_id", name="uq_basket_member_instrument"),
        )
        op.create_index("ix_basket_member_basket_id", "basket_member", ["basket_id"], unique=False)
        op.create_index("ix_basket_member_instrument_id", "basket_member", ["instrument_id"], unique=False)
        op.create_index("ix_basket_member_source_holding_id", "basket_member", ["source_holding_id"], unique=False)
        op.create_index("ix_basket_member_weight", "basket_member", ["basket_id", "weight"], unique=False)


def downgrade() -> None:
    op.drop_table("basket_member")
    op.drop_table("basket")
