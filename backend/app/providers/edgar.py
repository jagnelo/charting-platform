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
from app.providers.base import InstrumentEventRecord, InstrumentProfile, ListingRecord

logger = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_TICKER_CACHE_TTL = 3600 * 24  # 24 hours

# Module-level cache: upper-case ticker → {"cik": int, "title": str}
_ticker_map: dict[str, dict] = {}
_ticker_map_ts: float = 0.0


class EdgarProvider:
    name = "edgar"
    base_url = "https://data.sec.gov"
    description = (
        "SEC EDGAR — US company basic profile and historical earnings dates "
        "(derived from 10-Q/10-K filing dates)"
    )

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": settings.EDGAR_USER_AGENT}

    # ── Metadata ──────────────────────────────────────────────────────────────

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        entry = _resolve_cik(symbol, self._headers())
        if entry is None:
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
            return InstrumentProfile(
                provider="edgar",
                symbol=symbol.upper(),
                canonical_symbol=symbol.upper(),
                name=entry.get("title", symbol.upper()),
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

        tickers = sub.get("tickers") or [symbol.upper()]
        exchanges = sub.get("exchanges") or []
        name = sub.get("name") or entry.get("title") or symbol.upper()
        sic_desc = sub.get("sicDescription") or ""

        return InstrumentProfile(
            provider="edgar",
            symbol=symbol.upper(),
            canonical_symbol=symbol.upper(),
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
            },
        )

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
