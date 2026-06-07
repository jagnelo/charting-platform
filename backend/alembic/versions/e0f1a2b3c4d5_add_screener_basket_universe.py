"""add screener basket universe

Revision ID: e0f1a2b3c4d5
Revises: d0e1f2a3b4d5
Create Date: 2026-06-05 21:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: str | None = "d0e1f2a3b4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("screener_definition")}
    if "universe_basket_id" not in columns:
        op.add_column(
            "screener_definition",
            sa.Column("universe_basket_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_screener_definition_universe_basket_id",
            "screener_definition",
            "basket",
            ["universe_basket_id"],
            ["id"],
            ondelete="SET NULL",
        )
    indexes = {index["name"] for index in inspector.get_indexes("screener_definition")}
    if "ix_screener_definition_universe_basket_id" not in indexes:
        op.create_index(
            "ix_screener_definition_universe_basket_id",
            "screener_definition",
            ["universe_basket_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("screener_definition")}
    if "universe_basket_id" in columns:
        op.drop_index(
            "ix_screener_definition_universe_basket_id",
            table_name="screener_definition",
        )
        op.drop_constraint(
            "fk_screener_definition_universe_basket_id",
            "screener_definition",
            type_="foreignkey",
        )
        op.drop_column("screener_definition", "universe_basket_id")
