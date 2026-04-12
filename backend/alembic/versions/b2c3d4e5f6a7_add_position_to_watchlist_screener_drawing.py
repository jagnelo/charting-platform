"""Add position column to watchlist, screener_definition, chart_drawing

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-11 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('watchlist', sa.Column('position', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('screener_definition', sa.Column('position', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('chart_drawing', sa.Column('position', sa.Integer(), nullable=False, server_default='0'))

    # Initialise positions to match current creation order within each user's scope
    op.execute("""
        UPDATE watchlist w
        SET position = sub.rn - 1
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at) AS rn
            FROM watchlist
        ) sub
        WHERE w.id = sub.id
    """)

    op.execute("""
        UPDATE screener_definition sd
        SET position = sub.rn - 1
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at) AS rn
            FROM screener_definition
        ) sub
        WHERE sd.id = sub.id
    """)

    op.execute("""
        UPDATE chart_drawing cd
        SET position = sub.rn - 1
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id, instrument_id ORDER BY created_at) AS rn
            FROM chart_drawing
        ) sub
        WHERE cd.id = sub.id
    """)


def downgrade() -> None:
    op.drop_column('watchlist', 'position')
    op.drop_column('screener_definition', 'position')
    op.drop_column('chart_drawing', 'position')
