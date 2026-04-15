"""
Bar transformation service.

Converts standard OHLCV bars into alternative bar types for non-time-based charts.
All transformations are server-side so that screeners and alerts can eventually
operate on transformed series.

Supported types:
  - heikin_ashi   : Heikin-Ashi smoothed candles
  - ohlc          : Standard OHLC bars (pass-through, same schema as candles)
  - area          : Close-only (pass-through, used with area plugin)
  - baseline      : Close-only with a baseline reference (pass-through)
  - renko         : Renko bricks (price movement only, no time axis)
  - kagi          : Kagi reversal lines
  - point_figure  : Point & Figure boxes

Every function accepts a list of ORM bar objects (with .ts, .open, .high, .low,
.close, .volume attributes) and returns a list of dicts matching OHLCVBarOut schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# ── Helpers ───────────────────────────────────────────────────────────────────


def _bar_dict(
    ts: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 0.0,
    is_adjusted: bool = False,
) -> dict[str, Any]:
    return {
        "ts": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "is_adjusted": is_adjusted,
    }


# ── Transform functions ───────────────────────────────────────────────────────


def transform_heikin_ashi(bars: list) -> list[dict]:
    """
    Heikin-Ashi candles:
      HA_Close = (O + H + L + C) / 4
      HA_Open  = (prev_HA_Open + prev_HA_Close) / 2  (first bar uses real open)
      HA_High  = max(H, HA_Open, HA_Close)
      HA_Low   = min(L, HA_Open, HA_Close)
    """
    if not bars:
        return []

    result = []
    prev_ha_open = float(bars[0].open)
    prev_ha_close = (float(bars[0].open) + float(bars[0].high) + float(bars[0].low) + float(bars[0].close)) / 4

    for bar in bars:
        o = float(bar.open)
        h = float(bar.high)
        lo = float(bar.low)
        c = float(bar.close)
        vol = float(bar.volume or 0)

        ha_close = (o + h + lo + c) / 4
        ha_open = (prev_ha_open + prev_ha_close) / 2
        ha_high = max(h, ha_open, ha_close)
        ha_low = min(lo, ha_open, ha_close)

        result.append(_bar_dict(bar.ts, ha_open, ha_high, ha_low, ha_close, vol, bool(bar.is_adjusted)))

        prev_ha_open = ha_open
        prev_ha_close = ha_close

    return result


def transform_ohlc(bars: list) -> list[dict]:
    """Pass-through for OHLC bar rendering (same as standard candles)."""
    return [
        _bar_dict(b.ts, float(b.open), float(b.high), float(b.low), float(b.close), float(b.volume or 0), bool(b.is_adjusted))
        for b in bars
    ]


def transform_area(bars: list) -> list[dict]:
    """Area chart — only close matters; O/H/L are set to close for consistency."""
    return [
        _bar_dict(b.ts, float(b.close), float(b.close), float(b.close), float(b.close), float(b.volume or 0), bool(b.is_adjusted))
        for b in bars
    ]


def transform_baseline(bars: list) -> list[dict]:
    """Baseline chart — pass through, rendering layer handles baseline reference."""
    return transform_area(bars)


def transform_renko(bars: list, brick_size: float | None = None) -> list[dict]:
    """
    Renko bricks.

    brick_size: fixed ATR-style size.  If None, auto-calculated as ~0.3% of the
    first bar's close (coarse default that the user can override via params).

    Each brick is a dict with the standard OHLCV schema, but 'ts' refers to the
    source bar that completed the brick (for indicator cross-referencing).
    """
    if not bars:
        return []

    first_close = float(bars[0].close)
    if brick_size is None or brick_size <= 0:
        brick_size = max(first_close * 0.003, 0.01)

    result: list[dict] = []
    current_high = first_close + brick_size
    current_low = first_close - brick_size
    direction = 0  # 1 = up, -1 = down

    for bar in bars:
        close = float(bar.close)
        ts = bar.ts
        vol = float(bar.volume or 0)
        adj = bool(bar.is_adjusted)

        # Check for multiple bricks in one source bar
        while True:
            if close >= current_high:
                brick_open = current_low if direction <= 0 else current_high - brick_size
                brick_close = current_low + brick_size if direction <= 0 else current_high
                # Snap to grid
                brick_open = current_high - brick_size
                brick_close = current_high
                result.append(_bar_dict(ts, brick_open, brick_close, brick_open, brick_close, vol, adj))
                current_low = current_high - brick_size
                current_high = current_high + brick_size
                direction = 1
            elif close <= current_low:
                brick_open = current_high if direction >= 0 else current_low + brick_size
                brick_close = current_high - brick_size if direction >= 0 else current_low
                brick_open = current_low + brick_size
                brick_close = current_low
                result.append(_bar_dict(ts, brick_open, brick_open, brick_close, brick_close, vol, adj))
                current_high = current_low + brick_size
                current_low = current_low - brick_size
                direction = -1
            else:
                break

    return result


def transform_kagi(bars: list, reversal_pct: float = 1.0) -> list[dict]:
    """
    Kagi lines.

    reversal_pct: minimum percentage reversal to switch direction (default 1%).

    Returns synthetic bars where each entry represents one kagi segment.
    open/close represent the start/end price; high = max(o,c); low = min(o,c).
    """
    if not bars:
        return []

    closes = [float(b.close) for b in bars]
    result: list[dict] = []

    reversal_amt = closes[0] * (reversal_pct / 100)
    direction = 1  # 1 = up, -1 = down
    last_price = closes[0]
    segment_start = closes[0]
    segment_ts = bars[0].ts

    for i, bar in enumerate(bars[1:], start=1):
        c = closes[i]
        ts = bar.ts
        vol = float(bar.volume or 0)
        adj = bool(bar.is_adjusted)

        if direction == 1:
            if c < last_price - reversal_amt:
                # Reversal
                result.append(_bar_dict(segment_ts, segment_start, max(segment_start, last_price), min(segment_start, last_price), last_price, vol, adj))
                direction = -1
                segment_start = last_price
                segment_ts = ts
        else:
            if c > last_price + reversal_amt:
                # Reversal
                result.append(_bar_dict(segment_ts, segment_start, max(segment_start, last_price), min(segment_start, last_price), last_price, vol, adj))
                direction = 1
                segment_start = last_price
                segment_ts = ts

        last_price = c

    # Flush final segment
    if bars:
        result.append(_bar_dict(segment_ts, segment_start, max(segment_start, last_price), min(segment_start, last_price), last_price, 0, False))

    return result


def transform_point_figure(bars: list, box_size: float | None = None, reversal: int = 3) -> list[dict]:
    """
    Point & Figure boxes.

    box_size: price per box. Auto-calculated as ~0.5% of first close if None.
    reversal: number of boxes required to reverse direction.

    Returns synthetic bars — each entry is one P&F column (X = up, O = down).
    open/close span the column; high/low match open/close.
    """
    if not bars:
        return []

    first_close = float(bars[0].close)
    if box_size is None or box_size <= 0:
        box_size = max(first_close * 0.005, 0.01)

    import math
    result: list[dict] = []

    def _floor_box(price: float) -> float:
        return math.floor(price / box_size) * box_size

    current_price = _floor_box(first_close)
    direction = 0  # 0 = undecided, 1 = X (up), -1 = O (down)
    column_start = current_price
    column_ts = bars[0].ts

    for bar in bars[1:]:
        close = float(bar.close)
        ts = bar.ts
        vol = float(bar.volume or 0)
        adj = bool(bar.is_adjusted)

        new_price = _floor_box(close)
        boxes = round((new_price - current_price) / box_size)

        if direction == 0:
            if boxes >= 1:
                direction = 1
                column_start = current_price
                column_ts = ts
                current_price = new_price
            elif boxes <= -1:
                direction = -1
                column_start = current_price
                column_ts = ts
                current_price = new_price
        elif direction == 1:
            if boxes >= 1:
                current_price = new_price
            elif boxes <= -reversal:
                # Record completed X column
                result.append(_bar_dict(column_ts, column_start, max(column_start, current_price), min(column_start, current_price), current_price, vol, adj))
                direction = -1
                column_start = current_price
                column_ts = ts
                current_price = new_price
        else:  # direction == -1
            if boxes <= -1:
                current_price = new_price
            elif boxes >= reversal:
                # Record completed O column
                result.append(_bar_dict(column_ts, column_start, max(column_start, current_price), min(column_start, current_price), current_price, vol, adj))
                direction = 1
                column_start = current_price
                column_ts = ts
                current_price = new_price

    # Flush final column
    if bars and direction != 0:
        result.append(_bar_dict(column_ts, column_start, max(column_start, current_price), min(column_start, current_price), current_price, 0, False))

    return result


# ── Dispatcher ────────────────────────────────────────────────────────────────

TRANSFORM_REGISTRY = {
    "heikin_ashi": transform_heikin_ashi,
    "ohlc": transform_ohlc,
    "area": transform_area,
    "baseline": transform_baseline,
    "renko": transform_renko,
    "kagi": transform_kagi,
    "point_figure": transform_point_figure,
}


def apply_transform(bar_type: str, bars: list, params: dict | None = None) -> list[dict]:
    """
    Apply a bar transformation by type string.

    Raises ValueError for unknown types.
    """
    if bar_type not in TRANSFORM_REGISTRY:
        raise ValueError(
            f"Unknown bar type: '{bar_type}'. Available: {list(TRANSFORM_REGISTRY)}"
        )
    fn = TRANSFORM_REGISTRY[bar_type]
    resolved: dict = {}
    if params:
        resolved = {k: v for k, v in params.items() if v is not None}
    return fn(bars, **resolved)
