"""add_indicator_cache_and_watchlist_item

Revision ID: c1a2b3d4e5f6
Revises: 87505586ba42
Create Date: 2026-04-03 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, None] = '87505586ba42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create indicator_cache table
    op.create_table(
        'indicator_cache',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('instrument_id', sa.Integer(), nullable=False),
        sa.Column('timeframe', sa.String(length=10), nullable=False),
        sa.Column('indicator_type', sa.String(length=50), nullable=False),
        sa.Column('params_hash', sa.String(length=32), nullable=False),
        sa.Column('params_json', sa.Text(), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_ts', sa.DateTime(timezone=True), nullable=True),
        sa.Column('series_json', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['instrument_id'], ['instrument.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'instrument_id', 'timeframe', 'indicator_type', 'params_hash',
            name='uq_indicator_cache_key',
        ),
    )
    op.create_index('ix_indicator_cache_instrument_id', 'indicator_cache', ['instrument_id'])

    # Migrate watchlist_instrument association table → watchlist_item ORM table
    # Check if old association table exists and drop it; create new watchlist_item table.
    # (If watchlist_item already exists from a previous migration attempt, skip creation.)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'watchlist_item' not in existing_tables:
        op.create_table(
            'watchlist_item',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('watchlist_id', sa.Integer(), nullable=False),
            sa.Column('instrument_id', sa.Integer(), nullable=False),
            sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('added_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('left_screener_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['instrument_id'], ['instrument.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['watchlist_id'], ['watchlist.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_watchlist_item_watchlist_id', 'watchlist_item', ['watchlist_id'])
    else:
        watchlist_item_cols = {c['name'] for c in inspector.get_columns('watchlist_item')}
        if 'left_screener_at' not in watchlist_item_cols:
            op.add_column(
                'watchlist_item',
                sa.Column('left_screener_at', sa.DateTime(timezone=True), nullable=True),
            )

    if 'watchlist_instrument' in existing_tables:
        op.drop_table('watchlist_instrument')

    # Ensure watchlist table has user_id column (add if missing)
    watchlist_cols = {c['name'] for c in inspector.get_columns('watchlist')}
    if 'user_id' not in watchlist_cols:
        op.add_column('watchlist', sa.Column('user_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'fk_watchlist_user_id', 'watchlist', 'user', ['user_id'], ['id'],
            ondelete='CASCADE',
        )
        op.create_index('ix_watchlist_user_id', 'watchlist', ['user_id'])

    if 'is_default' not in watchlist_cols:
        op.add_column(
            'watchlist',
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        )


def downgrade() -> None:
    op.drop_table('indicator_cache')
    op.drop_table('watchlist_item')
