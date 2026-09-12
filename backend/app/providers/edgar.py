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
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings
from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.providers.base import (
    FundamentalFactRecord,
    InstrumentEventRecord,
    InstrumentProfile,
    ListingRecord,
    MarketEventRecord,
    ProviderSearchResult,
)
from app.providers.errors import ProviderNotConfiguredError, ProviderResponseError
from app.providers.telemetry import observe_response

logger = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_TICKER_CACHE_TTL = 3600 * 24  # 24 hours
_IPO_PIPELINE_FORMS = frozenset({"S-1", "S-1/A", "F-1", "F-1/A"})
_IPO_PIPELINE_MAX_EVENTS = 500

# Module-level cache: upper-case ticker → {"cik": int, "title": str}
_ticker_map: dict[str, dict] = {}
_ticker_map_ts: float = 0.0
_exchange_directory: list[dict] = []
_exchange_directory_ts: float = 0.0
_profile_cache: dict[str, tuple[float, InstrumentProfile | None]] = {}


def is_valid_edgar_user_agent(value: str | None) -> bool:
    """Return whether a SEC contact value is descriptive rather than example text."""

    normalized = str(value or "").strip().lower()
    placeholder_markers = (
        "example.com",
        "myemail@",
        "your.email",
        "<",
        ">",
    )
    return bool(normalized) and not any(marker in normalized for marker in placeholder_markers)


