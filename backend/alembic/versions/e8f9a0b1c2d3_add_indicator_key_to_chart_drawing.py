"""add indicator_key to chart_drawing

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-04-20 00:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'chart_drawing',
        sa.Column('indicator_key', sa.String(100), nullable=True),
    )
    op.create_index('ix_chart_drawing_indicator_key', 'chart_drawing', ['indicator_key'])


def downgrade() -> None:
    op.drop_index('ix_chart_drawing_indicator_key', table_name='chart_drawing')
    op.drop_column('chart_drawing', 'indicator_key')
