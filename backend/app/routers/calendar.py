"""
Economic calendar endpoint.

Extracts event data from yfinance for a given symbol:
  - Earnings dates (historical + estimates)
  - Dividends (historical)
  - Splits
  - Calendar events (next earnings, ex-dividend date, etc.)

Returns a unified list of CalendarEvent objects sorted by date.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarEvent(BaseModel):
    date: str          # ISO date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)
    event_type: str    # 'earnings' | 'dividend' | 'split' | 'ex_dividend' | 'earnings_estimate'
    symbol: str
    title: str
    value: float | None = None    # EPS estimate, dividend amount, split ratio, etc.
    actual: float | None = None   # Actual EPS (if reported)
    currency: str | None = None
    is_estimate: bool = False


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return None if (f != f) else f  # NaN check
    except (TypeError, ValueError):
        return None


def _to_iso(dt) -> str | None:
    """Convert various date types to ISO string."""
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        s = dt.isoformat()
        # Ensure timezone suffix for datetime objects
        if isinstance(dt, datetime) and dt.tzinfo is None:
            s += "Z"
        return s
    return str(dt)


def _fetch_calendar_sync(symbol: str) -> list[dict]:
    """Synchronous yfinance fetch — runs in a thread pool."""
    ticker = yf.Ticker(symbol)
    events: list[dict] = []

    # ── Next calendar events (earnings window, ex-div, etc.) ─────────────────
    try:
        cal = ticker.calendar
        if isinstance(cal, dict):
            # yfinance ≥ 0.2 returns a dict
            earnings_date = cal.get("Earnings Date")
            if earnings_date:
                dates = earnings_date if isinstance(earnings_date, list) else [earnings_date]
                for d in dates:
                    iso = _to_iso(d)
                    if iso:
                        events.append({
                            "date": iso[:10],
                            "event_type": "earnings_estimate",
                            "symbol": symbol,
                            "title": f"{symbol} Earnings (estimated)",
                            "is_estimate": True,
                            "value": _safe_float(cal.get("Earnings Average")),
                            "actual": None,
                        })

            ex_div = cal.get("Ex-Dividend Date")
            if ex_div:
                iso = _to_iso(ex_div)
                if iso:
                    events.append({
                        "date": iso[:10],
                        "event_type": "ex_dividend",
                        "symbol": symbol,
                        "title": f"{symbol} Ex-Dividend",
                        "is_estimate": False,
                        "value": _safe_float(cal.get("Dividend Amount")),
                        "actual": None,
                    })
    except Exception as e:
        logger.debug("calendar fetch failed for %s: %s", symbol, e)

    # ── Historical earnings ───────────────────────────────────────────────────
    try:
        earnings = ticker.earnings_dates
        if earnings is not None and not earnings.empty:
            for idx, row in earnings.iterrows():
                iso = _to_iso(idx)
                if not iso:
                    continue
                eps_estimate = _safe_float(row.get("EPS Estimate"))
                eps_actual = _safe_float(row.get("Reported EPS"))
                is_estimate = eps_actual is None
                events.append({
                    "date": iso[:10],
                    "event_type": "earnings_estimate" if is_estimate else "earnings",
                    "symbol": symbol,
                    "title": f"{symbol} Earnings",
                    "is_estimate": is_estimate,
                    "value": eps_estimate,
                    "actual": eps_actual,
                })
    except Exception as e:
        logger.debug("earnings_dates fetch failed for %s: %s", symbol, e)

    # ── Dividends ─────────────────────────────────────────────────────────────
    try:
        divs = ticker.dividends
        if divs is not None and not divs.empty:
            for idx, amount in divs.items():
                iso = _to_iso(idx)
                if not iso:
                    continue
                events.append({
                    "date": iso[:10],
                    "event_type": "dividend",
                    "symbol": symbol,
                    "title": f"{symbol} Dividend",
                    "is_estimate": False,
                    "value": _safe_float(amount),
                    "actual": _safe_float(amount),
                })
    except Exception as e:
        logger.debug("dividends fetch failed for %s: %s", symbol, e)

    # ── Splits ────────────────────────────────────────────────────────────────
    try:
        splits = ticker.splits
        if splits is not None and not splits.empty:
            for idx, ratio in splits.items():
                iso = _to_iso(idx)
                if not iso:
                    continue
                events.append({
                    "date": iso[:10],
                    "event_type": "split",
                    "symbol": symbol,
                    "title": f"{symbol} Stock Split ({ratio:.0f}:1)",
                    "is_estimate": False,
                    "value": _safe_float(ratio),
                    "actual": _safe_float(ratio),
                })
    except Exception as e:
        logger.debug("splits fetch failed for %s: %s", symbol, e)

    # Deduplicate by (date, event_type) — keep last (most specific) entry
    seen: dict[tuple, dict] = {}
    for ev in events:
        key = (ev["date"], ev["event_type"])
        seen[key] = ev

    # Sort by date descending (most recent first)
    result = sorted(seen.values(), key=lambda e: e["date"], reverse=True)
    return result


@router.get("/instruments/{symbol}/calendar", response_model=list[CalendarEvent])
async def get_instrument_calendar(
    symbol: str,
    current_user: User = Depends(get_current_user),
):
    """
    Return economic calendar events for a symbol sourced from Yahoo Finance.
    Includes: earnings (historical + estimates), dividends, splits, ex-dividend dates.
    """
    try:
        raw = await asyncio.get_event_loop().run_in_executor(
            None, _fetch_calendar_sync, symbol.upper()
        )
        return [CalendarEvent(**ev) for ev in raw]
    except Exception as e:
        logger.error("Calendar fetch error for %s: %s", symbol, e)
        raise HTTPException(500, f"Failed to fetch calendar for {symbol}: {e}")
