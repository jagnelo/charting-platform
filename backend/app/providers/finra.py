"""FINRA short-interest adapter.

FINRA publishes consolidated short-interest data through a public API, but
endpoints and access policies can evolve.  The URL is configurable and parsing
is intentionally schema-tolerant; unknown rows are preserved in raw_payload.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings
from app.providers.base import ShortInterestRecord

logger = logging.getLogger(__name__)


class FINRAProvider:
    name = "finra"
    base_url = "https://api.finra.org"
    description = "FINRA consolidated short-interest and market datasets"

    def fetch_short_interest(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[ShortInterestRecord]:
        endpoint = str(getattr(settings, "FINRA_SHORT_INTEREST_URL", "") or "").strip()
        if not endpoint:
            logger.info("finra short-interest endpoint is not configured; provider remains disabled")
            return []
        payload = {
            "symbol": str(symbol).strip().upper(),
            "startDate": start.isoformat() if start else None,
            "endDate": end.isoformat() if end else None,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        try:
            response = httpx.post(endpoint, json=payload, timeout=30)
            response.raise_for_status()
            raw = response.json()
        except Exception as exc:
            logger.warning("finra short-interest request failed: %s", exc)
            return []
        rows = raw.get("data", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            return []
        result: list[ShortInterestRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            settlement = _parse_date(row.get("settlementDate") or row.get("settlement_date"))
            if settlement is None:
                continue
            result.append(
                ShortInterestRecord(
                    settlement_date=settlement,
                    publication_date=_parse_date(row.get("publicationDate") or row.get("publication_date")),
                    short_position=_decimal(row.get("shortPosition") or row.get("short_position")),
                    short_percent_float=_decimal(row.get("shortPercentFloat") or row.get("short_percent_float")),
                    days_to_cover=_decimal(row.get("daysToCover") or row.get("days_to_cover")),
                    source_identifier=str(row.get("issueIdentifier") or row.get("sourceIdentifier") or "") or None,
                    raw_payload=row,
                )
            )
        return result


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except Exception:
        return None
