"""CTA Plan's public daily Consolidated Tape A/B symbol-file adapter.

The file is an official listing-source snapshot, not a quote API. Its source
participant codes are translated to ISO MICs only through an explicit map;
unknown codes remain attached to raw rows and fail the reconciliation closed.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.providers.errors import ProviderResponseError
from app.providers.telemetry import observe_response

_INDEX_URL = "https://ftp.nyse.com/cta_symbol_files/"
_FILE_URL = _INDEX_URL + "{filename}"
_FILE_NAME = re.compile(r"CTA\.Symbol\.File\.(\d{8})\.csv")
_EASTERN = ZoneInfo("America/New_York")
_COLUMNS = (
    "symbol",
    "prior_security_symbol",
    "participant_id",
    "primary_listing_previous_close",
    "consolidated_close",
    "round_lot_size",
    "minimum_price_increment",
    "luld_tier",
    "luld_leverage_ratio",
    "test",
    "ipo",
    "financial_status",
    "short_sale_restriction",
    "halt_reason",
    "instrument_type",
)

# CTA participant IDs are not MICs. Values are explicit listing-market mappings
# compiled from the CTA Symbol File specification, NYSE CTA participant table,
# and ISO 10383. Never fall back to the one-character participant ID as a MIC.
_PARTICIPANT_TO_MIC = {
    "A": "XASE",  # NYSE American
    "B": "XBOS",  # Nasdaq Texas (formerly Nasdaq BX; MIC retained)
    "C": "XCIS",  # NYSE National
    "D": "XADF",  # FINRA Alternative Display Facility
    "F": "TXSE",  # Texas Stock Exchange
    "G": "24EQ",  # 24X National Exchange
    "H": "EPRL",  # MIAX Pearl Equities (not MIAX Pearl options)
    "I": "XISE",  # Nasdaq ISE Equities MIC
    "J": "EDGA",  # Cboe EDGA
    "K": "EDGX",  # Cboe EDGX
    "L": "LTSE",  # Long-Term Stock Exchange
    "M": "XCHI",  # NYSE Texas
    "N": "XNYS",  # NYSE
    "P": "ARCX",  # NYSE Arca
    "T": "XNAS",  # Nasdaq (CTA Tape A/B participant code)
    "U": "MEMX",  # Members Exchange
    "V": "IEXG",  # Investors Exchange
    "W": "CBSX",  # Cboe Stock Exchange
    "X": "XPSX",  # Nasdaq PSX
    "Y": "BATY",  # Cboe BYX
    "Z": "BATS",  # Cboe BZX
}


class CTAPlanProvider:
    name = "cta_plan"
    base_url = _INDEX_URL
    description = "Official daily CTA Consolidated Tape A/B symbol directory"

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        # The source file covers the full Tape A/B universe in one download.
        # Return the complete equity-class observation as one page so quota
        # reservations match the two actual HTTP requests (index + file).
        if quote_type.strip().upper() != "EQUITY" or offset != 0:
            return {"total": 0, "quotes": [], "complete": True}

        index = _get(_INDEX_URL)
        snapshot_date, filename = _latest_file(index.text)
        source = _get(_FILE_URL.format(filename=filename))
        quotes, errors, total_rows = _parse_symbol_file(source.text)
        return {
            "total": len(quotes),
            "quotes": quotes,
            "complete": not errors,
            "validation_errors": errors,
            "source_files": ["cta_symbol_file_index", filename],
            "source_snapshot_date": snapshot_date.isoformat(),
            "source_row_count": total_rows,
            # Keep the complete provider responses in the durable raw snapshot;
            # the file is small and a live test must not discard rows it queried.
            "raw_source_payload": {
                "index_html": index.text,
                "symbol_file_csv": source.text,
            },
        }

    def supported_discovery_types(self) -> list[str]:
        # CTA's file instrument type distinguishes eligible equities/local
        # issues from bonds. ETF-vs-common-stock is not a field in this file;
        # preserve CTA evidence as EQUITY and let other official sources add
        # the ETF subtype without losing the CTA listing observation.
        return ["EQUITY"]


def _get(url: str) -> httpx.Response:
    try:
        # The shared runtime reserves the reviewed index+CSV cost before this
        # adapter runs. Do not let HTTPX send unmetered redirect hops inside a
        # single admitted operation; a redirect is a failed attempt until each
        # hop can be admitted independently.
        response = httpx.get(url, timeout=30, follow_redirects=False)
    except httpx.RequestError as exc:
        raise ProviderResponseError("cta_plan", f"transport failure: {exc}") from exc
    observe_response(response)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ProviderResponseError(
            "cta_plan", f"HTTP {response.status_code} from public symbol-file endpoint"
        ) from exc
    return response


def _latest_file(index_html: str, *, today: date | None = None) -> tuple[date, str]:
    """Select the newest dated file actually published; never guess holidays."""

    current_date = today or datetime.now(UTC).astimezone(_EASTERN).date()
    candidates: list[tuple[date, str]] = []
    for match in _FILE_NAME.finditer(index_html):
        try:
            file_date = datetime.strptime(match.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        if file_date <= current_date:
            candidates.append((file_date, match.group(0)))
    if not candidates:
        raise ProviderResponseError(
            "cta_plan", "public directory contains no valid dated symbol file"
        )
    return max(candidates)


def _parse_symbol_file(text: str) -> tuple[list[dict[str, Any]], list[str], int]:
    """Parse all rows, retaining mapped equities and reporting unknown source codes."""

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ProviderResponseError("cta_plan", "symbol file is empty")

    # Current CTA files are positional. Permit a descriptive header if the
    # source adds one, but do not let an unexpected shorter layout truncate.
    first = [cell.strip().casefold() for cell in rows[0]]
    if first and first[0] in {"symbol", "cta symbol"}:
        rows = rows[1:]
    if not rows:
        raise ProviderResponseError("cta_plan", "symbol file contains a header but no rows")

    quotes: list[dict[str, Any]] = []
    errors: list[str] = []
    total_rows = 0
    seen: set[tuple[str, str]] = set()
    for row_number, row in enumerate(rows, start=2):
        if not row or not any(cell.strip() for cell in row):
            continue
        total_rows += 1
        if len(row) < len(_COLUMNS):
            errors.append(
                f"row {row_number}: expected at least {len(_COLUMNS)} fields, got {len(row)}"
            )
            continue
        source_record = {name: row[index].strip() for index, name in enumerate(_COLUMNS)}
        # Preserve CTA's exact symbol spelling. The upstream file contains
        # case-distinct symbols that would collide if normalized here; raw
        # and normalized identity reconciliation are separate decisions.
        symbol = source_record["symbol"].strip()
        participant_id = source_record["participant_id"].strip().upper()
        cta_type = source_record["instrument_type"].strip()
        test_issue = source_record["test"].strip()
        if not symbol or not participant_id or cta_type not in {"0", "1", "2", "3"}:
            errors.append(
                f"row {row_number}: missing symbol/participant or unknown instrument type"
            )
            continue
        mic = _PARTICIPANT_TO_MIC.get(participant_id)
        if mic is None:
            errors.append(
                f"row {row_number}: unknown CTA primary-listing participant code {participant_id!r}"
            )
            continue
        if cta_type not in {"0", "1"} or test_issue == "1":
            # Bonds and test symbols remain verbatim in raw_source_payload;
            # they are outside this equity-universe projection.
            continue
        identity = (symbol, mic)
        if identity in seen:
            errors.append(f"row {row_number}: duplicate symbol/venue pair {symbol}/{mic}")
            continue
        seen.add(identity)
        quotes.append(
            {
                "symbol": symbol,
                "longName": symbol,
                "shortName": symbol,
                "exchange": mic,
                "exchange_mic": mic,
                "currency": "USD",
                "quoteType": "EQUITY",
                "instrument_type": "EQUITY",
                "status": "active",
                "prior_security_symbol": source_record["prior_security_symbol"] or None,
                "cta_instrument_type": cta_type,
                "source_record": source_record,
                "source_file": "cta_symbol_file",
            }
        )
    if total_rows == 0:
        errors.append("symbol file has no data rows")
    return quotes, errors, total_rows