class EdgarProvider:
    name = "edgar"
    base_url = "https://data.sec.gov"
    description = (
        "SEC EDGAR — US company basic profile and historical earnings dates "
        "(derived from 10-Q/10-K filing dates)"
    )

    def _headers(self) -> dict[str, str]:
        user_agent = str(settings.EDGAR_USER_AGENT or "").strip()
        if not is_valid_edgar_user_agent(user_agent):
            raise ProviderNotConfiguredError(
                "edgar requires EDGAR_USER_AGENT with a descriptive contact value"
            )
        return {"User-Agent": user_agent}

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
            if not entry.get("identity_ambiguity")
            and (needle in ticker or needle in str(entry.get("title") or "").upper())
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
            observe_response(r)
            r.raise_for_status()
            sub = r.json()
            if not isinstance(sub, dict):
                raise ProviderResponseError(self.name, "SEC EDGAR returned an invalid JSON object")
        except httpx.HTTPStatusError:
            # The runtime owns typed 429/418 conversion and circuit handling;
            # do not turn an upstream rejection into a synthetic profile.
            raise
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "SEC EDGAR returned invalid JSON") from exc

        raw_tickers = sub.get("tickers")
        if raw_tickers is None:
            tickers = [normalized_symbol]
        elif (
            not isinstance(raw_tickers, list)
            or any(not isinstance(value, str) or not value.strip() for value in raw_tickers)
        ):
            raise ProviderResponseError(
                self.name,
                "SEC EDGAR submissions returned an invalid tickers array",
            )
        else:
            tickers = [value.strip().upper() for value in raw_tickers]

        raw_exchanges = sub.get("exchanges")
        if raw_exchanges is None:
            exchanges = []
        elif (
            not isinstance(raw_exchanges, list)
            or any(not isinstance(value, str) or not value.strip() for value in raw_exchanges)
        ):
            raise ProviderResponseError(
                self.name,
                "SEC EDGAR submissions returned an invalid exchanges array",
            )
        else:
            exchanges = [value.strip() for value in raw_exchanges]
        if exchanges and len(exchanges) != len(tickers):
            raise ProviderResponseError(
                self.name,
                "SEC EDGAR submissions returned mismatched ticker/exchange arrays",
            )
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

    def fetch_ipo_pipeline_events(
        self,
        cik: str,
        *,
        start: date | None = None,
        end: date | None = None,
        max_events: int = 100,
    ) -> list[MarketEventRecord]:
        """Detect filings that indicate a possible future public listing.

        This is deliberately a candidate detector, not an IPO-date oracle:
        EDGAR filings expose submission dates and filing forms, while an
        exchange listing may later be postponed, withdrawn, or never occur.
        The method performs one bounded submissions request for the supplied
        issuer CIK and only inspects the SEC ``recent`` filing arrays.  It does
        not enumerate every issuer or fetch archived submission files
        implicitly; callers must provide an explicit bounded CIK set when
        building a watchlist.
        """

        normalized_cik = _normalize_cik(cik)
        if normalized_cik is None:
            raise ProviderResponseError(self.name, "SEC EDGAR IPO pipeline requires a valid CIK")
        if (
            not isinstance(max_events, int)
            or isinstance(max_events, bool)
            or not 1 <= max_events <= _IPO_PIPELINE_MAX_EVENTS
        ):
            raise ValueError(f"max_events must be between 1 and {_IPO_PIPELINE_MAX_EVENTS}")
        if start is not None and end is not None and end < start:
            raise ValueError("end must be on or after start")

        try:
            response = httpx.get(
                _SUBMISSIONS_URL.format(cik=int(normalized_cik)),
                headers=self._headers(),
                timeout=20,
            )
            observe_response(response)
            response.raise_for_status()
            submissions = response.json()
            if not isinstance(submissions, dict):
                raise ProviderResponseError(self.name, "SEC EDGAR returned an invalid JSON object")
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "SEC EDGAR returned invalid JSON") from exc

        return _parse_ipo_pipeline_events(
            submissions,
            cik=normalized_cik,
            start=start,
            end=end,
            max_events=max_events,
        )

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
            observe_response(r)
            r.raise_for_status()
            sub = r.json()
            if not isinstance(sub, dict):
                raise ProviderResponseError(self.name, "SEC EDGAR returned an invalid JSON object")
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "SEC EDGAR returned invalid JSON") from exc

        events: list[InstrumentEventRecord] = []
        fetched = datetime.now(UTC)
        filings = sub.get("filings", {})
        if not isinstance(filings, dict):
            raise ProviderResponseError(self.name, "SEC EDGAR submissions returned an invalid filings object")
        recent = filings.get("recent", {})
        if not isinstance(recent, dict):
            raise ProviderResponseError(self.name, "SEC EDGAR submissions returned an invalid recent filings object")

        columns: dict[str, list] = {}
        for field in ("form", "filingDate", "accessionNumber"):
            value = recent.get(field, [])
            if not isinstance(value, list):
                raise ProviderResponseError(self.name, f"SEC EDGAR submissions returned an invalid {field} array")
            columns[field] = value
        forms = columns["form"]
        dates = columns["filingDate"]
        accessions = columns["accessionNumber"]
        if not (len(forms) == len(dates) == len(accessions)):
            raise ProviderResponseError(self.name, "SEC EDGAR submissions returned misaligned filing arrays")

        for form, date_str, acc in zip(forms, dates, accessions, strict=True):
            if not all(isinstance(value, str) for value in (form, date_str, acc)):
                raise ProviderResponseError(self.name, "SEC EDGAR submissions returned a malformed filing row")
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
            except ValueError as exc:
                raise ProviderResponseError(self.name, "SEC EDGAR submissions returned an invalid filing date") from exc

        return events

    def fetch_fundamental_facts(self, cik: str) -> list[FundamentalFactRecord]:
        """Return raw SEC Company Facts observations with filing dates intact."""

        digits = "".join(character for character in str(cik) if character.isdigit())
        if not digits:
            return []
        try:
            response = httpx.get(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(digits):010d}.json",
                headers=self._headers(),
                timeout=30,
            )
            observe_response(response)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ProviderResponseError(self.name, "SEC EDGAR returned an invalid JSON object")
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "SEC EDGAR returned invalid JSON") from exc
        facts = payload.get("facts")
        if not isinstance(facts, dict):
            raise ProviderResponseError(self.name, "SEC EDGAR company facts returned an invalid facts object")
        records: list[FundamentalFactRecord] = []
        for namespace, namespace_facts in facts.items():
            if not isinstance(namespace_facts, dict):
                raise ProviderResponseError(self.name, "SEC EDGAR company facts returned malformed namespace facts")
            for key, definition in namespace_facts.items():
                if not isinstance(definition, dict):
                    raise ProviderResponseError(self.name, "SEC EDGAR company facts returned a malformed fact definition")
                units = definition.get("units")
                if not isinstance(units, dict):
                    raise ProviderResponseError(self.name, "SEC EDGAR company facts returned an invalid units object")
                for unit, observations in units.items():
                    if not isinstance(observations, list):
                        raise ProviderResponseError(self.name, "SEC EDGAR company facts returned an invalid observations array")
                    for observation in observations:
                        if not isinstance(observation, dict):
                            raise ProviderResponseError(self.name, "SEC EDGAR company facts returned a malformed observation")
                        records.append(
                            FundamentalFactRecord(
                                namespace=str(namespace),
                                key=str(key),
                                unit=str(unit),
                                value_numeric=_parse_numeric(observation.get("val")),
                                value_text=_parse_text(observation.get("val")),
                                period_start=_parse_date(observation.get("start")),
                                period_end=_parse_date(observation.get("end")),
                                filed_at=_parse_date(observation.get("filed")),
                                accepted_at=_parse_datetime(observation.get("acceptanceDateTime")),
                                source_identifier=str(observation.get("accn") or "") or None,
                                raw_payload=observation,
                            )
                        )
        return records


# ── Module helpers ────────────────────────────────────────────────────────────


def _normalize_cik(value: Any) -> str | None:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if not digits or len(digits) > 10:
        return None
    return digits.zfill(10)


