"""phase2: synthetic instruments, screener alerts, managed watchlists, instrument stats

Revision ID: e1f2a3b4c5d6
Revises: 9d802b701062
Create Date: 2026-04-06 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = '9d802b701062'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # ── instrument: add synthetic fields ─────────────────────────────────────
    op.add_column('instrument', sa.Column('is_synthetic', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('instrument', sa.Column('expression', sa.Text(), nullable=True))

    # ── synthetic_constituent join table ─────────────────────────────────────
    op.create_table(
        'synthetic_constituent',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('synthetic_instrument_id', sa.Integer(), sa.ForeignKey('instrument.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('constituent_instrument_id', sa.Integer(), sa.ForeignKey('instrument.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ticker_alias', sa.String(50), nullable=False),
    )
    op.create_unique_constraint(
        'uq_synthetic_constituent',
        'synthetic_constituent',
        ['synthetic_instrument_id', 'ticker_alias'],
    )

    # ── instrument_stats table ────────────────────────────────────────────────
    op.create_table(
        'instrument_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('instrument_id', sa.Integer(), sa.ForeignKey('instrument.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('week52_high', sa.Numeric(18, 6), nullable=True),
        sa.Column('week52_low', sa.Numeric(18, 6), nullable=True),
        sa.Column('avg_volume_30d', sa.Numeric(20, 2), nullable=True),
        sa.Column('pe_ratio', sa.Numeric(12, 4), nullable=True),
        sa.Column('market_cap', sa.Numeric(22, 2), nullable=True),
        sa.Column('beta', sa.Numeric(10, 4), nullable=True),
        sa.Column('dividend_yield', sa.Numeric(10, 6), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── watchlist: add managed-watchlist fields ───────────────────────────────
    op.add_column('watchlist', sa.Column('is_managed', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('watchlist', sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('watchlist', sa.Column('screener_id', sa.Integer(), sa.ForeignKey('screener_definition.id', ondelete='SET NULL'), nullable=True))
    op.add_column('watchlist', sa.Column('last_screener_run_at', sa.DateTime(timezone=True), nullable=True))

    # ── watchlist_item: grace-period tracking ────────────────────────────────
    if 'watchlist_item' in existing_tables:
        watchlist_item_cols = {c['name'] for c in inspector.get_columns('watchlist_item')}
        if 'left_screener_at' not in watchlist_item_cols:
            op.add_column('watchlist_item', sa.Column('left_screener_at', sa.DateTime(timezone=True), nullable=True))

    # ── screener_alert table ─────────────────────────────────────────────────
    op.create_table(
        'screener_alert',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('screener_id', sa.Integer(), sa.ForeignKey('screener_definition.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('trigger_type', sa.String(10), nullable=False, server_default='both'),  # 'entered' | 'left' | 'both'
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),       # 'active' | 'triggered' | 'disabled'
        sa.Column('repeat', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('last_checked_run_id', sa.Integer(), sa.ForeignKey('screener_result.id', ondelete='SET NULL'), nullable=True),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('screener_alert')
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if 'watchlist_item' in existing_tables:
        watchlist_item_cols = {c['name'] for c in inspector.get_columns('watchlist_item')}
        if 'left_screener_at' in watchlist_item_cols:
            op.drop_column('watchlist_item', 'left_screener_at')
    op.drop_column('watchlist', 'last_screener_run_at')
    op.drop_column('watchlist', 'screener_id')
    op.drop_column('watchlist', 'is_locked')
    op.drop_column('watchlist', 'is_managed')
    op.drop_table('instrument_stats')
    op.drop_table('synthetic_constituent')
    op.drop_column('instrument', 'expression')
    op.drop_column('instrument', 'is_synthetic')
