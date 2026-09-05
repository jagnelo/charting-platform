"""FINRA short-interest adapter.

FINRA publishes consolidated short-interest data through a public API, but
endpoints and access policies can evolve.  The URL is configurable and parsing
is intentionally schema-tolerant; unknown rows are preserved in raw_payload.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings
from app.providers.base import ShortInterestRecord
from app.providers.errors import ProviderNotConfiguredError

logger = logging.getLogger(__name__)

_token_cache: tuple[str, datetime] | None = None


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
        client_id = str(getattr(settings, "FINRA_CLIENT_ID", "") or "").strip()
        client_secret = str(getattr(settings, "FINRA_CLIENT_SECRET", "") or "").strip()
        if not client_id or not client_secret:
            raise ProviderNotConfiguredError(
                "finra requires FINRA_CLIENT_ID and FINRA_CLIENT_SECRET; "
                "FINRA's current API is OAuth-authenticated"
            )
        token = _access_token(client_id, client_secret)
        endpoint = str(getattr(settings, "FINRA_SHORT_INTEREST_URL", "") or "").strip()
        if not endpoint:
            endpoint = (
                str(getattr(settings, "FINRA_API_BASE_URL", self.base_url) or self.base_url).rstrip("/")
                + "/data/group/otcMarket/name/consolidatedShortInterest"
            )
        filters: list[dict[str, Any]] = [
            {
                "fieldName": "symbolCode",
                "compareType": "EQUAL",
                "fieldValue": str(symbol).strip().upper(),
            }
        ]
        if start:
            filters.append(
                {
                    "fieldName": "settlementDate",
                    "compareType": "GTE",
                    "fieldValue": start.isoformat(),
                }
            )
        if end:
            filters.append(
                {
                    "fieldName": "settlementDate",
                    "compareType": "LTE",
                    "fieldValue": end.isoformat(),
                }
            )
        payload = {"compareFilters": filters, "limit": 1000, "offset": 0}
        response = httpx.post(
            endpoint,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
        raw = response.json()
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
                    short_position=_decimal(
                        row.get("currentShortPositionQuantity")
                        or row.get("shortPosition")
                        or row.get("short_position")
                    ),
                    short_percent_float=_decimal(row.get("shortPercentFloat") or row.get("short_percent_float")),
                    days_to_cover=_decimal(
                        row.get("daysToCoverQuantity")
                        or row.get("daysToCover")
                        or row.get("days_to_cover")
                    ),
                    source_identifier=str(
                        row.get("issueIdentifier")
                        or row.get("issueSymbolIdentifier")
                        or row.get("symbolCode")
                        or row.get("sourceIdentifier")
                        or ""
                    )
                    or None,
                    raw_payload=row,
                )
            )
        return result


def _access_token(client_id: str, client_secret: str) -> str:
    global _token_cache
    now = datetime.now(UTC)
    if _token_cache and _token_cache[1] > now:
        return _token_cache[0]
    response = httpx.post(
        str(getattr(settings, "FINRA_TOKEN_URL", "") or ""),
        params={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    token = str(body.get("access_token") or "").strip() if isinstance(body, dict) else ""
    if not token:
        raise RuntimeError("FINRA OAuth response did not contain access_token")
    try:
        expires_in = int(body.get("expires_in") or 3600) if isinstance(body, dict) else 3600
    except (TypeError, ValueError):
        expires_in = 3600
    # FINRA documents caching the token for at most 30 minutes. Refresh one
    # minute before a shorter provider expiry and never reuse a stale grant.
    cache_seconds = min(1800, max(60, expires_in - 60))
    _token_cache = (token, now + timedelta(seconds=cache_seconds))
    return token


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
