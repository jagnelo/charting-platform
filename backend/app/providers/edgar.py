"""
SEC EDGAR provider.

Capabilities:
  - InstrumentMetadataProvider: basic company profile from EDGAR submissions
  - EventProvider             : historical earnings dates derived from 10-Q/10-K
                                filing dates (best free approximation available)

Auth: None required.  SEC guidelines require a descriptive User-Agent header
(EDGAR_USER_AGENT in settings).  Max rate: 10 requests/second.

Ticker→CIK resolution uses the SEC's public company_tickers.json (cached 24h).

Earnings date approximation:
  EDGAR records the date a filing was submitted, not the exact earnings
  announcement date.  10-Q/10-K filings typically follow earnings by 1-5 days
  for large-caps, up to 40 days for small-caps.  These dates are good enough
  for historical reference and event-proximity calculations; they should not be
  used for time-sensitive intraday trading logic.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

import httpx

from app.config import settings
from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.providers.base import (
    InstrumentEventRecord,
    InstrumentProfile,
    ListingRecord,
    ProviderSearchResult,
)

logger = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_TICKER_CACHE_TTL = 3600 * 24  # 24 hours

# Module-level cache: upper-case ticker → {"cik": int, "title": str}
_ticker_map: dict[str, dict] = {}
_ticker_map_ts: float = 0.0
_exchange_directory: list[dict] = []
_exchange_directory_ts: float = 0.0
_profile_cache: dict[str, tuple[float, InstrumentProfile | None]] = {}


class EdgarProvider:
    name = "edgar"
    base_url = "https://data.sec.gov"
    description = (
        "SEC EDGAR — US company basic profile and historical earnings dates "
        "(derived from 10-Q/10-K filing dates)"
    )

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": settings.EDGAR_USER_AGENT}

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        """Search the SEC's cached issuer ticker directory without provider fan-out.

        The directory is the authoritative SEC identity/search source for US
        issuers.  It deliberately returns only identity fields; prices and
        tradability are resolved separately through the configured market-data
        chain.
        """
        needle = query.strip().upper()
        if not needle or limit <= 0:
            return []
        self._ensure_ticker_map(self._headers())
        matches = [
            ProviderSearchResult(
                symbol=ticker,
                name=str(entry.get("title") or ticker),
                instrument_type="EQUITY",
            )
            for ticker, entry in _ticker_map.items()
            if needle in ticker or needle in str(entry.get("title") or "").upper()
        ]
        matches.sort(key=lambda item: (0 if item.symbol == needle else 1, item.symbol))
        return matches[:limit]

    def discover_universe_page(self, quote_type: str, offset: int) -> dict:
        """Page the SEC's official US ticker/exchange directory.

        ``company_tickers_exchange.json`` is an issuer/listing directory, not
        a price feed or a promise that every row is currently tradable.  It is
        therefore used only for canonical security-master discovery and venue
        evidence; price-history capabilities remain independently resolved.
        The SEC has published both a columnar ``fields``/``data`` shape and
        object-shaped variants over time, so parsing accepts both without
        guessing missing exchange values.
        """
        if quote_type.upper() != "EQUITY" or offset < 0:
            return {"total": 0, "quotes": []}
        self._ensure_exchange_directory(self._headers())
        page_size = 250
        rows = _exchange_directory[offset : offset + page_size]
        quotes = [
            {
                "symbol": row["ticker"],
                "longName": row["name"],
                "shortName": row["name"],
                "currency": "USD",
                "exchange": row.get("exchange") or "",
                "quoteType": "EQUITY",
                "sec_cik": row.get("cik"),
                "identity_ambiguity": row.get("identity_ambiguity"),
            }
            for row in rows
            if row.get("ticker")
        ]
        return {"total": len(_exchange_directory), "quotes": quotes}

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY"]

    # ── Metadata ──────────────────────────────────────────────────────────────

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        normalized_symbol = symbol.strip().upper()
        cached = _profile_cache.get(normalized_symbol)
        if cached is not None and (time.time() - cached[0]) < _TICKER_CACHE_TTL:
            return cached[1]
        entry = _resolve_cik(symbol, self._headers())
        if entry is None:
            _profile_cache[normalized_symbol] = (time.time(), None)
            return None

        cik = entry["cik"]
        try:
            r = httpx.get(
                _SUBMISSIONS_URL.format(cik=cik),
                headers=self._headers(),
                timeout=20,
            )
            r.raise_for_status()
            sub = r.json()
        except Exception as exc:
            logger.warning("edgar get_instrument_profile %s (CIK %d): %s", symbol, cik, exc)
            # Fall back to minimal profile from ticker map
            profile = InstrumentProfile(
                provider="edgar",
                symbol=normalized_symbol,
                canonical_symbol=normalized_symbol,
                name=entry.get("title", normalized_symbol),
                currency="USD",
                quote_type="EQUITY",
                exchange="",
                listings=[
                    ListingRecord(
                        provider_symbol=symbol.upper(),
                        currency="USD",
                        is_primary=True,
                    )
                ],
                extra={"cik": cik},
            )
            _profile_cache[normalized_symbol] = (time.time(), profile)
            return profile

        tickers = sub.get("tickers") or [symbol.upper()]
        exchanges = sub.get("exchanges") or []
        name = sub.get("name") or entry.get("title") or symbol.upper()
        sic_desc = sub.get("sicDescription") or ""

        profile = InstrumentProfile(
            provider="edgar",
            symbol=normalized_symbol,
            canonical_symbol=normalized_symbol,
            name=name,
            currency="USD",
            quote_type="EQUITY",
            exchange=exchanges[0] if exchanges else "",
            listings=[
                ListingRecord(
                    provider_symbol=t,
                    exchange_code=exchanges[i] if i < len(exchanges) else None,
                    currency="USD",
                    provider_instrument_type="EQUITY",
                    is_primary=(i == 0),
                )
                for i, t in enumerate(tickers)
            ],
            raw_payload={
                "cik": cik,
                "tickers": tickers,
                "exchanges": exchanges,
                "sic": sub.get("sic"),
                "sic_description": sic_desc,
                "entity_type": sub.get("entityType"),
                "fiscal_year_end": sub.get("fiscalYearEnd"),
                "ein": sub.get("ein"),
                "phone": sub.get("phone"),
                "state_of_incorporation": sub.get("stateOfIncorporation"),
            },
            extra={
                "cik": cik,
                "sector": sic_desc,
                # The SEC exposes SIC descriptions rather than GICS. Keep the
                # same source-labelled value in the industry field so callers
                # can distinguish an issuer classification from a fabricated
                # ETF taxonomy relationship.
                "industry": sic_desc,
                "classification_system": "SEC_SIC",
            },
        )
        _profile_cache[normalized_symbol] = (time.time(), profile)
        return profile

    @staticmethod
    def _ensure_ticker_map(headers: dict) -> None:
        _ensure_ticker_map(headers)

    @staticmethod
    def _ensure_exchange_directory(headers: dict) -> None:
        _ensure_exchange_directory(headers)

    # ── Events (earnings history) ─────────────────────────────────────────────

    def fetch_instrument_events(self, symbol: str) -> list[InstrumentEventRecord]:
        entry = _resolve_cik(symbol, self._headers())
        if entry is None:
            return []

        cik = entry["cik"]
        try:
            r = httpx.get(
                _SUBMISSIONS_URL.format(cik=cik),
                headers=self._headers(),
                timeout=20,
            )
            r.raise_for_status()
            sub = r.json()
        except Exception as exc:
            logger.warning("edgar fetch_instrument_events %s (CIK %d): %s", symbol, cik, exc)
            return []

        events: list[InstrumentEventRecord] = []
        fetched = datetime.now(UTC)
        recent = sub.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])

        for form, date_str, acc in zip(forms, dates, accessions):
            if form not in ("10-Q", "10-K"):
                continue
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                period = "Annual" if form == "10-K" else "Quarterly"
                events.append(
                    InstrumentEventRecord(
                        event_type=InstrumentEventType.EARNINGS,
                        event_time=dt,
                        time_hint=EventTimeHint.UNKNOWN,
                        title=f"{period} Report Filed ({form})",
                        source_event_key=f"edgar_{form}_{acc.replace('-', '')}",
                        fetched_at=fetched,
                        raw_payload=f'{{"form":"{form}","date":"{date_str}","accession":"{acc}"}}',
                    )
                )
            except (ValueError, KeyError):
                continue

        return events


# ── Module helpers ────────────────────────────────────────────────────────────


def _resolve_cik(symbol: str, headers: dict) -> dict | None:
    """Return {"cik": int, "title": str} for the given ticker, or None."""
    _ensure_ticker_map(headers)
    return _ticker_map.get(symbol.upper())


def _ensure_ticker_map(headers: dict) -> None:
    global _ticker_map, _ticker_map_ts
    now = time.monotonic()
    if _ticker_map and (now - _ticker_map_ts) < _TICKER_CACHE_TTL:
        return
    try:
        r = httpx.get(_TICKERS_URL, headers=headers, timeout=30)
        r.raise_for_status()
        raw = r.json()
        mapping: dict[str, dict] = {}
        for entry in raw.values():
            ticker = (entry.get("ticker") or "").upper()
            if ticker:
                mapping[ticker] = {
                    "cik": int(entry["cik_str"]),
                    "title": entry.get("title", ticker),
                }
        _ticker_map = mapping
        _ticker_map_ts = now
        logger.info("edgar: loaded %d ticker→CIK mappings", len(mapping))
    except Exception as exc:
        logger.warning("edgar _ensure_ticker_map: %s", exc)


def _ensure_exchange_directory(headers: dict) -> None:
    """Load and normalise the SEC's public ticker/exchange directory once daily."""
    global _exchange_directory, _exchange_directory_ts
    now = time.monotonic()
    if _exchange_directory and (now - _exchange_directory_ts) < _TICKER_CACHE_TTL:
        return
    try:
        response = httpx.get(_TICKERS_EXCHANGE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        fields = payload.get("fields") if isinstance(payload, dict) else None
        raw_rows = payload.get("data") if isinstance(payload, dict) else None
        rows: list[dict] = []
        if isinstance(fields, list) and isinstance(raw_rows, list):
            for raw in raw_rows:
                if not isinstance(raw, list | tuple):
                    continue
                row = dict(zip((str(field) for field in fields), raw, strict=False))
                rows.append(row)
        elif isinstance(raw_rows, list):
            rows = [row for row in raw_rows if isinstance(row, dict)]
        elif isinstance(payload, dict):
            rows = [row for row in payload.values() if isinstance(row, dict)]

        directory: list[dict] = []
        for row in rows:
            ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
            name = str(row.get("name") or row.get("title") or "").strip()
            exchange = str(row.get("exchange") or row.get("exchange_name") or "").strip()
            if not ticker or not name:
                continue
            cik_raw = row.get("cik") or row.get("cik_str")
            try:
                cik = int(cik_raw) if cik_raw not in (None, "") else None
            except (TypeError, ValueError):
                cik = None
            directory.append({"ticker": ticker, "name": name, "exchange": exchange, "cik": cik})
        by_ticker: dict[str, list[dict]] = {}
        for row in directory:
            by_ticker.setdefault(row["ticker"], []).append(row)
        for ticker_rows in by_ticker.values():
            identities = {(row.get("cik"), row.get("name")) for row in ticker_rows}
            if len(identities) <= 1:
                continue
            candidates = [
                {
                    "cik": row.get("cik"),
                    "name": row.get("name"),
                    "exchange": row.get("exchange"),
                }
                for row in ticker_rows
            ]
            for row in ticker_rows:
                row["identity_ambiguity"] = candidates
        directory.sort(key=lambda item: (item["ticker"], item["exchange"], item["name"]))
        _exchange_directory = directory
        _exchange_directory_ts = now
        logger.info("edgar: loaded %d ticker/exchange listings", len(directory))
    except Exception as exc:
        logger.warning("edgar _ensure_exchange_directory: %s", exc)
