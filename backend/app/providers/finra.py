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
from app.providers.base import MarketEventRecord, ShortInterestRecord
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
        token = self._authenticated_token()
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

    def fetch_market_events(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[MarketEventRecord]:
        """Fetch FINRA's OTC Daily List as lifecycle/corporate-action evidence.

        The Daily List is a delta feed, not a complete current OTC security
        master.  Callers must retain that distinction when reconciling the
        initial universe.  The same FINRA OAuth entitlement and documented
        Query API quota apply as for short interest.
        """
        token = self._authenticated_token()
        endpoint = str(getattr(settings, "FINRA_OTC_DAILY_LIST_URL", "") or "").strip()
        if not endpoint:
            endpoint = (
                str(getattr(settings, "FINRA_API_BASE_URL", self.base_url) or self.base_url).rstrip("/")
                + "/data/group/otcMarket/name/OTCDAILYLIST"
            )
        filters: list[dict[str, Any]] = []
        if start:
            filters.append(
                {
                    "fieldName": "calendarDay",
                    "compareType": "GTE",
                    "fieldValue": start.isoformat(),
                }
            )
        if end:
            filters.append(
                {
                    "fieldName": "calendarDay",
                    "compareType": "LTE",
                    "fieldValue": end.isoformat(),
                }
            )
        payload: dict[str, Any] = {"limit": 5000, "offset": 0}
        if filters:
            payload["compareFilters"] = filters
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
        result: list[MarketEventRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            event_date = _parse_date(row.get("calendarDay")) or _parse_date(row.get("exDate"))
            if (start and event_date and event_date < start) or (
                end and event_date and event_date > end
            ):
                continue
            event_time = _parse_datetime(row.get("dailyListDatetime"))
            event_type = _daily_list_event_type(row)
            daily_list_id = row.get("OTCDailyListID") or row.get("otcDailyListId")
            old_symbol = str(row.get("oldSymbolCode") or "").strip().upper()
            new_symbol = str(row.get("newSymbolCode") or "").strip().upper()
            symbol = new_symbol or old_symbol or "unknown"
            event_key = str(daily_list_id or f"{event_type}:{symbol}:{event_date or event_time}")
            result.append(
                MarketEventRecord(
                    event_type=event_type,
                    event_key=f"finra:otc_daily_list:{event_key}",
                    event_time=event_time,
                    effective_date=event_date,
                    title=str(
                        row.get("dailyListReasonDescription")
                        or row.get("newSecurityDescription")
                        or row.get("oldSecurityDescription")
                        or event_type
                    ),
                    source_version="OTCDAILYLIST",
                    is_provisional=True,
                    raw_payload=row,
                )
            )
        return result

    def _authenticated_token(self) -> str:
        client_id = str(getattr(settings, "FINRA_CLIENT_ID", "") or "").strip()
        client_secret = str(getattr(settings, "FINRA_CLIENT_SECRET", "") or "").strip()
        if not client_id or not client_secret:
            raise ProviderNotConfiguredError(
                "finra requires FINRA_CLIENT_ID and FINRA_CLIENT_SECRET; "
                "FINRA's current API is OAuth-authenticated"
            )
        return _access_token(client_id, client_secret)


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


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for pattern in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _daily_list_event_type(row: dict[str, Any]) -> str:
    if str(row.get("securityAddFlag") or "").upper() == "Y":
        return "otc_security_added"
    if str(row.get("securityDeleteFlag") or "").upper() == "Y":
        return "otc_security_deleted"
    if str(row.get("changeSymbolFlag") or "").upper() == "Y":
        return "otc_symbol_change"
    if str(row.get("changeSecurityDescriptionFlag") or "").upper() == "Y":
        return "otc_name_change"
    if str(row.get("bankruptcyFlag") or "").upper() == "Y":
        return "otc_bankruptcy"
    if row.get("forwardSplitRate") not in (None, "") or row.get("reverseSplitRate") not in (
        None,
        "",
    ):
        return "otc_split"
    if row.get("cashAmountText") not in (None, "") or row.get("dividendTypeCode") not in (None, ""):
        return "otc_dividend"
    return "otc_daily_list"


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except Exception:
        return None