def _parse_ipo_pipeline_events(
    submissions: dict[str, Any],
    *,
    cik: str,
    start: date | None,
    end: date | None,
    max_events: int,
) -> list[MarketEventRecord]:
    """Normalize recent SEC prospectus/registration filings as candidates."""

    filings = submissions.get("filings")
    if not isinstance(filings, dict):
        raise ProviderResponseError("edgar", "SEC EDGAR submissions returned an invalid filings object")
    recent = filings.get("recent")
    if not isinstance(recent, dict):
        raise ProviderResponseError("edgar", "SEC EDGAR submissions returned an invalid recent filings object")

    required_fields = ("form", "filingDate", "accessionNumber")
    columns: dict[str, list[Any]] = {}
    for field in required_fields:
        value = recent.get(field, [])
        if not isinstance(value, list):
            raise ProviderResponseError("edgar", f"SEC EDGAR submissions returned an invalid {field} array")
        columns[field] = value
    if len({len(values) for values in columns.values()}) != 1:
        raise ProviderResponseError("edgar", "SEC EDGAR submissions returned misaligned filing arrays")

    optional_columns: dict[str, list[Any]] = {}
    for field in ("primaryDocument", "reportDate"):
        value = recent.get(field, [])
        if value in (None, []):
            optional_columns[field] = [None] * len(columns["form"])
            continue
        if not isinstance(value, list) or len(value) != len(columns["form"]):
            raise ProviderResponseError("edgar", f"SEC EDGAR submissions returned an invalid {field} array")
        optional_columns[field] = value

    issuer_name = str(submissions.get("name") or "").strip() or None
    tickers = submissions.get("tickers")
    if not isinstance(tickers, list):
        tickers = []
    normalized_tickers = [str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()]
    events: list[MarketEventRecord] = []
    for index, (form, filing_date_raw, accession) in enumerate(
        zip(
            columns["form"],
            columns["filingDate"],
            columns["accessionNumber"],
            strict=True,
        )
    ):
        if not all(isinstance(value, str) for value in (form, filing_date_raw, accession)):
            raise ProviderResponseError("edgar", "SEC EDGAR submissions returned a malformed filing row")
        normalized_form = form.strip().upper()
        if normalized_form not in _IPO_PIPELINE_FORMS and not normalized_form.startswith("424B"):
            continue
        try:
            filing_date = date.fromisoformat(filing_date_raw)
        except ValueError as exc:
            raise ProviderResponseError("edgar", "SEC EDGAR submissions returned an invalid filing date") from exc
        if (start is not None and filing_date < start) or (end is not None and filing_date > end):
            continue
        accession_value = accession.strip()
        if not accession_value:
            raise ProviderResponseError("edgar", "SEC EDGAR submissions returned a filing without an accession number")
        primary_document = optional_columns["primaryDocument"][index]
        if primary_document is not None and not isinstance(primary_document, str):
            raise ProviderResponseError("edgar", "SEC EDGAR submissions returned a malformed primary document")
        accession_path = accession_value.replace("-", "")
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/"
            f"{primary_document.strip()}"
            if isinstance(primary_document, str) and primary_document.strip()
            else None
        )
        payload = {
            "cik": cik,
            "form": normalized_form,
            "filing_date": filing_date.isoformat(),
            "accession_number": accession_value,
            "primary_document": primary_document.strip() if isinstance(primary_document, str) else None,
            "filing_url": filing_url,
            "issuer_name": issuer_name,
            "tickers": normalized_tickers,
            "pipeline_status": "candidate",
            "source": "sec_edgar_submissions_recent",
        }
        events.append(
            MarketEventRecord(
                event_type="ipo_pipeline",
                event_key=f"edgar:ipo_pipeline:{cik}:{accession_path}",
                event_time=datetime.combine(filing_date, datetime.min.time(), tzinfo=UTC),
                effective_date=filing_date,
                title=f"SEC {normalized_form} IPO pipeline filing"
                + (f" — {issuer_name}" if issuer_name else ""),
                source_version="submissions:recent",
                is_provisional=True,
                raw_payload=payload,
            )
        )
        if len(events) >= max_events:
            break
    return events


