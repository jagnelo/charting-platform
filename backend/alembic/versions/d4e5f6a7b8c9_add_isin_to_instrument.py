"""add isin to instrument

Revision ID: d4e5f6a7b8c9
Revises: c1a2b3d4e5f6
Create Date: 2026-04-05 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c1a2b3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('instrument', sa.Column('isin', sa.String(20), nullable=True))
    # Partial unique index: enforce uniqueness only where isin IS NOT NULL
    op.create_index(
        'ix_instrument_isin_unique',
        'instrument',
        ['isin'],
        unique=True,
        postgresql_where=sa.text('isin IS NOT NULL'),
    )
    # Standard index for fast lookups
    op.create_index('ix_instrument_isin', 'instrument', ['isin'])


def downgrade() -> None:
    op.drop_index('ix_instrument_isin', table_name='instrument')
    op.drop_index('ix_instrument_isin_unique', table_name='instrument')
    op.drop_column('instrument', 'isin')
