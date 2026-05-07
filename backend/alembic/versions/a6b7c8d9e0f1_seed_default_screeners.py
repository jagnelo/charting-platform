"""Seed default screeners and managed watchlists for all existing users

Revision ID: a6b7c8d9e0f1
Revises: 19f2aa877634
Create Date: 2026-04-07 00:00:00.000000

"""
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a6b7c8d9e0f1'
down_revision: str | None = '19f2aa877634'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------
# Default screener definitions.
# Each entry: (name, description, timeframe, conditions_dict)
#
# Conditions format matches the screener engine:
#   { "operator": "AND", "conditions": [...] }
# Individual condition keys: type, op (not "condition"), value, indicator, etc.
# ---------------------------------------------------------------------------
_DEFAULTS = [
    (
        "RSI Oversold",
        "RSI(14) below 30 — potential mean-reversion bounce candidates.",
        "D1",
        {
            "operator": "AND",
            "conditions": [
                {
                    "type": "indicator_threshold",
                    "indicator": "rsi",
                    "params": {"period": 14},
                    "op": "lt",
                    "value": 30,
                }
            ],
        },
    ),
    (
        "RSI Overbought",
        "RSI(14) above 70 — overextended or sustained momentum plays.",
        "D1",
        {
            "operator": "AND",
            "conditions": [
                {
                    "type": "indicator_threshold",
                    "indicator": "rsi",
                    "params": {"period": 14},
                    "op": "gt",
                    "value": 70,
                }
            ],
        },
    ),
    (
        "Golden Cross",
        "50-day SMA has crossed above the 200-day SMA — classic bullish trend signal.",
        "D1",
        {
            "operator": "AND",
            "conditions": [
                {
                    "type": "indicator_cross",
                    "indicator_a": {"type": "sma", "params": {"period": 50}},
                    "indicator_b": {"type": "sma", "params": {"period": 200}},
                    "op": "crosses_above",
                }
            ],
        },
    ),
    (
        "Death Cross",
        "50-day SMA has crossed below the 200-day SMA — classic bearish trend signal.",
        "D1",
        {
            "operator": "AND",
            "conditions": [
                {
                    "type": "indicator_cross",
                    "indicator_a": {"type": "sma", "params": {"period": 50}},
                    "indicator_b": {"type": "sma", "params": {"period": 200}},
                    "op": "crosses_below",
                }
            ],
        },
    ),
    (
        "New 52-Week High",
        "Instruments at their highest weekly close in the past 52 weeks.",
        "W1",
        {
            "operator": "AND",
            "conditions": [
                {"type": "week52_new_high"}
            ],
        },
    ),
    (
        "New 52-Week Low",
        "Instruments at their lowest weekly close in the past 52 weeks.",
        "W1",
        {
            "operator": "AND",
            "conditions": [
                {"type": "week52_new_low"}
            ],
        },
    ),
    (
        "Strong Daily Gainers",
        "Up more than 3% on the day — momentum movers.",
        "D1",
        {
            "operator": "AND",
            "conditions": [
                {"type": "performance", "period": "1D", "op": "gt", "value": 0.03}
            ],
        },
    ),
    (
        "Strong Daily Losers",
        "Down more than 3% on the day — potential oversold or high-volatility names.",
        "D1",
        {
            "operator": "AND",
            "conditions": [
                {"type": "performance", "period": "1D", "op": "lt", "value": -0.03}
            ],
        },
    ),
    (
        "Near 52-Week High",
        "Within 5% of the 52-week high — breakout watch candidates.",
        "W1",
        {
            "operator": "AND",
            "conditions": [
                {"type": "pct_from_52w_high", "op": "lte", "value": 0.05}
            ],
        },
    ),
    (
        "Deep 52-Week Discount",
        "More than 20% below the 52-week high — deep pullback or value territory.",
        "W1",
        {
            "operator": "AND",
            "conditions": [
                {"type": "pct_from_52w_high", "op": "gte", "value": 0.20}
            ],
        },
    ),
    (
        "RSI Momentum Up",
        "RSI(14) crossing above 50 — trend turning bullish.",
        "D1",
        {
            "operator": "AND",
            "conditions": [
                {
                    "type": "indicator_threshold",
                    "indicator": "rsi",
                    "params": {"period": 14},
                    "op": "crosses_above",
                    "value": 50,
                }
            ],
        },
    ),
    (
        "Large Cap",
        "Market capitalisation above $10 billion.",
        "D1",
        {
            "operator": "AND",
            "conditions": [
                {
                    "type": "stats_filter",
                    "field": "market_cap",
                    "op": "gt",
                    "value": 10_000_000_000,
                }
            ],
        },
    ),
    (
        "Strong YTD Performers",
        "Up more than 20% year-to-date.",
        "D1",
        {
            "operator": "AND",
            "conditions": [
                {"type": "performance", "period": "YTD", "op": "gt", "value": 0.20}
            ],
        },
    ),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Fetch all existing user IDs
    user_ids = [row[0] for row in conn.execute(sa.text('SELECT id FROM "user"')).fetchall()]

    for uid in user_ids:
        for (name, description, timeframe, conditions) in _DEFAULTS:
            result = conn.execute(
                sa.text(
                    """
                    INSERT INTO screener_definition
                        (user_id, name, description, universe_type, timeframe, conditions,
                         schedule, is_active, created_at, updated_at)
                    VALUES
                        (:uid, :name, :desc, 'all', :tf, CAST(:conds AS jsonb),
                         NULL, TRUE, NOW(), NOW())
                    RETURNING id
                    """
                ),
                {
                    "uid": uid,
                    "name": name,
                    "desc": description,
                    "tf": timeframe,
                    "conds": json.dumps(conditions),
                },
            )
            screener_id = result.fetchone()[0]

            conn.execute(
                sa.text(
                    """
                    INSERT INTO watchlist
                        (user_id, name, description, is_default, is_managed, is_locked,
                         screener_id, created_at, updated_at)
                    VALUES
                        (:uid, :name, :desc, FALSE, TRUE, FALSE,
                         :screener_id, NOW(), NOW())
                    """
                ),
                {
                    "uid": uid,
                    "name": name,
                    "desc": description,
                    "screener_id": screener_id,
                },
            )


def downgrade() -> None:
    conn = op.get_bind()
    names = [d[0] for d in _DEFAULTS]
    for name in names:
        conn.execute(
            sa.text(
                """
                DELETE FROM watchlist
                WHERE is_managed = TRUE
                  AND screener_id IN (
                      SELECT id FROM screener_definition WHERE name = :name
                  )
                """
            ),
            {"name": name},
        )
        conn.execute(
            sa.text("DELETE FROM screener_definition WHERE name = :name"),
            {"name": name},
        )