def _resolve_cik(symbol: str, headers: dict) -> dict | None:
    """Return {"cik": int, "title": str} for the given ticker, or None."""
    _ensure_ticker_map(headers)
    entry = _ticker_map.get(symbol.upper())
    # SEC's ticker directory is an issuer lookup aid, not a globally unique
    # security key.  Preserve duplicate-ticker evidence in the cache and
    # refuse to choose one CIK silently; callers can reconcile with venue and
    # security-level identifiers instead.
    if entry is None or entry.get("identity_ambiguity"):
        return None
    return entry


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _parse_datetime(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _parse_numeric(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except Exception:
        return None


def _parse_text(value: object) -> str | None:
    if value is None or _parse_numeric(value) is not None:
        return None
    text = str(value).strip()
    return text or None


def _ensure_ticker_map(headers: dict) -> None:
    global _ticker_map, _ticker_map_ts
    now = time.monotonic()
    if _ticker_map and (now - _ticker_map_ts) < _TICKER_CACHE_TTL:
        return
    try:
        r = httpx.get(_TICKERS_URL, headers=headers, timeout=30)
        observe_response(r)
        r.raise_for_status()
        raw = r.json()
        if not isinstance(raw, dict):
            raise ProviderResponseError("edgar", "SEC EDGAR returned an invalid JSON object")
        mapping: dict[str, dict] = {}
        for entry in raw.values():
            if not isinstance(entry, dict):
                raise ProviderResponseError("edgar", "SEC EDGAR ticker directory returned a malformed row")
            ticker = (entry.get("ticker") or "").upper()
            if not ticker or entry.get("cik_str") in (None, ""):
                raise ProviderResponseError("edgar", "SEC EDGAR ticker directory returned an incomplete row")
            try:
                cik = int(entry["cik_str"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderResponseError("edgar", "SEC EDGAR ticker directory returned an invalid CIK") from exc
            candidate = {
                "cik": cik,
                "title": entry.get("title", ticker),
            }
            previous = mapping.get(ticker)
            if previous is None:
                mapping[ticker] = candidate
                continue
            previous_ciks = {
                int(previous["cik"])
            } if previous.get("cik") not in (None, "") else set()
            previous_ciks.update(
                int(item["cik"])
                for item in previous.get("candidates", [])
                if isinstance(item, dict) and item.get("cik") not in (None, "")
            )
            if cik in previous_ciks:
                continue
            candidates = list(previous.get("candidates", []))
            if not candidates and previous.get("cik") not in (None, ""):
                candidates.append(
                    {"cik": int(previous["cik"]), "title": previous.get("title", ticker)}
                )
            candidates.append(candidate)
            mapping[ticker] = {
                "cik": None,
                "title": ticker,
                "identity_ambiguity": True,
                "candidates": candidates,
            }
        _ticker_map = mapping
        _ticker_map_ts = now
        logger.info("edgar: loaded %d ticker→CIK mappings", len(mapping))
    except httpx.HTTPStatusError:
        raise
    except httpx.RequestError as exc:
        raise ProviderResponseError("edgar", str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("edgar", "SEC EDGAR returned invalid JSON") from exc


def _ensure_exchange_directory(headers: dict) -> None:
    """Load and normalise the SEC's public ticker/exchange directory once daily."""
    global _exchange_directory, _exchange_directory_ts
    now = time.monotonic()
    if _exchange_directory and (now - _exchange_directory_ts) < _TICKER_CACHE_TTL:
        return
    try:
        response = httpx.get(_TICKERS_EXCHANGE_URL, headers=headers, timeout=30)
        observe_response(response)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ProviderResponseError("edgar", "SEC EDGAR returned an invalid JSON object")
        fields = payload.get("fields")
        raw_rows = payload.get("data")
        rows: list[dict] = []
        if fields is not None or raw_rows is not None:
            if raw_rows is None or not isinstance(raw_rows, list):
                raise ProviderResponseError("edgar", "SEC EDGAR exchange directory returned an invalid data array")
            if fields is not None:
                if not isinstance(fields, list) or not fields or any(not isinstance(field, str) for field in fields):
                    raise ProviderResponseError("edgar", "SEC EDGAR exchange directory returned invalid fields")
                for raw in raw_rows:
                    if not isinstance(raw, list | tuple) or len(raw) != len(fields):
                        raise ProviderResponseError(
                            "edgar", "SEC EDGAR exchange directory returned a malformed table row"
                        )
                    rows.append(dict(zip(fields, raw, strict=True)))
            else:
                for raw in raw_rows:
                    if not isinstance(raw, dict):
                        raise ProviderResponseError("edgar", "SEC EDGAR exchange directory returned a malformed row")
                    rows.append(raw)
        elif payload:
            if any(not isinstance(row, dict) for row in payload.values()):
                raise ProviderResponseError("edgar", "SEC EDGAR exchange directory returned malformed object rows")
            rows = list(payload.values())

        directory: list[dict] = []
        for row in rows:
            ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
            name = str(row.get("name") or row.get("title") or "").strip()
            exchange = str(row.get("exchange") or row.get("exchange_name") or "").strip()
            if not ticker or not name:
                raise ProviderResponseError("edgar", "SEC EDGAR exchange directory returned an incomplete row")
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
    except httpx.HTTPStatusError:
        raise
    except httpx.RequestError as exc:
        raise ProviderResponseError("edgar", str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("edgar", "SEC EDGAR returned invalid JSON") from exc
