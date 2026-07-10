from __future__ import annotations

import asyncio
import base64
import csv
import html
import json
import re
import ssl
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from io import BytesIO, StringIO
from pathlib import Path
from string import Formatter
from typing import Any, Protocol
from urllib.parse import unquote_to_bytes, urlencode, urljoin, urlparse, urlunparse

import httpx
import requests

from app.config import settings


@dataclass(slots=True)
class CanonicalHoldingRow:
    symbol: str | None = None
    name: str | None = None
    cusip: str | None = None
    isin: str | None = None
    sedol: str | None = None
    weight: Decimal | None = None
    shares: Decimal | None = None
    market_value: Decimal | None = None
    currency: str | None = None
    country: str | None = None
    exchange: str | None = None
    holding_type: str = "equity"
    row_type: str = "security"
    source_row_id: str | None = None
    extra_data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ETFDiscoveryRow:
    symbol: str
    name: str | None = None
    issuer: str | None = None
    fund_family: str | None = None
    product_url: str | None = None
    issuer_product_id: str | None = None
    cusip: str | None = None
    isin: str | None = None
    figi: str | None = None
    composite_figi: str | None = None
    share_class_figi: str | None = None
    sec_cik: str | None = None
    sec_series_id: str | None = None
    sec_class_id: str | None = None
    holdings_url: str | None = None
    holdings_url_template: str | None = None
    dated_holdings_url_template: str | None = None
    extra_data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HoldingsAdapterProbe:
    adapter_key: str
    confidence: Decimal
    status: str
    reason: str | None = None
    source_url: str | None = None
    issuer_product_id: str | None = None
    required_identifiers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HoldingsFetchResult:
    rows: list[CanonicalHoldingRow]
    raw_text: str | None = None
    raw_json: dict[str, Any] | None = None
    source_url: str | None = None
    source_identifier: str | None = None
    legal_metadata: dict[str, Any] | None = None


class ETFHoldingsAdapter(Protocol):
    adapter_key: str
    source_provider: str

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        ...

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        ...

    async def fetch_for_date(
        self,
        *,
        symbol: str,
        requested_date: date,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        ...


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--", "N/A", "n/a", "null", "None"}:
        return None
    return text


def _decimal(value: Any) -> Decimal | None:
    text = _clean(value)
    if text is None:
        return None
    normalized = (
        text.replace(",", "")
        .replace("$", "")
        .replace("\u2212", "-")
        .strip()
    )
    is_parenthesized_negative = normalized.startswith("(") and normalized.endswith(")")
    if is_parenthesized_negative:
        normalized = normalized[1:-1].strip()
    is_percent = normalized.endswith("%")
    if is_percent:
        normalized = normalized[:-1].strip()
    try:
        result = Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None
    if is_parenthesized_negative:
        result = -result
    if is_percent:
        return result / Decimal("100")
    return result


def _decimal_percent_points(value: Any) -> Decimal | None:
    parsed = _decimal(value)
    if parsed is None:
        return None
    return parsed / Decimal("100")


def _first(row: dict[str, Any], aliases: list[str]) -> Any:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in aliases:
        if alias.lower() in lowered:
            return lowered[alias.lower()]
    return None


def _first_match(row: dict[str, Any], aliases: list[str]) -> tuple[str | None, Any]:
    lowered = {str(k).strip().lower(): (str(k), v) for k, v in row.items()}
    for alias in aliases:
        matched = lowered.get(alias.lower())
        if matched is not None:
            return matched
    return None, None


def _identifier(identifiers: dict[str, str], *keys: str) -> str | None:
    lowered = {key.strip().lower(): value for key, value in identifiers.items() if value}
    for key in keys:
        value = lowered.get(key.strip().lower())
        if value:
            return value.strip()
    return None


def _looks_like_cusip(value: str | None) -> bool:
    text = _clean(value)
    if text is None:
        return False
    return bool(re.fullmatch(r"[0-9A-Z]{8}[0-9A-Z]", text.strip().upper()))


def _looks_like_isin(value: str | None) -> bool:
    text = _clean(value)
    if text is None:
        return False
    return bool(re.fullmatch(r"[A-Z]{2}[0-9A-Z]{9}[0-9]", text.strip().upper()))


def _looks_like_sedol(value: str | None) -> bool:
    text = _clean(value)
    if text is None:
        return False
    return bool(re.fullmatch(r"[0-9BCDFGHJKLMNPQRSTVWXYZ]{6}[0-9]", text.strip().upper()))


def _template_fields(template: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name is not None and field_name
    }


def _format_template(template: str, values: dict[str, str]) -> str | None:
    required = _template_fields(template)
    if not required.issubset(values):
        return None
    try:
        return template.format(**values)
    except KeyError:
        return None


_CELL_REF_RE = re.compile(r"([A-Z]+)")


def _cell_column_index(cell_ref: str | None) -> int | None:
    if not cell_ref:
        return None
    match = _CELL_REF_RE.match(cell_ref.upper())
    if not match:
        return None
    index = 0
    for char in match.group(1):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _looks_like_holdings_header(row: list[Any]) -> bool:
    columns = {str(value).strip().lower() for value in row if _clean(value)}
    if not columns:
        return False
    groups = [
        {
            "ticker",
            "symbol",
            "holding ticker",
            "local ticker",
            "identifier",
            "security identifier",
            "stock ticker",
            "stockticker",
            "ticker/cusip",
        },
        {
            "name",
            "holding name",
            "security name",
            "securityname",
            "description",
            "security",
            "issuer",
            "issuer name",
            "name of issuer",
            "title of issue",
        },
        {
            "weight",
            "weight (%)",
            "% weight",
            "market value weight",
            "exposure weight",
            "etf weight",
            "% of fund",
            "percent of fund",
            "percentage of fund",
            "percent of assets",
            "% net assets",
            "% of net assets",
            "portfolio weight %",
            "weighting",
            "weightings",
            "percentage weighting",
        },
        {
            "shares",
            "shares held",
            "quantity",
            "shares/par",
            "shares/par (full)",
            "shares/par value",
            "shares / quantity",
            "shares or principal amount",
            "par value",
        },
        {
            "market value",
            "market_value",
            "market value ($)",
            "market value($)",
            "holding value",
            "market ($)",
            "market value usd",
            "marketvalue",
            "market/notional value",
            "traded market value (base)",
            "notional value",
            "value",
            "value usd",
        },
        {"currency", "local currency"},
        {"cusip", "isin", "sedol"},
    ]
    matched_groups = sum(1 for aliases in groups if columns & aliases)
    has_security_identifier = bool(columns & groups[0]) or bool(columns & groups[-1])
    return has_security_identifier and matched_groups >= 2


def _row_dict(header: list[Any], row: list[Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for index, value in enumerate(row):
        key = str(header[index]).strip() if index < len(header) and _clean(header[index]) else ""
        if not key:
            key = f"__column_{index + 1}"
        result[key] = value
    for index in range(len(row), len(header)):
        key = str(header[index]).strip() if _clean(header[index]) else f"__column_{index + 1}"
        result.setdefault(key, None)
    return result


def _table_to_text(rows: list[list[Any]]) -> str:
    output = StringIO()
    writer = csv.writer(output)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    return output.getvalue()


def parse_holdings_table(table_rows: list[list[Any]]) -> list[CanonicalHoldingRow]:
    """Parse a generic holdings table into canonical rows."""

    rows_by_index = [
        ["" if value is None else value for value in row]
        for row in table_rows
        if any(_clean(value) for value in row)
    ]
    header_index = next(
        (index for index, row in enumerate(rows_by_index[:30]) if _looks_like_holdings_header(row)),
        None,
    )
    if header_index is None:
        return []

    header = rows_by_index[header_index]
    rows: list[CanonicalHoldingRow] = []
    for idx, raw_row in enumerate(rows_by_index[header_index + 1 :], start=1):
        raw = _row_dict(header, raw_row)
        symbol_candidate = _clean(
            _first(
                raw,
                [
                    "ticker",
                    "symbol",
                    "holding ticker",
                    "local ticker",
                    "identifier",
                    "security identifier",
                    "stock ticker",
                    "stockticker",
                    "ticker/cusip",
                ],
            )
        )
        cusip = _clean(_first(raw, ["cusip"]))
        if cusip is None and _looks_like_cusip(symbol_candidate):
            cusip = symbol_candidate
            symbol = None
        else:
            symbol = symbol_candidate
        name = _clean(
            _first(
                raw,
                [
                    "name",
                    "holding name",
                    "security name",
                    "securityname",
                    "description",
                    "security description",
                    "security",
                    "company",
                    "company name",
                    "issuer",
                    "issuer name",
                    "name of issuer",
                    "title of issue",
                ],
            )
        )
        holding_type = (
            _clean(_first(raw, ["asset class", "asset_class", "holding type", "type"]))
            or "equity"
        ).lower()
        row_type = "cash" if (
            holding_type in {"cash", "currency"}
            or (symbol or "").upper() in {"CASH", "CASH&OTHER", "USD", "US DOLLAR"}
            or (name or "").strip().lower() in {
                "cash",
                "cash & other",
                "cash and other",
                "us dollar",
                "u.s. dollar",
            }
        ) else "security"
        if row_type == "cash":
            holding_type = "cash"
            symbol = None
        weight_key, weight_value = _first_match(
            raw,
            [
                "weight",
                "weight (%)",
                "% weight",
                "market value weight",
                "% of fund",
                "percent of fund",
                "percentage of fund",
                "percent of assets",
                "exposure weight",
                "etf weight",
                "% net assets",
                "% of net assets",
                "portfolio weight %",
                "weighting",
                "weightings",
                "percentage weighting",
            ],
        )
        weight_value_text = _clean(weight_value)
        should_treat_weight_as_percent_points = False
        if weight_key and weight_value_text and not weight_value_text.endswith("%"):
            lowered_weight_key = weight_key.lower()
            if (
                "%" in weight_key
                or "percent" in lowered_weight_key
                or "percentage" in lowered_weight_key
            ):
                should_treat_weight_as_percent_points = True
            else:
                raw_weight = _decimal(weight_value)
                if raw_weight is not None and abs(raw_weight) > 1 and abs(raw_weight) <= 100:
                    should_treat_weight_as_percent_points = True
        weight_parser = _decimal_percent_points if should_treat_weight_as_percent_points else _decimal
        weight = weight_parser(weight_value)
        shares = _decimal(
            _first(
                raw,
                [
                    "shares",
                    "shares held",
                    "quantity",
                    "shares/par",
                    "shares/par (full)",
                    "shares/par value",
                    "shares/contracts",
                    "shares / quantity",
                    "shares or principal amount",
                    "par value",
                ],
            )
        )
        market_value = _decimal(
            _first(
                raw,
                [
                    "market value",
                    "market_value",
                    "market value ($)",
                    "market value($)",
                    "holding value",
                    "market ($)",
                    "market value usd",
                    "marketvalue",
                    "market/notional value",
                    "traded market value (base)",
                    "notional value",
                    "value",
                    "value usd",
                ],
            )
        )
        raw_identifier = _clean(_first(raw, ["identifier", "security identifier"]))
        identifier_isin = (
            raw_identifier
            if raw_identifier and re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", raw_identifier)
            else None
        )
        identifier_cusip = (
            raw_identifier
            if raw_identifier and re.fullmatch(r"[A-Z0-9]{9}", raw_identifier)
            else None
        )
        cusip_value = cusip or identifier_cusip
        isin_value = _clean(_first(raw, ["isin"])) or identifier_isin
        sedol_value = _clean(_first(raw, ["sedol", "sedol number"]))
        identity_value = cusip_value or isin_value or sedol_value
        if not any([symbol, identity_value]) and not any(
            [weight, shares, market_value]
        ):
            continue
        rows.append(
            CanonicalHoldingRow(
                symbol=symbol,
                name=name,
                cusip=cusip_value,
                isin=isin_value,
                sedol=sedol_value,
                weight=weight,
                shares=shares,
                market_value=market_value,
                currency=_clean(_first(raw, ["currency", "local currency", "trading currency"])),
                country=_clean(_first(raw, ["country", "location"])),
                exchange=_clean(_first(raw, ["exchange", "exchange code", "market"])),
                holding_type=holding_type,
                row_type=row_type,
                source_row_id=_clean(_first(raw, ["id", "row id", "source row id"])) or str(idx),
                extra_data={k: v for k, v in raw.items() if v not in (None, "")},
            )
        )
    return rows


def parse_holdings_csv(raw_csv: str) -> list[CanonicalHoldingRow]:
    """Parse common issuer holdings CSV exports into canonical rows."""

    table_rows = list(csv.reader(StringIO(raw_csv.strip())))
    return parse_holdings_table(table_rows)


class _HTMLTableByIdParser(HTMLParser):
    def __init__(self, *, table_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.table_id = table_id
        self._capture_table = False
        self._table_depth = 0
        self._in_row = False
        self._in_cell = False
        self._cell_text: list[str] = []
        self._current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered_tag = tag.lower()
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if lowered_tag == "table":
            if attr_map.get("id") == self.table_id:
                self._capture_table = True
                self._table_depth = 1
            elif self._capture_table:
                self._table_depth += 1
        if not self._capture_table:
            return
        if lowered_tag == "tr":
            self._in_row = True
            self._current_row = []
        elif lowered_tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._cell_text = []

    def handle_endtag(self, tag: str) -> None:
        if not self._capture_table:
            return
        lowered_tag = tag.lower()
        if lowered_tag in {"td", "th"} and self._in_cell:
            self._current_row.append(" ".join("".join(self._cell_text).split()))
            self._in_cell = False
            self._cell_text = []
        elif lowered_tag == "tr" and self._in_row:
            if any(cell for cell in self._current_row):
                self.rows.append(self._current_row)
            self._in_row = False
            self._current_row = []
        elif lowered_tag == "table":
            self._table_depth -= 1
            if self._table_depth <= 0:
                self._capture_table = False

    def handle_data(self, data: str) -> None:
        if self._capture_table and self._in_cell:
            self._cell_text.append(data)


def parse_html_holdings_table_by_id(raw_html: str, *, table_id: str) -> list[CanonicalHoldingRow]:
    parser = _HTMLTableByIdParser(table_id=table_id)
    parser.feed(raw_html)
    return parse_holdings_table(parser.rows)


class _HTMLTablesParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._capture_table = False
        self._table_depth = 0
        self._in_row = False
        self._in_cell = False
        self._cell_text: list[str] = []
        self._current_row: list[str] = []
        self._current_table: list[list[str]] = []
        self.tables: list[list[list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered_tag = tag.lower()
        if lowered_tag == "table":
            if not self._capture_table:
                self._capture_table = True
                self._table_depth = 1
                self._current_table = []
            else:
                self._table_depth += 1
        if not self._capture_table:
            return
        if lowered_tag == "tr":
            self._in_row = True
            self._current_row = []
        elif lowered_tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._cell_text = []

    def handle_endtag(self, tag: str) -> None:
        if not self._capture_table:
            return
        lowered_tag = tag.lower()
        if lowered_tag in {"td", "th"} and self._in_cell:
            self._current_row.append(" ".join("".join(self._cell_text).split()))
            self._in_cell = False
            self._cell_text = []
        elif lowered_tag == "tr" and self._in_row:
            if any(cell for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._in_row = False
            self._current_row = []
        elif lowered_tag == "table":
            self._table_depth -= 1
            if self._table_depth <= 0:
                if self._current_table:
                    self.tables.append(self._current_table)
                self._capture_table = False
                self._current_table = []

    def handle_data(self, data: str) -> None:
        if self._capture_table and self._in_cell:
            self._cell_text.append(data)


def parse_html_holdings_table_by_headers(
    raw_html: str,
    *,
    required_headers: set[str],
) -> list[CanonicalHoldingRow]:
    parser = _HTMLTablesParser()
    parser.feed(raw_html)
    normalized_required = {header.strip().lower() for header in required_headers}
    for table in parser.tables:
        for row in table[:30]:
            normalized_row = {str(value).strip().lower() for value in row if _clean(value)}
            if normalized_required <= normalized_row:
                return parse_holdings_table(table)
    return []


def _looks_like_discovery_header(row: list[Any]) -> bool:
    columns = {str(value).strip().lower() for value in row if _clean(value)}
    if not columns:
        return False
    has_symbol = bool(
        columns
        & {
            "ticker",
            "symbol",
            "fund ticker",
            "fund symbol",
            "etf ticker",
            "etf symbol",
        }
    )
    has_name = bool(
        columns & {"name", "fund name", "etf name", "fund", "product name"}
    )
    has_route = bool(
        columns
        & {
            "product url",
            "fund url",
            "url",
            "holdings url",
            "issuer product id",
            "product id",
        }
    )
    return has_symbol and (has_name or has_route)


def parse_etf_discovery_table(table_rows: list[list[Any]]) -> list[ETFDiscoveryRow]:
    """Parse a generic issuer ETF/fund-list table into profile discovery rows."""

    rows_by_index = [
        ["" if value is None else value for value in row]
        for row in table_rows
        if any(_clean(value) for value in row)
    ]
    header_index = next(
        (index for index, row in enumerate(rows_by_index[:30]) if _looks_like_discovery_header(row)),
        None,
    )
    if header_index is None:
        return []

    header = rows_by_index[header_index]
    rows: list[ETFDiscoveryRow] = []
    for raw_row in rows_by_index[header_index + 1 :]:
        raw = _row_dict(header, raw_row)
        symbol = _clean(
            _first(
                raw,
                [
                    "ticker",
                    "symbol",
                    "fund ticker",
                    "fund symbol",
                    "etf ticker",
                    "etf symbol",
                ],
            )
        )
        if not symbol:
            continue
        rows.append(
            ETFDiscoveryRow(
                symbol=symbol.upper(),
                name=_clean(
                    _first(raw, ["name", "fund name", "etf name", "fund", "product name"])
                ),
                issuer=_clean(_first(raw, ["issuer", "sponsor", "provider"])),
                fund_family=_clean(_first(raw, ["fund family", "family"])),
                product_url=_clean(
                    _first(raw, ["product url", "fund url", "profile url", "url"])
                ),
                issuer_product_id=_clean(
                    _first(raw, ["issuer product id", "product id", "fund id"])
                ),
                cusip=_clean(_first(raw, ["cusip"])),
                isin=_clean(_first(raw, ["isin"])),
                figi=_clean(_first(raw, ["figi", "openfigi", "open figi"])),
                composite_figi=_clean(
                    _first(raw, ["composite figi", "composite_figi"])
                ),
                share_class_figi=_clean(
                    _first(raw, ["share class figi", "share_class_figi"])
                ),
                sec_cik=_clean(_first(raw, ["sec cik", "cik"])),
                sec_series_id=_clean(_first(raw, ["sec series id", "series id"])),
                sec_class_id=_clean(_first(raw, ["sec class id", "class id"])),
                holdings_url=_clean(
                    _first(raw, ["holdings url", "holdings_url", "download url"])
                ),
                holdings_url_template=_clean(
                    _first(raw, ["holdings url template", "holdings_url_template"])
                ),
                dated_holdings_url_template=_clean(
                    _first(
                        raw,
                        [
                            "dated holdings url template",
                            "dated_holdings_url_template",
                            "historical holdings url template",
                        ],
                    )
                ),
                extra_data={k: v for k, v in raw.items() if v not in (None, "")},
            )
        )
    return rows


def parse_etf_discovery_csv(raw_csv: str) -> list[ETFDiscoveryRow]:
    """Parse a CSV issuer ETF/fund list into profile discovery rows."""

    table_rows = list(csv.reader(StringIO(raw_csv.strip())))
    return parse_etf_discovery_table(table_rows)


def parse_holdings_xlsx(raw_workbook: bytes) -> list[CanonicalHoldingRow]:
    """Parse a simple issuer XLSX/OpenXML holdings workbook into canonical rows."""

    return parse_holdings_table(parse_xlsx_table(raw_workbook))


def parse_holdings_xls(raw_workbook: bytes) -> tuple[list[CanonicalHoldingRow], list[list[str]]]:
    """Parse a legacy XLS holdings workbook via pandas/xlrd."""

    import pandas as pd  # noqa: PLC0415

    frames = pd.read_excel(BytesIO(raw_workbook), sheet_name=None, header=None, dtype=str)
    fallback_rows: list[list[str]] = []
    for frame in frames.values():
        table_rows = [
            [
                ""
                if value is None or (isinstance(value, float) and pd.isna(value))
                else str(value).strip()
                for value in row
            ]
            for row in frame.fillna("").values.tolist()
        ]
        if not fallback_rows and any(any(_clean(cell) for cell in row) for row in table_rows):
            fallback_rows = table_rows
        rows = parse_holdings_table(table_rows)
        if rows:
            return rows, table_rows
    return [], fallback_rows


def parse_holdings_zip(raw_archive: bytes) -> tuple[list[CanonicalHoldingRow], str, dict[str, Any]]:
    """Parse a ZIP archive containing an issuer holdings CSV/XLSX file."""

    with zipfile.ZipFile(BytesIO(raw_archive)) as archive:
        file_names = [
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and name.lower().endswith((".csv", ".xlsx", ".xlsm"))
            and "__macosx/" not in name.lower()
        ]
        if not file_names:
            return [], "", {"source_format": "zip", "archive_files": archive.namelist()}

        def score(name: str) -> tuple[int, str]:
            lowered = name.lower()
            value = 0
            if "holding" in lowered:
                value += 30
            if "portfolio" in lowered:
                value += 20
            if "constituent" in lowered:
                value += 20
            if lowered.endswith(".csv"):
                value += 10
            return -value, name

        for file_name in sorted(file_names, key=score):
            raw_file = archive.read(file_name)
            if file_name.lower().endswith((".xlsx", ".xlsm")):
                workbook_rows = parse_xlsx_table(raw_file)
                rows = parse_holdings_table(workbook_rows)
                raw_text = _table_to_text(workbook_rows)
                member_format = "xlsx"
            else:
                raw_text = raw_file.decode("utf-8-sig", errors="replace")
                rows = parse_holdings_csv(raw_text)
                member_format = "csv"
            if rows:
                return rows, raw_text, {
                    "source_format": "zip",
                    "selected_archive_file": file_name,
                    "selected_archive_file_format": member_format,
                    "archive_files": file_names,
                }
    return [], "", {"source_format": "zip", "archive_files": file_names}


def parse_xlsx_table(raw_workbook: bytes, *, worksheet_index: int = 1) -> list[list[str]]:
    """Extract a worksheet from an XLSX workbook using stdlib OpenXML parsing."""

    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(BytesIO(raw_workbook)) as workbook:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("main:si", namespace):
                texts = [node.text or "" for node in item.findall(".//main:t", namespace)]
                shared_strings.append("".join(texts))

        worksheet_name = f"xl/worksheets/sheet{worksheet_index}.xml"
        if worksheet_name not in workbook.namelist():
            worksheet_prefix = "xl/worksheets/sheet"
            worksheet_name = next(
                name
                for name in workbook.namelist()
                if name.lower().startswith(worksheet_prefix)
            )
        worksheet_root = ET.fromstring(workbook.read(worksheet_name))

    table_rows: list[list[str]] = []
    for row in worksheet_root.findall(".//main:sheetData/main:row", namespace):
        values_by_column: dict[int, str] = {}
        for cell in row.findall("main:c", namespace):
            column_index = _cell_column_index(cell.attrib.get("r"))
            if column_index is None:
                column_index = len(values_by_column)
            cell_type = cell.attrib.get("t")
            if cell_type == "s":
                raw_index = cell.findtext("main:v", default="", namespaces=namespace)
                try:
                    value = shared_strings[int(raw_index)]
                except (IndexError, ValueError):
                    value = ""
            elif cell_type == "inlineStr":
                value = "".join(
                    node.text or "" for node in cell.findall(".//main:t", namespace)
                )
            else:
                value = cell.findtext("main:v", default="", namespaces=namespace)
            values_by_column[column_index] = value
        if values_by_column:
            max_column = max(values_by_column)
            table_rows.append([values_by_column.get(index, "") for index in range(max_column + 1)])
    return table_rows


_URL_ATTRIBUTE_RE = re.compile(
    r"""(?:href|data-[\w-]*url|download-url)=["'](?P<url>[^"']+)["']""",
    re.IGNORECASE,
)
_DOWNLOAD_ANCHOR_RE = re.compile(
    r"""<a[^>]+(?:download=["'](?P<filename_a>[^"']+)["'][^>]+href=["'](?P<url_a>[^"']+)["']|href=["'](?P<url_b>[^"']+)["'][^>]+download=["'](?P<filename_b>[^"']+)["'])""",
    re.IGNORECASE,
)
_QUOTED_FILE_URL_RE = re.compile(
    r"""["'](?P<url>[^"']+\.(?:csv|xlsx|xlsm|zip)(?:[?#][^"']*)?)["']""",
    re.IGNORECASE,
)
_SUPPORTED_HOLDINGS_FILE_RE = re.compile(r"\.(csv|xlsx|xlsm|zip)(?:$|[?#])", re.IGNORECASE)
_HOLDINGS_LINK_HINT_RE = re.compile(r"(holding|portfolio|constituent)", re.IGNORECASE)
_HOLDINGS_DOWNLOAD_HINT_RE = re.compile(
    r"(holding|portfolio|constituent).*(download|xls|xlsx|csv)|"
    r"(download|xls|xlsx|csv).*(holding|portfolio|constituent)",
    re.IGNORECASE,
)


def _holdings_request_headers(*, accept: str | None = None) -> dict[str, str]:
    return {
        "User-Agent": settings.ETF_HOLDINGS_HTTP_USER_AGENT or settings.EDGAR_USER_AGENT,
        "Accept": accept
        or (
            "text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
            "application/vnd.ms-excel,application/zip,text/html,*/*"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }


def _issuer_page_request_headers(*, accept: str | None = None) -> dict[str, str]:
    headers = _holdings_request_headers(accept=accept)
    headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            "Accept": accept
            or "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return headers


def _invesco_holdings_request_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "HeadlessChrome/145.0.7632.6 Safari/537.36"
        ),
        "Referer": "https://www.invesco.com/",
        "sec-ch-ua": '"Not:A-Brand";v="99", "HeadlessChrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }


def _discover_holdings_download_url(product_page_url: str, html: str) -> str | None:
    """Find the most likely linked holdings table from an issuer product page."""

    candidates: list[tuple[int, str]] = []
    discovered = [
        (match.group("url").strip(), match.group("url").strip())
        for match in _URL_ATTRIBUTE_RE.finditer(html)
    ]
    discovered.extend(
        (candidate, candidate)
        for match in _QUOTED_FILE_URL_RE.finditer(html)
        for candidate in [match.group("url").strip()]
        if candidate.startswith(("http://", "https://", "/", "data:"))
    )
    discovered.extend(
        (
            (match.group("url_a") or match.group("url_b") or "").strip(),
            " ".join(
                part
                for part in [
                    (match.group("filename_a") or match.group("filename_b") or "").strip(),
                    (match.group("url_a") or match.group("url_b") or "").strip(),
                ]
                if part
            ),
        )
        for match in _DOWNLOAD_ANCHOR_RE.finditer(html)
    )
    for href, hint_text in discovered:
        if not href:
            continue
        lowered_hint = hint_text.lower()
        if not (
            _SUPPORTED_HOLDINGS_FILE_RE.search(href)
            or href.lower().startswith("data:")
            or _HOLDINGS_DOWNLOAD_HINT_RE.search(href)
            or _HOLDINGS_DOWNLOAD_HINT_RE.search(lowered_hint)
        ):
            continue
        if not (
            _HOLDINGS_LINK_HINT_RE.search(href)
            or _HOLDINGS_DOWNLOAD_HINT_RE.search(href)
            or _HOLDINGS_LINK_HINT_RE.search(lowered_hint)
            or _HOLDINGS_DOWNLOAD_HINT_RE.search(lowered_hint)
        ):
            continue
        url = urljoin(product_page_url, href)
        lowered = url.lower()
        score = 0
        if "holding" in lowered:
            score += 30
        if "portfolio" in lowered:
            score += 20
        if "constituent" in lowered:
            score += 20
        if lowered.endswith(".csv") or ".csv?" in lowered:
            score += 10
        if lowered.endswith(".zip") or ".zip?" in lowered:
            score += 5
        if "download" in lowered:
            score += 8
        if "xls" in lowered:
            score += 6
        if "holding" in lowered_hint:
            score += 25
        if "portfolio" in lowered_hint:
            score += 20
        if lowered.startswith("data:"):
            score += 15
        candidates.append((score, url))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def _parse_data_url(source_url: str) -> tuple[str, bytes, str]:
    metadata, _, payload = source_url.partition(",")
    if not payload or not metadata.lower().startswith("data:"):
        raise ValueError("Unsupported data URL.")
    header = metadata[5:]
    is_base64 = header.lower().endswith(";base64")
    mime_type = header[:-7] if is_base64 else header
    mime_type = mime_type or "text/plain;charset=utf-8"
    raw_content = (
        base64.b64decode(payload)
        if is_base64
        else unquote_to_bytes(payload)
    )
    return mime_type.lower(), raw_content, raw_content.decode("utf-8", "ignore")


def _parse_ishares_inline_top_holdings(html_text: str) -> list[CanonicalHoldingRow]:
    """Parse iShares' embedded top-holdings JSON when CSV downloads serve the page shell."""

    decoded = html.unescape(html_text)
    marker = '"topHoldings":'
    start = decoded.find(marker)
    if start < 0:
        return []
    array_start = decoded.find("[", start)
    if array_start < 0:
        return []
    depth = 0
    array_end = -1
    for index, char in enumerate(decoded[array_start:], start=array_start):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                array_end = index + 1
                break
    if array_end < 0:
        return []
    try:
        holdings = json.loads(decoded[array_start:array_end])
    except json.JSONDecodeError:
        return []

    rows: list[CanonicalHoldingRow] = []
    for position, item in enumerate(holdings, start=1):
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("holdingsName"))
        weight = _decimal(item.get("holdingPercent"))
        if not name and weight is None:
            continue
        rows.append(
            CanonicalHoldingRow(
                name=name,
                weight=weight,
                source_row_id=str(item.get("holdingSerialNumber") or position),
                extra_data={"source": "ishares_inline_top_holdings"},
            )
        )
    return rows


ISSUER_NAME_HINTS: dict[str, list[str]] = {
    "ishares": ["ishares", "blackrock"],
    "spdr": ["spdr", "state street"],
    "vanguard": ["vanguard"],
    "invesco": ["invesco"],
    "schwab": ["schwab"],
    "ark": ["ark"],
    "global_x": ["global x"],
    "vaneck": ["vaneck", "van eck"],
    "wisdomtree": ["wisdomtree"],
    "proshares": ["proshares"],
    "direxion": ["direxion"],
    "jpmorgan": ["jpmorgan", "jp morgan"],
    "fidelity": ["fidelity"],
    "franklin": ["franklin"],
    "sprott": ["sprott"],
    "bny_mellon": ["bny mellon", "bny"],
}

ETFDB_RECOGNITION_ONLY_ISSUER_HINTS: dict[str, list[str]] = {
    "1251_capital": ["1251 capital"],
    "818": ["818, inc", "818 inc"],
    "abrdn": ["abrdn", "aberdeen"],
    "absolute_investment_advisers": ["absolute investment advisers"],
    "acp_horizon": ["acp horizon"],
    "acuitas": ["acuitas"],
    "adaptive_investments": ["adaptive investments"],
    "advisor_shares": ["advisorshares", "advisor shares"],
    "affiliated_managers_group": ["affiliated managers group"],
    "agf": ["agf"],
    "alger": ["alger"],
    "allianz": ["allianz"],
    "alliancebernstein": ["alliancebernstein", "alliance bernstein"],
    "american_century": ["american century"],
    "ameriprise": ["ameriprise"],
    "amplify": ["amplify"],
    "anfield": ["anfield"],
    "angel_oak": ["angel oak"],
    "applied_finance": ["applied finance"],
    "aptus": ["aptus"],
    "archer_investment": ["archer investment"],
    "astoria": ["astoria"],
    "axs": ["axs investments", "axs"],
    "bahl_gaynor": ["bahl & gaynor", "bahl and gaynor"],
    "baird": ["baird"],
    "baron": ["baron capital"],
    "bcp_cc": ["bcp cc"],
    "belpointe": ["belpointe"],
    "bitwise": ["bitwise"],
    "bny_mellon": ["bny mellon"],
    "bondbloxx": ["bondbloxx", "bondbloxx investment"],
    "brandes": ["brandes"],
    "brookmont": ["brookmont"],
    "brown_advisory": ["brown advisory"],
    "calamos": ["calamos"],
    "cambria": ["cambria"],
    "canary": ["canary capital"],
    "capital_group": ["capital group", "the capital group"],
    "capital_impact": ["capital impact advisors"],
    "clearshares": ["clearshares", "clear shares"],
    "clough": ["clough"],
    "cohen_steers": ["cohen & steers", "cohen and steers"],
    "convergence": ["convergence investment"],
    "corgi": ["corgi strategies", "corgi insurance"],
    "corient": ["corient"],
    "counterpoint": ["counterpoint mutual funds"],
    "cygnet": ["cygnet capital"],
    "dana": ["dana investment"],
    "davis": ["davis advisers", "davis advisors"],
    "defiance": ["defiance"],
    "delaware": ["delaware management"],
    "deutsche_bank": ["deutsche bank", "xtrackers", "dws"],
    "dhandho": ["dhandho"],
    "diamond_hill": ["diamond hill"],
    "dimensional": ["dimensional", "dimensional fund advisors"],
    "distillate": ["distillate capital"],
    "donoghue_forlines": ["donoghue forlines"],
    "doubleline": ["doubleline", "double line"],
    "eagle_capital": ["eagle capital"],
    "eighth_wonder": ["eighth wonder"],
    "eldridge": ["eldridge"],
    "envestnet": ["envestnet"],
    "equitable": ["equitable"],
    "etf_architect": ["etf architect", "alpha architect"],
    "eventide": ["eventide"],
    "exchange_traded_concepts": ["exchange traded concepts"],
    "faith_investor_services": ["faith investor services"],
    "federated_hermes": ["federated hermes", "federated"],
    "first_pacific": ["first pacific advisors"],
    "first_trust": ["first trust"],
    "fm_investments": ["f/m investments", "fm investments"],
    "gamco": ["gamco", "gabelli"],
    "gmo": ["gmo", "grantham mayo van otterloo", "grantham, mayo, van otterloo"],
    "golden_eagle": ["golden eagle"],
    "goldman_sachs": ["goldman sachs"],
    "gqg": ["gqg"],
    "graff": ["graff capital"],
    "graniteshares": ["graniteshares", "granite shares"],
    "grayscale": ["grayscale"],
    "groupe_bpce": ["groupe bpce", "natixis"],
    "guardian": ["guardian capital"],
    "guinness_atkinson": ["guinness atkinson"],
    "harbor": ["harbor"],
    "hartford": ["hartford"],
    "hashdex": ["hashdex"],
    "hedgeye": ["hedgeye"],
    "howard_capital": ["howard capital"],
    "hull": ["hull investments"],
    "idx": ["idx advisors"],
    "im_global_partner": ["im global partner", "iM global partner"],
    "infrastructure_capital": ["infrastructure capital"],
    "innovator": ["innovator"],
    "inspire": ["inspire impact", "inspire"],
    "intech": ["intech"],
    "janus_henderson": ["janus henderson", "janus"],
    "jensen": ["jensen investment"],
    "kensington": ["kensington"],
    "killir": ["killir kapital"],
    "kingsview": ["kingsview"],
    "kraneshares": ["kraneshares", "krane shares"],
    "kurv": ["kurv"],
    "lagan": ["lagan"],
    "lazard": ["lazard"],
    "leuthold": ["leuthold"],
    "liquid_strategies": ["liquid strategies"],
    "little_harbor": ["little harbor"],
    "main_management": ["main management"],
    "man_group": ["man group"],
    "manulife": ["manulife", "john hancock"],
    "marygold": ["marygold"],
    "matthews": ["matthews international", "matthews asia"],
    "mcivy": ["mcivy"],
    "mirae_asset": ["mirae asset"],
    "morgan_stanley": ["morgan stanley", "eaton vance", "parametric"],
    "motley_fool": ["motley fool"],
    "neil_azous": ["neil azous"],
    "neuberger_berman": ["neuberger berman"],
    "neos": ["neos"],
    "new_york_life": ["new york life", "indexiq", "index iq"],
    "nomura": ["nomura"],
    "northern_trust": ["northern trust", "flexshares", "flex shares"],
    "nsi": ["nsi holdings"],
    "oneascent": ["oneascent", "one ascent"],
    "optimize": ["optimize financial"],
    "pacer": ["pacer"],
    "pacific_investments": ["pacific investments"],
    "palmer_square": ["palmer square"],
    "peakshares": ["peakshares", "peak shares"],
    "planrock": ["planrock"],
    "pmv": ["pmv capital"],
    "polen": ["polen capital"],
    "praxis": ["praxis"],
    "principal": ["principal"],
    "procuream": ["procuream", "procure am"],
    "prudential": ["prudential", "pgim"],
    "ptam": ["ptam"],
    "q3": ["q3 asset"],
    "rayliant": ["rayliant"],
    "raymond_james": ["raymond james"],
    "rdj": ["rdj associates"],
    "reckoner": ["reckoner"],
    "redbird": ["redbird"],
    "reflection": ["reflection asset"],
    "regan": ["regan capital"],
    "resolute": ["resolute investment"],
    "reverence": ["reverence capital"],
    "rex": ["rex financial", "rex shares"],
    "roundhill": ["roundhill"],
    "russell_investments": ["russell investments"],
    "scm_edge": ["s.c.m. edge", "scm edge"],
    "sei": ["sei investments", "sei"],
    "shariaportfolio": ["shariaportfolio", "sharia portfolio"],
    "shelton": ["shelton capital"],
    "simplify": ["simplify"],
    "sofi": ["sofi"],
    "sound_capital": ["sound capital"],
    "spear": ["spear advisors"],
    "spend_life_wisely": ["spend life wisely"],
    "ssc": ["ss&c", "ss and c", "alps", "alps advisors"],
    "sterling_capital": ["sterling capital"],
    "sterling_fund": ["sterling fund"],
    "strive": ["strive"],
    "summit_global": ["summit global"],
    "sun_life": ["sun life"],
    "swan_global": ["swan global"],
    "swp": ["swp investment"],
    "symmetry": ["symmetry partners"],
    "t_rowe_price": ["t. rowe price", "t rowe price"],
    "tapp": ["tapp finance"],
    "tcw": ["tcw group", "tcw"],
    "tema": ["tema global"],
    "teucrium": ["teucrium"],
    "texas_capital": ["texas capital"],
    "themes": ["themes etf", "themes"],
    "thornburg": ["thornburg"],
    "thor": ["thor trading"],
    "thrivent": ["thrivent"],
    "tidal": ["tidal financial", "tidal"],
    "tiaa": ["tiaa", "nuveen"],
    "timothy_plan": ["timothy plan"],
    "tremblant": ["tremblant"],
    "true_shares": ["true shares", "trueshares"],
    "truemark": ["truemark", "true mark"],
    "tuttle": ["tuttle"],
    "twin_oak": ["twin oak"],
    "ubs": ["ubs"],
    "unlimited": ["unlimited funds"],
    "vert": ["vert asset"],
    "victory": ["victory capital", "usaa"],
    "virtus": ["virtus"],
    "volatility_shares": ["volatility shares"],
    "wahed": ["wahed"],
    "warren": ["warren capital"],
    "water_island": ["water island"],
    "wedbush": ["wedbush"],
    "weitz": ["weitz"],
    "wellington": ["wellington management"],
    "westwood": ["westwood"],
    "western_southern": ["western & southern", "western and southern"],
    "world_gold_council": ["world gold council", "spdr gold"],
    "yorkville": ["yorkville"],
    "yieldmax": ["yieldmax", "yield max"],
    "zacks": ["zacks"],
    "abacus_global": ["abacus global"],
    "advent_capital": ["advent capital"],
    "aegon": ["aegon"],
    "ag_financial": ["ag financial services"],
    "akre": ["akre capital"],
    "albert_mason": ["albert d. mason", "albert mason"],
    "alexis": ["alexis investment"],
    "allspring": ["allspring"],
    "alternative_access": ["alternative access"],
    "amerilife": ["amerilife"],
    "amun": ["amun"],
    "aot": ["aot invest"],
    "araq": ["arax investment"],
    "arrow": ["arrow funds"],
    "barclays": ["barclays"],
    "beacon_capital": ["beacon capital"],
    "beyond_investing": ["beyond investing"],
    "bmo": ["bmo financial", "bmo"],
    "brookfield": ["brookfield"],
    "brown_brothers_harriman": ["brown brothers harriman", "bbh"],
    "build": ["build asset"],
    "burney": ["burney"],
    "cary_street": ["cary street"],
    "castleark": ["castleark", "castle ark"],
    "cboe": ["cboe"],
    "ccm": ["ccm holding"],
    "ci_financial": ["ci financial"],
    "cicc": ["cicc"],
    "clough_cgi": ["clough cgi"],
    "cohanzick": ["cohanzick"],
    "coinshares": ["coinshares"],
    "colliers": ["colliers"],
    "concourse": ["concourse capital"],
    "core_alternative": ["core alternative capital"],
    "cotwo": ["cotwo"],
    "cullen": ["cullen capital"],
    "cyber_hornet": ["cyber hornet"],
    "dakota_wealth": ["dakota wealth"],
    "deepwater": ["deepwater asset"],
    "digital_currency_group": ["digital currency group"],
    "distribution_cognizant": ["distribution cognizant"],
    "emles": ["emles"],
    "epiris": ["epiris"],
    "epwa": ["epwa"],
    "estate_counselors": ["estate counselors"],
    "eurazeo": ["eurazeo"],
    "first_eagle": ["first eagle"],
    "fmc_group": ["fmc group"],
    "focus_financial": ["focus financial"],
    "formidable": ["formidable asset"],
    "fortuna": ["fortuna funds"],
    "frontier": ["frontier asset"],
    "future_fund": ["future fund advisors"],
    "gladius": ["gladius capital"],
    "goose_hollow": ["goose hollow"],
    "grace_partners": ["grace partners"],
    "hennessy": ["hennessy"],
    "horizon_kinetics": ["horizon kinetics"],
    "hwcap": ["hwcap"],
    "impax": ["impax"],
    "indexperts": ["indexperts"],
    "inverdale": ["inverdale"],
    "ironhorse": ["ironhorse", "iron horse"],
    "kingsbarn": ["kingsbarn"],
    "langar": ["langar"],
    "lionshares": ["lionshares", "lion shares"],
    "logan": ["logan capital"],
    "madison": ["madison investment"],
    "mairs_power": ["mairs & power", "mairs and power"],
    "marathon": ["marathon partners"],
    "miller_value": ["miller value"],
    "mitsubishi_ufj": ["mitsubishi ufj", "mufg"],
    "mm_vam": ["mm vam"],
    "msc_group": ["msc group"],
    "natixis": ["natixis"],
    "nightview": ["nightview"],
    "noa": ["noa llc"],
    "ocean_park": ["ocean park"],
    "orix": ["orix"],
    "osprey": ["osprey funds"],
    "paralel": ["paralel"],
    "pettee": ["pettee"],
    "pictet": ["pictet"],
    "point_bridge": ["point bridge"],
    "precidian": ["precidian"],
    "prospera": ["prospera"],
    "quantify_chaos": ["quantify chaos"],
    "rafferty": ["rafferty", "direxion"],
    "rational": ["rational advisors"],
    "redwood": ["redwood"],
    "renaissance_capital": ["renaissance capital"],
    "retireful": ["retireful"],
    "ridgeline": ["ridgeline"],
    "river_north": ["rivernorth", "river north"],
    "rock_point": ["rock point"],
    "running_oak": ["running oak"],
    "saracen": ["saracen energy"],
    "scharf": ["scharf investments"],
    "sovereign": ["sovereign's capital", "sovereigns capital"],
    "split_rock": ["split rock"],
    "srn": ["srn advisors"],
    "stf": ["stf management"],
    "toews": ["toews"],
    "tortoise": ["tortoise"],
    "vontobel": ["vontobel"],
    "voya": ["voya"],
    "waverly": ["waverly advisors"],
    "wbi": ["wbi"],
    "wealthtrust": ["wealthtrust", "wealth trust"],
    "webs": ["webs investments"],
    "x_square": ["x-square", "x square"],
}

ETFDB_LONG_TAIL_RECOGNITION_ONLY_ISSUER_HINTS: dict[str, list[str]] = {
    "21shares": ["21shares", "21 shares"],
    "3edge": ["3edge", "3 edge"],
    "3fourteen": ["3fourteen", "3 fourteen", "3fourteen & smi"],
    "acquirers": ["acquirers funds", "acquirers fund"],
    "arlington": ["arlington capital"],
    "artemis": ["artemis corp", "artemis corporation"],
    "cambiar": ["cambiar"],
    "cultivar": ["cultivar capital"],
    "dawn_global": ["dawn global"],
    "dividend_assets": ["dividend assets capital"],
    "founder": ["founder etfs", "founder etf"],
    "hypatia": ["hypatia capital"],
    "myriad": ["myriad asset"],
    "soundwatch": ["soundwatch capital", "sound watch capital"],
    "stone_ridge": ["stone ridge"],
    "us_global_investors": ["us global investors", "u.s. global investors"],
}

ETFDB_RECOGNITION_ONLY_ISSUER_HINTS.update(
    ETFDB_LONG_TAIL_RECOGNITION_ONLY_ISSUER_HINTS
)
ISSUER_NAME_HINTS.update(ETFDB_RECOGNITION_ONLY_ISSUER_HINTS)

ISSUER_DOMAIN_HINTS: dict[str, list[str]] = {
    "ishares": ["ishares.com", "blackrock.com"],
    "spdr": ["ssga.com", "spdrs.com", "spdrgoldshares.com"],
    "vanguard": ["vanguard.com"],
    "invesco": ["invesco.com"],
    "schwab": ["schwabassetmanagement.com", "schwab.com"],
    "ark": ["ark-funds.com"],
    "global_x": ["globalxetfs.com"],
    "vaneck": ["vaneck.com"],
    "wisdomtree": ["wisdomtree.com"],
    "proshares": ["proshares.com"],
    "direxion": ["direxion.com"],
    "jpmorgan": ["jpmorgan.com", "am.jpmorgan.com"],
    "fidelity": ["fidelity.com"],
    "franklin": ["franklintempleton.com"],
    "sprott": ["sprottetfs.com"],
}

ISSUER_DOMAIN_HINTS.update(
    {
        "advisor_shares": ["advisorshares.com"],
        "ssc": ["alpsfunds.com", "alpsinc.com"],
        "amplify": ["amplifyetfs.com"],
        "bitwise": ["bitwiseinvestments.com"],
        "bondbloxx": ["bondbloxxetf.com"],
        "calamos": ["calamos.com"],
        "capital_group": ["capitalgroup.com"],
        "defiance": ["defianceetfs.com"],
        "dimensional": ["dimensional.com"],
        "first_trust": ["ftportfolios.com", "firsttrust.com"],
        "goldman_sachs": ["goldmansachs.com"],
        "grayscale": ["grayscale.com"],
        "graniteshares": ["graniteshares.com"],
        "hartford": ["hartfordfunds.com"],
        "innovator": ["innovatoretfs.com"],
        "janus_henderson": ["janushenderson.com"],
        "kraneshares": ["kraneshares.com"],
        "neos": ["neosfunds.com"],
        "pacer": ["paceretfs.com"],
        "roundhill": ["roundhillinvestments.com"],
        "simplify": ["simplify.us"],
        "sofi": ["sofi.com"],
        "strive": ["strivefunds.com"],
        "teucrium": ["teucrium.com"],
        "tidal": ["tidalfinancialgroup.com"],
        "volatility_shares": ["volatilityshares.com"],
        "wahed": ["wahed.com"],
        "yieldmax": ["yieldmaxetfs.com"],
    }
)

ROUTING_URL_ALIAS_KEYS = (
    "holdings_url",
    "issuer_holdings_url",
    "holdings_csv_url",
    "latest_holdings_url",
    "holdings_download_url",
    "product_url",
    "issuer_product_url",
    "fund_url",
    "profile_url",
    "etf_url",
)


def _url_host(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    host = host.lower().removeprefix("www.")
    return host or None


def _domain_matches(host: str, domain: str) -> bool:
    domain = domain.lower().removeprefix("www.")
    return host == domain or host.endswith(f".{domain}")


class PublicCsvHoldingsAdapter:
    """Shared holdings-file fetch/parser helper for provider adapters.

    This class is intentionally not registered as a standalone adapter. Concrete
    issuer adapters may reuse it once they have resolved their own provider
    route, but ETF refresh must not treat an arbitrary configured URL as a
    supported provider implementation.
    """

    def __init__(self, adapter_key: str, source_provider: str | None = None) -> None:
        self.adapter_key = adapter_key
        self.source_provider = source_provider or adapter_key

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.5000"),
            status="candidate",
            reason="Shared parser helper is not a concrete ETF issuer route.",
            issuer_product_id=identifiers.get("issuer_product_id"),
            source_url=None,
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return _holdings_request_headers()

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        if not source_url:
            raise ValueError(f"{self.adapter_key} needs a configured source_url for {symbol}.")
        if source_url.lower().startswith("data:"):
            content_type, raw_content, response_text = _parse_data_url(source_url)
        else:
            async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    source_url,
                    headers=self.source_request_headers(source_url=source_url),
                    follow_redirects=True,
                )
            response.raise_for_status()
            raw_content = getattr(response, "content", None)
            response_text = response.text
            content_type = ""
            headers = getattr(response, "headers", None)
            if headers is not None:
                content_type = str(headers.get("content-type", "")).lower()
        source_format = "zip" if (
            source_url.lower().endswith(".zip")
            or "zip" in content_type
        ) else "xls" if (
            source_url.lower().endswith(".xls")
            or (
                "application/vnd.ms-excel" in content_type
                and isinstance(raw_content, bytes)
                and raw_content.startswith(b"\xd0\xcf\x11\xe0")
            )
        ) else "xlsx" if (
            source_url.lower().endswith((".xlsx", ".xlsm"))
            or "spreadsheetml" in content_type
            or (isinstance(raw_content, bytes) and raw_content.startswith(b"PK"))
        ) else "csv"
        raw_json = None
        if source_format == "zip":
            if not isinstance(raw_content, bytes):
                raw_content = response_text.encode()
            rows, raw_text, raw_json = parse_holdings_zip(raw_content)
        elif source_format == "xlsx":
            if not isinstance(raw_content, bytes):
                raw_content = response_text.encode()
            workbook_rows = parse_xlsx_table(raw_content)
            rows = parse_holdings_table(workbook_rows)
            raw_text = _table_to_text(workbook_rows)
            raw_json = {"source_format": "xlsx", "workbook_rows": workbook_rows}
        elif source_format == "xls":
            if not isinstance(raw_content, bytes):
                raw_content = response_text.encode()
            rows, workbook_rows = parse_holdings_xls(raw_content)
            raw_text = _table_to_text(workbook_rows)
            raw_json = {"source_format": "xls", "workbook_rows": workbook_rows}
        else:
            rows = parse_holdings_csv(response_text)
            raw_text = response_text
            if not rows and self.adapter_key == "ishares":
                rows = _parse_ishares_inline_top_holdings(response_text)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=raw_text,
            raw_json=raw_json,
            source_url=source_url,
            source_identifier=issuer_product_id,
            legal_metadata={
                "source_access": "configured_public_csv_url",
                "adapter_key": self.adapter_key,
                "source_format": source_format,
                **(
                    {
                        key: value
                        for key, value in (raw_json or {}).items()
                        if key
                        in {
                            "selected_archive_file",
                            "selected_archive_file_format",
                            "archive_files",
                        }
                    }
                    if source_format == "zip"
                    else {}
                ),
            },
        )

    async def fetch_for_date(
        self,
        *,
        symbol: str,
        requested_date: date,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        if not source_url:
            raise ValueError(
                f"{self.adapter_key} needs a concrete dated source_url for {symbol} "
                f"on {requested_date.isoformat()}."
            )
        result = await self.fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "requested_holdings_date": requested_date.isoformat(),
        }
        return result


@dataclass(frozen=True, slots=True)
class IssuerCsvAdapterConfig:
    adapter_key: str
    source_provider: str
    source_access: str = "issuer_public_holdings_file"
    url_templates: tuple[str, ...] = ()
    product_page_templates: tuple[str, ...] = ()
    required_identifiers: tuple[str, ...] = ()
    live_tested_default_route: bool = False
    supports_sec_filing_fallback: bool = True
    terms_note: str | None = None


class IssuerCsvHoldingsAdapter(PublicCsvHoldingsAdapter):
    """Issuer-aware CSV adapter driven by ETF identity/profile metadata.

    Free issuer files are useful but brittle. This adapter resolves routes from
    ETF profile identifiers, issuer-specific templates, and provider-specific
    built-in route catalogues where those routes are stable enough to test live.
    """

    source_url_aliases: tuple[str, ...] = (
        "holdings_url",
        "source_url",
        "issuer_holdings_url",
        "holdings_file_url",
    )
    url_template_aliases: tuple[str, ...] = (
        "holdings_url_template",
        "source_url_template",
    )
    dated_url_template_aliases: tuple[str, ...] = (
        "dated_holdings_url_template",
        "dated_source_url_template",
    )
    generic_dated_url_template_aliases: tuple[str, ...] = (
        "dated_holdings_url_template",
        "dated_source_url_template",
    )
    product_page_aliases = (
        "product_url",
        "issuer_product_url",
        "fund_url",
        "profile_url",
        "etf_url",
    )

    def __init__(self, config: IssuerCsvAdapterConfig) -> None:
        super().__init__(config.adapter_key, config.source_provider)
        self.config = config

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        normalized = self._normalized_identifiers(
            symbol=symbol,
            issuer_product_id=_identifier(
                identifiers,
                "issuer_product_id",
                "fund_id",
                "product_id",
                "sec_series_id",
            ),
            identifiers=identifiers,
        )
        source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=normalized.get("issuer_product_id"),
            source_url=_identifier(identifiers, *self.source_url_aliases),
            identifiers=identifiers,
        )
        if source_url is not None:
            return HoldingsAdapterProbe(
                adapter_key=self.adapter_key,
                confidence=Decimal("0.9000"),
                status="ready",
                reason="ETF profile contains enough issuer route metadata to fetch holdings.",
                source_url=source_url,
                issuer_product_id=normalized.get("issuer_product_id"),
            )
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=normalized.get("issuer_product_id"),
            identifiers=identifiers,
        )
        if product_page_url:
            return HoldingsAdapterProbe(
                adapter_key=self.adapter_key,
                confidence=Decimal("0.8000"),
                status="ready",
                reason="ETF profile has an issuer product page for holdings-link discovery.",
                source_url=product_page_url,
                issuer_product_id=normalized.get("issuer_product_id"),
            )

        sec_cik = _identifier(normalized, "sec_cik")
        if self.config.supports_sec_filing_fallback and sec_cik:
            return HoldingsAdapterProbe(
                adapter_key=self.adapter_key,
                confidence=Decimal("0.7800"),
                status="ready",
                reason=(
                    "ETF matched this issuer and has SEC identifiers, so holdings "
                    "can be reconstructed from SEC EDGAR filings even without an "
                    "issuer-native holdings route."
                ),
                source_url=f"https://data.sec.gov/submissions/CIK{sec_cik.zfill(10)}.json",
                issuer_product_id=normalized.get("issuer_product_id"),
            )

        missing = [
            key for key in self.config.required_identifiers if key not in normalized
        ]
        provider_specific_dated_aliases = tuple(
            alias
            for alias in self.dated_url_template_aliases
            if alias not in self.generic_dated_url_template_aliases
        )
        has_known_route_shape = bool(
            self.config.url_templates
            or self.config.product_page_templates
            or self.config.required_identifiers
            or provider_specific_dated_aliases
        )
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.6500"),
            status="needs_issuer_route" if has_known_route_shape else "needs_provider_implementation",
            reason=(
                "ETF matched this issuer, but SEC identifiers are required before "
                "the universal EDGAR holdings fallback can be used."
                if not has_known_route_shape
                else (
                    "ETF matched this issuer, but the provider-specific route "
                    "metadata required by this adapter is not configured yet and "
                    "SEC identifiers are not available for fallback."
                )
            ),
            issuer_product_id=normalized.get("issuer_product_id"),
            required_identifiers=missing or list(self.config.required_identifiers) or ["sec_cik"],
        )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        identifiers = identifiers or {}
        explicit = _identifier(identifiers, *self.source_url_aliases)
        if explicit:
            return explicit

        values = self._normalized_identifiers(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        for key in self.url_template_aliases:
            template = _identifier(identifiers, key)
            if template:
                resolved = _format_template(template, values)
                if resolved:
                    return resolved
        if _identifier(identifiers, *self.product_page_aliases):
            return None
        for template in self.config.url_templates:
            resolved = _format_template(template, values)
            if resolved:
                return resolved
        return None

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        identifiers = identifiers or {}
        explicit = _identifier(identifiers, *self.product_page_aliases)
        if explicit:
            return explicit
        values = self._normalized_identifiers(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        for template in self.config.product_page_templates:
            resolved = _format_template(template, values)
            if resolved:
                return resolved
        return None

    def resolve_dated_source_url(
        self,
        *,
        symbol: str,
        requested_date: date,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        identifiers = identifiers or {}
        values = self._normalized_identifiers(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        values.update(
            {
                "date": requested_date.isoformat(),
                "date_yyyymmdd": requested_date.strftime("%Y%m%d"),
                "date_yyyy_mm_dd": requested_date.strftime("%Y-%m-%d"),
                "year": requested_date.strftime("%Y"),
                "month": requested_date.strftime("%m"),
                "day": requested_date.strftime("%d"),
            }
        )
        for key in self.dated_url_template_aliases:
            template = _identifier(identifiers, key)
            if template:
                resolved = _format_template(template, values)
                if resolved:
                    return resolved
        return None

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            resolved_source_url = await self._discover_source_url_from_product_page(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                identifiers=identifiers or {}
            )
            if not resolved_source_url:
                if self.config.supports_sec_filing_fallback:
                    sec_result = await self._fetch_latest_sec_filing_holdings(
                        symbol=symbol,
                        issuer_product_id=issuer_product_id,
                        identifiers=identifiers or {},
                    )
                    if sec_result is not None:
                        return sec_result
                probe = self.probe(symbol=symbol, name="", identifiers=identifiers or {})
                required = ", ".join(probe.required_identifiers) or "provider-specific route"
                raise ValueError(
                    f"{self.adapter_key} needs issuer route metadata for {symbol}; "
                    f"configure the adapter-specific route fields or SEC fallback identifiers: "
                    f"product_url, {required}."
                )
            route_resolution = "issuer_product_page_discovery"
        else:
            route_resolution = "issuer_profile_metadata"
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=resolved_source_url,
            identifiers=identifiers,
        )
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_access": self.config.source_access,
            "source_provider": self.source_provider,
            "adapter_key": self.adapter_key,
            "terms_note": self.config.terms_note,
            "route_resolution": route_resolution,
        }
        return result

    async def _fetch_latest_sec_filing_holdings(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None,
        identifiers: dict[str, str],
    ) -> HoldingsFetchResult | None:
        sec_cik = _identifier(identifiers, "sec_cik")
        if not sec_cik:
            return None

        from app.services.etf_holdings_edgar import (  # noqa: PLC0415
            LEGACY_HOLDINGS_FORMS,
            NPORT_FORMS,
            discover_holdings_filings,
        )
        from app.services.etf_holdings_sec import (  # noqa: PLC0415
            parse_sec_legacy_holdings_xml,
            parse_sec_nport_xml,
        )

        attempts = [
            ("SEC N-PORT", NPORT_FORMS, parse_sec_nport_xml, "sec-nport-v1", "nport_xml"),
            (
                "SEC legacy holdings",
                LEGACY_HOLDINGS_FORMS,
                parse_sec_legacy_holdings_xml,
                "sec-legacy-v1",
                "legacy_xml_table",
            ),
        ]
        failures: list[str] = []
        for label, forms, parser, parser_version, source_format in attempts:
            try:
                filings = await discover_holdings_filings(
                    cik=sec_cik,
                    forms=forms,
                    max_filings=5,
                )
            except Exception as exc:  # noqa: BLE001 - collect all fallback attempts.
                failures.append(f"{label} discovery failed: {exc}")
                continue

            async with httpx.AsyncClient(
                timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS
            ) as client:
                for filing in filings:
                    try:
                        response = await client.get(
                            filing.filing_url,
                            headers={"User-Agent": settings.EDGAR_USER_AGENT},
                            follow_redirects=True,
                        )
                        response.raise_for_status()
                        composition_date, rows = parser(response.text)
                    except Exception as exc:  # noqa: BLE001 - try the next filing.
                        failures.append(f"{label} {filing.accession_number} failed: {exc}")
                        continue
                    composition_date = composition_date or filing.report_date
                    if not composition_date or not rows:
                        failures.append(
                            f"{label} {filing.accession_number} had no parseable holdings rows."
                        )
                        continue
                    return HoldingsFetchResult(
                        rows=rows,
                        raw_text=response.text,
                        source_url=filing.filing_url,
                        source_identifier=filing.accession_number,
                        legal_metadata={
                            "source_access": "sec_filing",
                            "source_provider": "sec",
                            "adapter_key": self.adapter_key,
                            "source_format": source_format,
                            "route_resolution": "sec_edgar_filing_fallback",
                            "composition_date": composition_date.isoformat(),
                            "as_of_date": (
                                filing.report_date.isoformat()
                                if filing.report_date
                                else composition_date.isoformat()
                            ),
                            "form": filing.form,
                            "accession_number": filing.accession_number,
                            "parser_version": parser_version,
                            "snapshot_provenance": (
                                "sec_nport_reconstructed_holdings"
                                if parser_version == "sec-nport-v1"
                                else "sec_legacy_reconstructed_holdings"
                            ),
                            "source_quality": "filing_reconstructed_holdings",
                            "completeness_status": "filing_reconstructed",
                            "terms_note": "Reconstructed from SEC EDGAR public holdings filings.",
                        },
                    )

        if failures:
            raise ValueError("; ".join(failures))
        return None

    async def fetch_for_date(
        self,
        *,
        symbol: str,
        requested_date: date,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_dated_source_url(
            symbol=symbol,
            requested_date=requested_date,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(
                f"{self.adapter_key} needs a dated holdings URL template for {symbol}; "
                "configure that provider's dated holdings URL template alias."
            )
        result = await super().fetch_for_date(
            symbol=symbol,
            requested_date=requested_date,
            issuer_product_id=issuer_product_id,
            source_url=resolved_source_url,
            identifiers=identifiers,
        )
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_access": self.config.source_access,
            "source_provider": self.source_provider,
            "adapter_key": self.adapter_key,
            "terms_note": self.config.terms_note,
            "route_resolution": "issuer_dated_profile_template",
        }
        return result

    async def _discover_source_url_from_product_page(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None,
        identifiers: dict[str, str],
    ) -> str | None:
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if not product_page_url:
            return None
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        return _discover_holdings_download_url(product_page_url, response.text)

    def _normalized_identifiers(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None,
        identifiers: dict[str, str],
    ) -> dict[str, str]:
        values: dict[str, str] = {
            "symbol": symbol.strip().upper(),
            "symbol_upper": symbol.strip().upper(),
            "symbol_lower": symbol.strip().lower(),
        }
        for key, value in identifiers.items():
            if value is not None and str(value).strip():
                values[key.strip().lower()] = str(value).strip()
        if issuer_product_id:
            values["issuer_product_id"] = issuer_product_id.strip()
            values.setdefault("fund_id", issuer_product_id.strip())
            values.setdefault("product_id", issuer_product_id.strip())
        holdings_file_name = _identifier(
            values,
            "holdings_file_name",
            "holdings_file",
            "csv_file_name",
            "issuer_file_name",
        )
        if holdings_file_name:
            values["holdings_file_name"] = holdings_file_name.removesuffix(".csv")
        product_slug = _identifier(values, "product_slug", "slug")
        if product_slug:
            values["product_slug"] = product_slug
        return values


ISHARES_PRODUCT_IDS_BY_SYMBOL: dict[str, str] = {
    "EEM": "239637",
    "IVV": "239726",
    "IWM": "239710",
}

KNOWN_ETF_PROVIDER_METADATA_BY_SYMBOL: dict[str, dict[str, Any]] = {
    "QQQ": {
        "issuer": "Invesco",
        "provider_aliases": {
            "sec_cik": "0001067839",
            "sec_series_id": "S000101292",
            "sec_class_id": "C000271435",
            "sec_fund_tickers_symbol": "QQQ",
        },
    },
    "EEM": {
        "issuer": "iShares",
        "provider_aliases": {
            "issuer_product_id": "239637",
            "sec_cik": "0000930667",
            "sec_series_id": "S000004266",
            "sec_class_id": "C000011970",
            "sec_fund_tickers_symbol": "EEM",
        },
    },
    "IVV": {
        "issuer": "iShares",
        "provider_aliases": {
            "issuer_product_id": "239726",
            "sec_cik": "0001100663",
            "sec_series_id": "S000004310",
            "sec_class_id": "C000012040",
            "sec_fund_tickers_symbol": "IVV",
        },
    },
    "IWM": {
        "issuer": "iShares",
        "provider_aliases": {
            "issuer_product_id": "239710",
            "sec_cik": "0001100663",
            "sec_series_id": "S000004344",
            "sec_class_id": "C000012074",
            "sec_fund_tickers_symbol": "IWM",
        },
    },
    "XLE": {
        "issuer": "State Street Global Advisors",
        "provider_aliases": {
            "sec_cik": "0001064641",
            "sec_series_id": "S000006410",
            "sec_class_id": "C000017596",
            "sec_fund_tickers_symbol": "XLE",
        },
    },
}


def known_etf_route_metadata(symbol: str) -> dict[str, Any]:
    """Return provider-specific route metadata we can safely seed by ticker."""

    normalized_symbol = symbol.strip().upper()
    known_metadata = KNOWN_ETF_PROVIDER_METADATA_BY_SYMBOL.get(normalized_symbol)
    if known_metadata:
        return {
            "issuer": known_metadata.get("issuer"),
            "provider_aliases": dict(known_metadata.get("provider_aliases") or {}),
        }
    ishares_product_id = ISHARES_PRODUCT_IDS_BY_SYMBOL.get(normalized_symbol)
    if ishares_product_id:
        return {
            "issuer": "iShares",
            "provider_aliases": {
                "issuer_product_id": ishares_product_id,
            },
        }
    return {}


class IsharesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """iShares holdings adapter with known product ids for tested ETFs."""

    api_base_url = (
        "https://www.blackrock.com/varnish-api/blk-one01-product-data/"
        "product-data/api/v2/get-product-data?"
    )
    dated_url_template_aliases = (
        "dated_holdings_url_template",
        "dated_source_url_template",
        "ishares_dated_holdings_url_template",
    )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        identifiers = identifiers or {}
        values = self._normalized_identifiers(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        product_id = values.get("issuer_product_id")
        if not product_id:
            return None
        query = urlencode(
            {
                "appSubType": "ISHARES",
                "appType": "PRODUCT_PAGE",
                "component": "holdings.all",
                "locale": "en_US",
                "portfolioId": product_id,
                "targetSite": "us-ishares",
                "userType": "individual",
                "excludeContent": "true",
                "includeConfig": "true",
            }
        )
        return f"{self.api_base_url}{query}"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        if source_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not resolved_source_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=_holdings_request_headers(accept="application/json,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        rows = self._parse_blackrock_holdings_payload(payload)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=payload,
            source_url=resolved_source_url,
            source_identifier=symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "terms_note": self.config.terms_note,
                "route_resolution": "issuer_public_json_api",
                "source_format": "json",
                "composition_date": self._composition_date_from_payload(payload),
            },
        )

    def _normalized_identifiers(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None,
        identifiers: dict[str, str],
    ) -> dict[str, str]:
        values = super()._normalized_identifiers(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        known_product_id = ISHARES_PRODUCT_IDS_BY_SYMBOL.get(symbol.strip().upper())
        if known_product_id:
            values.setdefault("issuer_product_id", known_product_id)
            values.setdefault("fund_id", known_product_id)
            values.setdefault("product_id", known_product_id)
        return values

    def _parse_blackrock_holdings_payload(self, payload: dict[str, Any]) -> list[CanonicalHoldingRow]:
        data_points = self._blackrock_holdings_data_points(payload)
        if not data_points:
            return []
        ticker_values = self._blackrock_values(data_points, "ticker")
        issue_values = self._blackrock_values(data_points, "issueName")
        row_count = max(len(ticker_values), len(issue_values))
        rows: list[CanonicalHoldingRow] = []
        for index in range(row_count):
            row = CanonicalHoldingRow(
                symbol=_clean(self._blackrock_value(data_points, "ticker", index)),
                name=_clean(self._blackrock_value(data_points, "issueName", index)),
                cusip=_clean(self._blackrock_value(data_points, "cusip", index)),
                isin=_clean(self._blackrock_value(data_points, "isin", index)),
                sedol=_clean(self._blackrock_value(data_points, "sedol", index)),
                weight=_decimal_percent_points(
                    self._blackrock_value(data_points, "holdingPercent", index)
                ),
                shares=_decimal(self._blackrock_value(data_points, "unitsHeld", index)),
                market_value=_decimal(self._blackrock_value(data_points, "marketValue", index)),
                currency=_clean(self._blackrock_value(data_points, "currencyCode", index)),
                country=_clean(self._blackrock_value(data_points, "countryOfRisk", index)),
                exchange=_clean(self._blackrock_value(data_points, "exchange", index)),
                holding_type=self._holding_type_from_asset_class(
                    self._blackrock_value(data_points, "assetClass", index)
                ),
                row_type="security",
                source_row_id=str(index + 1),
                extra_data={
                    "source": "blackrock_product_data_api",
                    "sector": _clean(self._blackrock_value(data_points, "sectorName", index)),
                },
            )
            if row.symbol or row.name or row.cusip or row.isin:
                rows.append(row)
        return rows

    @staticmethod
    def _blackrock_holdings_data_points(payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        holdings = payload.get("componentsByNameMap", {}).get("holdings", {})
        all_holdings = holdings.get("containersByNameMap", {}).get("all", {})
        data_points = all_holdings.get("dataPointsByNameMap", {})
        return data_points if isinstance(data_points, dict) else {}

    @staticmethod
    def _blackrock_values(data_points: dict[str, Any], key: str) -> list[Any]:
        data_point = data_points.get(key)
        if not isinstance(data_point, dict):
            return []
        values = data_point.get("value")
        if isinstance(values, list):
            return values
        formatted_values = data_point.get("formattedValue")
        if isinstance(formatted_values, list):
            return formatted_values
        return []

    @classmethod
    def _blackrock_value(cls, data_points: dict[str, Any], key: str, index: int) -> Any:
        values = cls._blackrock_values(data_points, key)
        if index < len(values):
            return values[index]
        return None

    @classmethod
    def _composition_date_from_payload(cls, payload: dict[str, Any]) -> str | None:
        value = cls._blackrock_holdings_data_points(payload).get("asOfDate", {}).get("value")
        if value is None:
            return None
        text = str(value)
        if len(text) != 8 or not text.isdigit():
            return None
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"

    @staticmethod
    def _holding_type_from_asset_class(value: Any) -> str:
        text = (_clean(value) or "").lower()
        if "cash" in text:
            return "cash"
        if "bond" in text or "fixed income" in text:
            return "fixed_income"
        return "equity"


ARK_HOLDINGS_FILE_STEMS: dict[str, str] = {
    "ARKB": "ARK_21SHARES_BITCOIN_ETF_ARKB_HOLDINGS",
    "ARKF": "ARK_FINTECH_INNOVATION_ETF_ARKF_HOLDINGS",
    "ARKG": "ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS",
    "ARKK": "ARK_INNOVATION_ETF_ARKK_HOLDINGS",
    "ARKQ": "ARK_AUTONOMOUS_TECHNOLOGY_&_ROBOTICS_ETF_ARKQ_HOLDINGS",
    "ARKW": "ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS",
    "ARKX": "ARK_SPACE_EXPLORATION_&_INNOVATION_ETF_ARKX_HOLDINGS",
    "IZRL": "ARK_ISRAEL_INNOVATIVE_TECHNOLOGY_ETF_IZRL_HOLDINGS",
    "PRNT": "THE_3D_PRINTING_ETF_PRNT_HOLDINGS",
}


class ArkHoldingsAdapter(IssuerCsvHoldingsAdapter):
    dated_url_template_aliases = (
        "dated_holdings_url_template",
        "dated_source_url_template",
        "ark_dated_holdings_url_template",
    )

    def _normalized_identifiers(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None,
        identifiers: dict[str, str],
    ) -> dict[str, str]:
        values = super()._normalized_identifiers(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        holdings_file_name = ARK_HOLDINGS_FILE_STEMS.get(symbol.strip().upper())
        if holdings_file_name:
            values.setdefault("holdings_file_name", holdings_file_name)
        return values


class SpdrHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class VanguardHoldingsAdapter(IssuerCsvHoldingsAdapter):
    holding_types = (
        "stock",
        "bond",
        "short-term-reserve",
        "currency",
        "derivative",
        "commodity",
        "money-market",
    )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        identifiers = identifiers or {}
        fund_id = _identifier(identifiers, "vanguard_fund_id", "fund_id", "issuer_product_id")
        lookup_id = (fund_id or issuer_product_id or symbol).strip().upper()
        if not lookup_id:
            return None
        return f"https://investor.vanguard.com/vmf/api/{lookup_id}/portfolio-holding/stock.json"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        identifiers = identifiers or {}
        normalized_symbol = symbol.strip().upper()
        lookup_id = (
            _identifier(identifiers, "vanguard_fund_id", "fund_id", "issuer_product_id")
            or issuer_product_id
            or normalized_symbol
        )
        if not lookup_id:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        rows: list[CanonicalHoldingRow] = []
        raw_payloads: dict[str, Any] = {}
        source_urls: list[str] = []
        as_of_dates: set[str] = set()
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            for holding_type in self.holding_types:
                resolved_source_url = (
                    source_url
                    if source_url and holding_type == "stock"
                    else (
                        "https://investor.vanguard.com/vmf/api/"
                        f"{lookup_id}/portfolio-holding/{holding_type}.json?start=1&count=20000"
                    )
                )
                response = await client.get(
                    resolved_source_url,
                    headers=_issuer_page_request_headers(accept="application/json,*/*"),
                    follow_redirects=True,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("status") in {404, "404"}:
                    continue
                parsed_rows = self._parse_vanguard_payload(
                    payload,
                    holding_type=holding_type,
                    row_offset=len(rows),
                )
                if not parsed_rows:
                    continue
                raw_payloads[holding_type] = payload
                source_urls.append(resolved_source_url)
                as_of_date = _clean(payload.get("asOfDate"))
                if as_of_date:
                    as_of_dates.add(as_of_date)
                rows.extend(parsed_rows)
                if source_url:
                    break

        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        primary_source_url = source_urls[0] if source_urls else self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=json.dumps(raw_payloads),
            raw_json={"holdings_by_type": raw_payloads},
            source_url=primary_source_url,
            source_identifier=lookup_id,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_public_json_api",
                "holding_types": list(raw_payloads),
                "composition_date": min(as_of_dates) if as_of_dates else None,
                "as_of_date": min(as_of_dates) if as_of_dates else None,
                "terms_note": self.config.terms_note,
            },
        )

    def _parse_vanguard_payload(
        self,
        payload: dict[str, Any],
        *,
        holding_type: str,
        row_offset: int,
    ) -> list[CanonicalHoldingRow]:
        fund = payload.get("fund")
        entities = fund.get("entity") if isinstance(fund, dict) else None
        if isinstance(entities, dict):
            entities = [entities]
        if not isinstance(entities, list):
            return []

        rows: list[CanonicalHoldingRow] = []
        for index, item in enumerate(entities, start=1):
            if not isinstance(item, dict):
                continue
            symbol_value = _clean(item.get("ticker"))
            name = _clean(item.get("longName") or item.get("shortName") or item.get("securityName"))
            cusip = _clean(item.get("cusip"))
            isin = _clean(item.get("isin"))
            if not any([symbol_value, name, cusip, isin]):
                continue
            normalized_holding_type = (
                _clean(item.get("holdingType") or item.get("secMainType") or holding_type)
                or holding_type
            ).lower()
            row_type = "cash" if holding_type in {"currency", "money-market"} else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value,
                    name=name,
                    cusip=cusip,
                    isin=isin,
                    sedol=_clean(item.get("sedol")),
                    weight=_decimal_percent_points(item.get("percentWeight")),
                    shares=_decimal(item.get("sharesHeld")),
                    market_value=_decimal(item.get("marketValue")),
                    currency=_clean(item.get("currency")),
                    holding_type=normalized_holding_type,
                    row_type=row_type,
                    source_row_id=str(row_offset + index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows


class InvescoHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        identifiers = identifiers or {}
        if _identifier(identifiers, *self.product_page_aliases):
            return None
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return None
        return (
            "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/"
            f"{normalized_symbol}/holdings/fund?idType=ticker&interval=monthly&productType=ETF"
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=_invesco_holdings_request_headers(),
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        holdings = payload.get("holdings") if isinstance(payload, dict) else None
        rows: list[CanonicalHoldingRow] = []
        for index, item in enumerate(holdings or [], start=1):
            if not isinstance(item, dict):
                continue
            symbol_value = _clean(item.get("ticker"))
            name = _clean(item.get("issuerName") or item.get("securityName"))
            if not any([symbol_value, name, item.get("cusip")]):
                continue
            holding_type = (_clean(item.get("securityTypeName")) or "security").lower()
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value,
                    name=name,
                    cusip=_clean(item.get("cusip")),
                    weight=_decimal_percent_points(item.get("percentageOfTotalNetAssets")),
                    shares=_decimal(item.get("units")),
                    currency=_clean(item.get("currency") or item.get("localCurrencyName")),
                    holding_type=holding_type,
                    row_type="cash" if holding_type in {"cash", "currency"} else "security",
                    source_row_id=str(index),
                    extra_data={key: value for key, value in item.items() if value not in (None, "")},
                )
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=payload,
            source_url=resolved_source_url,
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_public_json_api",
                "effective_date": payload.get("effectiveDate") if isinstance(payload, dict) else None,
                "effective_business_date": (
                    payload.get("effectiveBusinessDate") if isinstance(payload, dict) else None
                ),
                "total_number_of_holdings": (
                    payload.get("totalNumberOfHoldings") if isinstance(payload, dict) else None
                ),
                "terms_note": self.config.terms_note,
            },
        )


class SchwabHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers()
        headers["Referer"] = "https://www.schwabassetmanagement.com/"
        return headers


class GlobalXHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class VanEckHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class VoyaHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Voya ETF daily holdings from its issuer-hosted account CSV feed."""

    HOLDINGS_URL = "https://vimetfs.com/{symbol_lower}/holdings"

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        return self.HOLDINGS_URL.format(symbol_lower=normalized_symbol) if normalized_symbol else None

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="text/csv,text/plain,*/*")
        headers["Referer"] = "https://vimetfs.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        resolved_url = self.resolve_source_url(
            symbol=normalized_symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_url:
            raise ValueError(f"Voya holdings route not found for {normalized_symbol}.")
        response = await asyncio.to_thread(
            requests.get,
            resolved_url,
            headers=self.source_request_headers(source_url=resolved_url),
            timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()

        rows, composition_date = self._parse_csv(response.text, symbol=normalized_symbol)
        if not rows:
            raise ValueError(f"Voya returned no holdings for {normalized_symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={"source_format": "csv"},
            source_url=str(response.url),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": "issuer_public_daily_holdings_csv",
                "source_provider": "voya",
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "voya_symbol_daily_holdings_csv",
                **(
                    {"composition_date": composition_date.isoformat()}
                    if composition_date
                    else {}
                ),
            },
        )

    @classmethod
    def _parse_csv(
        cls,
        raw_csv: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        parsed_rows = csv.DictReader(StringIO(raw_csv.strip()))
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, raw_row in enumerate(parsed_rows):
            if (_clean(raw_row.get("Account")) or "").upper() != symbol:
                continue
            if composition_date is None:
                composition_date = cls._parse_date(raw_row.get("Date"))
            name = _clean(raw_row.get("SecurityName"))
            source_ticker = _clean(raw_row.get("StockTicker"))
            source_identifier = _clean(raw_row.get("CUSIP"))
            row_type, holding_type = cls._classify_row(name=name, source_ticker=source_ticker)
            row_symbol = source_ticker if row_type == "security" else None
            if not any([row_symbol, name, source_identifier]):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=row_symbol,
                    name=name,
                    cusip=source_identifier if row_type == "security" else None,
                    weight=_decimal(raw_row.get("Weightings")),
                    shares=_decimal(raw_row.get("Shares")),
                    market_value=_decimal(raw_row.get("MarketValue")),
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{symbol}:{index}",
                    extra_data={
                        "source_ticker": source_ticker,
                        "source_identifier": source_identifier,
                        "price": _clean(raw_row.get("Price")),
                        "net_assets": _clean(raw_row.get("NetAssets")),
                        "shares_outstanding": _clean(raw_row.get("SharesOutstanding")),
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _classify_row(
        *,
        name: str | None,
        source_ticker: str | None,
    ) -> tuple[str, str]:
        text = (name or "").upper()
        if any(token in text for token in ("CASH BALANCE", "IM BALANCE", "CASH COLLATERAL")):
            return "cash", "cash"
        if any(
            token in text
            for token in (
                "U.S. DOLLAR",
                "MEXICAN ",
                "KRONE",
                "EURO",
                "POUND STERLING",
                "YEN",
            )
        ):
            return "other", "forex"
        if any(token in text for token in ("CDX.", "FUTURE", "SWAP", "OPTION")):
            return "other", "derivative"
        if source_ticker:
            return "security", "equity"
        return "security", "fixed_income"

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        try:
            return datetime.strptime(text, "%m/%d/%Y").date()
        except ValueError:
            return None


class LazardHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Lazard ETF holdings from the issuer's public product API.

    Lazard's ETF directory exposes the issuer product ids, while the public API
    returns the full constituent payload for each product. Resolving that id in
    the adapter keeps a profile usable from just its trading symbol.
    """

    ETF_DIRECTORY_URL = (
        "https://www.lazardassetmanagement.com/us/en_us/"
        "investment-solutions/how-to-invest/etfs"
    )
    PRODUCT_API_URL = "https://lazardassetmanagement.com/api/products"
    PRODUCT_PATH_RE = re.compile(
        r'href=["\'](?:https?://www\.lazardassetmanagement\.com)?'
        r'(?P<path>/us/en_us/investment-solutions/how-to-invest/108/(?P<id>\d+))["\']',
        re.IGNORECASE,
    )

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        product_id = _identifier(identifiers, "issuer_product_id", "fund_id", "product_id")
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason=(
                "Lazard's public ETF directory resolves product ids and its public product API "
                "returns full ETF constituent holdings."
            ),
            source_url=self.PRODUCT_API_URL if product_id else self.ETF_DIRECTORY_URL,
            issuer_product_id=product_id,
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="application/json,*/*")
        headers["Referer"] = self.ETF_DIRECTORY_URL
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("Lazard holdings require an ETF symbol.")
        normalized_identifiers = identifiers or {}
        product_id = (
            issuer_product_id
            or _identifier(normalized_identifiers, "issuer_product_id", "fund_id", "product_id")
        )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if not product_id:
                product_id = await self._discover_product_id(client, symbol=normalized_symbol)
            if not product_id:
                raise ValueError(f"Lazard ETF product id not found for {normalized_symbol}.")

            resolved_url = source_url or self._product_api_url(product_id)
            response = await client.get(
                resolved_url,
                headers=self.source_request_headers(source_url=resolved_url),
                follow_redirects=True,
            )
            response.raise_for_status()

        payload = self._unwrap_payload(response.json(), product_id=product_id)
        rows, composition_date, source_symbol = self._parse_payload(payload, symbol=normalized_symbol)
        if source_symbol and source_symbol != normalized_symbol:
            raise ValueError(
                f"Lazard returned {source_symbol} holdings for {normalized_symbol}."
            )
        if not rows:
            raise ValueError(f"Lazard returned no holdings for {normalized_symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=payload,
            source_url=str(response.url),
            source_identifier=product_id,
            legal_metadata={
                "source_access": "issuer_public_product_api_full_holdings_json",
                "source_provider": "lazard",
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "lazard_etf_directory_product_api",
                "product_id": product_id,
                "product_url": f"{self.ETF_DIRECTORY_URL}#etfs",
                **(
                    {"composition_date": composition_date.isoformat()}
                    if composition_date
                    else {}
                ),
            },
        )

    async def _discover_product_id(self, client: httpx.AsyncClient, *, symbol: str) -> str | None:
        directory_response = await client.get(
            self.ETF_DIRECTORY_URL,
            headers=_issuer_page_request_headers(),
            follow_redirects=True,
        )
        directory_response.raise_for_status()
        product_ids = list(
            dict.fromkeys(
                match.group("id") for match in self.PRODUCT_PATH_RE.finditer(directory_response.text)
            )
        )
        for product_id in product_ids:
            response = await client.get(
                self._product_api_url(product_id),
                headers=self.source_request_headers(source_url=self.PRODUCT_API_URL),
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = self._unwrap_payload(response.json(), product_id=product_id)
            source_symbol = _clean(
                ((payload.get("data") or {}).get("etfg") or {}).get("ticker")
            )
            if source_symbol and source_symbol.upper() == symbol:
                return product_id
        return None

    @classmethod
    def _product_api_url(cls, product_id: str) -> str:
        return cls.PRODUCT_API_URL + "?" + urlencode({"id": product_id, "type": "Fund"})

    @staticmethod
    def _unwrap_payload(payload: Any, *, product_id: str) -> dict[str, Any]:
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and str(item.get("id") or "") == product_id:
                    return item
        if isinstance(payload, dict):
            return payload
        raise ValueError(f"Lazard returned an invalid product payload for {product_id}.")

    @classmethod
    def _parse_payload(
        cls,
        payload: dict[str, Any],
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None, str | None]:
        etfg = (payload.get("data") or {}).get("etfg")
        if not isinstance(etfg, dict):
            return [], None, None
        source_symbol = _clean(etfg.get("ticker"))
        composition_date = cls._parse_date(etfg.get("asOfDate"))
        currency = _clean(etfg.get("discountPremiumCurrencyCode"))
        raw_rows = etfg.get("constituents")
        if not isinstance(raw_rows, list):
            return [], composition_date, source_symbol.upper() if source_symbol else None

        rows: list[CanonicalHoldingRow] = []
        for index, raw_row in enumerate(raw_rows):
            if not isinstance(raw_row, dict):
                continue
            name = _clean(raw_row.get("entityName"))
            source_ticker = _clean(raw_row.get("constituentTicker"))
            security_type = _clean(raw_row.get("securityTypeName"))
            row_type, holding_type = cls._classify_row(name=name, security_type=security_type)
            row_symbol = cls._tradable_symbol(source_ticker) if row_type == "security" else None
            if not any(
                [
                    row_symbol,
                    name,
                    _clean(raw_row.get("cusip")),
                    _clean(raw_row.get("isin")),
                    _clean(raw_row.get("sedol")),
                ]
            ):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=row_symbol,
                    name=name,
                    cusip=_clean(raw_row.get("cusip")),
                    isin=_clean(raw_row.get("isin")),
                    sedol=_clean(raw_row.get("sedol")),
                    weight=_decimal_percent_points(raw_row.get("weight")),
                    shares=_decimal(raw_row.get("sharesHeld")),
                    market_value=_decimal(raw_row.get("marketValue")),
                    currency=currency,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{symbol}:{index}",
                    extra_data={
                        "source_ticker": source_ticker,
                        "security_type": security_type,
                        "security_type_code": _clean(raw_row.get("securityType")),
                        "asset_class": _clean(raw_row.get("assetClass")),
                    },
                )
            )
        return rows, composition_date, source_symbol.upper() if source_symbol else None

    @staticmethod
    def _classify_row(*, name: str | None, security_type: str | None) -> tuple[str, str]:
        text = f"{name or ''} {security_type or ''}".upper()
        if "CASH" in text or "MONEY MARKET" in text:
            return "cash", "cash"
        if any(token in text for token in ("CURRENCY", "FOREX", "FX")):
            return "other", "forex"
        if any(token in text for token in ("FUTURE", "OPTION", "SWAP", "DERIVATIVE")):
            return "other", "derivative"
        if any(token in text for token in ("BOND", "NOTE", "DEBT", "FIXED INCOME")):
            return "security", "fixed_income"
        if any(token in text for token in ("FUND", "ETF")):
            return "security", "fund"
        return "security", "equity"

    @staticmethod
    def _tradable_symbol(value: str | None) -> str | None:
        text = _clean(value)
        if text is None:
            return None
        normalized = text.upper()
        return normalized if re.fullmatch(r"[A-Z0-9][A-Z0-9.\-/]{0,14}", normalized) else None

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None


class RexHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch complete REX Shares holdings through the issuer's public CSV form."""

    PRODUCT_PAGE_TEMPLATE = "https://www.rexshares.com/{symbol_lower}/"

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        normalized_symbol = symbol.strip().upper()
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason=(
                "REX Shares publishes complete ETF holdings through the public CSV download "
                "form on each ETF product page."
            ),
            source_url=self._product_page_url(normalized_symbol),
            issuer_product_id=normalized_symbol,
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        del issuer_product_id, identifiers
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("REX holdings require an ETF symbol.")
        product_page_url = source_url or self._product_page_url(normalized_symbol)
        # REX's WordPress form serves its CSV reliably through requests, while
        # the same public endpoint rejects the async client's TLS fingerprint.
        response = await asyncio.to_thread(
            requests.post,
            product_page_url,
            data={"CSV": "Download CSV", "symbol": normalized_symbol},
            headers=self._request_headers(product_page_url),
            timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()
        rows = self._parse_csv(response.text, symbol=normalized_symbol)
        if not rows:
            raise ValueError(f"REX Shares returned no complete holdings CSV rows for {normalized_symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(response.url),
            source_identifier=normalized_symbol,
            legal_metadata={
                "source_access": "issuer_public_product_page_posted_full_holdings_csv",
                "source_provider": "rex",
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "rex_product_page_complete_holdings_csv_form",
                "product_page_url": product_page_url,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _product_page_url(cls, symbol: str) -> str:
        return cls.PRODUCT_PAGE_TEMPLATE.format(symbol_lower=symbol.lower())

    @staticmethod
    def _request_headers(product_page_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="text/csv,text/plain,*/*")
        headers["Referer"] = product_page_url
        return headers

    @classmethod
    def _parse_csv(cls, raw_csv: str, *, symbol: str) -> list[CanonicalHoldingRow]:
        table_rows = list(csv.reader(StringIO(raw_csv.strip())))
        rows = parse_holdings_table(table_rows)
        for row in rows:
            source_symbol = row.symbol
            text = f"{source_symbol or ''} {row.name or ''}".upper()
            if cls._is_cash(text):
                row.symbol = None
                row.row_type = "cash"
                row.holding_type = "cash"
            elif cls._is_derivative(text):
                row.symbol = None
                row.row_type = "other"
                row.holding_type = "derivative"
            elif cls._is_money_market(text):
                row.row_type = "cash"
                row.holding_type = "cash"
            else:
                row.row_type = "security"
                row.holding_type = "equity"
            row.currency = row.currency or "USD"
            row.source_row_id = row.source_row_id or f"{symbol}:{len(rows)}"
            row.extra_data = {
                **row.extra_data,
                "source_ticker": source_symbol,
                "source": "rex_product_page_complete_holdings_csv",
            }
        return rows

    @staticmethod
    def _is_cash(text: str) -> bool:
        return any(token in text for token in ("CASH&OTHER", "CASH & OTHER", "CASH AND OTHER"))

    @staticmethod
    def _is_money_market(text: str) -> bool:
        return any(token in text for token in ("MONEY MARKET", "GOVERNMENT OBLIG", "TREASURY OBLIG"))

    @staticmethod
    def _is_derivative(text: str) -> bool:
        return any(token in text for token in ("SWAP", " OPTION", " FUTURE", "-TRS-")) or bool(
            re.search(r"\b\d{2}/\d{2}/\d{2}\s+[CP]\d+(?:\s|$)", text)
        )


class EldridgeHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch the combined public daily holdings file published for Eldridge ETFs."""

    DAILY_HOLDINGS_URL = (
        "https://clozfund.com/assets/data/"
        "FilepointPanagram.40P2.P2_Holdings.csv"
    )

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason="Eldridge publishes a combined daily CSV with full CLOX and CLOZ holdings.",
            source_url=self.DAILY_HOLDINGS_URL,
            issuer_product_id=symbol.strip().upper() or None,
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("eldridge needs an ETF symbol.")

        # The issuer intentionally publishes CLOX and CLOZ in one daily file.
        # Always use that native route and select only the requested account.
        result = await super().fetch_latest(
            symbol=normalized_symbol,
            issuer_product_id=issuer_product_id or normalized_symbol,
            source_url=self.DAILY_HOLDINGS_URL,
            identifiers=identifiers,
        )
        rows = [
            row
            for row in result.rows
            if str(row.extra_data.get("Account", "")).strip().upper() == normalized_symbol
        ]
        if not rows:
            raise ValueError(
                f"Eldridge daily holdings do not contain the requested ETF {normalized_symbol}."
            )

        for row in rows:
            source_symbol = _clean(row.extra_data.get("StockTicker"))
            name = row.name or _clean(row.extra_data.get("SecurityName")) or ""
            text = f"{source_symbol or ''} {name}".upper()
            row.source_row_id = row.source_row_id or f"{normalized_symbol}:{row.cusip or name}"
            row.extra_data = {
                **row.extra_data,
                "source_symbol": source_symbol,
                "source": "eldridge_daily_combined_holdings_csv",
            }
            if "CASH" in text or source_symbol == "FXFXX":
                row.symbol = None
                row.row_type = "cash"
                row.holding_type = "cash"
            else:
                # The issuer's StockTicker column contains CUSIP-like loan/CLO
                # identifiers, not exchange-traded instrument tickers.
                row.symbol = None
                row.row_type = "security"
                row.holding_type = "fixed_income"

        composition_date = self._composition_date(rows)
        result.rows = rows
        result.source_identifier = issuer_product_id or normalized_symbol
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_access": self.config.source_access,
            "source_provider": self.source_provider,
            "adapter_key": self.adapter_key,
            "route_resolution": "issuer_combined_daily_holdings_csv",
            "composition_date": composition_date.isoformat() if composition_date else None,
            "as_of_date": composition_date.isoformat() if composition_date else None,
            "terms_note": self.config.terms_note,
        }
        return result

    @staticmethod
    def _composition_date(rows: list[CanonicalHoldingRow]) -> date | None:
        raw_date = _clean(rows[0].extra_data.get("Date")) if rows else None
        if not raw_date:
            return None
        try:
            return datetime.strptime(raw_date, "%m/%d/%Y").date()
        except ValueError:
            return None


class AkreHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch the complete daily FilePoint CSV published by the Akre Focus ETF."""

    HOLDINGS_URL = "https://akre.filepoint.live/assets/data/FilepointAkre.40B4.B4_ETF_Holdings.csv"
    FUND_SYMBOL = "AKRE"

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        normalized_symbol = symbol.strip().upper()
        if normalized_symbol != self.FUND_SYMBOL:
            return super().probe(symbol=symbol, name=name, identifiers=identifiers)
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason="Akre publishes the complete daily Focus ETF holdings CSV through its public FilePoint fund workspace.",
            source_url=self.HOLDINGS_URL,
            issuer_product_id=normalized_symbol or None,
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        del issuer_product_id, source_url, identifiers
        normalized_symbol = symbol.strip().upper()
        if normalized_symbol != self.FUND_SYMBOL:
            raise ValueError("Akre's public FilePoint holdings route currently supports only AKRE.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                self.HOLDINGS_URL,
                headers=_holdings_request_headers(accept="text/csv,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_holdings_csv(response.text)
        if not rows:
            raise ValueError("Akre's public FilePoint CSV returned no AKRE holdings rows.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(getattr(response, "url", self.HOLDINGS_URL)),
            source_identifier=self.FUND_SYMBOL,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_filepoint_daily_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_holdings_csv(cls, raw_csv: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(csv.DictReader(StringIO(raw_csv.strip())), start=1):
            if (_clean(item.get("Account")) or "").upper() != cls.FUND_SYMBOL:
                continue
            row_date = cls._parse_date(item.get("Date"))
            if row_date and (composition_date is None or row_date > composition_date):
                composition_date = row_date
            raw_symbol = _clean(item.get("StockTicker"))
            name = _clean(item.get("SecurityName"))
            holding_type = cls._holding_type(
                raw_symbol=raw_symbol,
                name=name,
                money_market_flag=item.get("MoneyMarketFlag"),
            )
            row_type = "cash" if holding_type == "cash" else "security"
            raw_identifier = _clean(item.get("CUSIP"))
            rows.append(
                CanonicalHoldingRow(
                    symbol=cls._tradable_symbol(raw_symbol) if row_type == "security" else None,
                    name=name,
                    cusip=raw_identifier if _looks_like_cusip(raw_identifier) else None,
                    sedol=raw_identifier if _looks_like_sedol(raw_identifier) else None,
                    weight=_decimal(item.get("Weightings")),
                    shares=_decimal(item.get("Shares")),
                    market_value=_decimal(item.get("MarketValue")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{cls.FUND_SYMBOL}:{index}",
                    extra_data={
                        **{
                            key: value
                            for key, value in item.items()
                            if key is not None and _clean(value) is not None
                        },
                        "source_symbol": raw_symbol,
                        "source": "akre_filepoint_daily_holdings_csv",
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        text = _clean(value)
        if not text:
            return None
        try:
            return datetime.strptime(text, "%m/%d/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _tradable_symbol(value: str | None) -> str | None:
        normalized = _clean(value)
        if not normalized or " " in normalized or _looks_like_cusip(normalized):
            return None
        return normalized.upper() if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,11}", normalized.upper()) else None

    @staticmethod
    def _holding_type(*, raw_symbol: str | None, name: str | None, money_market_flag: Any) -> str:
        text = " ".join(
            value.upper()
            for value in [raw_symbol, name, _clean(money_market_flag)]
            if value
        )
        if "CASH" in text or "MONEY MARKET" in text or _clean(money_market_flag) == "Y":
            return "cash"
        return "equity"


class RayliantHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch full holdings CSVs from Rayliant's published ETF product pages."""

    PRODUCT_SITEMAP_URL = "https://funds.rayliant.com/page-sitemap.xml"

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        del name, identifiers
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason=(
                "Rayliant publishes full holdings CSV downloads from ETF product pages "
                "listed in its public product sitemap."
            ),
            source_url=self.PRODUCT_SITEMAP_URL,
            issuer_product_id=symbol.strip().upper() or None,
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        del issuer_product_id, identifiers
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("Rayliant holdings require an ETF symbol.")

        product_page_url, product_page = await self._discover_product_page(
            normalized_symbol,
            product_page_url=source_url,
        )
        download_url = self._download_url(product_page_url, product_page)
        raw_csv = await self._fetch_text(download_url, accept="text/csv,*/*")
        rows = self._parse_holdings_csv(raw_csv, normalized_symbol)
        if not rows:
            raise ValueError(
                f"Rayliant's full holdings CSV returned no holdings rows for {normalized_symbol}."
            )

        composition_date = self._extract_holdings_date(product_page)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=raw_csv,
            source_url=download_url,
            source_identifier=normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_product_sitemap_full_holdings_csv",
                "product_page_url": product_page_url,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    async def _discover_product_page(
        self,
        symbol: str,
        *,
        product_page_url: str | None,
    ) -> tuple[str, str]:
        if product_page_url:
            raw_html = await self._fetch_text(product_page_url, accept="text/html,*/*")
            if self._page_symbol(raw_html) != symbol:
                raise ValueError(
                    f"Rayliant product page does not identify the requested ETF {symbol}."
                )
            return product_page_url, raw_html

        sitemap = await self._fetch_text(
            self.PRODUCT_SITEMAP_URL,
            accept="application/xml,text/xml,*/*",
        )
        product_page_urls = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", sitemap)
        expected_suffix = f"/{symbol.lower()}/"
        for candidate_url in product_page_urls:
            if not candidate_url.lower().rstrip("/").endswith(expected_suffix.rstrip("/")):
                continue
            raw_html = await self._fetch_text(candidate_url, accept="text/html,*/*")
            if self._page_symbol(raw_html) == symbol:
                return candidate_url, raw_html
        raise ValueError(f"Rayliant's product sitemap did not contain ETF {symbol}.")

    @staticmethod
    async def _fetch_text(url: str, *, accept: str) -> str:
        headers = _issuer_page_request_headers(accept=accept)
        try:
            async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
                response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise
        # Rayliant's CDN permits the same public request through requests but
        # currently rejects httpx's TLS fingerprint. Keep this as a narrow
        # issuer-local transport fallback, not a generic provider fallback.
        response = await asyncio.to_thread(
            requests.get,
            url,
            headers=headers,
            timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()
        return response.text

    @staticmethod
    def _page_symbol(raw_html: str) -> str | None:
        title_match = re.search(r"<title>\s*([A-Za-z0-9.\-]+)\s+Rayliant", raw_html, re.IGNORECASE)
        if title_match:
            return title_match.group(1).upper()
        ticker_match = re.search(r">\s*([A-Za-z][A-Za-z0-9.\-]{0,11})\s*</p>", raw_html)
        return ticker_match.group(1).upper() if ticker_match else None

    @staticmethod
    def _download_url(product_page_url: str, raw_html: str) -> str:
        match = re.search(r'href=["\']([^"\']*\?download_csv=1[^"\']*)["\']', raw_html, re.IGNORECASE)
        if not match:
            raise ValueError("Rayliant product page did not expose its full holdings CSV download.")
        return urljoin(product_page_url, html.unescape(match.group(1)))

    @classmethod
    def _parse_holdings_csv(cls, raw_csv: str, fund_symbol: str) -> list[CanonicalHoldingRow]:
        rows: list[CanonicalHoldingRow] = []
        for index, item in enumerate(csv.DictReader(StringIO(raw_csv.strip())), start=1):
            source_ticker = _clean(item.get("Ticker"))
            name = _clean(item.get("Company Name"))
            identifier = _clean(item.get("Security Identifier"))
            source_text = " ".join(value.upper() for value in [source_ticker, name] if value)
            is_cash = "CASH" in source_text or "MONEY MARKET" in source_text
            symbol = cls._tradable_symbol(source_ticker) if not is_cash else None
            if not any([symbol, source_ticker, name, identifier]):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    sedol=identifier if _looks_like_sedol(identifier) else None,
                    weight=_decimal(item.get("% of Net Assets")),
                    shares=_decimal(item.get("Quantity")),
                    holding_type="cash" if is_cash else "equity",
                    row_type="cash" if is_cash else "security",
                    source_row_id=f"{fund_symbol}:{index}",
                    extra_data={
                        **{
                            key: value
                            for key, value in item.items()
                            if key is not None and _clean(value) is not None
                        },
                        "source_symbol": source_ticker,
                        "source": "rayliant_product_page_full_holdings_csv",
                    },
                )
            )
        return rows

    @staticmethod
    def _tradable_symbol(value: str | None) -> str | None:
        normalized = _clean(value)
        if not normalized or " " in normalized:
            return None
        upper = normalized.upper()
        return upper if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,11}", upper) else None

    @staticmethod
    def _extract_holdings_date(raw_html: str) -> date | None:
        match = re.search(r"\(as\s+of\s+(\d{1,2}[./]\d{1,2}[./]\d{4})\)", raw_html, re.IGNORECASE)
        if not match:
            return None
        for date_format in ("%m.%d.%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(match.group(1), date_format).date()
            except ValueError:
                continue
        return None


class NatixisHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Natixis ETF holdings from its issuer-native daily CSV files."""

    DAILY_HOLDINGS_TEMPLATE = (
        "https://mkt.im.natixis.com/files/etfs/{symbol}_daily_full_holdings.csv"
    )
    INTERMEDIATE_CERTIFICATE_PATH = (
        Path(__file__).resolve().parents[1] / "lib" / "natixis-digicert-intermediate.pem"
    )

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        del name, identifiers
        normalized_symbol = symbol.strip().upper()
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready" if normalized_symbol else "needs_issuer_route",
            reason=(
                "Natixis publishes daily ETF holdings through issuer-native CSV files."
                if normalized_symbol
                else "Natixis holdings require an ETF symbol."
            ),
            source_url=(
                self.DAILY_HOLDINGS_TEMPLATE.format(symbol=normalized_symbol)
                if normalized_symbol
                else None
            ),
            issuer_product_id=normalized_symbol or None,
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        del issuer_product_id, identifiers
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("Natixis holdings require an ETF symbol.")

        daily_holdings_url = source_url or self.DAILY_HOLDINGS_TEMPLATE.format(
            symbol=normalized_symbol
        )
        async with httpx.AsyncClient(
            timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            verify=self._ssl_context(),
        ) as client:
            holdings_response = await client.get(
                daily_holdings_url,
                headers=_holdings_request_headers(accept="text/csv,application/csv,*/*"),
                follow_redirects=True,
            )
        holdings_response.raise_for_status()
        rows, composition_date = self._parse_daily_holdings_csv(
            holdings_response.text,
            symbol=normalized_symbol,
        )
        if not rows:
            raise ValueError(f"Natixis daily holdings CSV returned no rows for {normalized_symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=holdings_response.text,
            raw_json={"source_format": "issuer_daily_holdings_csv"},
            source_url=str(holdings_response.url),
            source_identifier=normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_symbol_daily_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_daily_holdings_csv(
        cls,
        raw_csv: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = list(csv.reader(StringIO(raw_csv)))
        csv_symbol = next(
            (
                match.group(1).upper()
                for row in table_rows[:8]
                for match in [
                    re.search(
                        r"ticker:\s*([A-Za-z][A-Za-z0-9.\-]{0,11})",
                        " ".join(row),
                        re.I,
                    )
                ]
                if match
            ),
            None,
        )
        if csv_symbol != symbol:
            return [], None
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows)
                if {cell.strip().lower() for cell in row}
                >= {"ticker", "cusip", "isin", "security name", "quantity held"}
            ),
            None,
        )
        if header_index is None:
            return [], None
        composition_date = cls._extract_composition_date(table_rows[:header_index])
        data_rows = [table_rows[header_index]] + [
            row
            for row in table_rows[header_index + 1 :]
            if not row
            or not all(not cell.strip() or re.fullmatch(r"-+", cell.strip()) for cell in row)
        ]
        rows = parse_holdings_table(data_rows)
        for index, row in enumerate(rows, start=1):
            row.weight = row.weight or _decimal_percent_points(
                row.extra_data.get("Percent of net assets")
            )
            row.shares = row.shares or _decimal(row.extra_data.get("Quantity held"))
            row.market_value = row.market_value or _decimal(row.extra_data.get("Market value"))
            row.source_row_id = row.source_row_id or f"{symbol}:{index}"
            row.extra_data = {
                **row.extra_data,
                "source": "natixis_daily_holdings_csv",
            }
        return rows, composition_date

    @staticmethod
    def _ssl_context() -> ssl.SSLContext:
        """Keep TLS verification enabled when Natixis omits its public intermediate."""

        context = ssl.create_default_context()
        context.load_verify_locations(cafile=str(NatixisHoldingsAdapter.INTERMEDIATE_CERTIFICATE_PATH))
        return context

    @staticmethod
    def _extract_composition_date(preamble_rows: list[list[str]]) -> date | None:
        for row in preamble_rows:
            text = " ".join(row).strip()
            match = re.search(r"as\s+of\s+date:\s*(\d{2}/\d{2}/\d{4})", text, re.I)
            if not match:
                continue
            try:
                return datetime.strptime(match.group(1), "%m/%d/%Y").date()
            except ValueError:
                continue
        return None


class AstoriaHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch complete holdings tables from Astoria's public ETF product pages."""

    PRODUCT_SITEMAP_URL = "https://astoriaadvisorsetfs.com/wp-sitemap-posts-page-1.xml"

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        del name, identifiers
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason=(
                "Astoria publishes complete current holdings tables on public ETF product pages "
                "listed in its WordPress sitemap."
            ),
            source_url=self.PRODUCT_SITEMAP_URL,
            issuer_product_id=symbol.strip().upper() or None,
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        del issuer_product_id, identifiers
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("Astoria holdings require an ETF symbol.")

        product_page_url, raw_html = await self._discover_product_page(
            normalized_symbol,
            product_page_url=source_url,
        )
        rows = parse_html_holdings_table_by_headers(
            raw_html,
            required_headers={"ticker", "name", "cusip", "shares", "% of net assets"},
        )
        if not rows:
            raise ValueError(
                f"Astoria product page returned no complete holdings rows for {normalized_symbol}."
            )
        for row in rows:
            market_value_millions = _decimal(row.extra_data.get("Market Value ($mm)"))
            if market_value_millions is not None:
                row.market_value = market_value_millions * Decimal("1000000")
            row.source_row_id = row.source_row_id or f"{normalized_symbol}:{row.cusip or row.name}"
            row.extra_data = {
                **row.extra_data,
                "source": "astoria_product_page_complete_holdings_table",
            }

        composition_date = self._composition_date(rows)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=raw_html,
            source_url=product_page_url,
            source_identifier=normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_wordpress_sitemap_complete_holdings_table",
                "product_page_url": product_page_url,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    async def _discover_product_page(
        self,
        symbol: str,
        *,
        product_page_url: str | None,
    ) -> tuple[str, str]:
        if product_page_url:
            raw_html = await self._fetch_page(product_page_url)
            if self._page_symbol(raw_html) != symbol:
                raise ValueError(
                    f"Astoria product page does not identify the requested ETF {symbol}."
                )
            return product_page_url, raw_html

        sitemap = await self._fetch_text(
            self.PRODUCT_SITEMAP_URL,
            accept="application/xml,text/xml,*/*",
        )
        expected_suffix = f"/{symbol.lower()}/"
        for candidate_url in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", sitemap):
            if not candidate_url.lower().rstrip("/").endswith(expected_suffix.rstrip("/")):
                continue
            raw_html = await self._fetch_page(candidate_url)
            if self._page_symbol(raw_html) == symbol:
                return candidate_url, raw_html
        raise ValueError(f"Astoria's ETF sitemap did not contain ETF {symbol}.")

    @staticmethod
    async def _fetch_page(product_page_url: str) -> str:
        return await AstoriaHoldingsAdapter._fetch_text(product_page_url, accept="text/html,*/*")

    @staticmethod
    async def _fetch_text(url: str, *, accept: str) -> str:
        headers = _issuer_page_request_headers(accept=accept)
        try:
            async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
                response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise
        # Astoria's public WordPress site currently accepts requests while
        # rejecting httpx's TLS fingerprint. Keep this issuer-specific.
        response = await asyncio.to_thread(
            requests.get,
            url,
            headers=headers,
            timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()
        return response.text

    @staticmethod
    def _page_symbol(raw_html: str) -> str | None:
        title_match = re.search(r"<title>\s*([A-Za-z][A-Za-z0-9.\-]{0,11})\s+ETF", raw_html, re.IGNORECASE)
        if title_match:
            return title_match.group(1).upper()
        match = re.search(
            r"ASTORIA.{0,200}?\(([A-Za-z][A-Za-z0-9.\-]{0,11})\)",
            raw_html,
            re.IGNORECASE,
        )
        return match.group(1).upper() if match else None

    @staticmethod
    def _composition_date(rows: list[CanonicalHoldingRow]) -> date | None:
        value = _clean(rows[0].extra_data.get("EFFECTIVE_DATE")) if rows else None
        if not value:
            return None
        try:
            return datetime.strptime(value, "%m/%d/%Y").date()
        except ValueError:
            return None


class TortoiseHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch complete daily holdings embedded on Tortoise ETF product pages."""

    ETF_SITEMAP_URL = "https://tortoisecapital.com/etfs-sitemap.xml"

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "fund_id", "product_id"),
            identifiers=identifiers,
        )
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason=(
                "Tortoise publishes complete daily holdings tables directly on each public "
                "ETF product page, discovered through its ETF sitemap."
            ),
            source_url=product_page_url or self.ETF_SITEMAP_URL,
            issuer_product_id=symbol.strip().upper() or None,
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("Tortoise holdings require an ETF symbol.")

        identifiers = identifiers or {}
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=normalized_symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if product_page_url:
            raw_html = await self._fetch_page(product_page_url)
        else:
            product_page_url, raw_html = await self._discover_product_page(normalized_symbol)

        rows = parse_html_holdings_table_by_headers(
            raw_html,
            required_headers={
                "security name",
                "stock ticker",
                "cusip",
                "shares",
                "market value",
                "weight",
            },
        )
        if not rows:
            raise ValueError(
                f"Tortoise product page returned no complete daily holdings rows for {normalized_symbol}."
            )

        composition_date = self._extract_holdings_date(raw_html)
        for row in rows:
            row.source_row_id = row.source_row_id or f"{normalized_symbol}:{row.cusip or row.name}"
            row.extra_data = {
                **row.extra_data,
                "source": "tortoise_product_page_daily_holdings_table",
            }

        return HoldingsFetchResult(
            rows=rows,
            raw_text=raw_html,
            source_url=product_page_url,
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_etf_sitemap_product_page_daily_holdings_table",
                "product_page_url": product_page_url,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    async def _discover_product_page(self, symbol: str) -> tuple[str, str]:
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            sitemap_response = await client.get(
                self.ETF_SITEMAP_URL,
                headers=_issuer_page_request_headers(accept="application/xml,text/xml,*/*"),
                follow_redirects=True,
            )
        sitemap_response.raise_for_status()
        product_page_urls = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", sitemap_response.text)
        for product_page_url in product_page_urls:
            raw_html = await self._fetch_page(product_page_url)
            if self._page_symbol(raw_html) == symbol:
                return product_page_url, raw_html
        raise ValueError(f"Tortoise ETF sitemap did not contain a product page for {symbol}.")

    @staticmethod
    async def _fetch_page(product_page_url: str) -> str:
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        return response.text

    @staticmethod
    def _page_symbol(raw_html: str) -> str | None:
        match = re.search(
            r"<th[^>]*>\s*Ticker\s*</th>\s*<td[^>]*>\s*([A-Za-z0-9.\-]+)",
            raw_html,
            re.IGNORECASE,
        )
        return match.group(1).strip().upper() if match else None

    @staticmethod
    def _extract_holdings_date(raw_html: str) -> date | None:
        holdings_index = raw_html.lower().find('id="holdings"')
        section = raw_html[holdings_index : holdings_index + 12_000] if holdings_index >= 0 else raw_html
        match = re.search(r"\bAs\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", section, re.IGNORECASE)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None


class WisdomTreeHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class VictoryHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch VictoryShares holdings from Victory Capital's public product API."""

    PRODUCT_SITEMAP_URL = "https://investor.vcm.com/sitemap.xml"
    PRODUCT_PATH_MARKER = "/products/victoryshares-etfs/victoryshares-etfs-list/"
    API_KEY_RE = re.compile(r'id=["\'](?:fundApiKey|productDetailKey)["\'][^>]*value=["\']([^"\']+)')
    FUND_ID_RE = re.compile(r'id=["\']fundID["\'][^>]*value=["\']([^"\']+)')
    DEFAULT_PUBLIC_API_KEY = "orcyfZFHdC9GK5Tk4haPn7o3CU5ItULauov6JsF9"
    ALL_HOLDINGS_ENDPOINT = "https://investorapi.vcm.com/search/product/{symbol_upper}/AllHoldings"

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "fund_id", "product_id"),
            identifiers=identifiers,
        )
        source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "fund_id", "product_id"),
            source_url=_identifier(identifiers, *self.source_url_aliases),
            identifiers=identifiers,
        )
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason="VictoryShares exposes public ETF holdings through the Victory Capital product API.",
            source_url=product_page_url or source_url,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "fund_id", "product_id")
            or symbol.strip().upper(),
        )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        api_symbol = (
            issuer_product_id
            or _identifier(identifiers or {}, "fund_id", "product_id", "issuer_product_id")
            or symbol
        ).strip().upper()
        if not api_symbol:
            return None
        return self.ALL_HOLDINGS_ENDPOINT.format(symbol_upper=api_symbol)

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return _identifier(
            identifiers or {},
            "victory_product_page_url",
            "product_url",
            "issuer_product_url",
            "fund_url",
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="application/json,text/plain,*/*"),
            "Referer": "https://advisor.vcm.com/products/victoryshares-etfs/",
            "x-api-key": self.DEFAULT_PUBLIC_API_KEY,
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        identifiers = identifiers or {}
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        api_symbol = issuer_product_id or _identifier(
            identifiers,
            "fund_id",
            "product_id",
            "issuer_product_id",
        ) or symbol.strip().upper()
        api_key = self.DEFAULT_PUBLIC_API_KEY
        raw_product_page: str | None = None

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if product_page_url:
                page_response = await client.get(
                    product_page_url,
                    headers=_issuer_page_request_headers(),
                    follow_redirects=True,
                )
                page_response.raise_for_status()
                raw_product_page = page_response.text
                api_key = self._extract_api_key(raw_product_page) or api_key
                api_symbol = self._extract_fund_id(raw_product_page) or api_symbol

            resolved_source_url = self.resolve_source_url(
                symbol=symbol,
                issuer_product_id=api_symbol,
                source_url=source_url,
                identifiers=identifiers,
            )
            if not resolved_source_url:
                raise ValueError(f"{self.adapter_key} needs a VictoryShares ticker for {symbol}.")
            headers = {
                **self.source_request_headers(source_url=resolved_source_url),
                "x-api-key": api_key,
            }
            response = await client.get(
                resolved_source_url,
                headers=headers,
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        rows = self._parse_holdings_payload(payload)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={
                "source_format": "json",
                "product_page_url": product_page_url,
                "product_page_fetched": raw_product_page is not None,
                "composition_date": self._composition_date_from_payload(payload),
            },
            source_url=resolved_source_url,
            source_identifier=api_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_public_product_api_all_holdings",
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_current_holdings",
                "snapshot_provenance": "issuer_native_product_api",
                "composition_date": self._composition_date_from_payload(payload),
            },
        )

    @classmethod
    def _extract_api_key(cls, raw_html: str) -> str | None:
        match = cls.API_KEY_RE.search(raw_html)
        if not match:
            return None
        return html.unescape(match.group(1)).strip() or None

    @classmethod
    def _extract_fund_id(cls, raw_html: str) -> str | None:
        match = cls.FUND_ID_RE.search(raw_html)
        if not match:
            return None
        return html.unescape(match.group(1)).strip().upper() or None

    @classmethod
    def _parse_holdings_payload(cls, payload: Any) -> list[CanonicalHoldingRow]:
        holdings = payload.get("holdings") if isinstance(payload, dict) else payload
        if not isinstance(holdings, list):
            return []
        rows: list[CanonicalHoldingRow] = []
        for index, raw_row in enumerate(holdings, start=1):
            if not isinstance(raw_row, dict):
                continue
            name = _clean(raw_row.get("holding_name") or raw_row.get("security_name"))
            raw_symbol = _clean(
                raw_row.get("stock_symbol")
                or raw_row.get("holding_ticker")
                or raw_row.get("symbol")
                or raw_row.get("ticker")
            )
            symbol, exchange = cls._split_symbol(raw_symbol)
            security_type = _clean(raw_row.get("security_type"))
            row_type = cls._row_type(symbol=symbol, name=name, security_type=security_type)
            holding_type = cls._holding_type(security_type=security_type, row_type=row_type)
            if row_type == "cash":
                symbol = None
                exchange = None
            weight = _decimal_percent_points(raw_row.get("portfolio_percentage"))
            market_value = _decimal(raw_row.get("market_value"))
            shares = _decimal(raw_row.get("shares"))
            if not any([symbol, name, raw_row.get("cusip"), raw_row.get("isin")]) and not any(
                [weight, market_value, shares]
            ):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    cusip=_clean(raw_row.get("cusip")) if _looks_like_cusip(_clean(raw_row.get("cusip"))) else None,
                    isin=_clean(raw_row.get("isin")) if _looks_like_isin(_clean(raw_row.get("isin"))) else None,
                    sedol=_clean(raw_row.get("sedol")) if _looks_like_sedol(_clean(raw_row.get("sedol"))) else None,
                    weight=weight,
                    shares=shares,
                    market_value=market_value,
                    currency=_clean(raw_row.get("currency")) or "USD",
                    country=_clean(raw_row.get("country")),
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"victory-{index}",
                    extra_data={
                        "raw_symbol": raw_symbol,
                        "security_type": security_type,
                        "coupon_rate": _decimal(raw_row.get("coupon_rate")),
                        "maturity_date": _clean(raw_row.get("maturity_date")),
                        "as_of_date": _clean(raw_row.get("as_of_date")),
                    },
                )
            )
        return rows

    @staticmethod
    def _split_symbol(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if text is None:
            return None, None
        parts = text.replace("/", ".").strip().upper().split()
        symbol = parts[0] if parts else text.strip().upper()
        exchange = parts[1] if len(parts) > 1 else None
        if symbol in {"CASH", "CASH&OTHER", "USD"}:
            return None, None
        return symbol or None, exchange

    @staticmethod
    def _row_type(*, symbol: str | None, name: str | None, security_type: str | None) -> str:
        lowered_name = (name or "").strip().lower()
        lowered_type = (security_type or "").strip().lower()
        if (
            lowered_type in {"cash", "cash equivalent"}
            or "cash" in lowered_name
            or (symbol or "").upper() in {"CASH", "USD"}
        ):
            return "cash"
        return "security"

    @staticmethod
    def _holding_type(*, security_type: str | None, row_type: str) -> str:
        if row_type == "cash":
            return "cash"
        lowered = (security_type or "").strip().lower()
        if "bond" in lowered or "fixed" in lowered:
            return "fixed_income"
        if "future" in lowered or "option" in lowered or "swap" in lowered:
            return "derivative"
        return "equity"

    @staticmethod
    def _composition_date_from_payload(payload: Any) -> str | None:
        holdings = payload.get("holdings") if isinstance(payload, dict) else payload
        if not isinstance(holdings, list):
            return None
        for row in holdings:
            if isinstance(row, dict):
                value = _clean(row.get("as_of_date"))
                if value:
                    return value
        return None


class DeutscheBankHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse DWS/Xtrackers public PDP holdings JSON."""

    holdings_endpoint_template = "https://etf.dws.com/api/pdp/en-us/etf/{symbol_upper}/holdings"

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "product_id"),
            source_url=_identifier(identifiers, *self.source_url_aliases),
            identifiers=identifiers,
        )
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason="DWS/Xtrackers exposes public PDP holdings JSON by ticker.",
            source_url=source_url,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "product_id"),
        )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        resolved_symbol = (issuer_product_id or symbol).strip().upper()
        if not resolved_symbol:
            return None
        return self.holdings_endpoint_template.format(symbol_upper=resolved_symbol)

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="application/json,text/plain,*/*"),
            "Referer": "https://etf.dws.com/en-us/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"{self.adapter_key} needs a DWS/Xtrackers symbol for {symbol}.")

        response = await asyncio.to_thread(
            requests.get,
            resolved_source_url,
            headers=self.source_request_headers(source_url=resolved_source_url),
            timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
        rows = self._parse_holdings_payload(payload)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={
                "source_format": "json",
                "tables_headline_text": payload.get("tablesHeadlineText"),
                "headline_text": payload.get("headlineText"),
                "as_of_date": payload.get("asOfDate"),
            },
            source_url=resolved_source_url,
            source_identifier=issuer_product_id or symbol.upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_public_pdp_holdings_json",
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_current_holdings",
                "snapshot_provenance": "issuer_native_pdp_holdings_json",
            },
        )

    @classmethod
    def _parse_holdings_payload(cls, payload: dict[str, Any]) -> list[CanonicalHoldingRow]:
        tables = payload.get("tables")
        if not isinstance(tables, list) or not tables:
            return []
        values = tables[0].get("values") if isinstance(tables[0], dict) else None
        if not isinstance(values, list):
            return []

        rows: list[CanonicalHoldingRow] = []
        for index, raw_row in enumerate(values, start=1):
            if not isinstance(raw_row, dict):
                continue
            identifiers = raw_row.get("ISIN") if isinstance(raw_row.get("ISIN"), dict) else {}
            raw_ticker = cls._cell_value(identifiers.get("ISIN_0"))
            symbol, exchange = cls._split_ticker(raw_ticker)
            cusip = cls._cell_value(identifiers.get("ISIN_1"))
            isin = cls._cell_value(identifiers.get("ISIN_2"))
            sedol = cls._cell_value(identifiers.get("ISIN_3"))
            name = cls._cell_value(raw_row.get("Name"))
            asset_class = cls._cell_value(raw_row.get("AssetClass"))
            holding_type = cls._holding_type(asset_class)
            row_type = "cash" if holding_type == "cash" else "security"
            if row_type == "cash":
                symbol = None
                exchange = None

            weight = cls._cell_decimal(raw_row.get("Weighting"), percent_points=True)
            market_value = cls._cell_decimal(raw_row.get("MarketValue"))
            shares = cls._cell_decimal(raw_row.get("Quantity"))
            if not any([symbol, cusip, isin, sedol, name]) and not any(
                [weight, market_value, shares]
            ):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    isin=isin if _looks_like_isin(isin) else None,
                    sedol=sedol if _looks_like_sedol(sedol) else None,
                    weight=weight,
                    shares=shares,
                    market_value=market_value,
                    currency="USD",
                    country=cls._cell_value(raw_row.get("Country")),
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"dws-{index}",
                    extra_data={
                        "raw_ticker": raw_ticker,
                        "sector": cls._cell_value(raw_row.get("IndustryClassName")),
                        "asset_class": asset_class,
                        "notional_value": cls._cell_decimal(raw_row.get("NotionalValue")),
                    },
                )
            )
        return rows

    @staticmethod
    def _cell_value(cell: Any) -> str | None:
        if isinstance(cell, dict):
            return _clean(cell.get("value"))
        return _clean(cell)

    @classmethod
    def _cell_decimal(cls, cell: Any, *, percent_points: bool = False) -> Decimal | None:
        value = cls._cell_value(cell)
        if percent_points:
            if value is not None and value.endswith("%"):
                return _decimal(value)
            parsed_percent = _decimal_percent_points(value)
            if parsed_percent is not None:
                return parsed_percent
            if isinstance(cell, dict):
                return _decimal_percent_points(cell.get("sortValue"))
            return None
        parsed = _decimal(value)
        if parsed is not None:
            return parsed
        if isinstance(cell, dict):
            sort_value = cell.get("sortValue")
            return _decimal(sort_value)
        return None

    @staticmethod
    def _split_ticker(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if text is None:
            return None, None
        normalized = text.replace("/", ".").strip().upper()
        if "." in normalized:
            symbol, exchange = normalized.split(".", 1)
            return symbol or None, exchange or None
        return normalized, None

    @staticmethod
    def _holding_type(asset_class: str | None) -> str:
        lowered = (asset_class or "").strip().lower()
        if "cash" in lowered:
            return "cash"
        if "fixed" in lowered or "bond" in lowered:
            return "fixed_income"
        if "derivative" in lowered or "swap" in lowered:
            return "derivative"
        return "equity"


class PrincipalHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Principal public ETF holdings workbooks."""

    holdings_endpoint_template = (
        "https://api.assetmgmt.principalam.com/public/files?key={symbol_upper}.xlsx"
    )

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "product_id"),
            source_url=_identifier(identifiers, *self.source_url_aliases),
            identifiers=identifiers,
        )
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason="Principal exposes public symbol-based ETF holdings workbooks.",
            source_url=source_url,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "product_id"),
        )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url and source_url.strip().lower().endswith(".xlsx"):
            return source_url.strip()
        resolved_symbol = (issuer_product_id or symbol).strip().upper()
        if not resolved_symbol:
            return None
        return self.holdings_endpoint_template.format(symbol_upper=resolved_symbol)

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(
                accept=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                    "application/octet-stream,*/*"
                )
            ),
            "Referer": "https://www.principalam.com/us/active-etfs",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Principal needs a symbol-based holdings workbook route for {symbol}.")

        response = await asyncio.to_thread(
            requests.get,
            resolved_source_url,
            headers=self.source_request_headers(source_url=resolved_source_url),
            timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()
        workbook_rows = parse_xlsx_table(response.content)
        rows, composition_date = self._parse_workbook_rows(workbook_rows)
        if not rows:
            raise ValueError(
                f"Principal holdings workbook did not expose holdings rows for {symbol}."
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=_table_to_text(workbook_rows),
            raw_json={"source_format": "xlsx", "workbook_rows": workbook_rows},
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "xlsx",
                "route_resolution": "issuer_symbol_holdings_xlsx",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "source_quality": "issuer_reported_current_holdings",
                "snapshot_provenance": "issuer_native_symbol_holdings_workbook",
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_workbook_rows(
        cls,
        workbook_rows: list[list[Any]],
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        composition_date = cls._extract_composition_date(workbook_rows)
        header_index = next(
            (
                index
                for index, row in enumerate(workbook_rows[:20])
                if {
                    "% of net assets",
                    "market value",
                    "security type",
                    "description",
                    "ticker",
                    "cusip/identifier",
                    "isin",
                    "sedol",
                }
                <= {str(cell).strip().lower() for cell in row}
            ),
            -1,
        )
        if header_index < 0:
            return [], composition_date

        header = [str(cell).strip() for cell in workbook_rows[header_index]]
        rows: list[CanonicalHoldingRow] = []
        for position, raw_row in enumerate(workbook_rows[header_index + 1 :], start=1):
            row = _row_dict(header, raw_row)
            name = _clean(row.get("Description"))
            if not name:
                continue
            security_type = _clean(row.get("Security Type"))
            symbol, exchange = cls._split_ticker(_clean(row.get("Ticker")))
            holding_type = cls._holding_type(security_type, name=name)
            row_type = "cash" if holding_type == "cash" else "security"
            if row_type == "cash":
                symbol = None
                exchange = None

            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    cusip=_clean(row.get("CUSIP/Identifier")),
                    isin=_clean(row.get("ISIN")),
                    sedol=_clean(row.get("SEDOL")),
                    weight=_decimal(row.get("% of Net Assets")),
                    shares=_decimal(row.get("Par Value/Quantity/Notional")),
                    market_value=_decimal(row.get("Market Value")),
                    currency=_clean(row.get("Currency")),
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"principal-{position}",
                    extra_data={
                        key: value
                        for key, value in row.items()
                        if key is not None and _clean(value) is not None
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _extract_composition_date(workbook_rows: list[list[Any]]) -> date | None:
        for row in workbook_rows[:10]:
            for cell in row:
                text = _clean(cell)
                if text is None:
                    continue
                match = re.search(
                    r"\bas\s+of:\s*(\d{1,2}/\d{1,2}/\d{4})\b",
                    text,
                    flags=re.IGNORECASE,
                )
                if not match:
                    continue
                try:
                    return datetime.strptime(match.group(1), "%m/%d/%Y").date()
                except ValueError:
                    return None
        return None

    @staticmethod
    def _split_ticker(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if text is None:
            return None, None
        normalized = text.strip().upper()
        if " " in normalized:
            symbol, exchange = normalized.split(None, 1)
            return symbol or None, exchange or None
        return normalized, None

    @staticmethod
    def _holding_type(security_type: str | None, *, name: str) -> str:
        lowered_type = (security_type or "").strip().lower()
        lowered_name = name.strip().lower()
        if "cash" in lowered_type or lowered_name in {"cash", "cash collateral"}:
            return "cash"
        if "future" in lowered_type:
            return "future"
        if "option" in lowered_type:
            return "option"
        if "fixed" in lowered_type or "bond" in lowered_type:
            return "fixed_income"
        if "equity" in lowered_type:
            return "equity"
        return lowered_type or "security"


class MillerValueHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Miller Value's public Nuxt ETF holdings payload."""

    product_page_template = "https://etf.millervaluefunds.com/{symbol_lower}"

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "product_id"),
            source_url=_identifier(identifiers, *self.source_url_aliases),
            identifiers=identifiers,
        )
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason="Miller Value publishes current ETF holdings in its public fund-page payload.",
            source_url=source_url,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "product_id"),
        )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url and "etf.millervaluefunds.com" in source_url.lower():
            return source_url.strip()
        resolved_symbol = (issuer_product_id or symbol).strip().lower()
        if not resolved_symbol:
            return None
        return self.product_page_template.format(symbol_lower=resolved_symbol)

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Miller Value needs a fund page route for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows = self._parse_embedded_holdings(response.text, symbol=symbol)
        if not rows:
            raise ValueError(f"Miller Value page did not expose holdings rows for {symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={"source_format": "nuxt_payload", "row_count": len(rows)},
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "nuxt_payload",
                "route_resolution": "issuer_public_fund_page_embedded_holdings",
                "source_quality": "issuer_reported_current_holdings",
                "snapshot_provenance": "issuer_native_fund_page_payload",
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_embedded_holdings(cls, raw_html: str, *, symbol: str) -> list[CanonicalHoldingRow]:
        component_id = f'milleretf-{symbol.strip().lower()}-holdings-1'
        component_match = re.search(
            rf'(?P<var>[A-Za-z_$][\w$]*)\.componentId="{re.escape(component_id)}";'
            rf'(?P<body>.*?)(?P=var)\.btnLink=',
            raw_html,
            flags=re.DOTALL,
        )
        if component_match is None:
            return []

        variable_name = component_match.group("var")
        body = component_match.group("body")
        data_match = re.search(
            rf'{re.escape(variable_name)}\.finData=\[(?P<rows>.*?)\];',
            body,
            flags=re.DOTALL,
        )
        if data_match is None:
            return []

        rows: list[CanonicalHoldingRow] = []
        for position, raw_object in enumerate(cls._split_js_objects(data_match.group("rows")), start=1):
            parsed = cls._parse_js_object(raw_object)
            ticker = _clean(parsed.get("ticker"))
            name = _clean(parsed.get("description"))
            if ticker is None and name is None:
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=ticker.upper() if ticker else None,
                    name=name,
                    weight=_decimal(parsed.get("percent_of_nav")),
                    shares=_decimal(parsed.get("quantity")),
                    market_value=_decimal(parsed.get("market_value")),
                    holding_type=cls._holding_type(ticker=ticker, name=name),
                    row_type="security",
                    source_row_id=f"miller-value-{position}",
                    extra_data={
                        key: value
                        for key, value in parsed.items()
                        if key not in {"ticker", "description", "quantity", "market_value", "percent_of_nav"}
                        and _clean(value) is not None
                    },
                )
            )
        return rows

    @staticmethod
    def _split_js_objects(raw_rows: str) -> list[str]:
        objects: list[str] = []
        depth = 0
        start: int | None = None
        in_string = False
        escaped = False
        for index, char in enumerate(raw_rows):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                if depth == 0:
                    start = index
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    objects.append(raw_rows[start : index + 1])
                    start = None
        return objects

    @staticmethod
    def _parse_js_object(raw_object: str) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for match in re.finditer(
            r'(?P<key>[A-Za-z_][\w]*)\s*:\s*(?:"(?P<string>(?:\\.|[^"])*)"|(?P<number>-?\d+(?:\.\d+)?))',
            raw_object,
        ):
            key = match.group("key")
            if match.group("string") is not None:
                try:
                    parsed[key] = json.loads(f'"{match.group("string")}"')
                except json.JSONDecodeError:
                    parsed[key] = match.group("string").replace(r"\/", "/")
            else:
                parsed[key] = match.group("number")
        return parsed

    @staticmethod
    def _holding_type(*, ticker: str | None, name: str | None) -> str:
        lowered_name = (name or "").lower()
        if "cash" in lowered_name:
            return "cash"
        if ticker and ticker.upper().endswith("WW"):
            return "warrant"
        return "equity"


class AdaptiveInvestmentsHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Adaptive Investments' public ADPV Nuxt ETF holdings payload."""

    product_page_template = "https://adpvetf.com/{symbol_lower}"

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "product_id"),
            source_url=_identifier(identifiers, *self.source_url_aliases),
            identifiers=identifiers,
        )
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason="Adaptive Investments publishes ETF holdings in its public fund-page payload.",
            source_url=source_url,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "product_id"),
        )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url and "adpvetf.com" in source_url.lower():
            return source_url.strip()
        resolved_symbol = (issuer_product_id or symbol).strip().lower()
        if not resolved_symbol:
            return None
        return self.product_page_template.format(symbol_lower=resolved_symbol)

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Adaptive Investments needs a fund page route for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_embedded_holdings(response.text, symbol=symbol)
        if not rows:
            raise ValueError(f"Adaptive Investments page did not expose holdings rows for {symbol}.")

        legal_metadata: dict[str, Any] = {
            "source_access": self.config.source_access,
            "source_provider": self.source_provider,
            "adapter_key": self.adapter_key,
            "source_format": "nuxt_payload",
            "route_resolution": "issuer_public_fund_page_embedded_holdings",
            "source_quality": "issuer_reported_current_holdings",
            "snapshot_provenance": "issuer_native_fund_page_payload",
            "terms_note": self.config.terms_note,
        }
        if composition_date is not None:
            legal_metadata["composition_date"] = composition_date.isoformat()

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={"source_format": "nuxt_payload", "row_count": len(rows)},
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata=legal_metadata,
        )

    @classmethod
    def _parse_embedded_holdings(
        cls,
        raw_html: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        payload = cls._extract_nuxt_payload(raw_html)
        if payload is None:
            return [], None

        component_id = f'adpvetf-{symbol.strip().lower()}-holdings-1'
        component_match = re.search(
            rf'(?P<var>[A-Za-z_$][\w$]*)\.componentId="{re.escape(component_id)}";',
            payload,
        )
        if component_match is None:
            return [], None

        variable_name = component_match.group("var")
        body_start = component_match.start()
        body_end = payload.find(f"{variable_name}.created_at=", body_start)
        if body_end == -1:
            body_end = payload.find(f"{variable_name}.quicklookDisplay=", body_start)
        if body_end == -1:
            body_end = payload.find(f"{variable_name}.componentType=", body_start)
        body = payload[body_start: body_end if body_end != -1 else len(payload)]

        value_map = cls._extract_nuxt_argument_map(payload)
        data_match = re.search(
            rf'{re.escape(variable_name)}\.finData=\[(?P<rows>.*?)\];',
            body,
            flags=re.DOTALL,
        )
        if data_match is None:
            return [], cls._parse_component_date(body, variable_name=variable_name, value_map=value_map)

        rows: list[CanonicalHoldingRow] = []
        for position, raw_object in enumerate(
            MillerValueHoldingsAdapter._split_js_objects(data_match.group("rows")),
            start=1,
        ):
            parsed = cls._parse_variable_js_object(raw_object, value_map=value_map)
            ticker = _clean(parsed.get("ticker"))
            name = _clean(parsed.get("description"))
            if ticker is None and name is None:
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=ticker.upper() if ticker else None,
                    name=name,
                    weight=_decimal(parsed.get("percent_of_nav")),
                    shares=_decimal(parsed.get("quantity")),
                    market_value=_decimal(parsed.get("market_value")),
                    holding_type=cls._holding_type(ticker=ticker, name=name),
                    row_type="security",
                    source_row_id=f"adaptive-investments-{position}",
                    extra_data={
                        key: value
                        for key, value in parsed.items()
                        if key
                        not in {"ticker", "description", "quantity", "market_value", "percent_of_nav"}
                        and _clean(value) is not None
                    },
                )
            )
        return rows, cls._parse_component_date(body, variable_name=variable_name, value_map=value_map)

    @staticmethod
    def _extract_nuxt_payload(raw_html: str) -> str | None:
        start = raw_html.find("window.__NUXT__=")
        if start == -1:
            return None
        end = raw_html.find("</script>", start)
        return raw_html[start:end] if end != -1 else raw_html[start:]

    @classmethod
    def _extract_nuxt_argument_map(cls, payload: str) -> dict[str, Any]:
        wrapper_match = re.search(r'window\.__NUXT__=\(function\((?P<params>.*?)\)\{', payload, re.DOTALL)
        invocation_start = payload.rfind("}(")
        if wrapper_match is None or invocation_start == -1:
            return {}

        params = [part.strip() for part in wrapper_match.group("params").split(",") if part.strip()]
        argument_text = payload[invocation_start + 2 :].strip()
        if argument_text.endswith(");"):
            argument_text = argument_text[:-2]
        elif argument_text.endswith(")"):
            argument_text = argument_text[:-1]
        values = cls._split_js_arguments(argument_text)
        return {
            param: cls._parse_js_literal(value)
            for param, value in zip(params, values, strict=False)
        }

    @staticmethod
    def _split_js_arguments(argument_text: str) -> list[str]:
        values: list[str] = []
        depth = 0
        start = 0
        in_string = False
        escaped = False
        for index, char in enumerate(argument_text):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char in "[{(":
                depth += 1
            elif char in "]})":
                depth -= 1
            elif char == "," and depth == 0:
                values.append(argument_text[start:index])
                start = index + 1
        values.append(argument_text[start:])
        return values

    @staticmethod
    def _parse_js_literal(value: str) -> Any:
        text = value.strip()
        if text == "null":
            return None
        if text == "true":
            return True
        if text == "false":
            return False
        if text.startswith('"') and text.endswith('"'):
            try:
                return html.unescape(json.loads(text))
            except json.JSONDecodeError:
                return html.unescape(text[1:-1].replace(r"\/", "/"))
        if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
            return text
        return text

    @classmethod
    def _parse_variable_js_object(
        cls,
        raw_object: str,
        *,
        value_map: dict[str, Any],
    ) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for match in re.finditer(
            r'(?P<key>[A-Za-z_][\w]*)\s*:\s*(?P<value>"(?:\\.|[^"])*"|[A-Za-z_$][\w$]*|-?\d+(?:\.\d+)?)',
            raw_object,
        ):
            raw_value = match.group("value")
            parsed[match.group("key")] = value_map.get(raw_value, cls._parse_js_literal(raw_value))
        return parsed

    @classmethod
    def _parse_component_date(
        cls,
        body: str,
        *,
        variable_name: str,
        value_map: dict[str, Any],
    ) -> date | None:
        date_match = re.search(rf'{re.escape(variable_name)}\.date=(?P<value>[A-Za-z_$][\w$]*|"[^"]*");', body)
        if date_match is None:
            return None
        value = value_map.get(date_match.group("value"), cls._parse_js_literal(date_match.group("value")))
        text = _clean(value)
        if text is None:
            return None
        for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _holding_type(*, ticker: str | None, name: str | None) -> str:
        lowered_name = (name or "").lower()
        if "cash" in lowered_name:
            return "cash"
        if ticker and ticker.upper().endswith("WW"):
            return "warrant"
        return "equity"


class AllspringHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url and source_url.strip().lower().endswith(".csv"):
            return source_url.strip()
        normalized_symbol = (issuer_product_id or symbol).strip().upper()
        if not normalized_symbol:
            return None
        return f"https://www.allspringglobal.com/globalassets/data/total-holdings/{normalized_symbol}.csv"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="text/csv,*/*"),
            "Referer": "https://www.allspringglobal.com/investments/performance/etfs/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        holdings_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers or {},
        )
        if not holdings_url:
            raise ValueError(f"Allspring needs a symbol-based holdings CSV route for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                holdings_url,
                headers=self.source_request_headers(source_url=holdings_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_allspring_csv(response.text)
        if not rows:
            raise ValueError(f"Allspring holdings CSV did not expose holdings rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(getattr(response, "url", holdings_url)),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_symbol_total_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_allspring_csv(
        cls,
        raw_csv: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        cleaned_csv = raw_csv.lstrip("\ufeff")
        composition_date = cls._extract_composition_date(cleaned_csv)
        lines = cleaned_csv.splitlines()
        header_index = next(
            (
                index
                for index, line in enumerate(lines)
                if line.lower().startswith("securityname,ticker,cusip,isin,sedol,")
            ),
            None,
        )
        if header_index is None:
            return [], composition_date

        rows: list[CanonicalHoldingRow] = []
        reader = csv.DictReader(StringIO("\n".join(lines[header_index:])))
        for index, row in enumerate(reader, start=1):
            name = _clean(row.get("SecurityName"))
            if not name or name.startswith("©") or name.startswith("Â©"):
                continue
            asset_class = (_clean(row.get("AssetClass")) or "").lower()
            symbol, exchange = cls._split_symbol(_clean(row.get("Ticker")))
            cusip = _clean(row.get("CUSIP"))
            isin = _clean(row.get("ISIN"))
            sedol = _clean(row.get("SEDOL"))
            if asset_class == "other asset":
                symbol = None
                exchange = None
                row_type = "other"
                holding_type = "other"
                cusip = None
                isin = None
                sedol = None
            elif "fixed income" in asset_class:
                row_type = "security"
                holding_type = "fixed_income"
            elif "cash" in asset_class or "cash" in name.lower():
                symbol = None
                exchange = None
                row_type = "cash"
                holding_type = "cash"
            else:
                row_type = "security"
                holding_type = "equity"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    cusip=cusip,
                    isin=isin,
                    sedol=sedol,
                    weight=_decimal(row.get("PercentOfNetAssets")),
                    shares=_decimal(row.get("SharesPrincipalAmount")),
                    market_value=_decimal(row.get("MarketValue")),
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in row.items()
                        if key is not None and _clean(value) is not None
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _extract_composition_date(raw_csv: str) -> date | None:
        first_line = raw_csv.splitlines()[0] if raw_csv.splitlines() else ""
        match = re.search(r"as of\s+(\d{1,2}/\d{1,2}/\d{4})", first_line, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _split_symbol(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if text is None:
            return None, None
        if text.endswith("-US") and len(text) > 3:
            return text[:-3], "US"
        return text, None


class SpearHoldingsAdapter(IssuerCsvHoldingsAdapter):
    holdings_url = "https://spear-funds.com/archivos/SpearAdv.40FU.FU_Holdings.csv"

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url and source_url.strip().lower().endswith(".csv"):
            return source_url.strip()
        normalized_symbol = (issuer_product_id or symbol).strip().upper()
        if normalized_symbol != "SPRX":
            return None
        return self.holdings_url

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="text/csv,*/*"),
            "Referer": "https://spear-funds.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        holdings_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers or {},
        )
        if not holdings_url:
            raise ValueError(f"Spear needs a known ETF holdings CSV route for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                holdings_url,
                headers=self.source_request_headers(source_url=holdings_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_spear_csv(response.text, symbol=normalized_symbol)
        if not rows:
            raise ValueError(f"Spear holdings CSV did not expose holdings rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(getattr(response, "url", holdings_url)),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_fixed_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_spear_csv(
        cls,
        raw_csv: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = list(csv.reader(StringIO(raw_csv.lstrip("\ufeff"))))
        if not table_rows:
            return [], None
        header = [str(value).strip() for value in table_rows[0]]
        account_index = next(
            (index for index, value in enumerate(header) if value.lower() == "account"),
            None,
        )
        date_index = next(
            (index for index, value in enumerate(header) if value.lower() == "date"),
            None,
        )
        filtered_rows = [table_rows[0]]
        composition_date: date | None = None
        for raw_row in table_rows[1:]:
            if account_index is not None and account_index < len(raw_row):
                account = raw_row[account_index].strip().upper()
                if account and account != symbol:
                    continue
            if composition_date is None and date_index is not None and date_index < len(raw_row):
                composition_date = cls._parse_composition_date(raw_row[date_index])
            filtered_rows.append(raw_row)
        return parse_holdings_table(filtered_rows), composition_date

    @staticmethod
    def _parse_composition_date(value: str | None) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None


class TimothyPlanHoldingsAdapter(IssuerCsvHoldingsAdapter):
    symbol_slugs = {
        "TPHD": "hds",
        "TPLC": "lcc",
        "TPSC": "scc",
        "TPIF": "int",
        "TPFC": "tpfc",
        "TPFG": "tpfg",
        "TPFI": "tpfi",
    }

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        normalized_symbol = symbol.strip().upper()
        slug = (issuer_product_id or "").strip().lower() or self.symbol_slugs.get(
            normalized_symbol
        )
        if not slug:
            return None
        return f"https://timothyplan.com/our-etfs/summary-etf-{slug}-holdings.php"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_issuer_page_request_headers(),
            "Referer": "https://timothyplan.com/our-etfs/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        holdings_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers or {},
        )
        if not holdings_url:
            raise ValueError(f"Timothy Plan needs a known ETF holdings route for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                holdings_url,
                headers=self.source_request_headers(source_url=holdings_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows = self._parse_timothy_plan_holdings_table(response.text)
        if not rows:
            raise ValueError(f"Timothy Plan holdings page did not expose rows for {symbol}.")
        as_of_date = self._extract_as_of_date(response.text)

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(getattr(response, "url", holdings_url)),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_symbol_holdings_page_table",
                "composition_date": as_of_date.isoformat() if as_of_date else None,
                "as_of_date": as_of_date.isoformat() if as_of_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_timothy_plan_holdings_table(cls, raw_html: str) -> list[CanonicalHoldingRow]:
        parser = _HTMLTablesParser()
        parser.feed(raw_html)
        required_headers = {
            "name",
            "symbol",
            "isin",
            "shares held",
            "market value %",
            "market value $",
        }
        for table in parser.tables:
            for header_index, row in enumerate(table[:30]):
                normalized_row = {str(value).strip().lower() for value in row if _clean(value)}
                if not required_headers <= normalized_row:
                    continue
                header = table[header_index]
                rows: list[CanonicalHoldingRow] = []
                for index, raw_row in enumerate(table[header_index + 1 :], start=1):
                    row_dict = _row_dict(header, raw_row)
                    name = _clean(_first(row_dict, ["name"]))
                    if not name:
                        continue
                    raw_symbol = _clean(_first(row_dict, ["symbol"]))
                    symbol, exchange = cls._split_symbol(raw_symbol)
                    isin = _clean(_first(row_dict, ["isin"]))
                    holding_type = "fixed_income" if symbol is None and isin is None else "equity"
                    rows.append(
                        CanonicalHoldingRow(
                            symbol=symbol,
                            name=name,
                            isin=isin,
                            weight=_decimal(_first(row_dict, ["market value %"])),
                            shares=_decimal(_first(row_dict, ["shares held"])),
                            market_value=_decimal(_first(row_dict, ["market value $"])),
                            exchange=exchange,
                            holding_type=holding_type,
                            row_type="security",
                            source_row_id=str(index),
                            extra_data={
                                key: value
                                for key, value in row_dict.items()
                                if key is not None and _clean(value) is not None
                            },
                        )
                    )
                return rows
        return []

    @staticmethod
    def _extract_as_of_date(raw_html: str) -> date | None:
        match = re.search(r"As\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", raw_html, re.IGNORECASE)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _split_symbol(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if text is None or text in {"-", "—"}:
            return None, None
        parts = text.split()
        if len(parts) == 2:
            return parts[0], parts[1]
        return text, None


class AcquirersHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        normalized_symbol = (issuer_product_id or symbol).strip().upper()
        if not normalized_symbol:
            return None
        return (
            "https://acquirersfund.com/download-holdings-usbanks.php"
            f"?fticker={normalized_symbol}"
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="application/vnd.ms-excel,*/*"),
            "Referer": "https://acquirersfund.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "route_resolution": "issuer_symbol_holdings_xls",
            "source_access": self.config.source_access,
            "source_provider": self.source_provider,
        }
        return result


class AlpsHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch ALPS ETF holdings through the public product-page API proxy."""

    proxy_url = "https://www.alpsfunds.com/_hcms/api/getData"
    holdings_api_template = (
        "https://secure.alpsinc.com/MarketingAPI/api/v1/Holding/{symbol_upper}/Full"
    )
    product_page_template = "https://www.alpsfunds.com/exchange-traded-funds/{symbol_lower}"

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        normalized_symbol = (issuer_product_id or symbol).strip().upper()
        if not normalized_symbol:
            return None
        api_url = self.holdings_api_template.format(symbol_upper=normalized_symbol)
        return f"{self.proxy_url}?{urlencode({'api_url': api_url})}"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        source = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers or {},
        )
        if not source:
            raise ValueError(f"{self.adapter_key} needs an ALPS ETF symbol.")

        product_page = self.product_page_template.format(symbol_lower=symbol.strip().lower())
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                source,
                headers={
                    **_issuer_page_request_headers(accept="application/json,*/*"),
                    "Referer": product_page,
                },
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"{self.adapter_key} returned a non-list holdings payload.")

        rows, composition_date = self._parse_rows(payload)
        if not rows:
            raise ValueError(f"{self.adapter_key} returned no parseable holdings rows for {symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={"rows": payload},
            source_url=str(getattr(response, "url", source)),
            source_identifier=(issuer_product_id or symbol).strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_public_hubspot_proxy_holdings_json",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_rows(
        cls,
        payload: list[Any],
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                continue
            name = _clean(item.get("name"))
            symbol = _clean(item.get("holdingsymbol") or item.get("primaryidentifier"))
            cusip = _clean(item.get("cusip"))
            isin = _clean(item.get("isin"))
            sedol = _clean(item.get("sedol"))
            if not any([name, symbol, cusip, isin, sedol]):
                continue
            row_date = cls._parse_as_of_date(item.get("asofdate"))
            if row_date and (composition_date is None or row_date > composition_date):
                composition_date = row_date
            holding_type = cls._holding_type(item)
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    isin=isin if _looks_like_isin(isin) else None,
                    sedol=sedol if _looks_like_sedol(sedol) else None,
                    weight=_decimal(item.get("weight")),
                    shares=_decimal(item.get("shares")),
                    market_value=_decimal(item.get("marketvalue")),
                    country=_clean(item.get("clientcountry")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_as_of_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    @staticmethod
    def _holding_type(item: dict[str, Any]) -> str:
        text = " ".join(
            str(part).upper()
            for part in [
                item.get("holdingtype"),
                item.get("holdingtypeabbrev"),
                item.get("name"),
                item.get("primaryidentifiername"),
            ]
            if part
        )
        if "CASH" in text or "MONEY MARKET" in text:
            return "cash"
        if "BOND" in text or "TREASURY" in text or "FIXED" in text:
            return "fixed_income"
        if "FUTURE" in text or "FORWARD" in text or "OPTION" in text or "SWAP" in text:
            return "derivative"
        if "ETF" in text or "FUND" in text:
            return "fund"
        return "equity"


class ClearSharesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        normalized_symbol = (issuer_product_id or symbol).strip().lower()
        if not normalized_symbol:
            return None
        return f"https://clear-shares.com/download-holdings-usbanks.php?fund={normalized_symbol}"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="application/vnd.ms-excel,*/*"),
            "Referer": "https://clear-shares.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "route_resolution": "issuer_symbol_holdings_xls",
            "source_access": self.config.source_access,
            "source_provider": self.source_provider,
        }
        return result


class AptusHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Aptus ETF holdings from server-rendered product pages."""

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = (issuer_product_id or symbol).strip().lower()
        if not normalized_symbol:
            return None
        return f"https://aptusetfs.com/{normalized_symbol}/"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if not product_page_url:
            raise ValueError(f"Aptus needs a product page URL for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers={
                    **_issuer_page_request_headers(accept="text/html,*/*"),
                    "Referer": "https://aptusetfs.com/",
                },
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_product_page(response.text)
        if not rows:
            raise ValueError(f"Aptus product page did not expose parseable holdings for {symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_product_page_holdings_table",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "product_page_url": product_page_url,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_product_page(cls, raw_html: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        parser = _HTMLTablesParser()
        parser.feed(raw_html)
        composition_date = cls._extract_current_as_of_date(raw_html)
        for table in parser.tables:
            if not table:
                continue
            header_values = {str(value).strip().lower() for value in table[0] if _clean(value)}
            if not {"stock ticker", "cusip", "security desc", "weightings"} <= header_values:
                continue
            normalized_table = [
                [cls._normalize_header(value) for value in table[0]],
                *table[1:],
            ]
            rows = parse_holdings_table(normalized_table)
            if composition_date is None:
                composition_date = cls._extract_effective_date(rows)
            return rows, composition_date
        return [], composition_date

    @staticmethod
    def _normalize_header(value: Any) -> str:
        text = str(value).strip()
        lowered = text.lower()
        if lowered == "stock ticker":
            return "Ticker"
        if lowered == "security desc":
            return "Security Description"
        if lowered == "weightings":
            return "Weightings"
        return text

    @staticmethod
    def _extract_current_as_of_date(raw_html: str) -> date | None:
        match = re.search(
            r"Current\s+as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})",
            raw_html,
            re.IGNORECASE,
        )
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _extract_effective_date(rows: list[CanonicalHoldingRow]) -> date | None:
        for row in rows:
            text = _clean(row.extra_data.get("Effective Date"))
            if not text:
                continue
            try:
                return datetime.strptime(text, "%m/%d/%Y").date()
            except ValueError:
                continue
        return None


class ArrowHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Arrow ETF holdings from the issuer's public export endpoint."""

    PRODUCT_IDS = {
        "ARCM": "4",
    }
    PRODUCT_PAGE_MENU_IDS = {
        "ARCM": "518",
    }

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        identifiers = identifiers or {}
        product_id = (
            issuer_product_id
            or _identifier(identifiers, "arrow_product_id", "product_id", "issuer_product_id")
            or self.PRODUCT_IDS.get(symbol.strip().upper())
        )
        if not product_id:
            return None
        return f"https://arrowfunds.com/ArrowSharesExport.aspx?ProductID={product_id}&type=holdings"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="text/csv,*/*"),
            "Referer": "https://arrowfunds.com/default.aspx?menuitemid=514",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_url:
            raise ValueError(f"Arrow needs a product id for {symbol}.")

        normalized_symbol = symbol.strip().upper()
        referer_menu_id = self.PRODUCT_PAGE_MENU_IDS.get(normalized_symbol)
        headers = self.source_request_headers(source_url=resolved_url)
        if referer_menu_id:
            headers["Referer"] = (
                f"https://arrowfunds.com/default.aspx?menuitemid={referer_menu_id}"
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_url,
                headers=headers,
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_arrow_csv(response.text)
        if not rows:
            raise ValueError(f"Arrow holdings export did not expose parseable rows for {symbol}.")

        source_identifier = (
            issuer_product_id
            or _identifier(identifiers or {}, "arrow_product_id", "product_id", "issuer_product_id")
            or self.PRODUCT_IDS.get(normalized_symbol)
        )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(response.url),
            source_identifier=source_identifier,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_product_id_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_arrow_csv(cls, raw_csv: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        cleaned_text = raw_csv.replace("<br>", "\n")
        lines = [
            line
            for line in cleaned_text.splitlines()
            if not line.strip().upper().startswith("SELECT ")
        ]
        reader = csv.reader(StringIO("\n".join(lines)))
        table = list(reader)
        composition_date = cls._extract_composition_date(table)
        header_index = next(
            (
                index
                for index, row in enumerate(table)
                if row and row[0].strip().lower() == "symbol"
            ),
            None,
        )
        if header_index is None:
            return [], composition_date

        header = table[header_index]
        rows: list[CanonicalHoldingRow] = []
        for index, raw_row in enumerate(table[header_index + 1 :], start=1):
            if not any(_clean(value) for value in raw_row):
                continue
            raw = _row_dict(header, raw_row)
            symbol = _clean(_first(raw, ["symbol"]))
            name = _clean(_first(raw, ["name"]))
            security_id = _clean(_first(raw, ["security id", "security identifier"]))
            cusip = security_id if _looks_like_cusip(security_id) else None
            weight = _decimal_percent_points(_first(raw, ["% of net assets"]))
            market_value = _decimal(_first(raw, ["market value ($)", "market value"]))
            country = _clean(_first(raw, ["country"]))
            if not any([symbol, name, cusip, weight, market_value]):
                continue
            holding_type = cls._classify_holding_type(name=name, symbol=symbol)
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=cusip,
                    weight=weight,
                    market_value=market_value,
                    country=country,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={k: v for k, v in raw.items() if v not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _extract_composition_date(table: list[list[str]]) -> date | None:
        for row in table[:20]:
            for cell in row:
                match = re.search(r"Holdings\s+as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", cell)
                if not match:
                    continue
                try:
                    return datetime.strptime(match.group(1), "%m/%d/%Y").date()
                except ValueError:
                    return None
        return None

    @staticmethod
    def _classify_holding_type(*, name: str | None, symbol: str | None) -> str:
        lowered_name = (name or "").strip().lower()
        upper_symbol = (symbol or "").strip().upper()
        if upper_symbol in {"CASH", "USD"} or lowered_name in {"cash", "us dollar", "u.s. dollar"}:
            return "cash"
        if " due " in lowered_name or re.search(r"\b\d+(?:\.\d+)?%\b", lowered_name):
            return "fixed_income"
        return "equity"


class AllianceBernsteinHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch AB ETF holdings through public AEM model JSON and linked workbooks."""

    PRODUCT_PAGE_URLS = {
        "FWD": (
            "https://www.alliancebernstein.com/us/en-us/investments/products/etf/"
            "equities/ab-disruptors-etf.-.00039J509.html"
        ),
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.PRODUCT_PAGE_URLS.get(symbol.strip().upper())

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if not product_page_url:
            raise ValueError(f"AllianceBernstein needs a product page URL for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            page_response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
            page_response.raise_for_status()
            model_url = self._extract_model_url(page_response.text, base_url=str(page_response.url))
            if not model_url:
                raise ValueError(
                    f"AllianceBernstein product page did not expose a holdings model for {symbol}."
                )
            model_response = await client.get(
                model_url,
                headers={
                    **_issuer_page_request_headers(accept="application/json,*/*"),
                    "Referer": str(page_response.url),
                },
                follow_redirects=True,
            )
            model_response.raise_for_status()
            model_payload = model_response.json()
            holdings_url = self._latest_holdings_url(model_payload, base_url=str(model_response.url))
            if not holdings_url:
                raise ValueError(
                    f"AllianceBernstein holdings model did not expose a workbook for {symbol}."
                )
            workbook_response = await client.get(
                holdings_url,
                headers={
                    **_holdings_request_headers(
                        accept=(
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*"
                        )
                    ),
                    "Referer": str(page_response.url),
                },
                follow_redirects=True,
            )
            workbook_response.raise_for_status()

        workbook_rows = parse_xlsx_table(workbook_response.content)
        rows, composition_date, net_assets, base_currency = self._parse_workbook_rows(
            workbook_rows
        )
        if not rows:
            raise ValueError(
                f"AllianceBernstein holdings workbook did not expose parseable rows for {symbol}."
            )
        raw_text = _table_to_text(workbook_rows)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=raw_text,
            raw_json={
                "source_format": "xlsx",
                "model_url": model_url,
                "workbook_url": str(workbook_response.url),
                "workbook_rows": workbook_rows,
            },
            source_url=str(workbook_response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "xlsx",
                "route_resolution": "issuer_product_page_model_workbook",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "net_assets": str(net_assets) if net_assets is not None else None,
                "base_currency": base_currency,
                "product_page_url": str(page_response.url),
                "model_url": model_url,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _extract_model_url(raw_html: str, *, base_url: str) -> str | None:
        match = re.search(
            r"""data-portfolio-holding=["'](?P<url>[^"']+\.model\.json)["']""",
            raw_html,
            re.IGNORECASE,
        )
        if not match:
            return None
        return urljoin(base_url, html.unescape(match.group("url")))

    @staticmethod
    def _latest_holdings_url(payload: Any, *, base_url: str) -> str | None:
        if not isinstance(payload, dict):
            return None
        links = payload.get("links")
        if not isinstance(links, list):
            return None
        for link in links:
            if not isinstance(link, dict):
                continue
            url = _clean(link.get("url"))
            if url and url.lower().endswith((".xlsx", ".xlsm")):
                return urljoin(base_url, url)
        return None

    @classmethod
    def _parse_workbook_rows(
        cls,
        workbook_rows: list[list[Any]],
    ) -> tuple[list[CanonicalHoldingRow], date | None, Decimal | None, str | None]:
        composition_date = cls._extract_composition_date(workbook_rows)
        net_assets = cls._extract_net_assets(workbook_rows)
        base_currency = cls._extract_base_currency(workbook_rows)
        header_index = next(
            (
                index
                for index, row in enumerate(workbook_rows[:30])
                if {
                    "units/par value/ # of contracts",
                    "issue description/name",
                    "% of net assets",
                    "ticker",
                }
                <= {str(value).strip().lower() for value in row if _clean(value)}
            ),
            None,
        )
        if header_index is None:
            return [], composition_date, net_assets, base_currency

        header = workbook_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        for index, raw_row in enumerate(workbook_rows[header_index + 1 :], start=1):
            if not any(_clean(value) for value in raw_row):
                continue
            raw = _row_dict(header, raw_row)
            symbol = _clean(_first(raw, ["ticker"]))
            name = _clean(_first(raw, ["issue description/name"]))
            shares = _decimal(_first(raw, ["units/par value/ # of contracts"]))
            market_value = _decimal(_first(raw, ["accounting value (bc)"]))
            weight = _decimal(_first(raw, ["% of net assets"]))
            isin = _clean(_first(raw, ["isin (primary id)"]))
            cusip = _clean(_first(raw, ["cusip"]))
            sedol = _clean(_first(raw, ["sedol"]))
            if not any([symbol, name, isin, cusip, sedol, weight, shares, market_value]):
                continue
            holding_type = "cash" if (symbol or "").upper() in {"CASH", "USD"} else "equity"
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    isin=isin,
                    sedol=sedol,
                    weight=weight,
                    shares=shares,
                    market_value=market_value,
                    currency=base_currency,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={k: v for k, v in raw.items() if v not in (None, "")},
                )
            )
        return rows, composition_date, net_assets, base_currency

    @staticmethod
    def _extract_composition_date(workbook_rows: list[list[Any]]) -> date | None:
        for row in workbook_rows[:10]:
            for cell in row:
                match = re.search(r"Full\s+Holdings\s+as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", str(cell))
                if not match:
                    continue
                try:
                    return datetime.strptime(match.group(1), "%m/%d/%Y").date()
                except ValueError:
                    return None
        return None

    @staticmethod
    def _extract_net_assets(workbook_rows: list[list[Any]]) -> Decimal | None:
        for row in workbook_rows[:10]:
            for cell in row:
                match = re.search(r"Net\s+Assets\s+\$?([\d,]+(?:\.\d+)?)", str(cell))
                if match:
                    return _decimal(match.group(1))
        return None

    @staticmethod
    def _extract_base_currency(workbook_rows: list[list[Any]]) -> str | None:
        for row in workbook_rows[:10]:
            for cell in row:
                match = re.search(r"Base\s+Currency:\s*([A-Z]{3})", str(cell))
                if match:
                    return match.group(1)
        return None


class TwentyOneSharesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    primary_base_url = "https://21sharesprimary.paradox-coworking.com"
    secondary_base_url = "https://21sharessecondary.paradox-coworking.com"

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        normalized_symbol = (issuer_product_id or symbol).strip().upper()
        if not normalized_symbol:
            return None
        return f"{self.primary_base_url}/api/product_details/{normalized_symbol}"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = (issuer_product_id or symbol).strip().upper()
        primary_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not primary_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        source_urls = [
            primary_url,
            f"{self.secondary_base_url}/api/product_details/{normalized_symbol}",
        ]
        failures: list[str] = []
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            for resolved_source_url in source_urls:
                try:
                    response = await client.get(
                        resolved_source_url,
                        headers=self.source_request_headers(source_url=resolved_source_url),
                        follow_redirects=True,
                    )
                    response.raise_for_status()
                    payload = response.json()
                except Exception as exc:  # noqa: BLE001 - fall through to secondary API host.
                    failures.append(f"{resolved_source_url}: {exc}")
                    continue

                rows = self._parse_constituents(payload)
                if rows:
                    data = payload.get("data") if isinstance(payload, dict) else None
                    if not isinstance(data, dict):
                        data = {}
                    return HoldingsFetchResult(
                        rows=rows,
                        raw_text=response.text,
                        raw_json=payload,
                        source_url=str(getattr(response, "url", resolved_source_url)),
                        source_identifier=normalized_symbol,
                        legal_metadata={
                            "source_access": self.config.source_access,
                            "source_provider": self.source_provider,
                            "adapter_key": self.adapter_key,
                            "source_format": "json",
                            "route_resolution": "issuer_public_product_details_api",
                            "product_name": data.get("product_name"),
                            "jurisdiction": data.get("jurisdiction"),
                            "valuation_date": data.get("valuation_date"),
                            "composition_date": data.get("valuation_date"),
                            "as_of_date": data.get("valuation_date"),
                            "total_nav": data.get("total_nav"),
                            "total_units_outstanding": data.get("total_units_outstanding"),
                            "nav_per_unit": data.get("nav_per_unit"),
                            "terms_note": self.config.terms_note,
                        },
                    )
                failures.append(f"{resolved_source_url}: no constituent rows")

        raise ValueError(
            f"21Shares did not return parseable {normalized_symbol} holdings: "
            f"{'; '.join(failures)}"
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="application/json,*/*")
        headers["Origin"] = "https://www.21shares.com"
        headers["Referer"] = "https://www.21shares.com/"
        return headers

    def _parse_constituents(self, payload: dict[str, Any]) -> list[CanonicalHoldingRow]:
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return []
        constituents = data.get("constituents")
        if not isinstance(constituents, list):
            return []

        rows: list[CanonicalHoldingRow] = []
        for index, item in enumerate(constituents, start=1):
            if not isinstance(item, dict):
                continue
            symbol_value = _clean(item.get("ticker"))
            name = _clean(item.get("name"))
            if not any([symbol_value, name, item.get("cusip")]):
                continue
            holding_type = "crypto" if symbol_value in {"BTC", "ETH", "SOL", "DOGE"} else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value,
                    name=name,
                    cusip=_clean(item.get("cusip")),
                    weight=_decimal(item.get("weight")),
                    shares=_decimal(item.get("quantity")),
                    market_value=_decimal(item.get("market_value")),
                    currency=_clean((data.get("currency") or {}).get("short_name"))
                    if isinstance(data.get("currency"), dict)
                    else None,
                    holding_type=holding_type,
                    row_type=holding_type,
                    source_row_id=str(index),
                    extra_data={
                        "price": item.get("price"),
                        "total_fiat": item.get("total_fiat"),
                        "amount_per_creation_unit": item.get("amount_per_creation_unit"),
                        "product_ticker": data.get("ticker"),
                        "valuation_date": data.get("valuation_date"),
                        **{key: value for key, value in item.items() if value not in (None, "")},
                    },
                )
            )
        return rows


class YieldMaxHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class ProSharesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows = parse_html_holdings_table_by_id(response.text, table_id="holdings")
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        as_of_date = self._extract_as_of_date(response.text)
        return HoldingsFetchResult(
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_html_holdings_table",
                "table_id": "holdings",
                "composition_date": as_of_date.isoformat() if as_of_date else None,
                "as_of_date": as_of_date.isoformat() if as_of_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _extract_as_of_date(raw_html: str) -> date | None:
        match = re.search(r"\bas\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", raw_html, re.IGNORECASE)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None


class RoundhillHoldingsAdapter(IssuerCsvHoldingsAdapter):
    daily_holdings_url_template = (
        "https://www.roundhillinvestments.com/assets/data/"
        "FilepointRoundhill.40RU.RU_Holdings_{date_mmddyyyy}.csv"
    )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        failures: list[str] = []
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            for days_back in range(16):
                source_date = date.today() - timedelta(days=days_back)
                resolved_source_url = self.daily_holdings_url_template.format(
                    date_mmddyyyy=source_date.strftime("%m%d%Y"),
                )
                try:
                    response = await client.get(
                        resolved_source_url,
                        headers=_holdings_request_headers(accept="text/csv,*/*"),
                        follow_redirects=True,
                    )
                    response.raise_for_status()
                except Exception as exc:  # noqa: BLE001 - try previous daily files.
                    failures.append(f"{source_date.isoformat()}: {exc}")
                    continue
                rows, composition_date = self._parse_roundhill_csv(
                    response.text,
                    account_symbol=normalized_symbol,
                )
                if rows:
                    return HoldingsFetchResult(
                        rows=rows,
                        raw_text=response.text,
                        raw_json=None,
                        source_url=str(response.url),
                        source_identifier=normalized_symbol,
                        legal_metadata={
                            "source_access": self.config.source_access,
                            "source_provider": self.source_provider,
                            "adapter_key": self.adapter_key,
                            "source_format": "csv",
                            "route_resolution": "issuer_daily_holdings_csv",
                            "composition_date": (
                                composition_date.isoformat() if composition_date else None
                            ),
                            "as_of_date": composition_date.isoformat() if composition_date else None,
                            "source_file_date": source_date.isoformat(),
                            "terms_note": self.config.terms_note,
                        },
                    )
                failures.append(f"{source_date.isoformat()}: no {normalized_symbol} rows")
        raise ValueError(
            f"Roundhill did not publish parseable {normalized_symbol} holdings "
            f"in the latest 16 daily files: {'; '.join(failures[-5:])}"
        )

    def _parse_roundhill_csv(
        self,
        raw_csv: str,
        *,
        account_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        reader = csv.DictReader(StringIO(raw_csv.strip()))
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(reader, start=1):
            if (item.get("Account") or "").strip().upper() != account_symbol:
                continue
            if composition_date is None:
                composition_date = self._parse_roundhill_date(item.get("Date"))
            raw_symbol = _clean(item.get("StockTicker"))
            holding_type = "cash" if raw_symbol == "Cash&Other" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=raw_symbol if holding_type != "cash" else None,
                    name=_clean(item.get("SecurityName")),
                    cusip=_clean(item.get("CUSIP")),
                    weight=_decimal(item.get("Weightings")),
                    shares=_decimal(item.get("Shares")),
                    market_value=_decimal(item.get("MarketValue")),
                    holding_type=holding_type,
                    row_type="cash" if holding_type == "cash" else "security",
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_roundhill_date(value: str | None) -> date | None:
        text = _clean(value)
        if not text:
            return None
        try:
            return datetime.strptime(text, "%m/%d/%Y").date()
        except ValueError:
            return None


class DefianceHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return f"https://www.defianceetfs.com/{normalized_symbol}-full-holdings/"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows = parse_html_holdings_table_by_id(response.text, table_id="table-full-holdings")
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        as_of_date = self._extract_as_of_date(response.text)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(getattr(response, "url", product_page_url)),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_full_holdings_html_table",
                "table_id": "table-full-holdings",
                "composition_date": as_of_date.isoformat() if as_of_date else None,
                "as_of_date": as_of_date.isoformat() if as_of_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _extract_as_of_date(raw_html: str) -> date | None:
        match = re.search(r"\bData\s+as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", raw_html, re.IGNORECASE)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None


class AdvisorSharesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return None
        return (
            "https://advisorshares.com/wp-content/uploads/csv/holdings/"
            f"AdvisorShares_{normalized_symbol}_Holdings_File.csv"
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,*/*")
        headers["Referer"] = "https://advisorshares.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
            source_url=source_url,
        )
        if not resolved_source_url:
            raise ValueError(f"AdvisorShares holdings route is unavailable for {normalized_symbol}")
        response = await asyncio.to_thread(
            requests.get,
            resolved_source_url,
            headers=self.source_request_headers(source_url=resolved_source_url),
            timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        rows = parse_holdings_csv(response.text)
        result = HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={},
        )
        rows = [
            row
            for row in result.rows
            if str(row.extra_data.get("Account Symbol") or "").strip().upper()
            in {"", normalized_symbol}
        ]
        composition_date = self._extract_composition_date(rows)
        result.rows = rows
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_access": self.config.source_access,
            "source_provider": self.source_provider,
            "adapter_key": self.adapter_key,
            "source_format": "csv",
            "route_resolution": "issuer_symbol_holdings_csv",
            "composition_date": composition_date.isoformat() if composition_date else None,
            "as_of_date": composition_date.isoformat() if composition_date else None,
            "terms_note": self.config.terms_note,
        }
        return result

    @staticmethod
    def _extract_composition_date(rows: list[CanonicalHoldingRow]) -> date | None:
        for row in rows:
            text = _clean(row.extra_data.get("Date"))
            if not text:
                continue
            try:
                return datetime.strptime(text, "%m/%d/%Y").date()
            except ValueError:
                return None
        return None


class AngelOakHoldingsAdapter(IssuerCsvHoldingsAdapter):
    source_url = "https://angeloakcapital.com/secure-gs/Angel_Oak_ETF_Holdings.csv"

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        return source_url.strip() if source_url else self.source_url

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/octet-stream,*/*")
        headers["Referer"] = "https://angeloakcapital.com/investments/?aofund=&vehicle=etf"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = (issuer_product_id or symbol).strip().upper()
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Angel Oak holdings route is unavailable for {normalized_symbol}.")

        response = await asyncio.to_thread(
            requests.get,
            resolved_source_url,
            headers=self.source_request_headers(source_url=resolved_source_url),
            timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()
        rows, composition_date = self._parse_angel_oak_csv(
            response.text,
            account_symbol=normalized_symbol,
        )
        if not rows:
            raise ValueError(
                f"Angel Oak did not publish parseable {normalized_symbol} rows "
                "in the current combined ETF holdings file."
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_combined_account_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_angel_oak_csv(
        cls,
        raw_csv: str,
        *,
        account_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        reader = csv.DictReader(StringIO(raw_csv.strip()))
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(reader, start=1):
            if (item.get("Account") or "").strip().upper() != account_symbol:
                continue
            row_date = cls._parse_angel_oak_date(item.get("Date"))
            if row_date and (composition_date is None or row_date > composition_date):
                composition_date = row_date
            raw_symbol = _clean(item.get("StockTicker"))
            cusip = _clean(item.get("CUSIP"))
            symbol = None if _looks_like_cusip(raw_symbol) else raw_symbol
            if cusip is None and _looks_like_cusip(raw_symbol):
                cusip = raw_symbol
            holding_type = cls._holding_type(
                symbol=symbol,
                name=_clean(item.get("SecurityName")),
                money_market_flag=item.get("MoneyMarketFlag"),
            )
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=_clean(item.get("SecurityName")),
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    weight=_decimal(item.get("Weightings")),
                    shares=_decimal(item.get("Shares")),
                    market_value=_decimal(item.get("MarketValue")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{account_symbol}-{index}",
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_angel_oak_date(value: str | None) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _holding_type(*, symbol: str | None, name: str | None, money_market_flag: Any) -> str:
        text = " ".join(
            part.upper()
            for part in [
                symbol,
                name,
                money_market_flag,
            ]
            if part
        )
        if "CASH" in text or "MONEY MARKET" in text or text.endswith(" MM"):
            return "cash"
        return "fixed_income"


class DoubleLineHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch DoubleLine ETF holdings from issuer-published holdings PDFs."""

    URL_TEMPLATE = (
        "https://doubleline.com/wp-content/uploads/holdings/"
        "DoubleLine_{symbol_upper}_Holdings_{date_mm_dd_yyyy}.pdf"
    )
    LOOKBACK_DAYS = 14
    PDF_ASSET_CLASSES = {
        "ABS",
        "AGENCY",
        "CASH",
        "CMBS",
        "CORPORATE",
        "ETF",
        "FUTURE",
        "LOAN",
        "MBS",
        "MONEY MARKET",
        "MUTUAL FUND",
        "NON-AGENCY",
        "OPTION",
        "RMBS",
        "SOVEREIGN",
        "TREASURY",
    }

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="application/pdf,*/*")
        headers["Referer"] = "https://doubleline.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        candidates = [source_url.strip()] if source_url else list(self._candidate_pdf_urls(normalized_symbol))
        failures: list[str] = []
        for candidate_url in candidates:
            try:
                response = await asyncio.to_thread(
                    requests.get,
                    candidate_url,
                    headers=self.source_request_headers(source_url=candidate_url),
                    timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
                    allow_redirects=True,
                )
                response.raise_for_status()
                raw_text = self._extract_pdf_text(response.content)
                rows, composition_date = self._parse_doubleline_pdf_text(
                    raw_text,
                    symbol=normalized_symbol,
                )
                if not rows:
                    failures.append(f"{candidate_url} had no parseable holdings rows")
                    continue
                return HoldingsFetchResult(
                    rows=rows,
                    raw_text=raw_text,
                    raw_json=None,
                    source_url=str(getattr(response, "url", candidate_url)),
                    source_identifier=normalized_symbol,
                    legal_metadata={
                        "source_access": self.config.source_access,
                        "source_provider": self.source_provider,
                        "adapter_key": self.adapter_key,
                        "source_format": "pdf",
                        "route_resolution": "issuer_recent_dated_holdings_pdf",
                        "composition_date": (
                            composition_date.isoformat() if composition_date else None
                        ),
                        "as_of_date": composition_date.isoformat() if composition_date else None,
                        "terms_note": self.config.terms_note,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - try the next recent dated file.
                failures.append(f"{candidate_url}: {exc}")
                continue
        raise ValueError(
            f"DoubleLine did not publish a parseable recent holdings PDF for {normalized_symbol}. "
            + "; ".join(failures[:3])
        )

    @classmethod
    def _candidate_pdf_urls(cls, symbol: str) -> list[str]:
        today = date.today()
        return [
            cls.URL_TEMPLATE.format(
                symbol_upper=symbol.strip().upper(),
                date_mm_dd_yyyy=(today - timedelta(days=offset)).strftime("%m-%d-%Y"),
            )
            for offset in range(cls.LOOKBACK_DAYS + 1)
        ]

    @staticmethod
    def _extract_pdf_text(raw_pdf: bytes) -> str:
        from pypdf import PdfReader  # noqa: PLC0415

        reader = PdfReader(BytesIO(raw_pdf))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    @classmethod
    def _parse_doubleline_pdf_text(
        cls,
        raw_text: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        composition_date = cls._parse_composition_date(raw_text)
        lines = [
            line.strip()
            for line in raw_text.splitlines()
            if line.strip() and not line.strip().startswith("% of Net")
        ]
        rows: list[CanonicalHoldingRow] = []
        index = 0
        source_row = 0
        while index < len(lines):
            if not cls._is_record_start(lines, index):
                index += 1
                continue
            weight = cls._parse_weight_line(lines[index])
            if weight is None:
                index += 1
                continue
            end = index + 1
            while end < len(lines) and not cls._is_record_start(lines, end):
                end += 1
            block = lines[index + 1 : end]
            parsed = cls._parse_holding_block(
                block,
                weight=weight,
                source_row_id=f"{symbol}-{source_row + 1}",
            )
            if parsed is not None:
                rows.append(parsed)
                source_row += 1
            index = end
        return rows, composition_date

    @staticmethod
    def _parse_composition_date(raw_text: str) -> date | None:
        match = re.search(r"Holdings\s+as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", raw_text, re.I)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None

    @classmethod
    def _is_record_start(cls, lines: list[str], index: int) -> bool:
        if cls._parse_weight_line(lines[index]) is None:
            return False
        if index > 0:
            previous = lines[index - 1].strip().upper()
            previous_allows_record = (
                previous in cls.PDF_ASSET_CLASSES
                or previous == "ASSET CLASS"
                or previous.startswith("HOLDINGS AS OF")
                or "DOUBLELINE" in previous
            )
            if not previous_allows_record:
                return False
        for value in lines[index + 1 : index + 8]:
            text = value.strip().upper()
            if _looks_like_cusip(text) or text in {"USD", "CAD", "EUR", "GBP", "JPY"}:
                return True
        return False

    @staticmethod
    def _parse_weight_line(value: str) -> Decimal | None:
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", value.strip()):
            return None
        parsed = _decimal(value)
        if parsed is None or parsed.copy_abs() > Decimal("100"):
            return None
        return parsed / Decimal("100")

    @classmethod
    def _parse_holding_block(
        cls,
        block: list[str],
        *,
        weight: Decimal,
        source_row_id: str,
    ) -> CanonicalHoldingRow | None:
        if len(block) < 5:
            return None
        asset_class = cls._extract_asset_class(block)
        if not asset_class:
            return None
        asset_index = max(
            idx for idx, value in enumerate(block) if value.strip().upper() == asset_class
        )
        payload = block[:asset_index]
        id_index = cls._find_security_id_index(payload)
        if id_index is None or id_index == 0:
            return None
        name = " ".join(payload[:id_index]).strip()
        security_id = payload[id_index].strip()
        issuer_ticker = payload[id_index + 1].strip() if id_index + 1 < len(payload) else None
        numeric_tail = [
            value
            for value in payload[id_index + 2 :]
            if _decimal(value) is not None or cls._parse_pdf_date(value) is not None
        ]
        market_value, shares = cls._parse_market_value_and_shares(numeric_tail)
        holding_type = cls._holding_type(asset_class=asset_class, name=name)
        row_type = "cash" if holding_type == "cash" else "security"
        symbol = issuer_ticker if holding_type in {"equity", "fund"} else None
        currency = security_id if holding_type == "cash" and len(security_id) == 3 else None
        return CanonicalHoldingRow(
            symbol=symbol,
            name=name or None,
            cusip=security_id if _looks_like_cusip(security_id) else None,
            weight=weight,
            shares=shares,
            market_value=market_value,
            currency=currency,
            holding_type=holding_type,
            row_type=row_type,
            source_row_id=source_row_id,
            extra_data={
                "security_id": security_id,
                "issuer_ticker": issuer_ticker,
                "asset_class": asset_class,
                "pdf_tail": payload[id_index + 2 :],
            },
        )

    @classmethod
    def _extract_asset_class(cls, block: list[str]) -> str | None:
        for value in reversed(block):
            normalized = re.sub(r"\s+", " ", value.strip().upper())
            if normalized in cls.PDF_ASSET_CLASSES:
                return normalized
        return None

    @staticmethod
    def _find_security_id_index(payload: list[str]) -> int | None:
        for idx, value in enumerate(payload):
            text = value.strip().upper()
            if _looks_like_cusip(text) or text in {"USD", "CAD", "EUR", "GBP", "JPY"}:
                return idx
        return None

    @staticmethod
    def _parse_pdf_date(value: str) -> date | None:
        try:
            return datetime.strptime(value.strip(), "%m/%d/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _parse_market_value_and_shares(values: list[str]) -> tuple[Decimal | None, Decimal | None]:
        numeric_values = [_decimal(value) for value in values if _decimal(value) is not None]
        if len(numeric_values) < 3:
            return None, None
        # Last numeric is the contract size. The two before it are quantity and market value.
        return numeric_values[-3], numeric_values[-2]

    @staticmethod
    def _holding_type(*, asset_class: str, name: str | None) -> str:
        text = f"{asset_class} {name or ''}".upper()
        if "CASH" in text or "MONEY MARKET" in text:
            return "cash"
        if "FUND" in asset_class or asset_class == "ETF":
            return "fund"
        if any(token in text for token in ("TREASURY", "BOND", "MBS", "ABS", "CMBS", "RMBS", "LOAN", "SOVEREIGN")):
            return "fixed_income"
        if asset_class in {"FUTURE", "OPTION"}:
            return "derivative"
        return "equity"


class TcwHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Read TCW's issuer-published combined fixed-income ETF holdings PDF."""

    HOLDINGS_PDF_URL = (
        "https://edge.sitecorecloud.io/thetcwgroupc320-tcwweb7bc3-prod0f26-25f9/"
        "media/Downloads/TCW/Products/ETFs/Holdings/FI-ETF-Q1-Holdings.pdf?sc_lang=en"
    )
    FUND_NAMES = {
        "ACLO": "TCW AAA CLO ETF",
        "FIXT": "TCW Core Plus Bond ETF",
        "IGCB": "TCW Corporate Bond ETF",
        "FLXR": "TCW Flexible Income ETF",
        "HYBX": "TCW High Yield Bond ETF",
        "MUSE": "TCW Multisector Credit Income ETF",
        "SLNZ": "TCW Senior Loan ETF",
    }
    _SCHEDULE_RE = re.compile(
        r"^(?P<fund>TCW .+? ETF)\s+SCHEDULE OF INVESTMENTS\s+"
        r"(?P<date>[A-Za-z]+\s+\d{1,2},\s+\d{4})",
        re.IGNORECASE | re.DOTALL,
    )
    _VALUE_LINE_RE = re.compile(
        r"^(?P<prefix>.*?)\s+(?P<maturity>\d{2}/\d{2}/\d{2})\s+"
        r"(?:(?P<currency>[A-Z]{3}|\$)\s+)?(?P<principal>[\d,]+(?:\.\d+)?)\s+"
        r"(?:\$\s*)?(?P<value>[\d,]+(?:\.\d+)?)$"
    )

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        normalized_symbol = symbol.strip().upper()
        if normalized_symbol not in self.FUND_NAMES:
            return super().probe(symbol=symbol, name=name, identifiers=identifiers)
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason="TCW publishes complete schedules for its fixed-income ETFs in an issuer PDF.",
            source_url=self.HOLDINGS_PDF_URL,
            issuer_product_id=normalized_symbol or None,
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        del issuer_product_id, identifiers
        normalized_symbol = symbol.strip().upper()
        if normalized_symbol not in self.FUND_NAMES:
            raise ValueError(f"TCW does not publish this ETF in its fixed-income holdings PDF: {normalized_symbol}.")
        pdf_url = source_url or self.HOLDINGS_PDF_URL
        response = await asyncio.to_thread(
            requests.get,
            pdf_url,
            headers=self.source_request_headers(source_url=pdf_url),
            timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()
        raw_text = self._extract_pdf_text(response.content)
        rows, composition_date = self._parse_pdf_text(raw_text, symbol=normalized_symbol)
        if not rows:
            raise ValueError(f"TCW PDF returned no parseable {normalized_symbol} holdings rows.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=raw_text,
            raw_json={"source_format": "issuer_combined_holdings_pdf"},
            source_url=str(getattr(response, "url", pdf_url)),
            source_identifier=normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "pdf",
                "route_resolution": "issuer_combined_selected_fund_holdings_pdf",
                "portfolio_semantics": "issuer_published_schedule_of_investments",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        del source_url
        headers = _holdings_request_headers(accept="application/pdf,*/*")
        headers["Referer"] = "https://www.tcw.com/"
        return headers

    @staticmethod
    def _extract_pdf_text(raw_pdf: bytes) -> str:
        from pypdf import PdfReader  # noqa: PLC0415

        reader = PdfReader(BytesIO(raw_pdf))
        return "\f".join(page.extract_text() or "" for page in reader.pages)

    @classmethod
    def _parse_pdf_text(
        cls,
        raw_text: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        expected_fund = cls.FUND_NAMES[symbol]
        selected_pages: list[str] = []
        current_fund: str | None = None
        composition_date: date | None = None
        for page in raw_text.split("\f"):
            page = page.strip()
            match = cls._SCHEDULE_RE.search(page)
            if match:
                current_fund = re.sub(r"\s+", " ", match.group("fund")).strip()
                if current_fund == expected_fund:
                    composition_date = cls._parse_composition_date(match.group("date"))
            if current_fund == expected_fund:
                selected_pages.append(page)
        return cls._parse_selected_pages("\n".join(selected_pages), symbol=symbol), composition_date

    @staticmethod
    def _parse_composition_date(value: str) -> date | None:
        try:
            return datetime.strptime(value, "%B %d, %Y").date()
        except ValueError:
            return None

    @classmethod
    def _parse_selected_pages(cls, raw_text: str, *, symbol: str) -> list[CanonicalHoldingRow]:
        rows: list[CanonicalHoldingRow] = []
        pending: list[str] = []
        for line in (line.strip() for line in raw_text.splitlines()):
            if not line or line.startswith("TCW ") or "SCHEDULE OF INVESTMENTS" in line:
                continue
            match = cls._VALUE_LINE_RE.match(line)
            if match:
                description_parts = pending + ([match.group("prefix")] if match.group("prefix") else [])
                description = re.sub(r"\s+", " ", " ".join(description_parts)).strip()
                pending = []
                if not cls._is_holding_description(description):
                    continue
                value = _decimal(match.group("value"))
                if value is None:
                    continue
                currency = match.group("currency")
                rows.append(
                    CanonicalHoldingRow(
                        symbol=None,
                        name=description,
                        shares=_decimal(match.group("principal")),
                        market_value=value,
                        currency="USD" if currency in {None, "$"} else currency,
                        holding_type="fixed_income",
                        row_type="security",
                        source_row_id=f"{symbol}:{len(rows) + 1}",
                        extra_data={
                            "source": "tcw_combined_holdings_pdf",
                            "maturity_date": match.group("maturity"),
                            "principal_amount": match.group("principal"),
                        },
                    )
                )
                continue
            if cls._is_section_line(line):
                pending = []
                continue
            pending.append(line)
        cls._apply_weights(rows)
        return rows

    @staticmethod
    def _is_section_line(line: str) -> bool:
        upper = line.upper()
        return (
            "NET ASSETS" in upper
            or upper.startswith(("FIXED INCOME", "ASSET-BACKED", "TOTAL INVESTMENTS"))
            or upper.startswith(("ISSUES", "MATURITY", "PRINCIPAL", "VALUE"))
            or upper.startswith("SEE NOTES")
        )

    @staticmethod
    def _is_holding_description(value: str) -> bool:
        upper = value.upper()
        return bool(value) and "NET ASSETS" not in upper and not upper.startswith("TOTAL ")

    @staticmethod
    def _apply_weights(rows: list[CanonicalHoldingRow]) -> None:
        total_value = sum((row.market_value or Decimal("0")) for row in rows)
        if total_value <= 0:
            return
        for row in rows:
            if row.market_value is not None:
                row.weight = row.market_value / total_value


class TeucriumHoldingsAdapter(IssuerCsvHoldingsAdapter):
    source_url = "https://etfs.teucrium.com/assets/data/FilepointTeucrium.40TZ.TZ_Holdings.csv"

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        return source_url.strip() if source_url else self.source_url

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/octet-stream,*/*")
        headers["Referer"] = "https://etfs.teucrium.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=self.resolve_source_url(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            ),
            identifiers=identifiers,
        )
        rows = [
            row
            for row in result.rows
            if str(row.extra_data.get("Account") or "").strip().upper() == normalized_symbol
        ]
        composition_date = self._extract_composition_date(rows)
        result.rows = rows
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_access": self.config.source_access,
            "source_provider": self.source_provider,
            "adapter_key": self.adapter_key,
            "source_format": "csv",
            "route_resolution": "issuer_aggregate_holdings_csv",
            "composition_date": composition_date.isoformat() if composition_date else None,
            "as_of_date": composition_date.isoformat() if composition_date else None,
            "terms_note": self.config.terms_note,
        }
        return result

    @staticmethod
    def _extract_composition_date(rows: list[CanonicalHoldingRow]) -> date | None:
        for row in rows:
            text = _clean(row.extra_data.get("Date"))
            if not text:
                continue
            try:
                return datetime.strptime(text, "%m/%d/%Y").date()
            except ValueError:
                return None
        return None


class AxsHoldingsAdapter(IssuerCsvHoldingsAdapter):
    latest_lookback_days = 10

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/octet-stream,*/*")
        headers["Referer"] = "https://www.tradretfs.com/"
        return headers

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return f"https://www.tradretfs.com/{normalized_symbol}"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        if source_url:
            return await self._fetch_aggregate_csv(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
            )

        for days_back in range(self.latest_lookback_days + 1):
            source_date = date.today() - timedelta(days=days_back)
            candidate_url = (
                "https://axsetf.filepoint.live/assets/data/"
                f"BBH_AXS_ETF_PVAL_WEB.{source_date.strftime('%Y%m%d')}.csv"
            )
            try:
                result = await self._fetch_aggregate_csv(
                    symbol=symbol,
                    issuer_product_id=issuer_product_id,
                    source_url=candidate_url,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {403, 404}:
                    continue
                raise
            if result.rows:
                return result
        raise ValueError(f"AXS/Tradr holdings feed did not expose rows for {symbol}.")

    async def _fetch_aggregate_csv(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None,
        source_url: str,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                source_url,
                headers=self.source_request_headers(source_url=source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows = [
            row
            for row in parse_holdings_csv(response.text)
            if str(row.extra_data.get("ETF Ticker") or "").strip().upper() == normalized_symbol
        ]
        composition_date = self._extract_composition_date(rows)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(response.url),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_dated_aggregate_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _extract_composition_date(rows: list[CanonicalHoldingRow]) -> date | None:
        for row in rows:
            text = _clean(row.extra_data.get("Date"))
            if not text:
                continue
            for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(text, date_format).date()
                except ValueError:
                    continue
        return None


class BahlGaynorHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Bahl & Gaynor ETF holdings from product-page linked CSV files."""

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return f"https://www.bahl-gaynor.com/etf/{normalized_symbol}/"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            raise ValueError(f"{self.adapter_key} needs a Bahl & Gaynor ETF page for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            page_response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
            page_response.raise_for_status()
            holdings_url = self._discover_holdings_csv_url(
                page_response.text,
                base_url=str(getattr(page_response, "url", product_page_url)),
                symbol=symbol,
            )
            if not holdings_url:
                raise ValueError(
                    f"{self.adapter_key} did not expose a holdings CSV link for {symbol}."
                )
            holdings_response = await client.get(
                holdings_url,
                headers=_holdings_request_headers(accept="text/csv,*/*"),
                follow_redirects=True,
            )
        holdings_response.raise_for_status()
        rows = self._parse_holdings_csv(holdings_response.text)
        if not rows:
            raise ValueError(f"{self.adapter_key} returned no parseable holdings rows for {symbol}.")
        composition_date = self._extract_date_from_url(
            str(getattr(holdings_response, "url", holdings_url))
        )
        return HoldingsFetchResult(
            source_url=str(getattr(holdings_response, "url", holdings_url)),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            rows=rows,
            raw_text=holdings_response.text,
            raw_json=None,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_product_page_linked_holdings_csv",
                "product_page_url": str(getattr(page_response, "url", product_page_url)),
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _discover_holdings_csv_url(raw_html: str, *, base_url: str, symbol: str) -> str | None:
        normalized_symbol = symbol.strip().upper()
        candidates: list[str] = []
        for match in re.finditer(r"""(?:href|src)=["']([^"']+)["']""", raw_html, re.I):
            href = html.unescape(match.group(1))
            lowered_href = href.lower()
            if "etf_holdings_csv" not in lowered_href or not lowered_href.endswith(".csv"):
                continue
            if f"/{normalized_symbol.lower()}_holdings_" not in lowered_href:
                continue
            candidates.append(urljoin(base_url, href))
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda value: BahlGaynorHoldingsAdapter._extract_date_from_url(value) or date.min,
            reverse=True,
        )[0]

    @staticmethod
    def _parse_holdings_csv(raw_csv: str) -> list[CanonicalHoldingRow]:
        source_rows = list(csv.DictReader(StringIO(raw_csv.strip())))
        rows: list[CanonicalHoldingRow] = []
        for index, row in enumerate(source_rows, start=1):
            symbol = _clean(row.get("Symbol/Ticker"))
            name = _clean(row.get("Name"))
            cusip = _clean(row.get("CUSIP"))
            if not any([symbol, name, cusip]):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    weight=_decimal(row.get("Weight (%)")),
                    shares=_decimal(row.get("Quantity")),
                    holding_type="equity",
                    row_type="security",
                    source_row_id=str(index),
                    extra_data={key: value for key, value in row.items() if value not in (None, "")},
                )
            )
        return rows

    @staticmethod
    def _extract_date_from_url(url: str) -> date | None:
        match = re.search(r"_holdings_(\d{4}-\d{2}-\d{2})\.csv", url)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None


class USGlobalInvestorsHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return f"https://usglobaletfs.com/fund/{normalized_symbol}/"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows = self._parse_holdings_table(response.text)
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        as_of_date = self._extract_as_of_date(response.text)
        return HoldingsFetchResult(
            source_url=str(getattr(response, "url", product_page_url)),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_product_page_holdings_table",
                "composition_date": as_of_date.isoformat() if as_of_date else None,
                "as_of_date": as_of_date.isoformat() if as_of_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _parse_holdings_table(raw_html: str) -> list[CanonicalHoldingRow]:
        parser = _HTMLTablesParser()
        parser.feed(raw_html)
        required_headers = {
            "% net assets",
            "name",
            "cusip",
            "ticker",
            "shares held",
            "market ($)",
        }
        for table in parser.tables:
            for header_index, row in enumerate(table[:30]):
                normalized_row = {str(value).strip().lower() for value in row if _clean(value)}
                if not required_headers <= normalized_row:
                    continue
                header = table[header_index]
                cleaned_rows = [
                    USGlobalInvestorsHoldingsAdapter._strip_mobile_cell_labels(
                        header,
                        raw_row,
                    )
                    for raw_row in table[header_index + 1 :]
                ]
                return parse_holdings_table([header, *cleaned_rows])
        return []

    @staticmethod
    def _strip_mobile_cell_labels(header: list[str], row: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, cell in enumerate(row):
            text = " ".join(str(cell).split())
            label = " ".join(str(header[index]).split()) if index < len(header) else ""
            if label and text.lower().startswith(label.lower()):
                text = text[len(label):].strip()
            cleaned.append(text)
        return cleaned

    @staticmethod
    def _extract_as_of_date(raw_html: str) -> date | None:
        match = re.search(
            r"id=[\"']holdings[\"'][\s\S]{0,1000}?Data\s+as\s+of\s+"
            r"(\d{1,2}/\d{1,2}/\d{4})",
            raw_html,
            re.IGNORECASE,
        ) or re.search(
            r"Holdings[\s\S]{0,1000}?Data\s+as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})",
            raw_html,
            re.IGNORECASE,
        )
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None


class FederatedHermesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    product_pages = {
        "payr": "https://www.federatedhermes.com/us/products/exchange-traded-funds/enhanced-income-etf.do",
        "fhil": "https://www.federatedhermes.com/us/products/exchange-traded-funds/intl-leaders-etf.do",
        "flcc": "https://www.federatedhermes.com/us/products/exchange-traded-funds/mdt-large-cap-core-etf.do",
        "flcg": "https://www.federatedhermes.com/us/products/exchange-traded-funds/mdt-large-cap-growth-etf.do",
        "flcv": "https://www.federatedhermes.com/us/products/exchange-traded-funds/mdt-large-cap-value-etf.do",
        "mktn": "https://www.federatedhermes.com/us/products/exchange-traded-funds/mdt-market-neutral-etf.do",
        "fscc": "https://www.federatedhermes.com/us/products/exchange-traded-funds/mdt-small-cap-core-etf.do",
        "fcsh": "https://www.federatedhermes.com/us/products/exchange-traded-funds/short-duration-corporate-etf.do",
        "fhys": "https://www.federatedhermes.com/us/products/exchange-traded-funds/short-duration-high-yield-etf.do",
        "ftrb": "https://www.federatedhermes.com/us/products/exchange-traded-funds/total-return-bond-etf.do",
        "fdv": "https://www.federatedhermes.com/us/products/exchange-traded-funds/us-strategic-dividend-etf.do",
        "fusd": "https://www.federatedhermes.com/us/products/exchange-traded-funds/ultrashort-bond-etf.do",
    }
    etf_listing_url = "https://www.federatedhermes.com/us/products.do?productType=12"
    product_post_url = "https://www.federatedhermes.com/us/products/product.do"
    daily_section = "section-characteristics-daily-holdings"

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.product_pages.get(symbol.strip().lower())

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            raise ValueError(f"{self.adapter_key} needs a Federated Hermes ETF product page.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            # The Federated Hermes section route depends on the same anonymous session cookies
            # that the product listing establishes in the browser.
            listing_response = await client.get(
                self.etf_listing_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
            listing_response.raise_for_status()

            product_response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
            product_response.raise_for_status()
            form_payload = self._extract_product_form_payload(product_response.text)
            form_payload["section"] = self.daily_section

            section_response = await client.post(
                self.product_post_url,
                data=form_payload,
                headers={
                    **_issuer_page_request_headers(accept="text/html,application/xhtml+xml,*/*"),
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": product_page_url,
                },
                follow_redirects=True,
            )
            section_response.raise_for_status()
            daily_holdings_url = self._extract_daily_holdings_url(
                section_response.text,
                base_url=product_page_url,
            )
            if not daily_holdings_url:
                raise ValueError(
                    f"{self.adapter_key} did not expose a daily holdings link for {symbol}."
                )

            holdings_response = await client.get(
                daily_holdings_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
            holdings_response.raise_for_status()

        rows, composition_date = self._parse_daily_holdings_page(holdings_response.text)
        if not rows:
            raise ValueError(f"{self.adapter_key} returned no parseable holdings rows for {symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=holdings_response.text,
            raw_json={
                "product_page_url": str(getattr(product_response, "url", product_page_url)),
                "daily_section_url": str(getattr(section_response, "url", self.product_post_url)),
            },
            source_url=str(getattr(holdings_response, "url", daily_holdings_url)),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_product_page_daily_holdings_table",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _extract_product_form_payload(raw_html: str) -> dict[str, str]:
        payload: dict[str, str] = {}
        for field_name in [
            "fundbasketid",
            "shareclassid",
            "managedaccountid",
            "compositeid",
            "section",
            "tab",
            "tokenW",
            "bonyClient",
        ]:
            match = re.search(
                rf'id="{re.escape(field_name)}"\s+name="{re.escape(field_name)}"'
                rf'\s+type="hidden"\s+value="([^"]*)"',
                raw_html,
            )
            payload[field_name] = html.unescape(match.group(1)) if match else ""
        if not payload.get("fundbasketid") or not payload.get("shareclassid"):
            raise ValueError("Federated Hermes product page did not expose fund identifiers.")
        return payload

    @staticmethod
    def _extract_daily_holdings_url(raw_html: str, *, base_url: str) -> str | None:
        match = re.search(
            r'href=["\']([^"\']*daily-portfolio-holdings/[^"\']+\.do)["\']',
            raw_html,
            re.IGNORECASE,
        )
        if not match:
            return None
        return urljoin(base_url, html.unescape(match.group(1)))

    @classmethod
    def _parse_daily_holdings_page(
        cls,
        raw_html: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        composition_date = cls._extract_as_of_date(raw_html)
        parser = _HTMLTableByIdParser(table_id="daily-portfolio-holdings-table")
        parser.feed(raw_html)
        if not parser.rows:
            return [], composition_date
        header = parser.rows[0]
        rows: list[CanonicalHoldingRow] = []
        for index, raw_row in enumerate(parser.rows[1:], start=1):
            raw = _row_dict(header, raw_row)
            name = _clean(_first(raw, ["name"]))
            security_type = _clean(_first(raw, ["security type"]))
            symbol = cls._clean_federated_text(_first(raw, ["ticker"]))
            cusip = cls._clean_federated_text(_first(raw, ["cusip"]))
            isin = cls._clean_federated_text(_first(raw, ["isin"]))
            sedol = cls._clean_federated_text(_first(raw, ["sedol"]))
            if not any([name, symbol, cusip, isin, sedol]):
                continue
            holding_type = cls._holding_type(security_type=security_type, name=name, symbol=symbol)
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    isin=isin if _looks_like_isin(isin) else None,
                    sedol=sedol if _looks_like_sedol(sedol) else None,
                    weight=_decimal(_first(raw, ["market valueweight (%)"])),
                    shares=_decimal(_first(raw, ["shares /number ofcontracts"])),
                    market_value=_decimal(
                        _first(
                            raw,
                            ["market value /unrealizedappreciationor depreciation"],
                        )
                    ),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _clean_federated_text(value: Any) -> str | None:
        text = _clean(value)
        if text in {"—", "\u2014"}:
            return None
        return text

    @staticmethod
    def _extract_as_of_date(raw_html: str) -> date | None:
        match = re.search(r'\bAS\s+OF\s*<time\s+datetime=["\'](\d{4}-\d{2}-\d{2})', raw_html)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None

    @staticmethod
    def _holding_type(*, security_type: str | None, name: str | None, symbol: str | None) -> str:
        text = " ".join(part.upper() for part in [security_type, name, symbol] if part)
        if "CASH" in text or text in {"USD", "US DOLLAR"}:
            return "cash"
        if "FORWARD" in text or "FUTURE" in text or "OPTION" in text or "SWAP" in text:
            return "derivative"
        if "BOND" in text or "NOTE" in text or "TREASURY" in text or "FIXED" in text:
            return "fixed_income"
        return "equity"


class BurneyHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Burney ETF holdings from public product-page wpDataTables."""

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return f"https://burneyetfs.com/{normalized_symbol}/"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            raise ValueError(f"{self.adapter_key} needs a Burney ETF product page for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_product_page(response.text)
        if not rows:
            raise ValueError(f"{self.adapter_key} returned no parseable holdings rows for {symbol}.")
        return HoldingsFetchResult(
            source_url=str(getattr(response, "url", product_page_url)),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_product_page_wpdatatables_holdings_table",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_product_page(cls, raw_html: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        parser = _HTMLTablesParser()
        parser.feed(raw_html)
        required_headers = {
            "ticker",
            "name",
            "cusip",
            "shares",
            "price (local)",
            "market value ($mm)",
            "% of net assets",
            "effective_date",
        }
        for table in parser.tables:
            for header_index, row in enumerate(table[:30]):
                normalized_row = {str(value).strip().lower() for value in row if _clean(value)}
                if not required_headers <= normalized_row:
                    continue
                rows: list[CanonicalHoldingRow] = []
                composition_date: date | None = None
                for source_row_id, raw_row in enumerate(table[header_index + 1 :], start=1):
                    row_data = _row_dict(row, raw_row)
                    parsed_date = cls._parse_date(row_data.get("EFFECTIVE_DATE"))
                    if composition_date is None and parsed_date is not None:
                        composition_date = parsed_date
                    rows.append(
                        CanonicalHoldingRow(
                            symbol=_clean(row_data.get("Ticker")),
                            name=_clean(row_data.get("Name")),
                            cusip=(
                                _clean(row_data.get("CUSIP"))
                                if _looks_like_cusip(_clean(row_data.get("CUSIP")))
                                else None
                            ),
                            weight=_decimal_percent_points(row_data.get("% of Net Assets")),
                            shares=_decimal(row_data.get("Shares")),
                            market_value=cls._market_value_from_millions(
                                row_data.get("Market Value ($mm)")
                            ),
                            holding_type="equity",
                            row_type="security",
                            source_row_id=str(source_row_id),
                            extra_data={k: v for k, v in row_data.items() if v not in (None, "")},
                        )
                    )
                return rows, composition_date
        return [], None

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _market_value_from_millions(value: Any) -> Decimal | None:
        parsed = _decimal(value)
        if parsed is None:
            return None
        return parsed * Decimal("1000000")


class ETFArchitectHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Alpha Architect / ETF Architect holdings from public fund pages."""

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return f"https://funds.alphaarchitect.com/{normalized_symbol}/"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            raise ValueError(f"{self.adapter_key} needs an ETF Architect fund page for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_product_page(response.text)
        if not rows:
            raise ValueError(f"{self.adapter_key} returned no parseable holdings rows for {symbol}.")
        return HoldingsFetchResult(
            source_url=str(getattr(response, "url", product_page_url)),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_product_page_wpdatatables_holdings_table",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_product_page(cls, raw_html: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        parser = _HTMLTablesParser()
        parser.feed(raw_html)
        required_headers = {
            "ticker",
            "name",
            "cusip",
            "shares",
            "price (local)",
            "market value ($mm)",
            "% of net assets",
        }
        for table in parser.tables:
            for header_index, row in enumerate(table[:30]):
                normalized_row = {str(value).strip().lower() for value in row if _clean(value)}
                if not required_headers <= normalized_row:
                    continue
                rows: list[CanonicalHoldingRow] = []
                for source_row_id, raw_row in enumerate(table[header_index + 1 :], start=1):
                    row_data = _row_dict(row, raw_row)
                    rows.append(
                        CanonicalHoldingRow(
                            symbol=_clean(row_data.get("Ticker")),
                            name=_clean(row_data.get("Name")),
                            cusip=(
                                _clean(row_data.get("CUSIP"))
                                if _looks_like_cusip(_clean(row_data.get("CUSIP")))
                                else None
                            ),
                            weight=_decimal_percent_points(row_data.get("% of Net Assets")),
                            shares=_decimal(row_data.get("Shares")),
                            market_value=cls._market_value_from_millions(
                                row_data.get("Market Value ($mm)")
                            ),
                            holding_type="equity",
                            row_type="security",
                            source_row_id=str(source_row_id),
                            extra_data={k: v for k, v in row_data.items() if v not in (None, "")},
                        )
                    )
                return rows, cls._extract_as_of_date(raw_html)
        return [], cls._extract_as_of_date(raw_html)

    @staticmethod
    def _extract_as_of_date(raw_html: str) -> date | None:
        date_candidates = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", raw_html)
        for value in date_candidates:
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _market_value_from_millions(value: Any) -> Decimal | None:
        parsed = _decimal(value)
        if parsed is None:
            return None
        return parsed * Decimal("1000000")


class CullenHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Cullen ETF holdings from the public SRP holdings CSV endpoint."""

    _FUND_IDS_BY_SYMBOL = {
        "DIVP": "3156",
    }
    _DOWNLOAD_ID = "38"

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return None
        return f"https://www.cullenfunds.com/US/P/ETF/{normalized_symbol}/"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        fund_id = self._resolve_fund_id(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not fund_id:
            fund_id = await self._discover_fund_id(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers or {},
            )
        if not fund_id:
            raise ValueError(f"{self.adapter_key} needs a Cullen fund id for {symbol}.")

        holdings_url = source_url or self._holdings_url(
            fund_id=fund_id,
            requested_date=date.today(),
        )
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                holdings_url,
                headers=_issuer_page_request_headers(accept="text/csv,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows = self._parse_cullen_csv(response.text)
        if not rows:
            raise ValueError(f"{self.adapter_key} returned no parseable holdings rows for {symbol}.")
        composition_date = self._extract_composition_date(response.text)
        return HoldingsFetchResult(
            source_url=str(getattr(response, "url", holdings_url)),
            source_identifier=fund_id,
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_public_srp_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "issuer_product_id": fund_id,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _resolve_fund_id(
        cls,
        *,
        symbol: str,
        issuer_product_id: str | None,
        identifiers: dict[str, str],
    ) -> str | None:
        return (
            _clean(issuer_product_id)
            or _identifier(identifiers, "issuer_product_id", "fund_id", "cullen_fund_id")
            or cls._FUND_IDS_BY_SYMBOL.get(symbol.strip().upper())
        )

    async def _discover_fund_id(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None,
        source_url: str | None,
        identifiers: dict[str, str],
    ) -> str | None:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if not product_page_url:
            return None
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        match = re.search(r"fund_id:\s*['\"]?(\d+)['\"]?", response.text)
        return match.group(1) if match else None

    @classmethod
    def _holdings_url(cls, *, fund_id: str, requested_date: date) -> str:
        return (
            "https://www.cullenfunds.com/srp/api/fund-holdings-csv-download/"
            f"{cls._DOWNLOAD_ID}/?fund_id={fund_id}&as_at_date={requested_date.isoformat()}"
        )

    @staticmethod
    def _parse_cullen_csv(raw_csv: str) -> list[CanonicalHoldingRow]:
        table_rows = list(csv.reader(StringIO(raw_csv.strip())))
        for row in table_rows:
            normalized = [str(value).strip().lower() for value in row]
            if normalized == [
                "security name",
                "ticker",
                "cusip",
                "shares",
                "market value",
                "percentage",
            ]:
                row[-1] = "% of Net Assets"
                break
        return parse_holdings_table(table_rows)

    @staticmethod
    def _extract_composition_date(raw_csv: str) -> date | None:
        match = re.search(r"Holdings\s+as\s+at\s+(\d{4}-\d{1,2}-\d{1,2})", raw_csv)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None


class VirtusHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Virtus ETF holdings from public product-page XLS position files."""

    _PRODUCT_PAGE_BY_SYMBOL = {
        "SSMG": "https://www.virtus.com/products/virtus-silvant-small-mid-growth-etf",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        return self._PRODUCT_PAGE_BY_SYMBOL.get(normalized_symbol)

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        requested_symbol = symbol.strip().upper()
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            raise ValueError(f"{self.adapter_key} needs a Virtus ETF product page for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if product_page_url.lower().endswith(".xls"):
                positions_url = product_page_url
                page_text = None
            else:
                page_response = await client.get(
                    product_page_url,
                    headers=_issuer_page_request_headers(accept="text/html,*/*"),
                    follow_redirects=True,
                )
                page_response.raise_for_status()
                page_text = page_response.text
                positions_url = self._discover_positions_xls_url(
                    page_text,
                    base_url=str(page_response.url),
                )
                if not positions_url:
                    raise ValueError(
                        f"{self.adapter_key} product page did not expose a positions XLS for {symbol}."
                    )

            workbook_response = await client.get(
                positions_url,
                headers=_issuer_page_request_headers(
                    accept="application/vnd.ms-excel,application/octet-stream,*/*",
                ),
                follow_redirects=True,
            )
        workbook_response.raise_for_status()
        _, table_rows = parse_holdings_xls(workbook_response.content)
        rows, composition_date = self._parse_positions_table(
            table_rows,
            fund_symbol=requested_symbol,
        )
        if not rows:
            raise ValueError(f"{self.adapter_key} returned no parseable holdings rows for {symbol}.")

        return HoldingsFetchResult(
            source_url=str(getattr(workbook_response, "url", positions_url)),
            source_identifier=issuer_product_id or requested_symbol,
            rows=rows,
            raw_text=page_text,
            raw_json=None,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "xls",
                "route_resolution": "issuer_product_page_positions_xls",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "positions_url": str(getattr(workbook_response, "url", positions_url)),
                "product_page_url": product_page_url,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _discover_positions_xls_url(raw_html: str, *, base_url: str) -> str | None:
        candidates: list[str] = []
        for match in re.finditer(r"href=[\"']([^\"']+\.xls(?:\?[^\"']*)?)[\"']", raw_html, re.I):
            href = html.unescape(match.group(1))
            if "positions_" not in href.lower():
                continue
            candidates.append(urljoin(base_url, href))
        return candidates[0] if candidates else None

    @classmethod
    def _parse_positions_table(
        cls,
        table_rows: list[list[str]],
        *,
        fund_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        composition_date = cls._extract_positions_date(table_rows)
        header_index = cls._find_header_index(table_rows)
        if header_index is None:
            return [], composition_date

        rows: list[CanonicalHoldingRow] = []
        for source_index, row in enumerate(table_rows[header_index + 1 :], start=1):
            row = [str(value).strip() for value in row]
            account_name = _clean(row[0] if len(row) > 0 else None)
            security_id = _clean(row[1] if len(row) > 1 else None)
            name = _clean(row[2] if len(row) > 2 else None)
            ticker = _clean(row[3] if len(row) > 3 else None)
            security_type = _clean(row[4] if len(row) > 4 else None)
            shares = _decimal(row[5] if len(row) > 5 else None)
            price = _decimal(row[6] if len(row) > 6 else None)
            market_value = _decimal(row[11] if len(row) > 11 else None)
            if not any([account_name, security_id, name, ticker, market_value]):
                continue
            row_type, holding_type = cls._classify_position(
                ticker=ticker,
                name=name,
                security_type=security_type,
            )
            symbol = ticker if row_type == "security" else None
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    shares=shares,
                    market_value=market_value,
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{fund_symbol}-{source_index}",
                    extra_data={
                        "account_name": account_name,
                        "security_id": security_id,
                        "security_type": security_type,
                        "price": str(price) if price is not None else None,
                    },
                )
            )

        total_market_value = sum(
            (row.market_value for row in rows if row.market_value is not None),
            Decimal("0"),
        )
        if total_market_value:
            for row in rows:
                if row.market_value is not None:
                    row.weight = row.market_value / total_market_value
        return rows, composition_date

    @staticmethod
    def _find_header_index(table_rows: list[list[str]]) -> int | None:
        required = {"account name", "security id", "name", "ticker", "security type"}
        for index, row in enumerate(table_rows[:40]):
            normalized = {str(value).strip().lower() for value in row if _clean(value)}
            if required <= normalized:
                return index
        return None

    @staticmethod
    def _extract_positions_date(table_rows: list[list[str]]) -> date | None:
        for row in table_rows[:10]:
            text = " ".join(str(value).strip() for value in row if _clean(value))
            match = re.search(r"Positions\s+as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
            if not match:
                continue
            try:
                return datetime.strptime(match.group(1), "%m/%d/%Y").date()
            except ValueError:
                return None
        return None

    @staticmethod
    def _classify_position(
        *,
        ticker: str | None,
        name: str | None,
        security_type: str | None,
    ) -> tuple[str, str]:
        type_text = (security_type or "").strip().lower()
        name_text = (name or "").strip().lower()
        ticker_text = (ticker or "").strip().upper()
        if type_text == "cash" or ticker_text in {"USD", "CASH"} or "cash" in name_text:
            return "cash", "cash"
        if "option" in type_text or "option" in name_text:
            return "security", "option"
        if "bond" in type_text or "debt" in type_text or "note" in type_text:
            return "security", "fixed_income"
        return "security", "equity"


class DirexionHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **super().source_request_headers(source_url=source_url),
            "Referer": "https://www.direxion.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        rows, composition_date = self._parse_direxion_csv(result.raw_text or "", symbol=symbol)
        result.rows = rows
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "route_resolution": "issuer_symbol_holdings_csv",
            "source_access": self.config.source_access,
            **(
                {"composition_date": composition_date.isoformat()}
                if composition_date is not None
                else {}
            ),
        }
        return result

    @staticmethod
    def _parse_direxion_csv(raw_csv: str, *, symbol: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {cell.strip().lower() for cell in row}
                >= {"tradedate", "accountticker", "stockticker"}
            ),
            None,
        )
        if header_index is None:
            return [], None
        header = table_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        requested_symbol = symbol.strip().upper()
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            account_ticker = (_clean(_first(raw, ["AccountTicker"])) or "").upper()
            if account_ticker and account_ticker != requested_symbol:
                continue
            row_date = DirexionHoldingsAdapter._parse_trade_date(_first(raw, ["TradeDate"]))
            if composition_date is None:
                composition_date = row_date
            raw_symbol = _clean(_first(raw, ["StockTicker"]))
            name = _clean(_first(raw, ["SecurityDescription"]))
            holding_type = DirexionHoldingsAdapter._holding_type(symbol=raw_symbol, name=name)
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=raw_symbol if row_type != "cash" else None,
                    name=name,
                    cusip=_clean(_first(raw, ["Cusip"])),
                    weight=_decimal_percent_points(_first(raw, ["HoldingsPercent"])),
                    shares=_decimal(_first(raw, ["Shares"])),
                    market_value=_decimal(_first(raw, ["MarketValue"])),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_trade_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _holding_type(*, symbol: str | None, name: str | None) -> str:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if text in {"USD", "US DOLLAR"} or "US DOLLAR" in text or "CASH" in text:
            return "cash"
        if any(marker in text for marker in ("FUTURE", "OPTION", "SWAP", "TREASURY BILL")):
            return "derivative"
        return "security"


class ThemesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        rows, composition_date = self._parse_themes_csv(result.raw_text or "", symbol=symbol)
        result.rows = rows
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "route_resolution": "issuer_symbol_holdings_csv",
            "source_access": self.config.source_access,
            **(
                {
                    "composition_date": composition_date.isoformat(),
                    "as_of_date": composition_date.isoformat(),
                }
                if composition_date is not None
                else {}
            ),
        }
        return result

    @staticmethod
    def _parse_themes_csv(raw_csv: str, *, symbol: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {cell.strip().lower() for cell in row}
                >= {"date", "account", "stock_ticker", "security_name"}
            ),
            None,
        )
        if header_index is None:
            return [], None
        header = table_rows[header_index]
        requested_symbol = symbol.strip().upper()
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            account = (_clean(_first(raw, ["account"])) or "").upper()
            if account and account != requested_symbol:
                continue
            row_date = ThemesHoldingsAdapter._parse_themes_date(_first(raw, ["date"]))
            if composition_date is None:
                composition_date = row_date
            raw_symbol = _clean(_first(raw, ["stock_ticker"]))
            name = _clean(_first(raw, ["security_name"]))
            holding_type = ThemesHoldingsAdapter._holding_type(symbol=raw_symbol, name=name)
            row_type = "cash" if holding_type == "cash" else "security"
            country = (
                _clean(_first(raw, ["country_code"]))
                or _clean(_first(raw, ["country_full"]))
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=raw_symbol if row_type != "cash" else None,
                    name=name,
                    cusip=_clean(_first(raw, ["cusip"])),
                    weight=_decimal_percent_points(_first(raw, ["weightings"])),
                    shares=_decimal(_first(raw, ["shares"])),
                    market_value=_decimal(_first(raw, ["market_value"])),
                    currency=raw_symbol if row_type == "cash" and raw_symbol else None,
                    country=country,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=_clean(_first(raw, ["id"])) or str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_themes_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _holding_type(*, symbol: str | None, name: str | None) -> str:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if (
            "DOLLAR" in text
            or "CASH" in text
            or (symbol is not None and re.fullmatch(r"[A-Z]{3}", symbol.strip().upper()))
        ):
            return "cash"
        return "security"


class TemaHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="text/csv,*/*"),
            "Referer": "https://temaetfs.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        rows, composition_date = self._parse_tema_csv(result.raw_text or "")
        result.rows = rows
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_format": "csv",
            "route_resolution": "issuer_symbol_holdings_csv",
            "source_access": self.config.source_access,
            **(
                {
                    "composition_date": composition_date.isoformat(),
                    "as_of_date": composition_date.isoformat(),
                }
                if composition_date is not None
                else {}
            ),
        }
        return result

    @staticmethod
    def _parse_tema_csv(raw_csv: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {cell.strip().lower() for cell in row}
                >= {"holdings_date", "ticker", "proper_name", "percent_of_nav"}
            ),
            None,
        )
        if header_index is None:
            return [], None
        header = table_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            row_date = TemaHoldingsAdapter._parse_tema_date(_first(raw, ["holdings_date"]))
            if composition_date is None:
                composition_date = row_date
            raw_symbol = _clean(_first(raw, ["ticker"]))
            symbol, exchange = TemaHoldingsAdapter._split_symbol(raw_symbol)
            raw_identifier = _clean(_first(raw, ["cusip"]))
            is_cash = (_clean(_first(raw, ["is_cash"])) or "").lower() in {"1", "true", "y", "yes"}
            holding_type = "cash" if is_cash else "security"
            row_type = "cash" if is_cash else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=_clean(_first(raw, ["proper_name"])),
                    cusip=raw_identifier if _looks_like_cusip(raw_identifier) else None,
                    sedol=(
                        raw_identifier
                        if raw_identifier
                        and not _looks_like_cusip(raw_identifier)
                        and re.fullmatch(r"[A-Z0-9]{6,7}", raw_identifier)
                        else None
                    ),
                    weight=_decimal(_first(raw, ["percent_of_nav"])),
                    shares=_decimal(_first(raw, ["shares"])),
                    market_value=_decimal(_first(raw, ["market_value"])),
                    country=_clean(_first(raw, ["country"])),
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_tema_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _split_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
        text = _clean(raw_symbol)
        if not text:
            return None, None
        normalized = " ".join(text.split()).upper()
        match = re.fullmatch(r"([A-Z0-9.=-]+)\s+([A-Z]{2})", normalized)
        if match:
            return match.group(1), match.group(2)
        if re.fullmatch(r"[A-Z0-9.=-]{1,12}", normalized):
            return normalized, None
        return None, None


class DistillateHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="text/csv,*/*"),
            "Referer": "https://distillatecapital.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        rows, composition_date = self._parse_distillate_csv(result.raw_text or "", symbol=symbol)
        result.rows = rows
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_format": "csv",
            "route_resolution": "issuer_symbol_holdings_csv",
            "source_access": self.config.source_access,
            **(
                {
                    "composition_date": composition_date.isoformat(),
                    "as_of_date": composition_date.isoformat(),
                }
                if composition_date is not None
                else {}
            ),
        }
        return result

    @staticmethod
    def _parse_distillate_csv(raw_csv: str, *, symbol: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {cell.strip().lower() for cell in row}
                >= {"date", "account", "stockticker", "securityname"}
            ),
            None,
        )
        if header_index is None:
            return [], None
        header = table_rows[header_index]
        requested_symbol = symbol.strip().upper()
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            account = (_clean(_first(raw, ["account"])) or "").upper()
            if account and account != requested_symbol:
                continue
            row_date = DistillateHoldingsAdapter._parse_distillate_date(_first(raw, ["date"]))
            if composition_date is None:
                composition_date = row_date
            raw_symbol = _clean(_first(raw, ["stockticker"]))
            name = _clean(_first(raw, ["securityname"]))
            money_market_flag = (_clean(_first(raw, ["moneymarketflag"])) or "").upper()
            holding_type = DistillateHoldingsAdapter._holding_type(
                symbol=raw_symbol,
                name=name,
                money_market_flag=money_market_flag,
            )
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=raw_symbol if row_type != "cash" else None,
                    name=name,
                    cusip=_clean(_first(raw, ["cusip"])),
                    weight=_decimal(_first(raw, ["weightings"])),
                    shares=_decimal(_first(raw, ["shares"])),
                    market_value=_decimal(_first(raw, ["marketvalue"])),
                    currency="USD" if row_type == "cash" else None,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_distillate_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _holding_type(*, symbol: str | None, name: str | None, money_market_flag: str | None) -> str:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if money_market_flag == "Y" or "CASH" in text or "CASH&OTHER" in text:
            return "cash"
        return "security"


class EventideHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Eventide ETF holdings from issuer-linked Contentful CSV files."""

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        return explicit or "https://www.eventideinvestments.com/etfs"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        holdings_url = source_url if source_url and source_url.lower().endswith(".csv") else None
        product_page_url = None
        page_text: str | None = None

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if holdings_url is None:
                product_page_url = source_url or self.resolve_product_page_url(
                    symbol=symbol,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers or {},
                )
                if not product_page_url:
                    raise ValueError(f"Eventide needs an ETF listing page for {symbol}.")
                page_response = await client.get(
                    product_page_url,
                    headers=self.source_request_headers(source_url=product_page_url),
                    follow_redirects=True,
                )
                page_response.raise_for_status()
                page_text = page_response.text
                holdings_url = self._discover_eventide_holdings_csv(
                    page_text,
                    symbol=normalized_symbol,
                    base_url=str(page_response.url),
                )
                if not holdings_url:
                    raise ValueError(
                        f"Eventide listing page did not expose a holdings CSV for {normalized_symbol}."
                    )

            csv_response = await client.get(
                holdings_url,
                headers=self.source_request_headers(source_url=holdings_url),
                follow_redirects=True,
            )
        csv_response.raise_for_status()
        rows, composition_date, product_name = self._parse_eventide_csv(
            csv_response.text,
            symbol=normalized_symbol,
        )
        if not rows:
            raise ValueError(f"Eventide holdings CSV did not expose holdings rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=csv_response.text,
            raw_json=None,
            source_url=str(getattr(csv_response, "url", holdings_url)),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_listing_page_contentful_holdings_csv",
                "product_page_url": product_page_url,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "product_name": product_name,
                "listing_page_cached": bool(page_text),
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="text/html,text/csv,*/*")
        headers["Referer"] = "https://www.eventideinvestments.com/etfs"
        return headers

    @classmethod
    def _discover_eventide_holdings_csv(
        cls,
        raw_html: str,
        *,
        symbol: str,
        base_url: str,
    ) -> str | None:
        unescaped = html.unescape(raw_html).replace("\\/", "/")
        candidates = sorted(
            set(
                re.findall(
                    r"(?:https:)?//assets\.ctfassets\.net/[^\"'<>\\\s]+?\.csv",
                    unescaped,
                    flags=re.IGNORECASE,
                )
            )
        )
        expected_file_name = f"{symbol.upper()}_etfholdingscsv.csv".lower()
        for candidate in candidates:
            url = candidate
            if url.startswith("//"):
                url = f"https:{url}"
            resolved = urljoin(base_url, url)
            if resolved.rsplit("/", 1)[-1].lower() == expected_file_name:
                return resolved
        return None

    @classmethod
    def _parse_eventide_csv(
        cls,
        raw_csv: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None, str | None]:
        table_rows = list(csv.reader(StringIO(raw_csv.strip())))
        metadata: dict[str, str] = {}
        for row in table_rows[:10]:
            key = _clean(row[0]) if row else ""
            if str(key).strip().lower() in {"ticker", "description"} and len(row) > 2:
                break
            if len(row) >= 2 and key:
                metadata.setdefault(str(row[0]).strip().lower(), str(row[1]).strip())
        if metadata.get("ticker", "").upper() not in {"", symbol.upper()}:
            raise ValueError(
                f"Eventide holdings CSV ticker {metadata.get('ticker')} did not match {symbol}."
            )
        composition_date = cls._parse_eventide_date(metadata.get("as-of date"))
        normalized_rows: list[CanonicalHoldingRow] = []
        for row in parse_holdings_table(table_rows):
            row_type = row.row_type
            holding_type = row.holding_type
            symbol_value, exchange = cls._split_eventide_symbol(row.symbol)
            name = row.name
            if (name or "").strip().lower() in {"cash and cash equivalents", "cash equivalents"}:
                symbol_value = None
                exchange = None
                row_type = "cash"
                holding_type = "cash"
            normalized_rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value if row_type != "cash" else None,
                    name=name,
                    cusip=row.cusip,
                    isin=row.isin,
                    sedol=row.sedol,
                    weight=row.weight,
                    shares=row.shares,
                    market_value=row.market_value,
                    currency=row.currency,
                    country=row.country,
                    exchange=exchange or row.exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=row.source_row_id,
                    extra_data=row.extra_data,
                )
            )
        return normalized_rows, composition_date, metadata.get("product")

    @staticmethod
    def _split_eventide_symbol(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if not text:
            return None, None
        normalized = " ".join(text.split()).upper()
        parts = normalized.split()
        if len(parts) == 2 and re.fullmatch(r"[A-Z0-9.=-]{1,12}", parts[0]):
            return parts[0], parts[1]
        if re.fullmatch(r"[A-Z0-9.=-]{1,12}", normalized):
            return normalized, None
        return normalized, None

    @staticmethod
    def _parse_eventide_date(value: str | None) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None


class FaithInvestorServicesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Faith Investor Services ETF holdings from issuer page metadata."""

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return f"https://faithinvestorservices.com/etfs/{symbol.strip().lower()}"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        product_page_url = None
        page_text: str | None = None
        holdings_url = source_url if source_url and source_url.lower().endswith(".csv") else None

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if holdings_url is None:
                product_page_url = source_url or self.resolve_product_page_url(
                    symbol=symbol,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers or {},
                )
                if not product_page_url:
                    raise ValueError(f"Faith Investor Services needs an ETF product page for {symbol}.")
                page_response = await client.get(
                    product_page_url,
                    headers=self.source_request_headers(source_url=product_page_url),
                    follow_redirects=True,
                )
                page_response.raise_for_status()
                page_text = page_response.text
                holdings_url = self._discover_holdings_csv(
                    page_text,
                    symbol=normalized_symbol,
                )
                if not holdings_url:
                    raise ValueError(
                        "Faith Investor Services product page did not expose a full "
                        f"holdings CSV for {normalized_symbol}."
                    )

            csv_response = await client.get(
                holdings_url,
                headers=self.source_request_headers(source_url=holdings_url),
                follow_redirects=True,
            )
        csv_response.raise_for_status()
        composition_date, rows = self._parse_holdings_csv(
            csv_response.text,
            symbol=normalized_symbol,
        )
        if not rows:
            raise ValueError(
                f"Faith Investor Services holdings CSV did not expose holdings rows for {symbol}."
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=csv_response.text,
            source_url=str(getattr(csv_response, "url", holdings_url)),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": (
                    "issuer_product_page_next_data_holdings_csv"
                    if page_text is not None
                    else "issuer_profile_metadata"
                ),
                "product_page_url": product_page_url,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="text/html,text/csv,*/*")
        headers["Referer"] = "https://faithinvestorservices.com/etfs"
        return headers

    @staticmethod
    def _discover_holdings_csv(page_text: str, *, symbol: str) -> str | None:
        match = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            page_text,
            flags=re.S | re.I,
        )
        if not match:
            return None
        try:
            payload = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            return None
        data = payload.get("props", {}).get("pageProps", {}).get("data", {})
        distributions_copy = data.get("distributionsCopy") or {}
        download = distributions_copy.get("download") or {}
        download_url = _clean(download.get("url")) if isinstance(download, dict) else None
        if (
            download_url
            and "holding" in download_url.lower()
            and download_url.lower().endswith(".csv")
        ):
            return download_url

        data_reference = data.get("dataReference") or {}
        for reference in data_reference.values():
            if not isinstance(reference, dict):
                continue
            media_url = _clean(reference.get("mediaItemUrl"))
            if (
                media_url
                and "holding" in media_url.lower()
                and symbol.lower() in media_url.lower()
                and media_url.lower().endswith(".csv")
            ):
                return media_url
        return download_url if download_url and download_url.lower().endswith(".csv") else None

    @staticmethod
    def _parse_holdings_csv(raw_csv: str, *, symbol: str) -> tuple[date | None, list[CanonicalHoldingRow]]:
        composition_date: date | None = None
        rows: list[CanonicalHoldingRow] = []
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        for index, row in enumerate(table_rows, start=1):
            if len(row) < 9:
                continue
            if row[0].strip().lower() == "date":
                continue
            account = _clean(row[1])
            if account and account.upper() != symbol:
                continue
            row_date = _clean(row[0])
            if row_date and composition_date is None:
                try:
                    composition_date = datetime.strptime(row_date, "%m/%d/%Y").date()
                except ValueError:
                    composition_date = None
            raw_symbol = _clean(row[2])
            name = _clean(row[4])
            money_market_flag = _clean(row[12]) if len(row) > 12 else None
            row_type = "cash" if (
                (money_market_flag or "").upper() == "Y"
                or (name or "").lower().startswith(("first american treasury", "cash"))
            ) else "security"
            holding_type = "cash" if row_type == "cash" else "equity"
            rows.append(
                CanonicalHoldingRow(
                    symbol=None if row_type == "cash" else raw_symbol,
                    name=name,
                    cusip=_clean(row[3]) if _looks_like_cusip(_clean(row[3])) else None,
                    weight=_decimal(row[8]),
                    shares=_decimal(row[5]),
                    market_value=_decimal(row[7]),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={
                        "account": account,
                        "source_symbol": raw_symbol,
                        "price": _clean(row[6]),
                        "net_assets": _clean(row[9]) if len(row) > 9 else None,
                        "shares_outstanding": _clean(row[10]) if len(row) > 10 else None,
                        "creation_units": _clean(row[11]) if len(row) > 11 else None,
                        "money_market_flag": money_market_flag,
                    },
                )
            )
        return composition_date, rows


class OneAscentHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch OneAscent ETF holdings from issuer product-page AJAX CSV routes."""

    product_page_template = "https://oneascent.com/investment-solutions/public-markets/etfs/{symbol_lower}/"

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.product_page_template.format(symbol_lower=symbol.strip().lower())

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        product_page_url = None
        holdings_url = source_url if source_url and "pds_download_holdings_csv" in source_url else None

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if holdings_url is None:
                product_page_url = source_url or self.resolve_product_page_url(
                    symbol=normalized_symbol,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers or {},
                )
                if not product_page_url:
                    raise ValueError(f"OneAscent needs an ETF product page for {symbol}.")
                page_response = await client.get(
                    product_page_url,
                    headers=self.source_request_headers(source_url=product_page_url),
                    follow_redirects=True,
                )
                page_response.raise_for_status()
                holdings_url = self._discover_holdings_csv(
                    page_response.text,
                    base_url=str(getattr(page_response, "url", product_page_url)),
                )
                if not holdings_url:
                    raise ValueError(f"OneAscent product page did not expose holdings CSV for {symbol}.")

            csv_response = await client.get(
                holdings_url,
                headers=self.source_request_headers(source_url=holdings_url),
                follow_redirects=True,
            )
        csv_response.raise_for_status()
        rows, composition_date = self._parse_oneascent_csv(csv_response.text)
        if not rows:
            raise ValueError(f"OneAscent holdings CSV did not expose holdings rows for {symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=csv_response.text,
            source_url=str(getattr(csv_response, "url", holdings_url)),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_product_page_ajax_holdings_csv",
                "product_page_url": product_page_url,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="text/html,text/csv,*/*")
        headers["Referer"] = "https://oneascent.com/investment-solutions/public-markets/etfs/"
        return headers

    @staticmethod
    def _discover_holdings_csv(page_text: str, *, base_url: str) -> str | None:
        match = re.search(
            r'["\']([^"\']*pds_download_holdings_csv[^"\']*)["\']',
            page_text,
            flags=re.I,
        )
        if not match:
            return None
        return urljoin(base_url, html.unescape(match.group(1)))

    @staticmethod
    def _parse_oneascent_csv(raw_csv: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None
        header = table_rows[0]
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, row in enumerate(table_rows[1:], start=1):
            raw = _row_dict(header, row)
            row_date = _clean(_first(raw, ["As Of Date"]))
            if row_date and composition_date is None:
                try:
                    composition_date = datetime.strptime(row_date, "%m/%d/%Y").date()
                except ValueError:
                    composition_date = None
            raw_symbol = _clean(_first(raw, ["Ticker"]))
            symbol_value, exchange = OneAscentHoldingsAdapter._split_symbol(raw_symbol)
            name = _clean(_first(raw, ["Security Name"]))
            cusip = _clean(_first(raw, ["CUSIP"]))
            holding_type = OneAscentHoldingsAdapter._holding_type(
                symbol=symbol_value,
                name=name,
            )
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value if row_type != "cash" else None,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    weight=_decimal_percent_points(_first(raw, ["Weight (%)"])),
                    shares=_decimal(_first(raw, ["Shares"])),
                    market_value=_decimal(_first(raw, ["Market Value"])),
                    country=_clean(_first(raw, ["Country"])),
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={
                        **{key: value for key, value in raw.items() if value not in (None, "")},
                        "source_symbol": raw_symbol,
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _split_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
        text = _clean(raw_symbol)
        if not text:
            return None, None
        normalized = " ".join(text.split()).upper()
        match = re.fullmatch(r"([A-Z0-9./=-]+)\s+([A-Z]{2})", normalized)
        if match:
            return match.group(1), match.group(2)
        return normalized, None

    @staticmethod
    def _holding_type(*, symbol: str | None, name: str | None) -> str:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if not text or "CASH" in text or "TREASURY BILL" in text or "MONEY MARKET" in text:
            return "cash"
        return "equity"


class AmplifyHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="text/csv,*/*"),
            "Referer": "https://amplifyetfs.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        rows, composition_date = self._parse_amplify_csv(result.raw_text or "", symbol=symbol)
        result.rows = rows
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_format": "csv",
            "route_resolution": "issuer_multi_account_holdings_csv",
            "source_access": self.config.source_access,
            **(
                {
                    "composition_date": composition_date.isoformat(),
                    "as_of_date": composition_date.isoformat(),
                }
                if composition_date is not None
                else {}
            ),
        }
        return result

    @staticmethod
    def _parse_amplify_csv(raw_csv: str, *, symbol: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {cell.strip().lower() for cell in row}
                >= {"date", "account", "stockticker", "securityname"}
            ),
            None,
        )
        if header_index is None:
            return [], None
        header = table_rows[header_index]
        requested_symbol = symbol.strip().upper()
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            account = (_clean(_first(raw, ["account"])) or "").upper()
            if account and account != requested_symbol:
                continue
            row_date = AmplifyHoldingsAdapter._parse_amplify_date(_first(raw, ["date"]))
            if composition_date is None:
                composition_date = row_date
            raw_symbol = _clean(_first(raw, ["stockticker"]))
            symbol_value, exchange = AmplifyHoldingsAdapter._split_symbol(raw_symbol)
            name = _clean(_first(raw, ["securityname"]))
            raw_identifier = _clean(_first(raw, ["cusip"]))
            money_market_flag = (_clean(_first(raw, ["moneymarketflag"])) or "").upper()
            holding_type = AmplifyHoldingsAdapter._holding_type(
                raw_symbol=raw_symbol,
                symbol=symbol_value,
                name=name,
                money_market_flag=money_market_flag,
            )
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value if row_type != "cash" else None,
                    name=name,
                    cusip=raw_identifier if _looks_like_cusip(raw_identifier) else None,
                    sedol=(
                        raw_identifier
                        if raw_identifier
                        and not _looks_like_cusip(raw_identifier)
                        and re.fullmatch(r"[A-Z0-9]{6,7}", raw_identifier)
                        else None
                    ),
                    weight=_decimal(_first(raw, ["weightings"])),
                    shares=_decimal(_first(raw, ["shares"])),
                    market_value=_decimal(_first(raw, ["marketvalue"])),
                    currency="USD" if row_type == "cash" else None,
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_amplify_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _split_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
        text = _clean(raw_symbol)
        if not text:
            return None, None
        normalized = " ".join(text.split()).upper()
        if normalized in {"CASH", "CASH&OTHER"}:
            return normalized, None
        match = re.fullmatch(r"([A-Z0-9.=-]+)\s+([A-Z]{2})", normalized)
        if match:
            return match.group(1), match.group(2)
        if re.fullmatch(r"[A-Z0-9.=-]{1,12}", normalized):
            return normalized, None
        return None, None

    @staticmethod
    def _holding_type(
        *,
        raw_symbol: str | None,
        symbol: str | None,
        name: str | None,
        money_market_flag: str | None,
    ) -> str:
        text = " ".join(part.upper() for part in (raw_symbol, symbol, name) if part)
        if money_market_flag == "Y" or "CASH" in text or "CASH&OTHER" in text:
            return "cash"
        if " INDEX" in text or " FUTURE" in text or " TIMECHARTER " in text:
            return "future"
        return "security"


class VolatilitySharesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="application/vnd.ms-excel,*/*"),
            "Referer": "https://www.volatilityshares.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        workbook_rows = (result.raw_json or {}).get("workbook_rows", [])
        rows = self._parse_volatility_shares_table(workbook_rows)
        result.rows = rows
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_format": "xls",
            "route_resolution": "issuer_symbol_holdings_xls",
            "source_access": self.config.source_access,
        }
        return result

    @staticmethod
    def _parse_volatility_shares_table(table_rows: list[list[Any]]) -> list[CanonicalHoldingRow]:
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {str(cell).strip().lower() for cell in row}
                >= {"description", "shares/contracts", "market value/notional"}
            ),
            None,
        )
        if header_index is None:
            return []
        header = table_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            name = _clean(_first(raw, ["description"]))
            if name is None:
                continue
            holding_type = VolatilitySharesHoldingsAdapter._holding_type(name)
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=None,
                    name=name,
                    shares=_decimal(_first(raw, ["shares/contracts"])),
                    market_value=_decimal(_first(raw, ["market value/notional"])),
                    currency="USD" if row_type == "cash" else None,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows

    @staticmethod
    def _holding_type(name: str) -> str:
        normalized = name.upper()
        if "CASH" in normalized:
            return "cash"
        if "FUTURE" in normalized:
            return "future"
        if re.search(r"\b[CP]\d+(?:\.\d+)?\b", normalized):
            return "option"
        return "security"


class WahedHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        if "docs.google.com" in source_url:
            return _holdings_request_headers(accept="text/csv,*/*")
        return {
            **_holdings_request_headers(accept="text/csv,*/*"),
            "Referer": "https://www.wahed.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = source_url
        route_resolution = "issuer_profile_metadata"
        if not resolved_source_url:
            product_page_url = self.resolve_product_page_url(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                identifiers=identifiers or {},
            )
            if product_page_url:
                async with httpx.AsyncClient(
                    timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS
                ) as client:
                    response = await client.get(
                        product_page_url,
                        headers=_issuer_page_request_headers(accept="text/html,*/*"),
                        follow_redirects=True,
                    )
                response.raise_for_status()
                resolved_source_url = self._discover_google_sheet_export(response.text)
                route_resolution = "issuer_product_page_google_sheet"
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=resolved_source_url,
            identifiers=identifiers,
        )
        rows, composition_date = self._parse_wahed_csv(result.raw_text or "", symbol=symbol)
        result.rows = rows
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_format": "csv",
            "route_resolution": route_resolution,
            "source_access": self.config.source_access,
            **(
                {
                    "composition_date": composition_date.isoformat(),
                    "as_of_date": composition_date.isoformat(),
                }
                if composition_date is not None
                else {}
            ),
        }
        return result

    @staticmethod
    def _discover_google_sheet_export(raw_html: str) -> str | None:
        for match in re.finditer(
            r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>",
            raw_html,
            re.IGNORECASE | re.DOTALL,
        ):
            body_text = re.sub(r"<[^>]+>", " ", match.group("body"))
            if not re.search(r"\bHoldings\b", " ".join(body_text.split()), re.IGNORECASE):
                continue
            href_match = re.search(r'href="([^"]+)"', match.group("attrs"), re.IGNORECASE)
            if href_match is None:
                continue
            href = html.unescape(href_match.group(1))
            sheet_match = re.search(r"/spreadsheets/d/([^/#?]+)", href)
            if sheet_match:
                sheet_id = sheet_match.group(1)
                gid_match = re.search(r"[?#&]gid=(\d+)", href)
                gid = gid_match.group(1) if gid_match else "0"
                return (
                    f"https://docs.google.com/spreadsheets/d/{sheet_id}/export"
                    f"?format=csv&gid={gid}"
                )
        return None

    @staticmethod
    def _parse_wahed_csv(raw_csv: str, *, symbol: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {cell.strip().lower() for cell in row}
                >= {"date", "account", "stockticker", "securityname"}
            ),
            None,
        )
        if header_index is None:
            return [], None
        header = table_rows[header_index]
        requested_symbol = symbol.strip().upper()
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            account = (_clean(_first(raw, ["account"])) or "").upper()
            if account and account != requested_symbol:
                continue
            row_date = WahedHoldingsAdapter._parse_wahed_date(_first(raw, ["date"]))
            if composition_date is None:
                composition_date = row_date
            raw_symbol = _clean(_first(raw, ["stockticker"]))
            name = _clean(_first(raw, ["securityname"]))
            money_market_flag = (_clean(_first(raw, ["moneymarketflag"])) or "").upper()
            holding_type = WahedHoldingsAdapter._holding_type(
                symbol=raw_symbol,
                name=name,
                money_market_flag=money_market_flag,
            )
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=(
                        WahedHoldingsAdapter._clean_symbol(raw_symbol)
                        if row_type != "cash"
                        else None
                    ),
                    name=name,
                    cusip=(
                        _clean(_first(raw, ["cusip"]))
                        if _looks_like_cusip(_clean(_first(raw, ["cusip"])))
                        else None
                    ),
                    weight=_decimal(_first(raw, ["weightings"])),
                    shares=_decimal(_first(raw, ["shares"])),
                    market_value=_decimal(_first(raw, ["marketvalue"])),
                    currency="USD" if row_type == "cash" else None,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_wahed_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _clean_symbol(value: str | None) -> str | None:
        text = _clean(value)
        if not text:
            return None
        normalized = text.strip().upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", normalized):
            return normalized
        return None

    @staticmethod
    def _holding_type(*, symbol: str | None, name: str | None, money_market_flag: str | None) -> str:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if money_market_flag == "Y" or "CASH" in text or "CASH&OTHER" in text:
            return "cash"
        return "security"


class AllianzHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse AllianzIM's public multi-fund holdings feed by ETF account symbol."""

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers={
                    **_holdings_request_headers(accept="text/csv,*/*"),
                    "Referer": "https://www.allianzim.com/etfs/",
                },
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_allianz_csv(response.text, symbol=symbol)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_multi_fund_holdings_csv",
                "terms_note": self.config.terms_note,
                **(
                    {
                        "composition_date": composition_date.isoformat(),
                        "as_of_date": composition_date.isoformat(),
                    }
                    if composition_date is not None
                    else {}
                ),
            },
        )

    @staticmethod
    def _parse_allianz_csv(
        raw_csv: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        requested_symbol = symbol.strip().upper()
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for position, item in enumerate(csv.DictReader(StringIO(raw_csv)), start=1):
            account = (_clean(item.get("Account")) or "").upper()
            if account != requested_symbol:
                continue
            row_date = AllianzHoldingsAdapter._parse_allianz_date(item.get("Date"))
            if composition_date is None:
                composition_date = row_date
            raw_symbol = _clean(item.get("StockTicker"))
            name = _clean(item.get("SecurityName"))
            money_market_flag = (_clean(item.get("MoneyMarketFlag")) or "").upper()
            row_type, holding_type = AllianzHoldingsAdapter._classify_holding(
                symbol=raw_symbol,
                name=name,
                money_market_flag=money_market_flag,
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=(
                        AllianzHoldingsAdapter._clean_security_symbol(raw_symbol)
                        if holding_type not in {"cash", "option"}
                        else None
                    ),
                    name=name,
                    cusip=(
                        _clean(item.get("CUSIP"))
                        if _looks_like_cusip(_clean(item.get("CUSIP")))
                        else None
                    ),
                    weight=_decimal(item.get("Weightings")),
                    shares=_decimal(item.get("Shares")),
                    market_value=_decimal(item.get("MarketValue")),
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(position),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_allianz_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _clean_security_symbol(value: str | None) -> str | None:
        text = _clean(value)
        if not text:
            return None
        normalized = text.strip().upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", normalized):
            return normalized
        return None

    @staticmethod
    def _classify_holding(
        *,
        symbol: str | None,
        name: str | None,
        money_market_flag: str | None,
    ) -> tuple[str, str]:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if money_market_flag == "Y" or "CASH" in text or "CASH&OTHER" in text:
            return "cash", "cash"
        if re.search(r"\b\d{2}/\d{2}/\d{4}\b.+\b[CP]\b", name or ""):
            return "security", "option"
        if re.search(r"\b\d{6}[CP]\d{8}\b", text):
            return "security", "option"
        return "security", "equity"


class SwanGlobalHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Swan Global HEGD holdings from the issuer's public ETF product page."""

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        route_resolution = "issuer_profile_metadata"
        if not resolved_source_url:
            resolved_source_url = await self._discover_source_url_from_product_page(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                identifiers=identifiers or {},
            )
            route_resolution = "issuer_product_page_linked_holdings_csv"
        if not resolved_source_url:
            raise ValueError(f"Swan Global product page did not expose holdings CSV for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = AllianzHoldingsAdapter._parse_allianz_csv(
            response.text,
            symbol=normalized_symbol,
        )
        if not rows:
            raise ValueError(f"Swan Global holdings CSV did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": route_resolution,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,*/*")
        headers["Referer"] = "https://etfs.swanglobalinvestments.com/hedged-equity-etf/"
        return headers


class RunningOakHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Running Oak Efficient Growth ETF holdings from its FilePoint-backed feed."""

    PRODUCT_IDS = {
        "ROEQ": "1363",
    }

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        product_id = (
            issuer_product_id
            or _identifier(identifiers or {}, "running_oak_fund_id", "fund_id", "issuer_product_id")
            or self.PRODUCT_IDS.get(symbol.strip().upper())
        )
        if not product_id:
            return None
        return f"https://filepoint.live/runningoak_holdings_{product_id}_data.json"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Running Oak needs a FilePoint fund id for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        rows, composition_date = self._parse_running_oak_json(payload)
        if not rows:
            raise ValueError(f"Running Oak holdings feed did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={"source_format": "json", "payload": payload},
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=issuer_product_id or self.PRODUCT_IDS.get(symbol.strip().upper()),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_filepoint_holdings_json",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="application/json,*/*")
        headers["Referer"] = "https://www.runningoaketfs.com/full-holdings.html"
        return headers

    @classmethod
    def _parse_running_oak_json(
        cls,
        payload: Any,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        if not isinstance(payload, list):
            return [], None
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                continue
            if composition_date is None:
                composition_date = cls._parse_as_of_date(item.get("asOfDate"))
            raw_symbol = _clean(item.get("securityTicker"))
            symbol, exchange = cls._split_security_ticker(raw_symbol)
            name = _clean(
                item.get("securityDescriptionLong")
                or item.get("securityDescriptionShort")
            )
            cusip = _clean(item.get("securityIdentifier"))
            if not any([symbol, name, cusip, item.get("marketValuePercent")]):
                continue
            holding_type = cls._classify_holding(item)
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    weight=_decimal(item.get("marketValuePercent")),
                    shares=_decimal(item.get("shares")),
                    market_value=_decimal(item.get("marketValueBase")),
                    currency=_clean(item.get("tradingCurrency")),
                    country=_clean(item.get("country")),
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_as_of_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    @staticmethod
    def _split_security_ticker(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if not text:
            return None, None
        parts = text.split()
        if len(parts) == 2 and re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", parts[0].upper()):
            return parts[0].upper(), parts[1].upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", text.upper()):
            return text.upper(), None
        return None, None

    @staticmethod
    def _classify_holding(item: dict[str, Any]) -> str:
        segment = (_clean(item.get("segment")) or "").lower()
        ticker = (_clean(item.get("securityTicker")) or "").upper()
        name = (_clean(item.get("securityDescriptionLong")) or "").lower()
        if "cash" in segment or ticker in {"CASH", "USD", "RECPAY"} or name in {"cash"}:
            return "cash"
        if "option" in segment or re.search(r"\b\d{6}[CP]\d{8}\b", ticker):
            return "option"
        return "equity"


class HennessyHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Hennessy ETF holdings from issuer-rendered product-page tables."""

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        ) or self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Hennessy needs an ETF product page for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows = self._parse_hennessy_product_page(response.text)
        if not rows:
            raise ValueError(f"Hennessy product page did not expose holdings rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_product_page_holdings_table",
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return _holdings_request_headers(accept="text/html,*/*")

    @classmethod
    def _parse_hennessy_product_page(cls, raw_html: str) -> list[CanonicalHoldingRow]:
        tables = re.findall(r"<table\b[^>]*>.*?</table>", raw_html, flags=re.IGNORECASE | re.DOTALL)
        best_rows: list[CanonicalHoldingRow] = []
        for table in tables:
            matrix = cls._html_table_to_matrix(table)
            if not matrix:
                continue
            header = [_clean(cell) or "" for cell in matrix[0]]
            normalized_header = {cell.lower() for cell in header}
            if not {"name", "ticker", "cusip", "shares", "market value", "% of net assets"}.issubset(
                normalized_header
            ):
                continue
            rows: list[CanonicalHoldingRow] = []
            for position, values in enumerate(matrix[1:], start=1):
                raw = _row_dict(header, values)
                name = _clean(_first(raw, ["name"]))
                ticker = cls._clean_symbol(_first(raw, ["ticker"]))
                cusip = _clean(_first(raw, ["cusip"]))
                if not any([name, ticker, cusip]):
                    continue
                rows.append(
                    CanonicalHoldingRow(
                        symbol=ticker,
                        name=name,
                        cusip=cusip if _looks_like_cusip(cusip) else None,
                        weight=_decimal(_first(raw, ["% of net assets"])),
                        shares=_decimal(_first(raw, ["shares"])),
                        market_value=_decimal(_first(raw, ["market value"])),
                        currency="USD",
                        holding_type="equity",
                        row_type="security",
                        source_row_id=str(position),
                        extra_data={
                            key: value
                            for key, value in raw.items()
                            if value not in (None, "")
                        },
                    )
                )
            if rows:
                best_rows = max(best_rows, rows, key=len)
        return best_rows

    @staticmethod
    def _html_table_to_matrix(table_html: str) -> list[list[str]]:
        matrix: list[list[str]] = []
        for row_html in re.findall(
            r"<tr\b[^>]*>(.*?)</tr>",
            table_html,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            cells = [
                _clean(html.unescape(re.sub(r"<[^>]+>", " ", cell))) or ""
                for cell in re.findall(
                    r"<t[dh]\b[^>]*>(.*?)</t[dh]>",
                    row_html,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            ]
            if any(cells):
                matrix.append(cells)
        return matrix

    @staticmethod
    def _clean_symbol(value: Any) -> str | None:
        text = _clean(value)
        if not text:
            return None
        normalized = text.strip().upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", normalized):
            return normalized
        return None


class TappAlphaHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch TappAlpha holdings from issuer product pages and linked Google CSV exports."""

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        route_resolution = "issuer_profile_metadata"
        if not resolved_source_url:
            resolved_source_url = await self._discover_source_url_from_product_page(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                identifiers=identifiers or {},
            )
            route_resolution = "issuer_product_page_google_holdings_csv"
        if not resolved_source_url:
            raise ValueError(f"TappAlpha product page did not expose holdings CSV for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_tapp_csv(response.text, symbol=normalized_symbol)
        if not rows:
            raise ValueError(f"TappAlpha holdings CSV did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": route_resolution,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="text/csv,*/*"),
            "Referer": "https://www.tappalphafunds.com/",
        }

    async def _discover_source_url_from_product_page(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None,
        identifiers: dict[str, str],
    ) -> str | None:
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if not product_page_url:
            return None
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_holdings_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        return self._discover_google_csv_export(response.text, base_url=str(response.url))

    @staticmethod
    def _discover_google_csv_export(raw_html: str, *, base_url: str) -> str | None:
        for match in re.finditer(
            r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>",
            raw_html,
            re.IGNORECASE | re.DOTALL,
        ):
            body_text = " ".join(re.sub(r"<[^>]+>", " ", match.group("body")).split())
            attrs = match.group("attrs")
            href_match = re.search(r'href=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if href_match is None:
                continue
            href = html.unescape(href_match.group(1))
            haystack = f"{body_text} {href}".lower()
            if "holdings" not in haystack or "docs.google.com/spreadsheets/export" not in href:
                continue
            parsed = urlparse(urljoin(base_url, href))
            if parsed.netloc.endswith("docs.google.com") and "/spreadsheets/export" in parsed.path:
                return urlunparse(parsed)
        return None

    @classmethod
    def _parse_tapp_csv(
        cls,
        raw_csv: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {"date", "account", "stock ticker", "security name"}.issubset(
                    {(_clean(cell) or "").lower() for cell in row}
                )
            ),
            None,
        )
        if header_index is None:
            return [], None
        header = table_rows[header_index]
        requested_symbol = symbol.strip().upper()
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for position, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            account = (_clean(_first(raw, ["account"])) or "").upper()
            if account and account != requested_symbol:
                continue
            row_date = cls._parse_tapp_date(_first(raw, ["date"]))
            if composition_date is None:
                composition_date = row_date
            raw_symbol = _clean(_first(raw, ["stock ticker", "stockticker", "ticker"]))
            name = _clean(_first(raw, ["security name", "securityname", "name"]))
            row_type, holding_type = cls._classify_holding(symbol=raw_symbol, name=name)
            cleaned_symbol = (
                cls._clean_symbol(raw_symbol)
                if holding_type not in {"cash", "swap"}
                else None
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=cleaned_symbol,
                    name=name,
                    cusip=(
                        _clean(_first(raw, ["cusip"]))
                        if _looks_like_cusip(_clean(_first(raw, ["cusip"])))
                        else None
                    ),
                    weight=_decimal(_first(raw, ["weightings", "weight", "% of net assets"])),
                    shares=_decimal(_first(raw, ["shares"])),
                    market_value=_decimal(_first(raw, ["market value", "marketvalue"])),
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(position),
                    extra_data={
                        key: value
                        for key, value in raw.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_tapp_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _clean_symbol(value: Any) -> str | None:
        text = _clean(value)
        if not text:
            return None
        normalized = text.strip().upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", normalized):
            return normalized
        return None

    @staticmethod
    def _classify_holding(*, symbol: str | None, name: str | None) -> tuple[str, str]:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if "CASH&OTHER" in text or "CASH & OTHER" in text or text == "CASH":
            return "cash", "cash"
        if "-TRS-" in text or " SWAP " in f" {text} ":
            return "security", "swap"
        if "FUND" in text:
            return "security", "fund"
        return "security", "equity"


class TuttleHoldingsAdapter(TappAlphaHoldingsAdapter):
    """Fetch Tuttle-managed ETF holdings from public product-page Google CSV exports."""

    PRODUCT_PAGE_URLS: dict[str, str] = {
        "BITK": "https://www.incomeblastetfs.com/etf/bitk",
        "DRMP": "https://www.incomeblastetfs.com/etf/drmp",
        "MAGO": "https://www.incomeblastetfs.com/etf/mago",
        "MEMY": "https://www.incomeblastetfs.com/etf/memy",
        "SPCI": "https://www.incomeblastetfs.com/etf/spci",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        return self.PRODUCT_PAGE_URLS.get(
            normalized_symbol,
            f"https://www.incomeblastetfs.com/etf/{normalized_symbol.lower()}",
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="text/csv,*/*"),
            "Referer": "https://www.incomeblastetfs.com/",
        }

    @staticmethod
    def _classify_holding(*, symbol: str | None, name: str | None) -> tuple[str, str]:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if "CASH&OTHER" in text or "CASH & OTHER" in text or text == "CASH":
            return "cash", "cash"
        if "TREASURY BILL" in text or re.fullmatch(r"91279[A-Z0-9]{4}", (symbol or "").strip().upper()):
            return "security", "fixed_income"
        if re.search(r"\b\d{6}[CP]\d{8}\b", text) or re.search(r"\b[CP]\s*$", text):
            return "security", "option"
        if "-TRS-" in text or " SWAP " in f" {text} ":
            return "security", "swap"
        if "FUND" in text:
            return "security", "fund"
        return "security", "equity"


class YorkvilleHoldingsAdapter(TappAlphaHoldingsAdapter):
    """Fetch Yorkville/Truth Social ETF holdings from public Google CSV exports."""

    PRODUCT_PAGE_URLS: dict[str, str] = {
        "TSES": "https://www.truthsocialfunds.com/etfs/tses",
        "TSIC": "https://www.truthsocialfunds.com/etfs/tsic",
        "TSNF": "https://www.truthsocialfunds.com/etfs/tsnf",
        "TSRS": "https://www.truthsocialfunds.com/etfs/tsrs",
        "TSSD": "https://www.truthsocialfunds.com/etfs/tssd",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        return self.PRODUCT_PAGE_URLS.get(
            normalized_symbol,
            f"https://www.truthsocialfunds.com/etfs/{normalized_symbol.lower()}",
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="text/csv,*/*"),
            "Referer": "https://www.truthsocialfunds.com/",
        }


class TrueSharesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch TrueShares holdings from ETF product pages and linked Google CSV exports."""

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return f"https://www.true-shares.com/etf/{symbol.strip().lower()}"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="text/csv,*/*"),
            "Referer": "https://www.true-shares.com/etfs",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        route_resolution = "issuer_profile_metadata"
        if not resolved_source_url:
            resolved_source_url = await self._discover_source_url_from_product_page(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                identifiers=identifiers or {},
            )
            route_resolution = "issuer_product_page_google_holdings_csv"
        if not resolved_source_url:
            raise ValueError(f"TrueShares product page did not expose holdings CSV for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_true_shares_csv(
            response.text,
            symbol=normalized_symbol,
        )
        if not rows:
            raise ValueError(f"TrueShares holdings CSV did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": route_resolution,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_daily_holdings",
                "snapshot_provenance": "issuer_native_google_sheet_csv",
            },
        )

    async def _discover_source_url_from_product_page(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None,
        identifiers: dict[str, str],
    ) -> str | None:
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if not product_page_url:
            return None
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        return TappAlphaHoldingsAdapter._discover_google_csv_export(
            response.text,
            base_url=str(response.url),
        )

    @classmethod
    def _parse_true_shares_csv(
        cls,
        raw_csv: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        reader = csv.DictReader(StringIO(raw_csv.strip()))
        requested_symbol = symbol.strip().upper()
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for position, raw in enumerate(reader, start=1):
            account = (_clean(_first(raw, ["Account"])) or "").upper()
            if account and account != requested_symbol:
                continue
            row_date = cls._parse_date(_first(raw, ["Date"]))
            if composition_date is None:
                composition_date = row_date

            raw_symbol = _clean(_first(raw, ["Stock Ticker", "StockTicker", "Ticker"]))
            name = _clean(_first(raw, ["Security Name", "SecurityName", "Name"]))
            row_type, holding_type = cls._classify_holding(symbol=raw_symbol, name=name)
            symbol_value = cls._clean_symbol(raw_symbol) if holding_type == "equity" else None
            cusip_value = _clean(_first(raw, ["CUSIP", "Cusip"]))
            cusip = cusip_value if _looks_like_cusip(cusip_value) else None

            if not any([symbol_value, name, cusip, _first(raw, ["Weightings"]), _first(raw, ["Market Value"])]):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value,
                    name=name,
                    cusip=cusip,
                    weight=_decimal_percent_points(_first(raw, ["Weightings", "Weight"])),
                    shares=_decimal(_first(raw, ["Shares"])),
                    market_value=_decimal(_first(raw, ["Market Value", "MarketValue"])),
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{requested_symbol}-{position}",
                    extra_data={
                        "source_symbol": raw_symbol,
                        "account": account,
                        "price": _clean(_first(raw, ["Price"])),
                        "net_assets": _clean(_first(raw, ["Net Assets", "NetAssets"])),
                        **{key: value for key, value in raw.items() if _clean(value) is not None},
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _clean_symbol(value: Any) -> str | None:
        text = _clean(value)
        if not text:
            return None
        normalized = text.strip().upper()
        if _looks_like_cusip(normalized):
            return None
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", normalized):
            return normalized
        return None

    @staticmethod
    def _classify_holding(*, symbol: str | None, name: str | None) -> tuple[str, str]:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if any(marker in text for marker in ("CASH", "MMDA", "MONEY MARKET", "SWEEP")):
            return "cash", "cash"
        if "TREASURY BILL" in text or "TREASURY NOTE" in text:
            return "security", "fixed_income"
        if any(marker in text for marker in ("RECV ", "PAYB ", "RECEIVABLE", "PAYABLE")):
            return "other", "derivative"
        if "FUND" in text or "ETF" in text:
            return "security", "fund"
        return "security", "equity"


class MainManagementHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **super().source_request_headers(source_url=source_url),
            "Referer": "https://www.mainmgtetfs.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        rows, composition_date = self._parse_main_management_csv(result.raw_text or "")
        result.rows = rows
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "route_resolution": "issuer_symbol_holdings_csv",
            "source_access": self.config.source_access,
            **(
                {
                    "composition_date": composition_date.isoformat(),
                    "as_of_date": composition_date.isoformat(),
                }
                if composition_date is not None
                else {}
            ),
        }
        return result

    @staticmethod
    def _parse_main_management_csv(raw_csv: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None
        composition_date = MainManagementHoldingsAdapter._extract_as_of_date(table_rows[:5])
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {cell.strip().lower() for cell in row}
                >= {"name", "security identifier", "symbol"}
            ),
            None,
        )
        if header_index is None:
            return [], composition_date
        header = table_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            raw_symbol = _clean(_first(raw, ["Symbol"]))
            symbol, exchange = MainManagementHoldingsAdapter._split_symbol(raw_symbol)
            name = _clean(_first(raw, ["Name"]))
            security_identifier = _clean(_first(raw, ["Security Identifier"]))
            holding_type = MainManagementHoldingsAdapter._holding_type(
                raw_symbol=raw_symbol,
                symbol=symbol,
                name=name,
                identifier=security_identifier,
            )
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=security_identifier if _looks_like_cusip(security_identifier) else None,
                    weight=_decimal_percent_points(_first(raw, ["Market Value %", "Net Assets %"])),
                    shares=_decimal(_first(raw, ["Shares Held"])),
                    market_value=_decimal(_first(raw, ["Market Value"])),
                    currency="USD" if row_type == "cash" else None,
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _extract_as_of_date(prefix_rows: list[list[Any]]) -> date | None:
        text = " ".join(str(cell) for row in prefix_rows for cell in row if cell is not None)
        match = re.search(r"as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _split_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
        text = _clean(raw_symbol)
        if not text:
            return None, None
        normalized = " ".join(text.split())
        if normalized.endswith(" US") and re.fullmatch(r"[A-Z0-9. -]+ US", normalized):
            return normalized[:-3].strip(), "US"
        return normalized, None

    @staticmethod
    def _holding_type(
        *,
        raw_symbol: str | None,
        symbol: str | None,
        name: str | None,
        identifier: str | None,
    ) -> str:
        text = " ".join(part.upper() for part in (raw_symbol, symbol, name, identifier) if part)
        if any(marker in text for marker in ("DOLLAR", "RECEIVABLE", "PAYABLE", "SWEEP")):
            return "cash"
        if re.search(r"\b\d{2}/\d{2}/\d{2,4}\s+[CP]\d", text) or re.search(
            r"\b\d{6}[CP]\d{8}\b",
            text,
        ):
            return "option"
        return "security"


class ProcureHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,*/*")
        headers["Referer"] = "https://procureetfs.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        composition_date = self._normalize_rows(result.rows)
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_format": "csv",
            "route_resolution": (
                result.legal_metadata or {}
            ).get("route_resolution", "issuer_product_page_discovery"),
            **(
                {
                    "composition_date": composition_date.isoformat(),
                    "as_of_date": composition_date.isoformat(),
                }
                if composition_date is not None
                else {}
            ),
        }
        return result

    @classmethod
    def _normalize_rows(cls, rows: list[CanonicalHoldingRow]) -> date | None:
        composition_date: date | None = None
        for row in rows:
            row_date = cls._parse_procure_date(row.extra_data.get("Date"))
            if composition_date is None and row_date is not None:
                composition_date = row_date
            symbol, exchange = cls._split_symbol(row.symbol)
            row.symbol = symbol
            row.exchange = row.exchange or exchange
            if row.cusip and not _looks_like_cusip(row.cusip):
                if re.fullmatch(r"[A-Z0-9]{6,7}", row.cusip.strip().upper()):
                    row.sedol = row.sedol or row.cusip.strip().upper()
                row.cusip = None
            if row.row_type == "cash":
                row.symbol = None
                row.holding_type = "cash"
        return composition_date

    @staticmethod
    def _parse_procure_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _split_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
        normalized = _clean(raw_symbol)
        if normalized is None:
            return None, None
        match = re.fullmatch(r"([A-Z0-9.=-]+)\s+([A-Z]{2})", normalized.upper())
        if match:
            return match.group(1), match.group(2)
        return normalized, None


class HorizonKineticsHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(
                accept=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                    "application/octet-stream,*/*"
                )
            ),
            "Referer": "https://horizonkinetics.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = source_url or self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not resolved_source_url:
            raise ValueError(f"{self.adapter_key} could not resolve a holdings source URL for {symbol}.")
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        workbook_rows = parse_xlsx_table(response.content)
        rows, composition_date = self._parse_horizon_workbook(workbook_rows)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=_table_to_text(workbook_rows),
            raw_json={"source_format": "xlsx", "workbook_rows": workbook_rows},
            source_url=resolved_source_url,
            source_identifier=issuer_product_id,
            legal_metadata={
                "source_access": self.config.source_access,
                "adapter_key": self.adapter_key,
                "source_format": "xlsx",
                "route_resolution": "issuer_symbol_holdings_xlsx",
                **(
                    {
                        "composition_date": composition_date.isoformat(),
                        "as_of_date": composition_date.isoformat(),
                    }
                    if composition_date is not None
                    else {}
                ),
            },
        )

    @staticmethod
    def _parse_horizon_workbook(
        workbook_rows: list[list[Any]],
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        if not workbook_rows:
            return [], None
        header_index = next(
            (
                index
                for index, row in enumerate(workbook_rows[:20])
                if {str(cell).strip().lower() for cell in row}
                >= {"data as of:", "% net assets", "name", "ticker", "cusip"}
            ),
            None,
        )
        if header_index is None:
            return [], None
        header = workbook_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, row in enumerate(workbook_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            row_date = HorizonKineticsHoldingsAdapter._parse_horizon_date(
                _first(raw, ["Data as of:"])
            )
            if composition_date is None:
                composition_date = row_date
            raw_symbol = _clean(_first(raw, ["Ticker"]))
            symbol, exchange = HorizonKineticsHoldingsAdapter._split_symbol(raw_symbol)
            name = _clean(_first(raw, ["Name"]))
            raw_identifier = _clean(_first(raw, ["CUSIP"]))
            holding_type = HorizonKineticsHoldingsAdapter._holding_type(
                symbol=symbol,
                name=name,
                identifier=raw_identifier,
            )
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=raw_identifier if _looks_like_cusip(raw_identifier) else None,
                    sedol=(
                        raw_identifier
                        if raw_identifier
                        and not _looks_like_cusip(raw_identifier)
                        and re.fullmatch(r"[A-Z0-9]{6,7}", raw_identifier)
                        else None
                    ),
                    weight=_decimal(_first(raw, ["% Net Assets"])),
                    shares=_decimal(_first(raw, ["Shares Held"])),
                    market_value=_decimal(_first(raw, ["Market Value"])),
                    currency=symbol if row_type == "cash" and symbol else None,
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_horizon_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _split_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
        text = _clean(raw_symbol)
        if not text:
            return None, None
        normalized = " ".join(text.split())
        match = re.fullmatch(r"([A-Z0-9. -]+)\s+([A-Z]{2})", normalized)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return normalized, None

    @staticmethod
    def _holding_type(
        *,
        symbol: str | None,
        name: str | None,
        identifier: str | None,
    ) -> str:
        text = " ".join(part.upper() for part in (symbol, name, identifier) if part)
        if "CASH" in text or "DOLLAR" in text or symbol in {"JPY", "CAD", "EUR", "USD"}:
            return "cash"
        return "equity"


class BnyMellonHoldingsAdapter(IssuerCsvHoldingsAdapter):
    PRODUCT_PAGE_URLS = {
        "BKAG": (
            "https://www.bny.com/investments/us/en/individual/products/etf/fund/"
            "bny-mellon-core-bond-etf.html"
        ),
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.PRODUCT_PAGE_URLS.get(symbol.strip().upper())

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if not source_url:
            if not product_page_url:
                raise ValueError(f"BNY Mellon needs a product page URL for {symbol}.")
            async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
                page_response = await client.get(
                    product_page_url,
                    headers=self.source_request_headers(source_url=product_page_url),
                    follow_redirects=True,
                )
            page_response.raise_for_status()
            source_url = _discover_holdings_download_url(product_page_url, page_response.text)
            if not source_url:
                raise ValueError(f"BNY Mellon product page did not expose holdings for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            workbook_response = await client.get(
                source_url,
                headers=self.source_request_headers(source_url=source_url),
                follow_redirects=True,
            )
        workbook_response.raise_for_status()
        _, workbook_rows = parse_holdings_xls(workbook_response.content)
        rows, composition_date = self._parse_bny_workbook(workbook_rows)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=_table_to_text(workbook_rows),
            raw_json={
                "source_format": "xls",
                "workbook_rows": workbook_rows,
            },
            source_url=source_url,
            source_identifier=issuer_product_id,
            legal_metadata={
                "source_access": self.config.source_access,
                "adapter_key": self.adapter_key,
                "source_provider": self.source_provider,
                "source_format": "xls",
                "route_resolution": "issuer_product_page_daily_holdings_xls",
                **(
                    {"product_page_url": product_page_url}
                    if product_page_url is not None
                    else {}
                ),
                **(
                    {"composition_date": composition_date.isoformat()}
                    if composition_date is not None
                    else {}
                ),
            },
        )

    @staticmethod
    def _parse_bny_workbook(table_rows: list[list[Any]]) -> tuple[list[CanonicalHoldingRow], date | None]:
        composition_date = BnyMellonHoldingsAdapter._extract_composition_date(table_rows)
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:40])
                if {str(cell).strip().lower() for cell in row}
                >= {"ticker", "cusip", "security description"}
            ),
            None,
        )
        if header_index is None:
            return [], composition_date
        header = table_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            if not any(_clean(cell) for cell in row):
                continue
            raw = _row_dict(header, row)
            symbol = _clean(_first(raw, ["Ticker"]))
            name = _clean(_first(raw, ["Security Description"]))
            cusip = _clean(_first(raw, ["CUSIP"]))
            weight = _decimal(_first(raw, ["Weight of Holdings"]))
            shares = _decimal(_first(raw, ["Shares/Par"]))
            market_value = _decimal(_first(raw, ["Market Value"]))
            if not any([symbol, name, cusip, weight, shares, market_value]):
                continue
            asset_class = _clean(_first(raw, ["Asset Class"]))
            holding_type = (asset_class or "security").strip().lower()
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    cusip=cusip,
                    weight=weight,
                    shares=shares,
                    market_value=market_value,
                    holding_type=holding_type,
                    row_type="security",
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _extract_composition_date(table_rows: list[list[Any]]) -> date | None:
        for row in table_rows[:10]:
            text = " ".join(str(cell) for cell in row if _clean(cell))
            match = re.search(r"As of\s+(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
            if not match:
                continue
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d").date()
            except ValueError:
                return None
        return None


class HarborHoldingsAdapter(IssuerCsvHoldingsAdapter):
    PRODUCT_PATHS = {
        "WINN": "/etf/winn/",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        path = self.PRODUCT_PATHS.get(symbol.strip().upper())
        return urljoin("https://www.harborcapital.com", path) if path else None

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if not product_page_url:
            return None
        path = urlparse(product_page_url).path.strip("/")
        if not path:
            return None
        return f"https://www.harborcapital.com/page-data/{path}/page-data.json"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        source_url = source_url or self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if not source_url:
            raise ValueError(f"Harbor needs a product page-data route for {symbol}.")
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                source_url,
                headers=self.source_request_headers(source_url=source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        rows, composition_date = self._parse_page_data(payload)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=payload,
            source_url=source_url,
            source_identifier=issuer_product_id,
            legal_metadata={
                "source_access": self.config.source_access,
                "adapter_key": self.adapter_key,
                "source_provider": self.source_provider,
                "source_format": "json",
                "route_resolution": "issuer_gatsby_page_data_full_holdings",
                **(
                    {"composition_date": composition_date.isoformat()}
                    if composition_date is not None
                    else {}
                ),
            },
        )

    @staticmethod
    def _parse_page_data(payload: dict[str, Any]) -> tuple[list[CanonicalHoldingRow], date | None]:
        sections = (
            payload.get("result", {})
            .get("data", {})
            .get("contentstackProductV2", {})
            .get("product_tabs", [])
        )
        holdings: list[dict[str, Any]] = []
        for tab in sections if isinstance(sections, list) else []:
            if not isinstance(tab, dict):
                continue
            data_section = tab.get("data_section")
            if not isinstance(data_section, dict):
                continue
            data_sections = data_section.get("section", [])
            for section in data_sections if isinstance(data_sections, list) else []:
                if not isinstance(section, dict):
                    continue
                references = section.get("api_reference", [])
                for reference in references if isinstance(references, list) else []:
                    if not isinstance(reference, dict):
                        continue
                    candidate = reference.get("data", {}).get("fullHoldings")
                    if isinstance(candidate, list) and candidate:
                        holdings = [item for item in candidate if isinstance(item, dict)]
                        break
                if holdings:
                    break
            if holdings:
                break

        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(holdings, start=1):
            row_date = HarborHoldingsAdapter._parse_harbor_date(
                item.get("calendar", {}).get("date")
                if isinstance(item.get("calendar"), dict)
                else None
            )
            if composition_date is None:
                composition_date = row_date
            rows.append(
                CanonicalHoldingRow(
                    symbol=_clean(item.get("ticker")),
                    name=_clean(item.get("securityName")),
                    cusip=_clean(item.get("cusip")),
                    sedol=_clean(item.get("sedol")),
                    weight=_decimal(item.get("weight")),
                    shares=_decimal(item.get("shares")),
                    market_value=_decimal(item.get("marketValue")),
                    holding_type=(_clean(item.get("assetGroup")) or "security").lower(),
                    row_type="security",
                    source_row_id=str(item.get("key") or index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "") and key != "calendar"
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_harbor_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None


class InspireHoldingsAdapter(IssuerCsvHoldingsAdapter):
    API_KEY = "263752e3-765e-4dab-aa89-ab3d6a49d7dc"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return {
            **_holdings_request_headers(accept="application/json,text/plain,*/*"),
            "Referer": "https://www.inspireetf.com/",
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        if source_url:
            return await self._fetch_source_url(
                symbol=symbol,
                source_url=source_url,
                issuer_product_id=issuer_product_id,
            )

        date_candidates = self._quarter_end_date_candidates(
            explicit_date=_identifier(identifiers or {}, "holdings_date", "as_of_date"),
        )
        last_error: Exception | None = None
        for holdings_date in date_candidates:
            candidate_url = self._source_url(symbol=symbol, holdings_date=holdings_date)
            try:
                result = await self._fetch_source_url(
                    symbol=symbol,
                    source_url=candidate_url,
                    issuer_product_id=issuer_product_id or holdings_date,
                )
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                continue
            if result.rows:
                return result
        if last_error is not None:
            raise last_error
        raise ValueError(f"Inspire did not return holdings for {symbol}.")

    async def _fetch_source_url(
        self,
        *,
        symbol: str,
        source_url: str,
        issuer_product_id: str | None,
    ) -> HoldingsFetchResult:
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                source_url,
                headers=self.source_request_headers(source_url=source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise ValueError(str(payload["error"]))
        rows, composition_date = self._parse_inspire_payload(payload, symbol=symbol)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={"source_format": "json", "payload": payload},
            source_url=source_url,
            source_identifier=issuer_product_id,
            legal_metadata={
                "source_access": self.config.source_access,
                "adapter_key": self.adapter_key,
                "source_provider": self.source_provider,
                "source_format": "json",
                "route_resolution": "issuer_page_public_quarterly_holdings_api",
                "source_frequency": "quarterly",
                **(
                    {
                        "composition_date": composition_date.isoformat(),
                        "as_of_date": composition_date.isoformat(),
                    }
                    if composition_date is not None
                    else {}
                ),
            },
        )

    @classmethod
    def _source_url(cls, *, symbol: str, holdings_date: str) -> str:
        query = urlencode(
            {
                "apikey": cls.API_KEY,
                "function": "holdings",
                "format": "json",
                "ticker": symbol.strip().upper(),
                "date": holdings_date,
            }
        )
        return f"https://data.etflogic.io/prod?{query}"

    @staticmethod
    def _quarter_end_date_candidates(explicit_date: str | None = None) -> list[str]:
        if explicit_date:
            normalized = re.sub(r"[^0-9]", "", explicit_date)
            return [normalized] if len(normalized) == 8 else [explicit_date]
        candidates: list[str] = []
        cursor = date.today().replace(day=1)
        for _ in range(30):
            cursor = (cursor - timedelta(days=1)).replace(day=1)
            year = cursor.year
            month = cursor.month
            if month in {2, 8}:
                last_day = (date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1)).day
                candidates.append(f"{year}{month:02d}{last_day:02d}")
        return candidates

    @staticmethod
    def _parse_inspire_payload(
        payload: Any,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        if not isinstance(payload, list):
            return [], None
        requested_symbol = symbol.strip().upper()
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                continue
            etf_symbol = (_clean(item.get("etfticker")) or "").upper()
            if etf_symbol and etf_symbol != requested_symbol:
                continue
            row_date = InspireHoldingsAdapter._parse_inspire_date(item.get("as_of_date"))
            if composition_date is None:
                composition_date = row_date
            raw_ticker = _clean(item.get("ticker"))
            tradable_symbol = (
                raw_ticker
                if raw_ticker and re.fullmatch(r"[A-Z0-9.=-]{1,12}", raw_ticker.strip().upper())
                else None
            )
            name = _clean(item.get("security_name")) or raw_ticker
            holding_type = InspireHoldingsAdapter._holding_type(
                symbol=tradable_symbol,
                name=" ".join(part for part in (name, raw_ticker) if part),
                cusip=_clean(item.get("cusip")),
            )
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=tradable_symbol if row_type != "cash" else None,
                    name=name,
                    cusip=_clean(item.get("cusip")),
                    isin=_clean(item.get("isin")),
                    weight=_decimal(item.get("weight")),
                    shares=_decimal(item.get("shares_held")),
                    market_value=_decimal(item.get("market_value")),
                    currency=_clean(item.get("currency")),
                    country=_clean(item.get("country")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(item.get("security_number") or index),
                    extra_data={key: value for key, value in item.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_inspire_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    @staticmethod
    def _holding_type(*, symbol: str | None, name: str | None, cusip: str | None) -> str:
        text = " ".join(part.upper() for part in (symbol, name, cusip) if part)
        if "CASH" in text or "DOLLAR" in text:
            return "cash"
        if re.search(r"\b\d+(\.\d+)?\s+\d{2}/\d{2}/\d{2,4}\b", text):
            return "fixed_income"
        return "equity"


class BitwiseHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return f"https://{normalized_symbol}etf.com/"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = self._extract_next_data(response.text)
        rows, as_of_date = self._parse_bitwise_next_data(payload)
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=payload,
            source_url=product_page_url,
            source_identifier=symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "next_json",
                "route_resolution": "issuer_product_page_embedded_json",
                "composition_date": as_of_date,
                "as_of_date": as_of_date,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _extract_next_data(raw_html: str) -> dict[str, Any]:
        match = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            raw_html,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return {}
        try:
            payload = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _parse_bitwise_next_data(
        self,
        payload: dict[str, Any],
    ) -> tuple[list[CanonicalHoldingRow], str | None]:
        fund_data = (
            payload.get("props", {})
            .get("pageProps", {})
            .get("fundData", {})
            .get("data", {})
        )
        holdings = fund_data.get("holdings") if isinstance(fund_data, dict) else None
        basket = holdings.get("basket") if isinstance(holdings, dict) else None
        if not isinstance(basket, list):
            return [], None
        rows: list[CanonicalHoldingRow] = []
        for index, item in enumerate(basket, start=1):
            if not isinstance(item, dict):
                continue
            symbol_value = _clean(item.get("ticker"))
            name = _clean(item.get("companyName") or item.get("name"))
            if not any([symbol_value, name]):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value,
                    name=name,
                    weight=_decimal(item.get("weight")),
                    shares=_decimal(item.get("shares")),
                    market_value=_decimal(item.get("marketValue")),
                    holding_type="crypto" if (name or "").upper() == "BITCOIN" else "security",
                    row_type="security",
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, _clean(holdings.get("asOfDate")) if isinstance(holdings, dict) else None


class GrayscaleHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Grayscale ETF product pages with embedded holdings payloads."""

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        holdings, product_data = self._extract_embedded_holdings(response.text)
        rows = self._parse_embedded_holdings(holdings, product_data=product_data)
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        as_of_date = _clean(
            product_data.get("pricingDataDate")
            if isinstance(product_data, dict)
            else None
        ) or _clean(rows[0].extra_data.get("date") if rows else None)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={"holdingsData": holdings, "productData": product_data},
            source_url=str(getattr(response, "url", product_page_url)),
            source_identifier=symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "embedded_json",
                "route_resolution": "issuer_product_page_embedded_json",
                "composition_date": as_of_date,
                "as_of_date": as_of_date,
                "product_name": product_data.get("name") if isinstance(product_data, dict) else None,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _decode_json_after_key(raw_html: str, key: str) -> Any:
        marker = f'"{key}":'
        marker_index = raw_html.find(marker)
        escaped = False
        if marker_index < 0:
            marker = rf'\"{key}\":'
            marker_index = raw_html.find(marker)
            escaped = marker_index >= 0
        if marker_index < 0:
            return None
        value_start = marker_index + len(marker)
        source = raw_html[value_start:]
        if escaped:
            source = source.replace(r"\/", "/").replace(r"\"", '"')
        try:
            value, _ = json.JSONDecoder().raw_decode(source)
        except json.JSONDecodeError:
            return None
        return value

    def _extract_embedded_holdings(self, raw_html: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        holdings = self._decode_json_after_key(raw_html, "holdingsData")
        product_data = self._decode_json_after_key(raw_html, "productData")
        return (
            holdings if isinstance(holdings, list) else [],
            product_data if isinstance(product_data, dict) else {},
        )

    def _parse_embedded_holdings(
        self,
        holdings: list[dict[str, Any]],
        *,
        product_data: dict[str, Any],
    ) -> list[CanonicalHoldingRow]:
        rows: list[CanonicalHoldingRow] = []
        for index, item in enumerate(holdings, start=1):
            if not isinstance(item, dict):
                continue
            symbol_value = _clean(item.get("symbol"))
            name = _clean(item.get("name"))
            if not any([symbol_value, name, item.get("cusip")]):
                continue
            row_type = "crypto" if symbol_value in {"BTC", "ETH", "SOL", "XRP", "DOGE"} else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value,
                    name=name,
                    cusip=_clean(item.get("cusip")),
                    weight=_decimal(item.get("weight")),
                    shares=_decimal(item.get("sharesHeld")),
                    market_value=_decimal(item.get("marketValue")),
                    currency="USD",
                    holding_type=row_type,
                    row_type=row_type,
                    source_row_id=str(item.get("id") or index),
                    extra_data={
                        "asset_per_share": item.get("assetPerShare"),
                        "closing_price": item.get("closingPrice"),
                        "date": item.get("date"),
                        "fund_ticker": product_data.get("ticker"),
                        "fund_cusip": product_data.get("cusip"),
                        "fund_isin": product_data.get("isin"),
                        "total_asset_in_trust": product_data.get("totalAssetInTrust"),
                        **{
                            key: value
                            for key, value in item.items()
                            if value not in (None, "")
                        },
                    },
                )
            )
        return rows


class GoldmanSachsHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Goldman Sachs ETF holdings from public GSAM XLSX workbooks."""

    holdings_workbook_ids_by_symbol = {
        "GVIP": "Goldman Sachs Hedge Industry VIP ETF_9532",
    }

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        resolved = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if resolved:
            return resolved
        workbook_id = issuer_product_id or self.holdings_workbook_ids_by_symbol.get(
            symbol.strip().upper()
        )
        if not workbook_id:
            return None
        encoded_id = workbook_id.strip().replace(" ", "%20")
        return f"https://www.gsam.com/content/dam/gsam/xls/us/en/etf/{encoded_id}.xlsx"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        return _holdings_request_headers(
            accept=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                "application/vnd.ms-excel,*/*"
            )
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not source_url:
            raise ValueError(f"Goldman Sachs holdings workbook route is unavailable for {symbol}.")
        async with httpx.AsyncClient(
            timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                source_url,
                headers=self.source_request_headers(source_url=source_url),
            )
        response.raise_for_status()
        workbook_rows = parse_xlsx_table(response.content)
        rows, composition_date = self._parse_workbook_rows(workbook_rows)
        if not rows:
            raise ValueError(f"Goldman Sachs holdings workbook did not expose rows for {symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=_table_to_text(workbook_rows),
            raw_json={"source_format": "xlsx", "workbook_rows": workbook_rows},
            source_url=str(getattr(response, "url", source_url)),
            source_identifier=symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "xlsx",
                "route_resolution": "issuer_symbol_holdings_xlsx",
                "terms_note": self.config.terms_note,
                **(
                    {
                        "composition_date": composition_date.isoformat(),
                        "as_of_date": composition_date.isoformat(),
                    }
                    if composition_date is not None
                    else {}
                ),
            },
        )

    @classmethod
    def _parse_workbook_rows(
        cls,
        workbook_rows: list[list[Any]],
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        header_index = next(
            (
                index
                for index, row in enumerate(workbook_rows[:10])
                if {
                    "date",
                    "ticker",
                    "cusip",
                    "isin",
                    "sedol",
                    "description",
                    "market value",
                    "number of shares",
                    "% weighting",
                }
                <= {str(cell).strip().lower() for cell in row}
            ),
            -1,
        )
        if header_index < 0:
            return [], None

        header = [str(cell).strip() for cell in workbook_rows[header_index]]
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for position, raw_row in enumerate(workbook_rows[header_index + 1 :], start=1):
            row = _row_dict(header, raw_row)
            name = _clean(row.get("Description"))
            symbol = _clean(row.get("Ticker"))
            if not any([name, symbol, row.get("CUSIP"), row.get("ISIN")]):
                continue
            if composition_date is None:
                composition_date = cls._parse_excel_serial_date(row.get("Date"))
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    cusip=_clean(row.get("Cusip") or row.get("CUSIP")),
                    isin=_clean(row.get("ISIN")),
                    sedol=_clean(row.get("Sedol") or row.get("SEDOL")),
                    weight=_decimal_percent_points(row.get("% Weighting")),
                    shares=_decimal(row.get("Number of Shares")),
                    market_value=_decimal(row.get("Market Value")),
                    currency="USD",
                    holding_type="equity",
                    row_type="security",
                    source_row_id=f"goldman-sachs-{position}",
                    extra_data={
                        key: value
                        for key, value in row.items()
                        if key is not None and _clean(value) is not None
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_excel_serial_date(value: Any) -> date | None:
        parsed = _decimal(value)
        if parsed is None:
            return None
        try:
            return (datetime(1899, 12, 30) + timedelta(days=int(parsed))).date()
        except (OverflowError, ValueError):
            return None


class GmoHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch GMO ETF holdings workbooks from GMO's public document paths."""

    holdings_slugs_by_symbol = {
        "GMOC": "ultra-short-income-etf",
        "INVG": "systematic-investment-grade-credit-etf",
        "QLTY": "u.s.-quality-etf",
    }
    product_pages_by_symbol = {
        "GMOC": (
            "https://www.gmo.com/americas/product-index-page/fixed-income/"
            "ultra-short-income-strategy/ultra-short-income-etf/"
        ),
        "INVG": (
            "https://www.gmo.com/americas/product-index-page/fixed-income/"
            "systematic-investment-grade-credit-strategy/"
            "systematic-investment-grade-credit-etf/"
        ),
        "QLTY": (
            "https://www.gmo.com/americas/product-index-page/equities/"
            "u.s.-quality-strategy/gmo-u.s.-quality-etf"
        ),
    }

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        resolved = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if resolved:
            return resolved
        slug = self._holdings_slug(symbol=symbol, issuer_product_id=issuer_product_id)
        if not slug:
            return None
        return (
            "https://www.gmo.com/globalassets/documents---manually-loaded/"
            f"documents/{slug}_etf_holdings/"
        )

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        resolved = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if resolved:
            return resolved
        return self.product_pages_by_symbol.get(symbol.strip().upper())

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        referer = "https://www.gmo.com/americas/etf-documents/"
        for symbol, slug in self.holdings_slugs_by_symbol.items():
            if f"/{slug}_etf_holdings" in source_url:
                referer = self.product_pages_by_symbol.get(symbol, referer)
                break
        return {
            **_holdings_request_headers(
                accept=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                    "application/octet-stream,*/*"
                )
            ),
            "Referer": referer,
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        composition_date = self._extract_composition_date(result.raw_json)
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_access": self.config.source_access,
            "source_provider": self.source_provider,
            "adapter_key": self.adapter_key,
            "source_format": "xlsx",
            "route_resolution": "issuer_symbol_holdings_xlsx",
            "terms_note": self.config.terms_note,
            **(
                {
                    "composition_date": composition_date.isoformat(),
                    "as_of_date": composition_date.isoformat(),
                }
                if composition_date is not None
                else {}
            ),
        }
        return result

    def _holdings_slug(self, *, symbol: str, issuer_product_id: str | None) -> str | None:
        if issuer_product_id:
            return issuer_product_id.strip().strip("/")
        return self.holdings_slugs_by_symbol.get(symbol.strip().upper())

    @staticmethod
    def _extract_composition_date(raw_json: dict[str, Any] | None) -> date | None:
        if not isinstance(raw_json, dict):
            return None
        workbook_rows = raw_json.get("workbook_rows")
        if not isinstance(workbook_rows, list):
            return None
        for row in workbook_rows[:10]:
            if not isinstance(row, list):
                continue
            text = " ".join(_clean(cell) or "" for cell in row)
            match = re.search(r"\bAs\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
            if not match:
                continue
            try:
                return datetime.strptime(match.group(1), "%m/%d/%Y").date()
            except ValueError:
                return None
        return None


class HashdexHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Hashdex public ETF holdings workbooks."""

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        route_resolution = "issuer_profile_metadata"
        if not resolved_source_url:
            resolved_source_url = await self._discover_source_url_from_product_page(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                identifiers=identifiers or {},
            )
            route_resolution = "issuer_product_page_discovery"
        if not resolved_source_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=_holdings_request_headers(
                    accept=(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                        "application/octet-stream,*/*"
                    )
                ),
                follow_redirects=True,
            )
        response.raise_for_status()
        workbook_rows = parse_xlsx_table(response.content)
        rows, composition_date = self._parse_hashdex_workbook(workbook_rows)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=_table_to_text(workbook_rows),
            raw_json={"source_format": "xlsx", "workbook_rows": workbook_rows},
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "xlsx",
                "route_resolution": route_resolution,
                "composition_date": composition_date,
                "as_of_date": composition_date,
                "terms_note": self.config.terms_note,
            },
        )

    def _parse_hashdex_workbook(
        self,
        workbook_rows: list[list[Any]],
    ) -> tuple[list[CanonicalHoldingRow], str | None]:
        composition_date = None
        header_index = None
        for index, row in enumerate(workbook_rows[:20]):
            first = _clean(row[0] if row else None)
            if first and first.lower() == "reference date" and len(row) > 1:
                composition_date = self._parse_hashdex_date(row[1])
            columns = [(_clean(value) or "").lower() for value in row]
            if columns[:4] == ["name", "shares", "price", "weight"]:
                header_index = index
                break
        if header_index is None:
            return [], composition_date

        rows: list[CanonicalHoldingRow] = []
        for position, row in enumerate(workbook_rows[header_index + 1 :], start=1):
            name = _clean(row[0] if len(row) > 0 else None)
            if not name:
                continue
            shares = _decimal(row[1] if len(row) > 1 else None)
            price = _decimal(row[2] if len(row) > 2 else None)
            weight = _decimal(row[3] if len(row) > 3 else None)
            market_value = shares * price if shares is not None and price is not None else None
            name_lower = name.lower()
            is_cash = "cash" in name_lower
            symbol = "BTC" if name_lower == "bitcoin" else None
            holding_type = "cash" if is_cash else "crypto" if symbol == "BTC" else "fund"
            rows.append(
                CanonicalHoldingRow(
                    symbol=None if is_cash else symbol,
                    name=name,
                    weight=weight,
                    shares=shares,
                    market_value=market_value,
                    currency="USD",
                    holding_type=holding_type,
                    row_type="cash" if is_cash else holding_type,
                    source_row_id=str(position),
                    extra_data={
                        "price": row[2] if len(row) > 2 else None,
                        "reference_date": composition_date,
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_hashdex_date(value: Any) -> str | None:
        text = _clean(value)
        if not text:
            return None
        for fmt in ("%m-%d-%Y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        return text


class CoinSharesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch CoinShares/Valkyrie holdings from the public widget API."""

    api_key = "094DA478-140C-4E3E-B394-7A19BBE8326B"
    widgets_url = "https://www-api.coinshares.com/api/v2/Widgets"

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return f"https://coinshares.com/us/etf/{normalized_symbol}/"

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return None
        return (
            f"{self.widgets_url}?"
            f"{urlencode({'ApiKey': self.api_key, 'names': f'VALKYRIE_HOLDINGS_{normalized_symbol}'})}"
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        headers = _holdings_request_headers(accept="application/json,*/*")
        if product_page_url:
            headers["Referer"] = product_page_url
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=headers,
                follow_redirects=True,
            )
        response.raise_for_status()
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = []
        rows, composition_date = self._parse_widgets_payload(payload)
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={"widgets": payload},
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "coinshares_widgets_json",
                "route_resolution": "issuer_public_widgets_api",
                "composition_date": composition_date,
                "as_of_date": composition_date,
                "product_page_url": product_page_url,
                "terms_note": self.config.terms_note,
            },
        )

    def _parse_widgets_payload(
        self,
        payload: Any,
    ) -> tuple[list[CanonicalHoldingRow], str | None]:
        widgets = payload if isinstance(payload, list) else []
        rows: list[CanonicalHoldingRow] = []
        composition_date = None
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            sections = widget.get("sections")
            if not isinstance(sections, list):
                continue
            for section in sections:
                if not isinstance(section, dict):
                    continue
                item = self._meta_to_dict(section.get("meta"))
                symbol_value = _clean(item.get("stockticker"))
                name = _clean(item.get("securityname"))
                cusip = _clean(item.get("cusip"))
                if not any([symbol_value, name, cusip]):
                    continue
                date_value = self._parse_composition_date(item.get("date"))
                composition_date = composition_date or date_value
                holding_type = self._holding_type(symbol=symbol_value, name=name, cusip=cusip)
                rows.append(
                    CanonicalHoldingRow(
                        symbol=None if holding_type == "cash" else symbol_value,
                        name=name,
                        cusip=None if holding_type == "cash" else cusip,
                        weight=_decimal(item.get("weightpercentage")),
                        shares=_decimal(item.get("shares")),
                        market_value=_decimal(item.get("marketvalue")),
                        currency="USD",
                        holding_type=holding_type,
                        row_type="cash" if holding_type == "cash" else "security",
                        source_row_id=_clean(section.get("key")) or str(len(rows) + 1),
                        extra_data={
                            "creation_units": _decimal(item.get("creationunits")),
                            "net_assets": _decimal(item.get("netassets")),
                            "price": _decimal(item.get("price")),
                            "shares_outstanding": _decimal(item.get("sharesoutstanding")),
                            "date": date_value,
                            "widget_code": widget.get("code"),
                            "source": section.get("source"),
                            "updated": section.get("updated"),
                            **{
                                key: value
                                for key, value in item.items()
                                if value not in (None, "")
                            },
                        },
                    )
                )
        return rows, composition_date

    @staticmethod
    def _meta_to_dict(meta: Any) -> dict[str, Any]:
        if not isinstance(meta, list):
            return {}
        values: dict[str, Any] = {}
        for item in meta:
            if not isinstance(item, dict):
                continue
            key = _clean(item.get("key"))
            if not key:
                continue
            values[key] = item.get("value")
        return values

    @staticmethod
    def _parse_composition_date(value: Any) -> str | None:
        text = _clean(value)
        if not text:
            return None
        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        return text

    @staticmethod
    def _holding_type(*, symbol: str | None, name: str | None, cusip: str | None) -> str:
        text = " ".join(part.upper() for part in (symbol, name, cusip) if part)
        if "CASH" in text or "OTHER" in text:
            return "cash"
        return "equity"


class KurvHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Kurv public holdings CSV files without trusting option IDs as CUSIPs."""

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=_holdings_request_headers(accept="text/csv,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows = self._parse_kurv_csv(response.text)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_public_holdings_csv",
                "terms_note": self.config.terms_note,
            },
        )

    def _parse_kurv_csv(self, raw_text: str) -> list[CanonicalHoldingRow]:
        reader = csv.DictReader(StringIO(raw_text))
        rows: list[CanonicalHoldingRow] = []
        for position, item in enumerate(reader, start=1):
            symbol_value = _clean(item.get("Ticker"))
            description = _clean(item.get("Description"))
            if not any([symbol_value, description]):
                continue
            cusip_candidate = _clean(item.get("CUSIP"))
            row_type = "cash" if (description or "").lower() == "cash" else "security"
            holding_type = "cash" if row_type == "cash" else (
                "option"
                if re.search(r"\b\d{2}/\d{2}/\d{4}\b.+\b[CP]\b", description or "")
                else "equity"
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=None if row_type == "cash" else symbol_value,
                    name=description,
                    cusip=cusip_candidate if _looks_like_cusip(cusip_candidate) else None,
                    weight=_decimal(item.get("% of fund")),
                    shares=_decimal(item.get("Quantity")),
                    market_value=_decimal(item.get("Market Value")),
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(position),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows


class InnovatorHoldingsAdapter(IssuerCsvHoldingsAdapter):
    aggregate_holdings_url = "https://www.innovatoretfs.com/etf/xt_holdings.csv"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        resolved_source_url = source_url or self.aggregate_holdings_url
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_innovator_csv(
            response.text,
            account_symbol=normalized_symbol,
        )
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=resolved_source_url,
            source_identifier=normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_aggregate_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "account_symbol": normalized_symbol,
                "terms_note": self.config.terms_note,
            },
        )

    def _parse_innovator_csv(
        self,
        raw_csv: str,
        *,
        account_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        reader = csv.DictReader(StringIO(raw_csv.strip()))
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(reader, start=1):
            if (item.get("Account") or "").strip().upper() != account_symbol:
                continue
            if composition_date is None:
                composition_date = self._parse_innovator_date(item.get("Date"))
            raw_symbol = _clean(item.get("StockTicker"))
            name = _clean(item.get("SecurityName"))
            holding_type = (
                "cash"
                if (raw_symbol or "").upper() in {"CASH", "USD"} or (item.get("MoneyMarketFlag") or "")
                else "security"
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=raw_symbol if holding_type != "cash" else None,
                    name=name,
                    cusip=_clean(item.get("CUSIP")),
                    weight=_decimal(item.get("Weightings")),
                    shares=_decimal(item.get("Shares")),
                    market_value=_decimal(item.get("MarketValue")),
                    holding_type=holding_type,
                    row_type="cash" if holding_type == "cash" else "security",
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_innovator_date(value: str | None) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None


class CambriaHoldingsAdapter(InnovatorHoldingsAdapter):
    aggregate_holdings_url = (
        "https://www.cambriafunds.com/assets/data/FilepointCambria.40C1.C1_ETF_Holdings.csv"
    )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,*/*")
        headers["Referer"] = "https://www.cambriafunds.com/"
        return headers


class BeyondInvestingHoldingsAdapter(InnovatorHoldingsAdapter):
    aggregate_holdings_url = (
        "https://www.veganetf-sftp.com/csvs/BeyondAdvisorsWEB.40XZ.XZ_Holdings.csv"
    )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,*/*")
        headers["Referer"] = "https://veganetf.com/"
        return headers


class MotleyFoolHoldingsAdapter(InnovatorHoldingsAdapter):
    """Parse Motley Fool Asset Management FilePoint holdings by ETF account symbol."""

    aggregate_holdings_url = (
        "https://etfs.fooletfs.com/assets/data/FilepointMotleyF.40MU.FW_Holdings.csv"
    )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,*/*")
        headers["Referer"] = "https://etfs.fooletfs.com/"
        return headers


class BaronHoldingsAdapter(IssuerCsvHoldingsAdapter):
    product_index_url = "https://www.baroncapitalgroup.com/"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        page_or_csv_url = source_url or self.product_index_url
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if self._is_csv_url(page_or_csv_url):
                holdings_url = page_or_csv_url
            else:
                page_url, page_text = await self._fetch_product_page(
                    client,
                    page_or_csv_url,
                )
                holdings_url = self._discover_holdings_url(
                    page_text,
                    symbol=normalized_symbol,
                    base_url=page_url,
                )
            if not holdings_url:
                raise ValueError(f"Baron product pages did not expose holdings CSV for {symbol}.")
            holdings_url, response_text = await self._fetch_holdings_csv(client, holdings_url)
        rows = self._parse_baron_csv(response_text)
        if not rows:
            raise ValueError(f"Baron holdings CSV did not expose rows for {symbol}.")
        composition_date = self._composition_date_from_url(holdings_url)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response_text,
            raw_json=None,
            source_url=holdings_url,
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_product_page_linked_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,*/*")
        headers["Referer"] = self.product_index_url
        return headers

    async def _fetch_product_page(
        self,
        client: httpx.AsyncClient,
        source_url: str,
    ) -> tuple[str, str]:
        headers = _issuer_page_request_headers(accept="text/html,*/*")
        try:
            response = await client.get(
                source_url,
                headers=headers,
                follow_redirects=True,
            )
            response.raise_for_status()
            return source_url, response.text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise

        def _request() -> requests.Response:
            return requests.get(
                source_url,
                headers=headers,
                allow_redirects=True,
                timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            )

        response = await asyncio.to_thread(_request)
        response.raise_for_status()
        return source_url, response.text

    async def _fetch_holdings_csv(
        self,
        client: httpx.AsyncClient,
        source_url: str,
    ) -> tuple[str, str]:
        headers = self.source_request_headers(source_url=source_url)
        try:
            response = await client.get(
                source_url,
                headers=headers,
                follow_redirects=True,
            )
            response.raise_for_status()
            return source_url, response.text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise

        def _request() -> requests.Response:
            return requests.get(
                source_url,
                headers=headers,
                allow_redirects=True,
                timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            )

        response = await asyncio.to_thread(_request)
        response.raise_for_status()
        return source_url, response.text

    @staticmethod
    def _is_csv_url(value: str) -> bool:
        return value.split("?", 1)[0].lower().endswith(".csv")

    @staticmethod
    def _discover_holdings_url(raw_html: str, *, symbol: str, base_url: str) -> str | None:
        candidates: list[tuple[date, str]] = []
        for pattern in (
            re.compile(
                rf"""(?P<url>https?://[^\s"'<>)]*{re.escape(symbol)}-HOLDINGS-(?P<date>\d{{8}})-0\.csv)""",
                re.IGNORECASE,
            ),
            re.compile(
                rf"""(?P<url>[^\s"'<>)]*{re.escape(symbol)}-HOLDINGS-(?P<date>\d{{8}})-0\.csv)""",
                re.IGNORECASE,
            ),
        ):
            for match in pattern.finditer(raw_html):
                parsed_date = BaronHoldingsAdapter._parse_compact_yyyymmdd(
                    match.group("date")
                )
                if parsed_date is None:
                    continue
                candidates.append((parsed_date, urljoin(base_url, match.group("url"))))
            if candidates:
                break
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    @staticmethod
    def _composition_date_from_url(source_url: str) -> date | None:
        match = re.search(r"-HOLDINGS-(\d{8})-0\.csv", source_url, flags=re.IGNORECASE)
        if not match:
            return None
        return BaronHoldingsAdapter._parse_compact_yyyymmdd(match.group(1))

    @staticmethod
    def _parse_compact_yyyymmdd(value: str) -> date | None:
        try:
            return datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            return None

    @staticmethod
    def _parse_baron_csv(raw_csv: str) -> list[CanonicalHoldingRow]:
        reader = csv.DictReader(StringIO(raw_csv.strip()))
        rows: list[CanonicalHoldingRow] = []
        for index, item in enumerate(reader, start=1):
            symbol = _clean(item.get("Ticker"))
            name = _clean(item.get("Holding"))
            if not symbol and not name:
                continue
            cash_like = (
                (symbol or "").strip().upper() in {"CASH", "USD", "US DOLLAR"}
                or "CASH" in (name or "").strip().upper()
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=None if cash_like else symbol,
                    name=name,
                    cusip=_clean(item.get("CUSIP")),
                    isin=_clean(item.get("ISIN")),
                    sedol=_clean(item.get("SEDOL")),
                    weight=_decimal(item.get("Weight (%)")),
                    shares=_decimal(item.get("Quantity")),
                    market_value=_decimal(item.get("Market Value ($)")),
                    currency=_clean(item.get("Currency Code")),
                    holding_type="cash" if cash_like else "equity",
                    row_type="cash" if cash_like else "security",
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows


class BrandesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Brandes ETF holdings from the public iframe data CSV."""

    holdings_url = "https://etfs.brandes.com/assets/data/6c11_Report.csv"
    product_page_template = "https://www.brandes.com/etfs/fund-detail/{slug}"
    fund_slugs = {
        "BINV": "brandes-international-etf",
        "BSMC": "brandes-us-small-mid-cap-value-etf",
        "BUSA": "brandes-us-value-etf",
    }

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        return explicit or self.holdings_url

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        resolved_url = self.resolve_source_url(
            symbol=normalized_symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_url:
            raise ValueError(f"Brandes did not expose a holdings CSV route for {symbol}.")
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_url,
                headers=self.source_request_headers(source_url=resolved_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_brandes_csv(
            response.text,
            symbol=normalized_symbol,
        )
        if not rows:
            raise ValueError(f"Brandes holdings CSV did not expose rows for {symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=resolved_url,
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_iframe_public_holdings_csv",
                "product_page_url": self._product_page_url(normalized_symbol),
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,*/*")
        headers["Referer"] = "https://etfs.brandes.com/busa"
        return headers

    @classmethod
    def _product_page_url(cls, symbol: str) -> str | None:
        slug = cls.fund_slugs.get(symbol)
        if not slug:
            return None
        return cls.product_page_template.format(slug=slug)

    @classmethod
    def _parse_brandes_csv(
        cls,
        raw_csv: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        reader = csv.DictReader(StringIO(raw_csv.strip()))
        rows: list[CanonicalHoldingRow] = []
        composition_dates: list[date] = []
        expected_basket_ticker = f"{symbol}.P"
        for index, item in enumerate(reader, start=1):
            basket_ticker = (_clean(item.get("Basket Ticker")) or "").upper()
            if basket_ticker != expected_basket_ticker:
                continue
            parsed_date = cls._parse_iso_date(item.get("Basket Evaluation Date"))
            if parsed_date:
                composition_dates.append(parsed_date)
            asset_group = _clean(item.get("Fund Accounting Asset Group Code"))
            symbol_value = _clean(item.get("Ticker"))
            name = _clean(item.get("Security Description"))
            holding_type = cls._holding_type(asset_group=asset_group, name=name, symbol=symbol_value)
            row_type = "cash" if holding_type == "cash" else "security"
            if row_type == "cash":
                symbol_value = None
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value,
                    name=name,
                    cusip=_clean(item.get("CUSIP")),
                    isin=_clean(item.get("ISIN")),
                    sedol=_clean(item.get("SEDOL")),
                    weight=_decimal(item.get("Calculated Weight - Base")),
                    shares=_decimal(item.get("Benchmark Quantity")),
                    market_value=_decimal(item.get("Benchmark Market Value (Base)")),
                    currency=_clean(item.get("ETF Base Currency")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        composition_date = max(composition_dates) if composition_dates else None
        return rows, composition_date

    @staticmethod
    def _parse_iso_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None

    @staticmethod
    def _holding_type(
        *,
        asset_group: str | None,
        name: str | None,
        symbol: str | None,
    ) -> str:
        text = f"{asset_group or ''} {name or ''} {symbol or ''}".upper()
        if any(token in text for token in ["CASH", "CURRENCY", "RECEIVABLE", "PAYABLE"]):
            return "cash"
        if "BOND" in text or "FIXED" in text:
            return "fixed_income"
        if "FUTURE" in text:
            return "future"
        if "OPTION" in text:
            return "option"
        if "FOREIGN STOCK" in text or "EQUITY" in text or "STOCK" in text:
            return "equity"
        return "security"


class AppliedFinanceHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Applied Finance ETF holdings from its public ETFData pages."""

    product_page_template = "https://appliedfinancefunds.com/ETF/ETFData/{symbol_upper}"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        del issuer_product_id, identifiers
        normalized_symbol = symbol.strip().upper()
        product_page_url = source_url or self.product_page_template.format(
            symbol_upper=normalized_symbol
        )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(),
                follow_redirects=True,
            )
        response.raise_for_status()

        table_parser = _HTMLTableByIdParser(table_id="etf_constituents")
        table_parser.feed(response.text)
        rows = self._parse_applied_finance_rows(table_parser.rows)
        if not rows:
            raise ValueError(
                f"Applied Finance product page did not expose holdings rows for {symbol}."
            )
        composition_date = self._composition_date_from_table(table_parser.rows)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=product_page_url,
            source_identifier=normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_public_product_page_holdings_table",
                "product_page_url": product_page_url,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_applied_finance_rows(
        cls,
        table_rows: list[list[Any]],
    ) -> list[CanonicalHoldingRow]:
        rows = parse_holdings_table(table_rows)
        for row in rows:
            row.currency = row.currency or "USD"
            row.holding_type = cls._holding_type(
                symbol=row.symbol,
                name=row.name,
                market_value=row.market_value,
            )
            row.row_type = "cash" if row.holding_type == "cash" else "security"
            if row.row_type == "cash":
                row.symbol = None
        return rows

    @staticmethod
    def _composition_date_from_table(table_rows: list[list[Any]]) -> date | None:
        rows_by_index = [
            ["" if value is None else value for value in row]
            for row in table_rows
            if any(_clean(value) for value in row)
        ]
        header_index = next(
            (
                index
                for index, row in enumerate(rows_by_index[:30])
                if "as of date" in {str(value).strip().lower() for value in row}
            ),
            None,
        )
        if header_index is None:
            return None
        header = rows_by_index[header_index]
        dates: list[date] = []
        for raw_row in rows_by_index[header_index + 1 :]:
            raw = _row_dict(header, raw_row)
            parsed = AppliedFinanceHoldingsAdapter._parse_date(raw.get("As Of Date"))
            if parsed:
                dates.append(parsed)
        return max(dates) if dates else None

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _holding_type(
        *,
        symbol: str | None,
        name: str | None,
        market_value: Decimal | None,
    ) -> str:
        text = f"{symbol or ''} {name or ''}".upper()
        if any(token in text for token in ["CASH", "CURRENCY", "RECEIVABLE", "PAYABLE"]):
            return "cash"
        if market_value == Decimal("0") and not _clean(symbol):
            return "cash"
        return "equity"


class OceanParkHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Ocean Park ETF holdings from its public FilePoint-backed JSON endpoint."""

    holdings_endpoint = "https://filepoint.live/oceanpark_getholdings_cached4.php"
    product_pages = {
        "DUKQ": "https://oceanparketfs.com/domestic-etf",
        "DUKX": "https://oceanparketfs.com/international-etf",
        "DUKZ": "https://oceanparketfs.com/diversified-income-etf.html",
        "DUKH": "https://oceanparketfs.com/high-income-etf.html",
    }
    fund_ids = {
        "DUKQ": "1356",
        "DUKX": "1357",
        "DUKZ": "1358",
        "DUKH": "1359",
    }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        fund_id = (
            _clean(issuer_product_id)
            or _identifier(identifiers or {}, "issuer_product_id", "ocean_park_fund_id")
            or self.fund_ids.get(normalized_symbol)
        )
        if not fund_id:
            raise ValueError(f"Ocean Park did not expose a fund id for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.post(
                self.holdings_endpoint,
                data={"fundID": fund_id},
                headers=self.source_request_headers(symbol=normalized_symbol),
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        rows, composition_date = self._parse_ocean_park_rows(payload)
        if not rows:
            raise ValueError(f"Ocean Park holdings endpoint did not expose rows for {symbol}.")
        product_page_url = self.product_pages.get(normalized_symbol)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={"rows": payload} if isinstance(payload, list) else None,
            source_url=self.holdings_endpoint,
            source_identifier=fund_id,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_public_filepoint_holdings_json",
                "fund_id": fund_id,
                "product_page_url": product_page_url,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, symbol: str) -> dict[str, str]:
        referer = self.product_pages.get(symbol, "https://oceanparketfs.com/")
        headers = _issuer_page_request_headers(accept="application/json, text/javascript, */*; q=0.01")
        headers.update(
            {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://oceanparketfs.com",
                "Referer": referer,
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        return headers

    @classmethod
    def _parse_ocean_park_rows(
        cls,
        payload: Any,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        if not isinstance(payload, list):
            return [], None
        rows: list[CanonicalHoldingRow] = []
        composition_dates: list[date] = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                continue
            composition_date = cls._parse_date(item.get("asOfDate"))
            if composition_date:
                composition_dates.append(composition_date)
            raw_symbol = _clean(item.get("securityTicker"))
            symbol = cls._clean_symbol(raw_symbol)
            name = _clean(item.get("securityDescriptionLong") or item.get("securityDescriptionShort"))
            row_type, holding_type = cls._classify_row(
                symbol=symbol,
                name=name,
                segment=_clean(item.get("segment")),
                category=_clean(item.get("category")),
            )
            identifier = _clean(item.get("securityIdentifier"))
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type == "security" else None,
                    name=name,
                    cusip=identifier if _looks_like_cusip(identifier) else None,
                    weight=_decimal(item.get("marketValuePercent")),
                    shares=_decimal(item.get("shares")),
                    market_value=_decimal(item.get("marketValueBase")),
                    currency=_clean(item.get("tradingCurrency") or item.get("incomeCurrency")),
                    country=_clean(item.get("country")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        composition_date = max(composition_dates) if composition_dates else None
        return rows, composition_date

    @staticmethod
    def _clean_symbol(value: str | None) -> str | None:
        text = _clean(value)
        if text is None:
            return None
        return text.split()[0].strip().upper() or None

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    @staticmethod
    def _classify_row(
        *,
        symbol: str | None,
        name: str | None,
        segment: str | None,
        category: str | None,
    ) -> tuple[str, str]:
        haystack = " ".join(
            part.upper()
            for part in (symbol, name, segment, category)
            if part
        )
        if any(
            marker in haystack
            for marker in (
                "CASH",
                "SWEEP",
                "SHORT TERM INVESTMENTS",
                "DEPOSIT ACCOUNT",
                "MONEY MARKET",
            )
        ):
            return "cash", "cash"
        return "security", "fund"


class SimplifyHoldingsAdapter(IssuerCsvHoldingsAdapter):
    product_index_url = "https://www.simplify.us/etfs"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        source_page_url = source_url or self.product_index_url
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if self._is_workbook_url(source_page_url):
                workbook_url = source_page_url
            else:
                page_response = await client.get(
                    source_page_url,
                    headers=_issuer_page_request_headers(accept="text/html,*/*"),
                    follow_redirects=True,
                )
                page_response.raise_for_status()
                workbook_url = _discover_holdings_download_url(
                    str(getattr(page_response, "url", source_page_url)),
                    page_response.text,
                )
                if not workbook_url:
                    return await super().fetch_latest(
                        symbol=symbol,
                        issuer_product_id=issuer_product_id,
                        source_url=source_url,
                        identifiers=identifiers,
                    )

            workbook_response = await client.get(
                workbook_url,
                headers=_holdings_request_headers(
                    accept=(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                        "application/vnd.ms-excel,*/*"
                    ),
                ),
                follow_redirects=True,
            )
        workbook_response.raise_for_status()
        workbook_rows = parse_xlsx_table(workbook_response.content)
        rows, composition_date = self._parse_simplify_workbook(
            workbook_rows,
            account_symbol=normalized_symbol,
        )
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=_table_to_text(workbook_rows),
            raw_json={"source_format": "xlsx", "workbook_rows": workbook_rows},
            source_url=str(getattr(workbook_response, "url", workbook_url)),
            source_identifier=normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "xlsx",
                "route_resolution": "issuer_aggregate_holdings_xlsx",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "account_symbol": normalized_symbol,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _is_workbook_url(value: str) -> bool:
        return value.lower().split("?", 1)[0].endswith((".xlsx", ".xlsm"))

    def _parse_simplify_workbook(
        self,
        workbook_rows: list[list[str]],
        *,
        account_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        header_index = next(
            (
                index
                for index, row in enumerate(workbook_rows)
                if row and str(row[0]).strip().upper() == "FUND NAME"
            ),
            None,
        )
        if header_index is None:
            return [], None
        composition_date = self._parse_simplify_date(
            workbook_rows[0][-1] if workbook_rows and workbook_rows[0] else None
        )
        headers = workbook_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        for row_index, row in enumerate(workbook_rows[header_index + 1 :], start=header_index + 2):
            item = _row_dict(headers, row)
            if (_clean(item.get("FUND NAME")) or "").upper() != account_symbol:
                continue
            raw_symbol = _clean(item.get("TICKER"))
            name = _clean(item.get("SECURITY DESCRIPTION"))
            cusip = _clean(item.get("CUSIP"))
            isin = _clean(item.get("ISIN"))
            if not any([raw_symbol, name, cusip, isin]):
                continue
            holding_type = self._simplify_holding_type(raw_symbol=raw_symbol, name=name)
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=raw_symbol if row_type != "cash" else None,
                    name=name,
                    cusip=cusip,
                    isin=isin,
                    sedol=_clean(item.get("SEDOL")),
                    weight=_decimal(item.get("Weight")),
                    shares=_decimal(item.get("Quantity")),
                    market_value=_decimal(item.get("Market Value/Exposure")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(row_index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _simplify_holding_type(*, raw_symbol: str | None, name: str | None) -> str:
        symbol_text = (raw_symbol or "").upper()
        name_text = (name or "").upper()
        if symbol_text == "CASH" or name_text == "CASH":
            return "cash"
        if " COMDTY" in symbol_text:
            return "commodity"
        if " INDEX" in symbol_text:
            return "derivative"
        if " GOVT" in symbol_text:
            return "fixed_income"
        return "security"

    @staticmethod
    def _parse_simplify_date(value: str | None) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None


class NeosHoldingsAdapter(InnovatorHoldingsAdapter):
    holdings_url_template = (
        "https://neosfunds.com/wp-admin/admin-ajax.php"
        "?action=download_holdings_csv&ticker={symbol_upper}"
    )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url or self.holdings_url_template.format(
                symbol_upper=symbol.strip().upper(),
            ),
            identifiers=identifiers,
        )
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "route_resolution": "issuer_ajax_holdings_csv",
        }
        return result

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,*/*")
        headers["Referer"] = "https://neosfunds.com/"
        return headers


class StriveHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return None
        return f"https://www.strivefunds.com/download-holdings?fund={normalized_symbol}"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/download,*/*")
        headers["Referer"] = "https://www.strivefunds.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=self.resolve_source_url(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            ),
            identifiers=identifiers,
        )
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_access": self.config.source_access,
            "source_provider": self.source_provider,
            "route_resolution": "issuer_public_holdings_csv",
            "terms_note": self.config.terms_note,
        }
        return result


class AmericanCenturyHoldingsAdapter(IssuerCsvHoldingsAdapter):
    AVANTIS_PRODUCT_SLUGS: dict[str, str] = {
        "AVUV": "avantis-us-small-cap-value-etf",
    }

    @classmethod
    def _extract_balanced_array(cls, raw_html: str, *, marker: str) -> str | None:
        marker_index = raw_html.find(marker)
        if marker_index == -1:
            return None
        array_start = raw_html.find("[", marker_index)
        if array_start == -1:
            return None

        depth = 0
        in_string = False
        escaped = False
        for index in range(array_start, len(raw_html)):
            char = raw_html[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return raw_html[array_start : index + 1]
        return None

    @classmethod
    def _decode_js_string(cls, value: str) -> str:
        try:
            decoded = json.loads(f'"{value}"')
        except json.JSONDecodeError:
            decoded = value
        return html.unescape(str(decoded))

    @classmethod
    def _parse_js_object_array(cls, array_text: str) -> list[dict[str, str]]:
        objects: list[str] = []
        depth = 0
        in_string = False
        escaped = False
        object_start: int | None = None
        for index, char in enumerate(array_text):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                if depth == 0:
                    object_start = index
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and object_start is not None:
                    objects.append(array_text[object_start : index + 1])
                    object_start = None

        rows: list[dict[str, str]] = []
        field_pattern = re.compile(r"([A-Za-z_][A-Za-z0-9_]*):\"((?:\\.|[^\"])*)\"")
        for item in objects:
            row = {
                key: cls._decode_js_string(value)
                for key, value in field_pattern.findall(item)
            }
            if row:
                rows.append(row)
        return rows

    @classmethod
    def _parse_embedded_avantis_holdings(
        cls,
        raw_html: str,
    ) -> tuple[date | None, list[CanonicalHoldingRow]]:
        as_of_date: date | None = None
        date_match = re.search(r'etfHoldingsAsOfDate:"([^"]+)"', raw_html)
        if date_match:
            try:
                as_of_date = datetime.strptime(date_match.group(1), "%m/%d/%Y").date()
            except ValueError:
                as_of_date = None

        array_text = cls._extract_balanced_array(raw_html, marker="etfHoldings:")
        if not array_text:
            return as_of_date, []

        rows: list[CanonicalHoldingRow] = []
        for item in cls._parse_js_object_array(array_text):
            symbol = _clean(item.get("ticker"))
            name = _clean(item.get("name"))
            holding_type = (_clean(item.get("securityType")) or "security").lower()
            row_type = "cash" if "cash" in holding_type else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=_clean(item.get("cusip")),
                    isin=_clean(item.get("isin")),
                    sedol=_clean(item.get("sedol")),
                    weight=_decimal(item.get("weight")),
                    shares=_decimal(item.get("shareQuantity")),
                    market_value=_decimal(item.get("baseMarketValue")),
                    currency="USD",
                    country=_clean(item.get("country")),
                    holding_type=holding_type,
                    row_type=row_type,
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if key not in {
                            "ticker",
                            "name",
                            "securityType",
                            "cusip",
                            "isin",
                            "sedol",
                            "weight",
                            "shareQuantity",
                            "baseMarketValue",
                            "country",
                        }
                    },
                )
            )
        return as_of_date, rows

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        slug = self.AVANTIS_PRODUCT_SLUGS.get(normalized_symbol)
        if not slug:
            return None
        return f"https://www.avantisinvestors.com/avantis-investments/{slug}/"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        as_of_date, rows = self._parse_embedded_avantis_holdings(response.text)
        if not rows:
            raise ValueError(f"American Century/Avantis holdings page did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(response.url),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "terms_note": self.config.terms_note,
                "route_resolution": "issuer_product_page_embedded_holdings",
                "composition_date": as_of_date.isoformat() if as_of_date else None,
                "as_of_date": as_of_date.isoformat() if as_of_date else None,
            },
        )


class JPMorganHoldingsAdapter(IssuerCsvHoldingsAdapter):
    product_data_url = "https://am.jpmorgan.com/FundsMarketingHandler/product-data"
    KNOWN_CUSIPS: dict[str, str] = {
        "JEPI": "46641Q332",
    }

    def _resolve_cusip(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        identifiers = identifiers or {}
        candidate = (
            _identifier(identifiers, "cusip", "csp_code", "jpmorgan_cusip")
            or issuer_product_id
            or self._extract_cusip_from_url(source_url)
            or self.KNOWN_CUSIPS.get(symbol.strip().upper())
        )
        if candidate and _looks_like_cusip(candidate):
            return candidate.strip().upper()
        return None

    @staticmethod
    def _extract_cusip_from_url(source_url: str | None) -> str | None:
        if not source_url:
            return None
        for token in re.findall(r"[0-9A-Z]{8}[0-9A-Z]", source_url.upper()):
            if _looks_like_cusip(token):
                return token
        return None

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        cusip = self._resolve_cusip(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not cusip:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                self.product_data_url,
                params={
                    "country": "us",
                    "role": "adv",
                    "language": "en",
                    "cusip": cusip,
                },
                headers={
                    **_issuer_page_request_headers(accept="application/json,text/plain,*/*"),
                    "Referer": source_url
                    or (
                        "https://am.jpmorgan.com/us/en/asset-management/adv/products/"
                        f"dynamic-pdp.productpage.{cusip.lower()}.html"
                    ),
                },
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        rows, composition_date = self._parse_product_data_payload(payload)
        if not rows:
            raise ValueError(f"J.P. Morgan product-data endpoint returned no holdings for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=payload,
            source_url=str(response.url),
            source_identifier=cusip,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_product_data_json",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "cusip": cusip,
                "terms_note": self.config.terms_note,
            },
        )

    def _parse_product_data_payload(
        self,
        payload: dict[str, Any],
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        fund_data = payload.get("fundData") if isinstance(payload, dict) else None
        if not isinstance(fund_data, dict):
            return [], None
        holdings = fund_data.get("dailyHoldingsAll") or fund_data.get("dailyHoldings")
        if not isinstance(holdings, dict):
            return [], None
        raw_rows = holdings.get("data")
        if not isinstance(raw_rows, list):
            return [], None

        composition_date = self._parse_jpmorgan_date(holdings.get("effectiveDate"))
        rows: list[CanonicalHoldingRow] = []
        for index, item in enumerate(raw_rows, start=1):
            if not isinstance(item, dict):
                continue
            symbol = _clean(item.get("securityTicker"))
            name = _clean(item.get("securityDescription"))
            cusip = _clean(item.get("securityCusip") or item.get("securityId"))
            isin = _clean(item.get("securityIsin"))
            sedol = _clean(item.get("securitySedol"))
            if not any([symbol, name, cusip, isin, sedol]):
                continue
            holding_type = self._jpmorgan_holding_type(
                security_type=_clean(item.get("securityType")),
                symbol=symbol,
                name=name,
            )
            row_type = "cash" if holding_type == "cash" else "security"
            row_date = self._parse_jpmorgan_date(item.get("navDate") or item.get("effectiveDate"))
            if composition_date is None:
                composition_date = row_date
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    isin=isin,
                    sedol=sedol,
                    weight=_decimal_percent_points(
                        item.get("netAssetValuePercent")
                        if item.get("netAssetValuePercent") is not None
                        else item.get("marketValuePercent")
                    ),
                    shares=_decimal(item.get("shares")),
                    market_value=_decimal(item.get("marketValue")),
                    currency=_clean(item.get("currency")),
                    country=_clean(item.get("country")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_jpmorgan_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for date_format in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _jpmorgan_holding_type(
        *,
        security_type: str | None,
        symbol: str | None,
        name: str | None,
    ) -> str:
        text = " ".join(part.upper() for part in (security_type, symbol, name) if part)
        if "CASH" in text or text in {"USD", "US DOLLAR"}:
            return "cash"
        if "EQUITY LINKED NOTE" in text or "SWAP" in text or "OPTION" in text:
            return "derivative"
        if "TREASURY" in text or "BOND" in text or "NOTE" in text:
            return "fixed_income"
        return "security"


class PacerHoldingsAdapter(IssuerCsvHoldingsAdapter):
    HOLDINGS_FILE_CODES: dict[str, str] = {
        "COWZ": "x330",
    }

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        identifiers = identifiers or {}
        holdings_code = (
            _identifier(identifiers, "pacer_holdings_code", "holdings_file_code")
            or issuer_product_id
            or self.HOLDINGS_FILE_CODES.get(normalized_symbol)
        )
        if not normalized_symbol or not holdings_code:
            return None
        return (
            "https://www.paceretfs.com/usbank/live/"
            f"fsb0.pacer.{holdings_code}.{normalized_symbol}_Holdings.csv"
        )

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return f"https://www.paceretfs.com/products/{normalized_symbol}"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/csv,*/*")
        headers["Referer"] = "https://www.paceretfs.com/"
        return headers


class GraniteSharesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    PRODUCT_PAGE_SLUGS: dict[str, str] = {
        "NVD": "nvd",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        slug = self.PRODUCT_PAGE_SLUGS.get(normalized_symbol)
        if not slug:
            return None
        return f"https://graniteshares.com/etfs/{slug}/"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="application/vnd.ms-excel,*/*")
        headers["Referer"] = "https://graniteshares.com/"
        return headers


class CapitalGroupHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Capital Group ETF holdings from the issuer's public JSON API."""

    API_TEMPLATE = (
        "https://www.capitalgroup.com/api/investments/investment-service/v1/"
        "etfs/{symbol}/holdings"
    )
    HOLDINGS_PAGE = (
        "https://www.capitalgroup.com/individual/investments/"
        "exchange-traded-funds/holdings"
    )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return None
        return (
            self.API_TEMPLATE.format(symbol=normalized_symbol)
            + "?"
            + urlencode({"audience": "individual", "redirect": "true"})
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        resolved_url = self.resolve_source_url(
            symbol=normalized_symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_url:
            raise ValueError(f"Capital Group holdings route not found for {normalized_symbol}.")

        headers = _holdings_request_headers(accept="application/json,*/*")
        headers.update(
            {
                "Referer": f"{self.HOLDINGS_PAGE}?etf={normalized_symbol}",
                "x-app-source": "dis-etf-web",
            }
        )
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_url,
                headers=headers,
                follow_redirects=True,
            )
            response.raise_for_status()
        payload = response.json()
        rows, composition_date = self._parse_payload(payload, symbol=normalized_symbol)
        if not rows:
            raise ValueError(f"Capital Group returned no holdings for {normalized_symbol}.")

        fund_id = _clean(payload.get("fundId"))
        actual_symbol = _clean(payload.get("abbreviatedName"))
        if actual_symbol and actual_symbol.upper() != normalized_symbol:
            raise ValueError(
                f"Capital Group returned {actual_symbol} holdings for {normalized_symbol}."
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=payload,
            source_url=str(response.url),
            source_identifier=fund_id or issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": "issuer_public_daily_holdings_api",
                "source_provider": "capital_group",
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "capital_group_daily_holdings_api",
                "product_url": f"{self.HOLDINGS_PAGE}?etf={normalized_symbol}",
                **({"fund_id": fund_id} if fund_id else {}),
                **(
                    {"composition_date": composition_date.isoformat()}
                    if composition_date
                    else {}
                ),
            },
        )

    @classmethod
    def _parse_payload(
        cls,
        payload: dict[str, Any],
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        daily_holdings = payload.get("dailyHoldings")
        if not isinstance(daily_holdings, dict):
            return [], None
        composition_date = cls._parse_date(daily_holdings.get("asOfDate"))
        raw_rows = daily_holdings.get("holdings")
        if not isinstance(raw_rows, list):
            return [], composition_date

        rows: list[CanonicalHoldingRow] = []
        for index, raw_row in enumerate(raw_rows):
            if not isinstance(raw_row, dict):
                continue
            asset_class = (_clean(raw_row.get("assetClass")) or "").lower()
            source_ticker = _clean(raw_row.get("ticker"))
            row_type, holding_type = cls._classify_asset(asset_class)
            row_symbol = cls._tradable_symbol(source_ticker) if row_type == "security" else None
            name = _clean(raw_row.get("securityName"))
            if not any(
                [
                    row_symbol,
                    name,
                    _clean(raw_row.get("cusip")),
                    _clean(raw_row.get("isin")),
                ]
            ):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=row_symbol,
                    name=name,
                    cusip=_clean(raw_row.get("cusip")),
                    isin=_clean(raw_row.get("isin")),
                    sedol=_clean(raw_row.get("sedol")),
                    weight=_decimal_percent_points(raw_row.get("percentageOfNetAssets")),
                    shares=_decimal(raw_row.get("sharesOrPrincipalAmount")),
                    market_value=_decimal(raw_row.get("marketValue")),
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{symbol}:{index}",
                    extra_data={
                        "asset_class": _clean(raw_row.get("assetClass")),
                        "source_ticker": source_ticker,
                        "notional_value": _clean(raw_row.get("notionalValue")),
                        "details_link": _clean(raw_row.get("detailsLink")),
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _classify_asset(asset_class: str) -> tuple[str, str]:
        if "cash" in asset_class or "equivalent" in asset_class:
            return "cash", "cash"
        if "spot fx" in asset_class or "currency" in asset_class:
            return "other", "forex"
        if any(term in asset_class for term in ("bond", "fixed income", "debt", "short term")):
            return "security", "fixed_income"
        if any(term in asset_class for term in ("option", "future", "swap", "derivative")):
            return "other", "derivative"
        if any(term in asset_class for term in ("fund", "etf")):
            return "security", "fund"
        return "security", "equity"

    @staticmethod
    def _tradable_symbol(value: str | None) -> str | None:
        text = _clean(value)
        if text is None:
            return None
        normalized = text.upper()
        if _looks_like_cusip(normalized) or _looks_like_isin(normalized):
            return None
        return normalized if re.fullmatch(r"[A-Z0-9][A-Z0-9.\-/]{0,14}", normalized) else None

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None


class FidelityHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch complete Fidelity ETF creation baskets from Fidelity Research."""

    BASKET_URL = (
        "https://research2.fidelity.com/fidelity/screeners/etf/etfholdings.asp"
    )
    AS_OF_RE = re.compile(
        r"Basket\s+Holdings:\s*(?P<count>[\d,]+).*?AS\s+OF\s+(?P<date>\d{2}/\d{2}/\d{4})",
        re.IGNORECASE | re.DOTALL,
    )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return None
        return self.BASKET_URL + "?" + urlencode(
            {
                "sortBy": "Symbol",
                "sortDir": "asc",
                "symbol": normalized_symbol,
                "view": "Holdings",
            }
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers()
        headers["Referer"] = "https://www.fidelity.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        resolved_url = self.resolve_source_url(
            symbol=normalized_symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_url:
            raise ValueError(f"Fidelity basket holdings route not found for {normalized_symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_url,
                headers=self.source_request_headers(source_url=resolved_url),
                follow_redirects=True,
            )
            response.raise_for_status()

        rows = parse_html_holdings_table_by_headers(
            response.text,
            required_headers={"symbol", "company", "weight"},
        )
        match = self.AS_OF_RE.search(response.text)
        expected_count = int(match.group("count").replace(",", "")) if match else None
        composition_date = self._parse_date(match.group("date")) if match else None
        if not rows:
            raise ValueError(f"Fidelity returned no basket holdings for {normalized_symbol}.")
        if expected_count is not None and len(rows) != expected_count:
            raise ValueError(
                f"Fidelity declared {expected_count} basket holdings for {normalized_symbol} "
                f"but only {len(rows)} rows were parsed."
            )
        for row in rows:
            row.currency = row.currency or "USD"
            row.extra_data["basket_composition"] = True
            if (row.name or "").strip().lower().startswith("cash"):
                row.symbol = None
                row.row_type = "cash"
                row.holding_type = "cash"

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={
                "source_format": "html",
                "declared_basket_holding_count": expected_count,
            },
            source_url=str(response.url),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": "issuer_public_complete_creation_basket_html",
                "source_provider": "fidelity",
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "fidelity_research_complete_basket_holdings",
                "portfolio_semantics": "daily_creation_redemption_basket",
                "portfolio_semantics_note": (
                    "Fidelity states that basket holdings may not represent the fund's full "
                    "current or future investment portfolio."
                ),
                **(
                    {"composition_date": composition_date.isoformat()}
                    if composition_date
                    else {}
                ),
                **(
                    {"declared_basket_holding_count": expected_count}
                    if expected_count is not None
                    else {}
                ),
            },
        )

    @staticmethod
    def _parse_date(value: str) -> date | None:
        try:
            return datetime.strptime(value.strip(), "%m/%d/%Y").date()
        except ValueError:
            return None


class DimensionalHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Dimensional ETF holdings through the issuer's public fund-details API."""

    COUNTRY_KEY = "5EDA63C7CB764D13BFFC44188EE331A5"
    INDIVIDUAL_INVESTOR_AUDIENCE_ID = "72F4ED1678744217ADBB47C57F3F0638"
    PRODUCT_SITEMAP_URL = "https://www.dimensional.com/us-en/funds/sitemap.xml"
    PUBLIC_API_BASE = "https://etf.dimensional.com/public"

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        slug = _clean(
            issuer_product_id
            or _identifier(identifiers or {}, "issuer_product_id", "dimensional_fund_slug")
        )
        if slug and "/" in slug:
            return f"https://www.dimensional.com/us-en/funds/{slug.strip('/')}"
        return None

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            product_url = (
                source_url
                or self.resolve_product_page_url(
                    symbol=normalized_symbol,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers,
                )
                or await self._discover_product_url(client, symbol=normalized_symbol)
            )
            if not product_url:
                raise ValueError(f"Dimensional ETF product page not found for {normalized_symbol}.")

            await self._select_us_individual_audience(client)
            page_response = await client.get(
                product_url,
                headers=self._page_headers(referer="https://www.dimensional.com/us-en/funds"),
                follow_redirects=True,
            )
            page_response.raise_for_status()
            page_html = page_response.text

            portfolio_number = self._extract_portfolio_number(page_html)
            api_base = self._extract_services_api_base(page_html) or self.PUBLIC_API_BASE
            if portfolio_number is None:
                raise ValueError(f"Dimensional product page did not expose a portfolio number for {normalized_symbol}.")

            details_url = f"{api_base.rstrip('/')}/v2/fundcenter/funddetail"
            details_response = await client.post(
                details_url,
                json={"portfolioNumber": str(portfolio_number)},
                headers=self._api_headers(referer=product_url),
                follow_redirects=True,
            )
            details_response.raise_for_status()
            details_payload = details_response.json()
            holdings_url = self._find_full_holdings_csv_url(details_payload)
            if not holdings_url:
                raise ValueError(f"Dimensional fund details did not expose full holdings CSV for {normalized_symbol}.")

            csv_response = await client.get(
                holdings_url,
                headers=self._page_headers(referer=product_url, accept="text/csv,application/octet-stream,*/*"),
                follow_redirects=True,
            )
            csv_response.raise_for_status()

        rows, composition_date = self._parse_dimensional_csv(
            csv_response.text,
            symbol=normalized_symbol,
        )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=csv_response.text,
            raw_json={
                "portfolio_number": portfolio_number,
                "product_url": product_url,
                "fund_details_url": details_url,
                "full_holdings_csv_url": holdings_url,
            },
            source_url=holdings_url,
            source_identifier=str(portfolio_number),
            legal_metadata={
                "source_access": "issuer_public_fund_details_api_full_holdings_csv",
                "adapter_key": self.adapter_key,
                "route_resolution": "dimensional_public_fund_details_api",
                "product_url": product_url,
                "fund_details_url": details_url,
                "full_holdings_csv_url": holdings_url,
                "portfolio_number": str(portfolio_number),
                **({"composition_date": composition_date.isoformat()} if composition_date else {}),
            },
        )

    @classmethod
    async def _discover_product_url(cls, client: httpx.AsyncClient, *, symbol: str) -> str | None:
        response = await client.get(
            cls.PRODUCT_SITEMAP_URL,
            headers=cls._page_headers(referer="https://www.dimensional.com/us-en/funds"),
            follow_redirects=True,
        )
        response.raise_for_status()
        pattern = re.compile(
            rf"https://www\.dimensional\.com/us-en/funds/{re.escape(symbol.lower())}/[^<\s]+",
            re.IGNORECASE,
        )
        match = pattern.search(response.text)
        return html.unescape(match.group(0)) if match else None

    @classmethod
    async def _select_us_individual_audience(cls, client: httpx.AsyncClient) -> None:
        headers = cls._page_headers(referer="https://www.dimensional.com/")
        await client.post(
            "https://www.dimensional.com/audience-selector-api/get-splash-page-data-for-country",
            json={"countryKey": cls.COUNTRY_KEY},
            headers=headers,
            follow_redirects=True,
        )
        response = await client.post(
            "https://www.dimensional.com/audience-selector-api/select-audience-type",
            json={
                "countryKey": cls.COUNTRY_KEY,
                "audienceTypeId": cls.INDIVIDUAL_INVESTOR_AUDIENCE_ID,
            },
            headers=headers,
            follow_redirects=True,
        )
        response.raise_for_status()

    @staticmethod
    def _page_headers(*, referer: str, accept: str = "text/html,application/xhtml+xml,*/*") -> dict[str, str]:
        headers = _holdings_request_headers(accept=accept)
        headers["Referer"] = referer
        return headers

    @classmethod
    def _api_headers(cls, *, referer: str) -> dict[str, str]:
        headers = cls._page_headers(referer=referer, accept="application/json,*/*")
        headers["Content-Type"] = "application/json"
        headers["Origin"] = "https://www.dimensional.com"
        headers["x-selected-country"] = "US"
        return headers

    @staticmethod
    def _extract_portfolio_number(raw_html: str) -> str | None:
        match = re.search(r"\bvar\s+portfolioNumber\s*=\s*([0-9]+)\s*;", raw_html)
        return match.group(1) if match else None

    @staticmethod
    def _extract_services_api_base(raw_html: str) -> str | None:
        match = re.search(r'\bvar\s+servicesApiBaseUrl\s*=\s*"([^"]+)"\s*;', raw_html)
        return html.unescape(match.group(1)) if match else None

    @classmethod
    def _find_full_holdings_csv_url(cls, payload: Any) -> str | None:
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key == "fullHoldingsCsvUrl" and isinstance(value, str) and value.strip():
                    return value.strip()
                found = cls._find_full_holdings_csv_url(value)
                if found:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = cls._find_full_holdings_csv_url(item)
                if found:
                    return found
        return None

    @staticmethod
    def _parse_dimensional_csv(raw_csv: str, *, symbol: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        reader = csv.DictReader(StringIO(raw_csv))
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, raw in enumerate(reader, start=1):
            fund_symbol = (_clean(raw.get("etf_ticker")) or "").upper()
            if fund_symbol and fund_symbol != symbol.upper():
                continue
            raw_ticker = _clean(raw.get("ticker"))
            row_symbol, exchange = DimensionalHoldingsAdapter._split_dimensional_ticker(raw_ticker)
            name = _clean(raw.get("description"))
            if not (row_symbol or name or _clean(raw.get("identifier"))):
                continue
            row_date = DimensionalHoldingsAdapter._parse_iso_date(raw.get("date"))
            composition_date = composition_date or row_date
            holding_type = DimensionalHoldingsAdapter._holding_type(raw=raw, symbol=row_symbol, name=name)
            row_type = "cash" if holding_type == "cash" else "security"
            if row_type == "cash":
                row_symbol = None
            rows.append(
                CanonicalHoldingRow(
                    symbol=row_symbol,
                    name=name,
                    cusip=_clean(raw.get("identifier")),
                    isin=_clean(raw.get("isin")),
                    sedol=_clean(raw.get("sedol")),
                    weight=_decimal(raw.get("weight")),
                    shares=_decimal(raw.get("shares")),
                    market_value=_decimal(raw.get("market_value")),
                    currency="USD",
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{symbol}:{index}",
                    extra_data={
                        "source_provider": "dimensional",
                        "etf_ticker": fund_symbol or symbol,
                        "raw_ticker": raw_ticker,
                        "coupon_rate": _clean(raw.get("coupon_rate")),
                        "maturity_date": _clean(raw.get("maturity_date")),
                        "principal": _clean(raw.get("principal")),
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _split_dimensional_ticker(value: str | None) -> tuple[str | None, str | None]:
        ticker = _clean(value)
        if not ticker:
            return None, None
        parts = ticker.split()
        symbol = parts[0].strip().upper() if parts else ticker.upper()
        exchange = parts[1].strip().upper() if len(parts) > 1 else None
        if symbol in {"CASH", "USD", "US$", "$"}:
            return None, exchange
        return symbol, exchange

    @staticmethod
    def _holding_type(*, raw: dict[str, Any], symbol: str | None, name: str | None) -> str:
        lowered_name = (name or "").strip().lower()
        if symbol is None or lowered_name in {"cash", "cash collateral", "us dollar"}:
            return "cash"
        if _clean(raw.get("maturity_date")) or _decimal(raw.get("coupon_rate")):
            return "fixed_income"
        return "equity"

    @staticmethod
    def _parse_iso_date(value: Any) -> date | None:
        cleaned = _clean(value)
        if not cleaned:
            return None
        try:
            return datetime.strptime(cleaned, "%Y-%m-%d").date()
        except ValueError:
            return None


class TexasCapitalHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Texas Capital ETF holdings from issuer-published static JSON files."""

    FUND_SLUGS: dict[str, str] = {
        "TXS": "txs",
        "TXSS": "txss",
        "OILT": "oilt",
        "MMKT": "mmkt",
    }

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        fund_slug = (
            _clean(issuer_product_id)
            or _identifier(identifiers or {}, "issuer_product_id", "texas_capital_fund_slug")
            or self.FUND_SLUGS.get(normalized_symbol)
        )
        if not fund_slug:
            return None
        return (
            "https://texascapitalbank.com/sites/default/files/documents/"
            f"etf-funds-management/{fund_slug.strip().lower()}/data/holdings-data.json"
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Texas Capital did not expose a holdings JSON route for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=_holdings_request_headers(accept="application/json,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        rows, composition_date = self._parse_holdings_payload(payload, fund_symbol=symbol)
        if not rows:
            raise ValueError(f"Texas Capital holdings JSON did not expose rows for {symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={"rows": payload} if isinstance(payload, list) else None,
            source_url=resolved_source_url,
            source_identifier=issuer_product_id,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_static_holdings_json",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_daily_holdings",
                "snapshot_provenance": "issuer_native_static_json",
            },
        )

    @classmethod
    def _parse_holdings_payload(
        cls,
        payload: Any,
        *,
        fund_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        if not isinstance(payload, list):
            return [], None
        rows: list[CanonicalHoldingRow] = []
        composition_dates: list[date] = []
        for index, raw_row in enumerate(payload, start=1):
            if not isinstance(raw_row, dict):
                continue
            row = cls._flatten_suffixed_row(raw_row)
            if not row:
                continue
            composition_date = cls._parse_date(row.get("asOfDate"))
            if composition_date:
                composition_dates.append(composition_date)
            raw_symbol = _clean(row.get("ticker") or row.get("symbol"))
            symbol = cls._normalize_symbol(raw_symbol)
            name = _clean(row.get("securityDescriptionLong") or row.get("securityDescription"))
            segment = _clean(row.get("segment"))
            category = _clean(row.get("category"))
            identifier = _clean(row.get("securityIdentifier"))
            row_type, holding_type = cls._classify_row(
                symbol=symbol,
                name=name,
                segment=segment,
                category=category,
                identifier=identifier,
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type == "security" else None,
                    name=name,
                    cusip=identifier if _looks_like_cusip(identifier) else None,
                    weight=_decimal_percent_points(row.get("marketValuePercentage")),
                    shares=_decimal(row.get("sharesHeldOfSecurity")),
                    market_value=_decimal(row.get("marketValueOfHolding")),
                    currency=_clean(row.get("tradingCurrency") or row.get("incomeCurrency")),
                    country=_clean(row.get("country")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=(
                        f"{fund_symbol.strip().upper()}-"
                        f"{composition_date.isoformat() if composition_date else 'latest'}-"
                        f"{index}"
                    ),
                    extra_data={
                        key: value
                        for key, value in row.items()
                        if value not in (None, "")
                    },
                )
            )
        composition_date = max(composition_dates) if composition_dates else None
        return rows, composition_date

    @staticmethod
    def _flatten_suffixed_row(raw_row: dict[str, Any]) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for key, value in raw_row.items():
            match = re.fullmatch(r"(.+)_\d+", str(key))
            if match:
                row[match.group(1)] = value
            else:
                row[str(key)] = value
        return row

    @staticmethod
    def _normalize_symbol(value: str | None) -> str | None:
        text = _clean(value)
        if text is None:
            return None
        normalized = text.strip().upper()
        if normalized in {"USD", "CASH"}:
            return normalized
        if "." in normalized or " " in normalized:
            return None
        return normalized

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        for date_format in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _classify_row(
        *,
        symbol: str | None,
        name: str | None,
        segment: str | None,
        category: str | None,
        identifier: str | None,
    ) -> tuple[str, str]:
        haystack = " ".join(
            part.upper()
            for part in (symbol, name, segment, category, identifier)
            if part
        )
        if any(marker in haystack for marker in ("CASH", "CURRENCY", "US DOLLARS", "USD")):
            return "cash", "cash"
        if any(marker in haystack for marker in ("TREASURY", "BILL", "NOTE", "BOND")):
            return "security", "fixed_income"
        return "security", "equity"


class CloughHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Clough Capital ETF holdings from its public WordPress JSON endpoint."""

    HOLDINGS_URL_TEMPLATE = (
        "https://www.cloughcapital.com/wp-admin/admin-ajax.php"
        "?action=get_holdings_json&slug={symbol_lower}"
    )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.HOLDINGS_URL_TEMPLATE.format(symbol_lower=symbol.strip().lower())

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"{self.adapter_key} needs a Clough holdings URL for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=_holdings_request_headers(accept="application/json,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        rows, composition_date = self._parse_holdings_payload(payload, fund_symbol=symbol)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=payload if isinstance(payload, dict) else {"payload": payload},
            source_url=resolved_source_url,
            source_identifier=issuer_product_id,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_wordpress_holdings_json",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_daily_holdings",
                "snapshot_provenance": "issuer_native_json_endpoint",
            },
        )

    @classmethod
    def _parse_holdings_payload(
        cls,
        payload: Any,
        *,
        fund_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        if not isinstance(payload, dict) or payload.get("success") is not True:
            return [], None
        data = payload.get("data")
        if not isinstance(data, dict):
            return [], None
        composition_date = cls._parse_date(data.get("asOfDate"))
        raw_holdings = data.get("holdings")
        if not isinstance(raw_holdings, list):
            return [], composition_date

        rows: list[CanonicalHoldingRow] = []
        for index, raw in enumerate(raw_holdings, start=1):
            if not isinstance(raw, dict):
                continue
            name = _clean(raw.get("name"))
            raw_symbol = _clean(raw.get("hTicker"))
            cusip = _clean(raw.get("cusip"))
            row_type, holding_type = cls._classify_row(name=name, symbol=raw_symbol, cusip=cusip)
            symbol_value = None if row_type == "cash" else cls._normalize_symbol(raw_symbol)
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value,
                    name=name,
                    cusip=cusip if cusip and _looks_like_cusip(cusip) else None,
                    weight=_decimal(raw.get("weight")),
                    shares=_decimal(raw.get("sharesPar")),
                    market_value=_decimal(raw.get("marketValue")),
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=(
                        f"{fund_symbol.strip().upper()}-"
                        f"{composition_date.isoformat() if composition_date else 'latest'}-"
                        f"{index}"
                    ),
                    extra_data={
                        "source_symbol": raw_symbol,
                        "source_cusip": cusip,
                        "source_weight": _clean(raw.get("weight")),
                        "source_market_value": _clean(raw.get("marketValue")),
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _normalize_symbol(value: str | None) -> str | None:
        text = _clean(value)
        if text is None:
            return None
        if "." in text:
            return None
        return text.upper()

    @staticmethod
    def _classify_row(
        *,
        name: str | None,
        symbol: str | None,
        cusip: str | None,
    ) -> tuple[str, str]:
        lowered_name = (name or "").strip().lower()
        lowered_symbol = (symbol or "").strip().lower()
        lowered_cusip = (cusip or "").strip().lower()
        if (
            "cash" in lowered_name
            or "broker sweep" in lowered_name
            or lowered_symbol in {"cash", "usd", "gs.broker"}
            or lowered_cusip in {"cash", "usd", "gs.broker"}
        ):
            return "cash", "cash"
        return "security", "equity"


class PalmerSquareHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Palmer Square ETF holdings from issuer product-page JSON data."""

    PRODUCT_PAGE_SLUGS: dict[str, str] = {
        "PSQO": "palmer-square-credit-opportunities-etf",
        "PSQA": "palmer-square-clo-senior-debt-etf",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        slug = issuer_product_id or self.PRODUCT_PAGE_SLUGS.get(normalized_symbol)
        if not slug:
            return None
        return f"https://etf.palmersquarefunds.com/funds/us-etfs/{slug}"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            raise ValueError(f"Palmer Square product page route is unavailable for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date, holdings_payload = self._parse_product_page(
            response.text,
            fund_symbol=symbol,
        )
        if not rows:
            raise ValueError(f"Palmer Square product page did not expose holdings rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={
                "source_format": "html_embedded_json",
                "holdings": holdings_payload,
            },
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html_embedded_json",
                "route_resolution": "issuer_product_page_embedded_holdings_json",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_full_investment_holdings",
                "snapshot_provenance": "issuer_native_product_page_json",
            },
        )

    @classmethod
    def _parse_product_page(
        cls,
        page_text: str,
        *,
        fund_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None, list[dict[str, Any]]]:
        holdings_payload = cls._extract_holdings_payload(page_text)
        composition_date = cls._extract_composition_date(page_text)
        rows: list[CanonicalHoldingRow] = []
        for index, raw in enumerate(holdings_payload, start=1):
            if not isinstance(raw, dict):
                continue
            name = _clean(raw.get("name"))
            cusip = _clean(raw.get("cusip"))
            asset_type = _clean(raw.get("asset_type"))
            if not any([name, cusip, asset_type]):
                continue
            row_type, holding_type = cls._classify_row(name=name, asset_type=asset_type)
            rows.append(
                CanonicalHoldingRow(
                    symbol=None,
                    name=name,
                    cusip=cusip if cusip and _looks_like_cusip(cusip) else None,
                    weight=_decimal_percent_points(raw.get("weight_percent")),
                    shares=_decimal(raw.get("shares_par")),
                    market_value=_decimal(raw.get("market_value")),
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=(
                        f"{fund_symbol.strip().upper()}-"
                        f"{composition_date.isoformat() if composition_date else 'latest'}-"
                        f"{index}:{cusip or name or asset_type}"
                    ),
                    extra_data={
                        key: value
                        for key, value in raw.items()
                        if _clean(value) is not None
                    },
                )
            )
        return rows, composition_date, holdings_payload

    @staticmethod
    def _extract_holdings_payload(page_text: str) -> list[dict[str, Any]]:
        marker = "var holdingsData ="
        marker_index = page_text.find(marker)
        if marker_index < 0:
            return []
        payload_start = page_text.find("[", marker_index)
        if payload_start < 0:
            return []
        decoder = json.JSONDecoder()
        try:
            payload, _ = decoder.raw_decode(page_text[payload_start:])
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _extract_composition_date(page_text: str) -> date | None:
        match = re.search(
            r"Full\s+Investment\s+Holdings\s+as\s+of\s+(?P<value>[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
            page_text,
            flags=re.I,
        )
        if not match:
            return None
        for date_format in ("%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(match.group("value"), date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _classify_row(*, name: str | None, asset_type: str | None) -> tuple[str, str]:
        text = " ".join(part.upper() for part in (name, asset_type) if part)
        if "CASH" in text or "MONEY MARKET" in text:
            return "cash", "cash"
        if any(token in text for token in ("BOND", "NOTE", "DEBT", "LOAN", "CDO", "CLO")):
            return "security", "fixed_income"
        return "security", "security"


class FutureFundHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Future Fund ETF holdings from issuer-published CSV modules."""

    HOLDINGS_URLS: dict[str, str] = {
        "FFLS": "https://futurefundetf.com/modules/mod_csvtables_copy/cron/holdings.csv",
        "FFOX": (
            "https://futurefundetf.com/modules/mod_csvtables_ffox/cron/"
            "FundxFutureWeb.40F3.F3_Holdings.csv"
        ),
    }

    PRODUCT_PAGE_SLUGS: dict[str, str] = {
        "FFLS": "the-future-fund-long-short-etf",
        "FFOX": "fundx-future-fund-opportunities-etf",
    }

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.HOLDINGS_URLS.get(symbol.strip().upper())

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        slug = issuer_product_id or self.PRODUCT_PAGE_SLUGS.get(symbol.strip().upper())
        if not slug:
            return None
        return f"https://futurefundetf.com/fund/{slug}"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/csv,*/*")
        headers["Referer"] = "https://futurefundetf.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers or {},
        )
        if not resolved_source_url:
            raise ValueError(f"Future Fund holdings CSV route is unavailable for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date, source_format = self._parse_holdings_csv(
            response.text,
            symbol=symbol,
        )
        if not rows:
            raise ValueError(f"Future Fund holdings CSV did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "issuer_schema": source_format,
                "route_resolution": "issuer_symbol_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_daily_holdings",
                "snapshot_provenance": "issuer_native_csv_module",
            },
        )

    @classmethod
    def _parse_holdings_csv(
        cls,
        raw_csv: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None, str]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None, "empty"
        first_row = {cell.strip().lower() for cell in table_rows[0]}
        if {"date", "account", "stockticker", "cusip", "securityname"} <= first_row:
            rows, composition_date = cls._parse_account_csv(raw_csv, symbol=symbol)
            return rows, composition_date, "account_holdings_csv"
        rows, composition_date = cls._parse_preamble_csv(table_rows)
        return rows, composition_date, "preamble_holdings_csv"

    @classmethod
    def _parse_account_csv(
        cls,
        raw_csv: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        requested_symbol = symbol.strip().upper()
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(csv.DictReader(StringIO(raw_csv.strip())), start=1):
            account = (_clean(item.get("Account")) or "").upper()
            if account and account != requested_symbol:
                continue
            row_date = cls._parse_date(item.get("Date"))
            if composition_date is None:
                composition_date = row_date
            raw_symbol = _clean(item.get("StockTicker"))
            name = _clean(item.get("SecurityName"))
            money_market_flag = _clean(item.get("MoneyMarketFlag"))
            row_type, holding_type = cls._classify_row(
                raw_symbol=raw_symbol,
                name=name,
                identifier=_clean(item.get("CUSIP")),
                money_market_flag=money_market_flag,
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=raw_symbol if row_type != "cash" else None,
                    name=name,
                    cusip=(
                        _clean(item.get("CUSIP"))
                        if _looks_like_cusip(_clean(item.get("CUSIP")))
                        else None
                    ),
                    weight=_decimal(item.get("Weightings")),
                    shares=_decimal(item.get("Shares")),
                    market_value=_decimal(item.get("MarketValue")),
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in item.items() if _clean(value) is not None},
                )
            )
        return rows, composition_date

    @classmethod
    def _parse_preamble_csv(
        cls,
        table_rows: list[list[str]],
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        composition_date = cls._extract_as_of_date(table_rows[:5])
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {cell.strip().lower() for cell in row}
                >= {"name", "security identifier", "symbol"}
            ),
            None,
        )
        if header_index is None:
            return [], composition_date
        header = table_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            raw_symbol = _clean(_first(raw, ["Symbol"]))
            symbol, exchange = cls._split_symbol(raw_symbol)
            name = _clean(_first(raw, ["Name"]))
            security_identifier = _clean(_first(raw, ["Security Identifier"]))
            row_type, holding_type = cls._classify_row(
                raw_symbol=raw_symbol,
                name=name,
                identifier=security_identifier,
                money_market_flag=None,
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=security_identifier if _looks_like_cusip(security_identifier) else None,
                    weight=_decimal_percent_points(_first(raw, ["Market Value %", "Net Assets %"])),
                    shares=_decimal(_first(raw, ["Shares Held"])),
                    market_value=_decimal(_first(raw, ["Market Value"])),
                    currency="USD",
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if _clean(value) is not None},
                )
            )
        return rows, composition_date

    @staticmethod
    def _extract_as_of_date(prefix_rows: list[list[Any]]) -> date | None:
        text = " ".join(str(cell) for row in prefix_rows for cell in row if cell is not None)
        match = re.search(r"as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
        if not match:
            return None
        return FutureFundHoldingsAdapter._parse_date(match.group(1))

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _split_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
        text = _clean(raw_symbol)
        if text is None:
            return None, None
        normalized = " ".join(text.split())
        if normalized.endswith(" US") and re.fullmatch(r"[A-Z0-9. -]+ US", normalized):
            return normalized[:-3].strip(), "US"
        return normalized, None

    @staticmethod
    def _classify_row(
        *,
        raw_symbol: str | None,
        name: str | None,
        identifier: str | None,
        money_market_flag: str | None,
    ) -> tuple[str, str]:
        text = " ".join(part.upper() for part in (raw_symbol, name, identifier) if part)
        if money_market_flag or any(
            marker in text
            for marker in ("DOLLAR", "CASH", "BROKER", "RECEIVABLE", "PAYABLE", "SWEEP")
        ):
            return "cash", "cash"
        if "FUND" in text or "ETF" in text:
            return "security", "fund"
        return "security", "equity"


class CounterpointHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Counterpoint ETF holdings from issuer-published CSV feeds."""

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return f"https://counterpointfunds.com/etfdata/holdings_{normalized_symbol}.csv"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/csv,*/*")
        headers["Referer"] = "https://counterpointfunds.com/quantitative-equity-etf/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Counterpoint holdings CSV route is unavailable for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_counterpoint_csv(response.text, fund_symbol=symbol)
        if not rows:
            raise ValueError(f"Counterpoint holdings CSV did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_symbol_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_daily_holdings",
                "snapshot_provenance": "issuer_native_csv_feed",
            },
        )

    @classmethod
    def _parse_counterpoint_csv(
        cls,
        raw_csv: str,
        *,
        fund_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(csv.DictReader(StringIO(raw_csv.strip())), start=1):
            if composition_date is None:
                composition_date = cls._parse_as_of_date(item.get("asOfDate"))
            raw_symbol = _clean(item.get("securityTicker"))
            symbol, exchange = cls._split_security_ticker(raw_symbol)
            name = _clean(
                item.get("securityDescriptionLong")
                or item.get("securityDescriptionShort")
            )
            cusip = _clean(item.get("securityIdentifier"))
            holding_type = cls._classify_holding(item)
            row_type = "cash" if holding_type == "cash" else "security"
            if not any([symbol, name, cusip, item.get("marketValueBase"), item.get("netAssetsPercent")]):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    weight=_decimal(item.get("netAssetsPercent") or item.get("marketValuePercent")),
                    shares=_decimal(item.get("shares")),
                    market_value=_decimal(item.get("marketValueBase")),
                    currency=_clean(item.get("tradingCurrency")),
                    country=_clean(item.get("country")),
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{fund_symbol.strip().upper()}-{index}",
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if _clean(value) is not None
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_as_of_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    @staticmethod
    def _split_security_ticker(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if text is None:
            return None, None
        normalized = " ".join(text.split()).upper()
        parts = normalized.split()
        if len(parts) == 2 and re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", parts[0]):
            return parts[0], parts[1]
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", normalized):
            return normalized, None
        return None, None

    @staticmethod
    def _classify_holding(item: dict[str, Any]) -> str:
        text = " ".join(
            (_clean(item.get(key)) or "").upper()
            for key in (
                "securityTicker",
                "securityIdentifier",
                "securityDescriptionShort",
                "securityDescriptionLong",
                "segment",
                "category",
            )
        )
        if any(
            marker in text
            for marker in ("CASH", "SWEEP", "SHORT TERM INVESTMENTS", "RECEIVABLE", "PAYABLE")
        ):
            return "cash"
        if "OPTION" in text:
            return "option"
        if "BOND" in text or "FIXED INCOME" in text:
            return "fixed_income"
        return "equity"


class DeepwaterHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Deepwater ETF holdings from its server-rendered product page."""

    PRODUCT_PAGE_URLS: dict[str, str] = {
        "DBSC": "https://etfs.deepwatermgmt.com/dbsc-2/",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.PRODUCT_PAGE_URLS.get(symbol.strip().upper())

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            raise ValueError(f"Deepwater product page route is unavailable for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_product_page(response.text, fund_symbol=symbol)
        if not rows:
            raise ValueError(f"Deepwater product page did not expose holdings rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_product_page_holdings_table",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_holdings_table",
                "snapshot_provenance": "issuer_native_product_page",
                "product_page_url": product_page_url,
            },
        )

    @classmethod
    def _parse_product_page(
        cls,
        raw_html: str,
        *,
        fund_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        parser = _HTMLTablesParser()
        parser.feed(raw_html)
        composition_date = cls._extract_as_of_date(raw_html)
        for table in parser.tables:
            if not table:
                continue
            header_values = {str(value).strip().lower() for value in table[0] if _clean(value)}
            if not {"name", "symbol", "shares", "market value", "weightings (%)"} <= header_values:
                continue
            header = table[0]
            rows: list[CanonicalHoldingRow] = []
            for index, row in enumerate(table[1:], start=1):
                item = _row_dict(header, row)
                symbol = cls._normalize_symbol(_first(item, ["Symbol"]))
                name = _clean(_first(item, ["Name"]))
                if not any([symbol, name, _first(item, ["Shares"]), _first(item, ["Market Value"])]):
                    continue
                rows.append(
                    CanonicalHoldingRow(
                        symbol=symbol,
                        name=name,
                        weight=_decimal(_first(item, ["Weightings (%)", "Weightings"])),
                        shares=_decimal(_first(item, ["Shares"])),
                        market_value=_decimal(_first(item, ["Market Value"])),
                        currency="USD",
                        holding_type="equity",
                        row_type="security",
                        source_row_id=f"{fund_symbol.strip().upper()}-{index}",
                        extra_data={key: value for key, value in item.items() if _clean(value) is not None},
                    )
                )
            return rows, composition_date
        return [], composition_date

    @staticmethod
    def _normalize_symbol(value: Any) -> str | None:
        text = _clean(value)
        if text is None:
            return None
        normalized = " ".join(text.split()).upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", normalized):
            return normalized
        return None

    @staticmethod
    def _extract_as_of_date(raw_html: str) -> date | None:
        match = re.search(
            r"data-asof=[\"'](\d{4}-\d{2}-\d{2})[\"']",
            raw_html,
            re.IGNORECASE,
        ) or re.search(
            r"<time[^>]+datetime=[\"'](\d{4}-\d{2}-\d{2})[\"']",
            raw_html,
            re.IGNORECASE,
        )
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None


class ZacksHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Zacks ETF holdings from issuer-published holdings downloads."""

    HOLDINGS_URLS: dict[str, str] = {
        "ZECP": "https://www.zacksetfs.com/webservices/holdings.php",
        "SMIZ": "https://www.zacksetfs.com/webservices/smiz-holdings.php",
        "GROZ": "https://www.zacksetfs.com/webservices/groz-holdings.php",
        "QUIZ": "https://www.zacksetfs.com/webservices/quiz-holdings.php",
        "PRIZ": "https://www.zacksetfs.com/webservices/priz-holdings.php",
        "ZINC": "https://www.zacksetfs.com/webservices/zinc-holdings.php",
    }
    PRODUCT_PAGE_URLS: dict[str, str] = {
        symbol: f"https://www.zacksetfs.com/{symbol.lower()}.php"
        for symbol in ("ZECP", "SMIZ", "GROZ", "QUIZ", "PRIZ", "ZINC")
    }

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = (issuer_product_id or symbol).strip().upper()
        return self.HOLDINGS_URLS.get(normalized_symbol)

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.PRODUCT_PAGE_URLS.get(symbol.strip().upper())

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,text/plain,application/octet-stream,*/*")
        headers["Referer"] = "https://www.zacksetfs.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers or {},
        )
        if not resolved_source_url:
            raise ValueError(f"Zacks ETF holdings route is unavailable for {symbol}.")
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        composition_date, rows = self._parse_holdings_csv(response.text)
        if not rows:
            raise ValueError(f"Zacks holdings download did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_symbol_holdings_download",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_daily_holdings",
                "snapshot_provenance": "issuer_native_csv_export",
                "product_page_url": self.resolve_product_page_url(
                    symbol=symbol,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers or {},
                ),
            },
        )

    @staticmethod
    def _split_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
        text = _clean(raw_symbol)
        if not text:
            return None, None
        parts = text.split()
        if len(parts) == 2:
            return parts[0].upper(), parts[1].upper()
        return text.upper(), None

    def _parse_holdings_csv(self, raw_csv: str) -> tuple[date | None, list[CanonicalHoldingRow]]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        composition_date: date | None = None
        for row in table_rows[:5]:
            line = " ".join(str(cell) for cell in row if _clean(cell))
            match = re.search(r"as of\s+([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", line, re.I)
            if match:
                composition_date = datetime.strptime(match.group(1), "%m/%d/%Y").date()
                break
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows)
                if {"name", "security identifier", "symbol"}.issubset(
                    {str(cell).strip().lower() for cell in row}
                )
            ),
            None,
        )
        if header_index is None:
            return composition_date, []
        header = table_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        for row_index, raw_row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, raw_row)
            name = _clean(_first(raw, ["name"]))
            raw_symbol = _clean(_first(raw, ["symbol"]))
            symbol, exchange = self._split_symbol(raw_symbol)
            identifier = _clean(_first(raw, ["security identifier"]))
            cusip = identifier if _looks_like_cusip(identifier) else None
            isin = identifier if _looks_like_isin(identifier) else None
            sedol = identifier if _looks_like_sedol(identifier) else None
            row_type, holding_type = self._classify_holding(raw_symbol, name, identifier)
            if row_type == "cash":
                symbol = None
                exchange = None
            weight = _decimal_percent_points(_first(raw, ["net assets %"]))
            if weight is None:
                weight = _decimal_percent_points(_first(raw, ["market value %"]))
            if not any([name, symbol, cusip, isin, sedol, weight]):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    cusip=cusip,
                    isin=isin,
                    sedol=sedol,
                    weight=weight,
                    shares=_decimal(_first(raw, ["shares held"])),
                    market_value=_decimal(_first(raw, ["market value"])),
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(row_index),
                    extra_data={
                        "source_symbol": raw_symbol,
                        "market_price": _clean(_first(raw, ["market price"])),
                        **{key: value for key, value in raw.items() if value not in (None, "")},
                    },
                )
            )
        return composition_date, rows

    @staticmethod
    def _classify_holding(
        raw_symbol: str | None,
        name: str | None,
        identifier: str | None,
    ) -> tuple[str, str]:
        text = " ".join(part.upper() for part in (raw_symbol, name, identifier) if part)
        if any(marker in text for marker in ("CASH", "SWEEP", "MONEY MARKET")):
            return "cash", "cash"
        if " ETF" in text or "FUND" in text:
            return "security", "fund"
        if any(marker in text for marker in ("BOND", "TREASURY", "NOTE")):
            return "security", "fixed_income"
        return "security", "equity"


class HowardCapitalHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Howard Capital ETF holdings from issuer-hosted CSV files."""

    HOLDINGS_URLS: dict[str, str] = {
        "QQH": "https://howardcmfunds.com/wp-content/themes/cms/assets/hcm-defender-100-holdings.csv",
        "LGH": "https://howardcmfunds.com/wp-content/themes/cms/assets/hcm-defender-500-holdings.csv",
    }
    PRODUCT_PAGE_URLS: dict[str, str] = {
        "QQH": "https://howardcmfunds.com/fund/hcm-defender-100/",
        "LGH": "https://howardcmfunds.com/fund/hcm-defender-500/",
    }

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.HOLDINGS_URLS.get(symbol.strip().upper())

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.PRODUCT_PAGE_URLS.get(symbol.strip().upper())

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/csv,*/*")
        parsed_path = urlparse(source_url).path
        referer = "https://howardcmfunds.com/fund/"
        for symbol, url in self.HOLDINGS_URLS.items():
            if parsed_path == urlparse(url).path:
                referer = self.PRODUCT_PAGE_URLS[symbol]
                break
        headers["Referer"] = referer
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Howard Capital holdings route is unavailable for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_holdings_csv(response.text, fund_symbol=symbol)
        if not rows:
            raise ValueError(f"Howard Capital holdings CSV did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_symbol_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_daily_holdings",
                "snapshot_provenance": "issuer_native_csv_feed",
                "product_page_url": self.resolve_product_page_url(
                    symbol=symbol,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers or {},
                ),
            },
        )

    @classmethod
    def _parse_holdings_csv(
        cls,
        raw_csv: str,
        *,
        fund_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(csv.DictReader(StringIO(raw_csv.strip())), start=1):
            if composition_date is None:
                composition_date = cls._parse_as_of_date(item.get("asOfDate"))
            raw_symbol = _clean(item.get("securityTicker"))
            symbol, exchange = cls._split_security_ticker(raw_symbol)
            name = _clean(
                item.get("securityDescriptionLong")
                or item.get("securityDescriptionShort")
            )
            identifier = _clean(item.get("securityIdentifier"))
            row_type, holding_type = cls._classify_holding(
                raw_symbol=raw_symbol,
                name=name,
                identifier=identifier,
                segment=item.get("segment"),
                category=item.get("category"),
                sector=item.get("sector"),
            )
            if not any([symbol, name, identifier, item.get("marketValueBase"), item.get("netAssetsPercent")]):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type == "security" and holding_type not in {"cash", "option"} else None,
                    name=name,
                    cusip=identifier if _looks_like_cusip(identifier) else None,
                    weight=_decimal(item.get("netAssetsPercent") or item.get("marketValuePercent")),
                    shares=_decimal(item.get("shares")),
                    market_value=_decimal(item.get("marketValueBase")),
                    currency=_clean(item.get("tradingCurrency")),
                    country=_clean(item.get("country")),
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{fund_symbol.strip().upper()}-{index}",
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if _clean(value) is not None
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_as_of_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    @staticmethod
    def _split_security_ticker(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if text is None:
            return None, None
        normalized = " ".join(text.split()).upper()
        parts = normalized.split()
        if len(parts) == 2 and re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", parts[0]):
            return parts[0], parts[1]
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", normalized):
            return normalized, None
        return None, None

    @staticmethod
    def _classify_holding(
        *,
        raw_symbol: str | None,
        name: str | None,
        identifier: str | None,
        segment: str | None,
        category: str | None,
        sector: str | None,
    ) -> tuple[str, str]:
        text = " ".join(
            part.upper()
            for part in (raw_symbol, name, identifier, segment, category, sector)
            if part
        )
        if any(
            marker in text
            for marker in ("CASH", "SWEEP", "RECEIVABLE", "PAYABLE", "DOLLAR")
        ):
            return "cash", "cash"
        if "OPTION" in text:
            return "security", "option"
        if "EXCHANGE-TRADED FUNDS" in text or " ETF" in text or "FUND" in text:
            return "security", "fund"
        if any(marker in text for marker in ("BOND", "TREASURY", "FIXED INCOME")):
            return "security", "fixed_income"
        return "security", "equity"


class AnfieldHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Anfield ETF holdings from issuer product-page CSV exports."""

    PRODUCT_PAGE_URLS: dict[str, str] = {
        "AEMS": "https://anfieldfunds.com/our-funds/anfield-enhanced-market-strategy-etf/",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.PRODUCT_PAGE_URLS.get(symbol.strip().upper())

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/csv,*/*")
        headers["Referer"] = "https://anfieldfunds.com/our-funds/anfield-enhanced-market-strategy-etf/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = (
            source_url
            if source_url and source_url.lower().split("?", 1)[0].endswith(".csv")
            else None
        )
        page_url = None
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if not resolved_source_url:
                page_url = source_url or self.resolve_product_page_url(
                    symbol=symbol,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers or {},
                )
                if not page_url:
                    raise ValueError(f"Anfield product page route is unavailable for {symbol}.")
                page_response = await client.get(
                    page_url,
                    headers=_issuer_page_request_headers(accept="text/html,*/*"),
                    follow_redirects=True,
                )
                page_response.raise_for_status()
                resolved_source_url = self._discover_holdings_csv(
                    page_response.text,
                    base_url=str(page_response.url),
                )
                if not resolved_source_url:
                    raise ValueError(f"Anfield product page did not expose a holdings CSV for {symbol}.")

            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_holdings_csv(response.text, fund_symbol=symbol)
        if not rows:
            raise ValueError(f"Anfield holdings CSV did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_product_page_discovered_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_daily_holdings",
                "snapshot_provenance": "issuer_native_csv_export",
                "product_page_url": page_url,
            },
        )

    @staticmethod
    def _discover_holdings_csv(page_text: str, *, base_url: str) -> str | None:
        candidates: list[str] = []
        for match in re.finditer(
            r"""(?P<url>(?:https?:)?//[^"'<>]+/csv/holdings-[^"'<>]+\.csv|/csv/holdings-[^"'<>]+\.csv)""",
            page_text,
            flags=re.I,
        ):
            raw_url = html.unescape(match.group("url")).replace("\\/", "/")
            candidates.append(urljoin(base_url, raw_url))
        return candidates[0] if candidates else None

    @classmethod
    def _parse_holdings_csv(
        cls,
        raw_csv: str,
        *,
        fund_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None
        composition_date = cls._extract_as_of_date(table_rows[:5])
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {cell.strip().lower() for cell in row}
                >= {"name", "security identifier", "symbol"}
            ),
            None,
        )
        if header_index is None:
            return [], composition_date
        header = table_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            raw_symbol = _clean(_first(raw, ["Symbol"]))
            symbol, exchange = cls._split_symbol(raw_symbol)
            name = _clean(_first(raw, ["Name"]))
            security_identifier = _clean(_first(raw, ["Security Identifier"]))
            row_type, holding_type = cls._classify_row(
                raw_symbol=raw_symbol,
                name=name,
                identifier=security_identifier,
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=security_identifier if _looks_like_cusip(security_identifier) else None,
                    weight=_decimal_percent_points(_first(raw, ["Market Value %", "Net Assets %"])),
                    shares=_decimal(_first(raw, ["Shares Held"])),
                    market_value=_decimal(_first(raw, ["Market Value"])),
                    currency="USD",
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{fund_symbol.strip().upper()}-{index}",
                    extra_data={key: value for key, value in raw.items() if _clean(value) is not None},
                )
            )
        return rows, composition_date

    @staticmethod
    def _extract_as_of_date(prefix_rows: list[list[Any]]) -> date | None:
        text = " ".join(str(cell) for row in prefix_rows for cell in row if cell is not None)
        match = re.search(r"as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _split_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
        text = _clean(raw_symbol)
        if text is None:
            return None, None
        normalized = " ".join(text.split()).upper()
        if normalized.endswith(" US") and re.fullmatch(r"[A-Z0-9. -]+ US", normalized):
            return normalized[:-3].strip(), "US"
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", normalized):
            return normalized, None
        return None, None

    @staticmethod
    def _classify_row(
        *,
        raw_symbol: str | None,
        name: str | None,
        identifier: str | None,
    ) -> tuple[str, str]:
        text = " ".join(part.upper() for part in (raw_symbol, name, identifier) if part)
        if any(
            marker in text
            for marker in (
                "USD",
                "US DOLLAR",
                "CASH",
                "FUTURE",
                "RECEIVABLE",
                "PAYABLE",
                "RECPAY",
                "SWEEP",
            )
        ):
            return "cash", "cash"
        if "FUND" in text or "ETF" in text:
            return "security", "fund"
        return "security", "equity"


class CastleArkHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch CastleArk ETF holdings from issuer-hosted daily text files."""

    HOLDINGS_URL_TEMPLATE = (
        "http://castleark-etfs.com/assets/data/SEI_CRK_Tradedate_Holdings_{date_mmddyyyy}.txt"
    )
    PRODUCT_PAGE_URLS: dict[str, str] = {
        "CARK": "http://castleark-etfs.com",
    }

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "product_id"),
            source_url=_identifier(identifiers, *self.source_url_aliases),
            identifiers=identifiers,
        )
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.9000"),
            status="ready",
            reason="CastleArk publishes current ETF holdings in issuer-hosted daily text files.",
            source_url=source_url,
            issuer_product_id=_identifier(identifiers, "issuer_product_id", "product_id"),
        )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self._source_url_for_date(date.today())

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.PRODUCT_PAGE_URLS.get(symbol.strip().upper())

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/plain,text/csv,*/*")
        headers["Referer"] = "http://castleark-etfs.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        requested_symbol = symbol.strip().upper()
        candidate_urls = (
            [source_url]
            if source_url
            else [self._source_url_for_date(date.today() - timedelta(days=offset)) for offset in range(15)]
        )
        response = None
        resolved_source_url = None
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            for candidate_url in candidate_urls:
                if not candidate_url:
                    continue
                candidate_response = await client.get(
                    candidate_url,
                    headers=self.source_request_headers(source_url=candidate_url),
                    follow_redirects=True,
                )
                if candidate_response.status_code == 404 and not source_url:
                    continue
                candidate_response.raise_for_status()
                response = candidate_response
                resolved_source_url = str(candidate_response.url)
                break
        if response is None or resolved_source_url is None:
            raise ValueError(f"CastleArk holdings file was unavailable for {requested_symbol}.")

        rows, composition_date = self._parse_holdings_text(
            response.text,
            requested_symbol=requested_symbol,
        )
        if not rows:
            raise ValueError(f"CastleArk holdings file did not expose rows for {requested_symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=resolved_source_url,
            source_identifier=issuer_product_id or requested_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "pipe_delimited_text",
                "route_resolution": "issuer_public_daily_holdings_text",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_daily_holdings",
                "snapshot_provenance": "issuer_native_daily_holdings_text",
                "product_page_url": self.resolve_product_page_url(
                    symbol=requested_symbol,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers or {},
                ),
            },
        )

    @classmethod
    def _source_url_for_date(cls, source_date: date) -> str:
        return cls.HOLDINGS_URL_TEMPLATE.format(date_mmddyyyy=source_date.strftime("%m%d%Y"))

    @classmethod
    def _parse_holdings_text(
        cls,
        raw_text: str,
        *,
        requested_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_text.strip()), delimiter="|")
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None
        header = table_rows[0]
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, row in enumerate(table_rows[1:], start=1):
            raw = _row_dict(header, row)
            fund_ticker = (_clean(_first(raw, ["fund_ticker"])) or "").upper()
            if fund_ticker and fund_ticker != requested_symbol:
                continue
            if composition_date is None:
                composition_date = cls._parse_row_date(_first(raw, ["date"]))

            raw_symbol = _clean(_first(raw, ["security_ticker"]))
            name = _clean(_first(raw, ["security_description"]))
            security_group = _clean(_first(raw, ["security_group"]))
            security_type = _clean(_first(raw, ["security_type"]))
            row_type, holding_type = cls._classify_row(
                raw_symbol=raw_symbol,
                name=name,
                security_group=security_group,
                security_type=security_type,
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=raw_symbol.strip().upper() if raw_symbol and row_type != "cash" else None,
                    name=name,
                    cusip=(
                        _first(raw, ["security_cusip"])
                        if _looks_like_cusip(_first(raw, ["security_cusip"]))
                        else None
                    ),
                    isin=(
                        _first(raw, ["security_isin"])
                        if _looks_like_isin(_first(raw, ["security_isin"]))
                        else None
                    ),
                    sedol=(
                        _first(raw, ["security_sedol"])
                        if _looks_like_sedol(_first(raw, ["security_sedol"]))
                        else None
                    ),
                    weight=_decimal_percent_points(_first(raw, ["percent_of_net_assets"])),
                    shares=_decimal(_first(raw, ["quantity"])),
                    market_value=_decimal(_first(raw, ["market_value"])),
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{requested_symbol}-{index}",
                    extra_data={key: value for key, value in raw.items() if _clean(value) is not None},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_row_date(value: str | None) -> date | None:
        cleaned = _clean(value)
        if not cleaned:
            return None
        try:
            return datetime.strptime(cleaned, "%m/%d/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _classify_row(
        *,
        raw_symbol: str | None,
        name: str | None,
        security_group: str | None,
        security_type: str | None,
    ) -> tuple[str, str]:
        text = " ".join(
            part.upper()
            for part in (raw_symbol, name, security_group, security_type)
            if part
        )
        if "CASH" in text or "RECEIVABLE" in text or "PAYABLE" in text:
            return "cash", "cash"
        if "ETF" in text or "FUND" in text:
            return "security", "fund"
        if "BOND" in text or "FIXED" in text or "TREASURY" in text:
            return "security", "fixed_income"
        return "security", "equity"


class BrookmontHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Brookmont/Brookstone ETF holdings from public product-page CSV exports."""

    PRODUCT_PAGE_URLS: dict[str, str] = {
        "BAMA": "https://www.brookstoneam.com/brookstone-active-etf",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.PRODUCT_PAGE_URLS.get(symbol.strip().upper())

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/csv,*/*")
        headers["Referer"] = "https://www.brookstoneam.com/brookstone-active-etf"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = (
            source_url
            if source_url and source_url.lower().split("?", 1)[0].endswith(".csv")
            else None
        )
        page_url = None
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if not resolved_source_url:
                page_url = source_url or self.resolve_product_page_url(
                    symbol=symbol,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers or {},
                )
                if not page_url:
                    raise ValueError(f"Brookmont product page route is unavailable for {symbol}.")
                page_response = await client.get(
                    page_url,
                    headers=_issuer_page_request_headers(accept="text/html,*/*"),
                    follow_redirects=True,
                )
                page_response.raise_for_status()
                resolved_source_url = self._discover_holdings_csv(
                    page_response.text,
                    base_url=str(page_response.url),
                )
                if not resolved_source_url:
                    raise ValueError(
                        f"Brookmont product page did not expose a holdings CSV for {symbol}."
                    )

            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_holdings_csv(response.text, fund_symbol=symbol)
        if not rows:
            raise ValueError(f"Brookmont holdings CSV did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_product_page_all_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_daily_holdings",
                "snapshot_provenance": "issuer_native_csv_export",
                "product_page_url": page_url,
            },
        )

    @staticmethod
    def _discover_holdings_csv(page_text: str, *, base_url: str) -> str | None:
        candidates: list[str] = []
        for match in re.finditer(
            r"""(?P<url>(?:https?:)?//[^"'<>]+/[^"'<>]*_all_holdings\.csv|/[^"'<>]*_all_holdings\.csv)""",
            page_text,
            flags=re.I,
        ):
            raw_url = html.unescape(match.group("url")).replace("\\/", "/")
            candidates.append(urljoin(base_url, raw_url))
        return candidates[0] if candidates else None

    @classmethod
    def _parse_holdings_csv(
        cls,
        raw_csv: str,
        *,
        fund_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        if not table_rows:
            return [], None
        composition_date = cls._extract_as_of_date(table_rows[:5])
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows[:20])
                if {cell.strip().lower() for cell in row}
                >= {"name", "security identifier", "symbol", "net assets %"}
            ),
            None,
        )
        if header_index is None:
            return [], composition_date
        header = table_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        for index, row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, row)
            raw_symbol = _clean(_first(raw, ["Symbol"]))
            symbol, exchange = cls._split_symbol(raw_symbol)
            name = _clean(_first(raw, ["Name"]))
            security_identifier = _clean(_first(raw, ["Security Identifier"]))
            row_type, holding_type = cls._classify_row(
                raw_symbol=raw_symbol,
                name=name,
                identifier=security_identifier,
            )
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=security_identifier if _looks_like_cusip(security_identifier) else None,
                    weight=_decimal_percent_points(_first(raw, ["Market Value %", "Net Assets %"])),
                    shares=_decimal(_first(raw, ["Shares Held"])),
                    market_value=_decimal(_first(raw, ["Market Value"])),
                    currency="USD",
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{fund_symbol.strip().upper()}-{index}",
                    extra_data={key: value for key, value in raw.items() if _clean(value) is not None},
                )
            )
        return rows, composition_date

    @staticmethod
    def _extract_as_of_date(prefix_rows: list[list[Any]]) -> date | None:
        text = " ".join(str(cell) for row in prefix_rows for cell in row if cell is not None)
        match = re.search(r"as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _split_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
        text = _clean(raw_symbol)
        if text is None:
            return None, None
        normalized = " ".join(text.split()).upper()
        if normalized.endswith(" US") and re.fullmatch(r"[A-Z0-9. -]+ US", normalized):
            return normalized[:-3].strip(), "US"
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", normalized):
            return normalized, None
        return None, None

    @staticmethod
    def _classify_row(
        *,
        raw_symbol: str | None,
        name: str | None,
        identifier: str | None,
    ) -> tuple[str, str]:
        text = " ".join(part.upper() for part in (raw_symbol, name, identifier) if part)
        if any(
            marker in text
            for marker in (
                "USD",
                "US DOLLAR",
                "CASH",
                "FUTURE",
                "RECEIVABLE",
                "PAYABLE",
                "RECPAY",
                "SWEEP",
            )
        ):
            return "cash", "cash"
        if any(marker in text for marker in ("FUND", "ETF", "SPDR", "ISHARES", "STATE STREET")):
            return "security", "fund"
        return "security", "equity"


class MadisonHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Madison ETF holdings from its public multi-account holdings CSV."""

    HOLDINGS_URL = "https://madisonfunds.com/data/etf/MadisonAdvWeb.40M3.M3_ETF_Holdings.csv"

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        return explicit or self.HOLDINGS_URL

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/csv,*/*")
        headers["Referer"] = "https://madisonfunds.com/etfs/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Madison holdings route is unavailable for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_holdings_csv(response.text, symbol=symbol)
        if not rows:
            raise ValueError(f"Madison holdings CSV did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_aggregate_account_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_daily_holdings",
                "snapshot_provenance": "issuer_native_csv_feed",
            },
        )

    @classmethod
    def _parse_holdings_csv(
        cls,
        raw_csv: str,
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        normalized_symbol = symbol.strip().upper()
        reader = csv.DictReader(StringIO(raw_csv.strip()))
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for source_index, item in enumerate(reader, start=1):
            account = (_clean(item.get("Account")) or "").upper()
            if account != normalized_symbol:
                continue
            if composition_date is None:
                composition_date = cls._parse_composition_date(item.get("Date"))

            raw_symbol = _clean(item.get("StockTicker"))
            name = _clean(item.get("SecurityName"))
            cusip_value = _clean(item.get("CUSIP"))
            row_type, holding_type = cls._classify_row(
                raw_symbol=raw_symbol,
                name=name,
                money_market_flag=item.get("MoneyMarketFlag"),
            )
            symbol_value = (
                cls._normalize_symbol(raw_symbol)
                if row_type == "security" and holding_type != "option"
                else None
            )
            cusip = cusip_value if _looks_like_cusip(cusip_value) else None

            if not any([symbol_value, name, cusip, item.get("Weightings"), item.get("MarketValue")]):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value,
                    name=name,
                    cusip=cusip,
                    isin=None,
                    sedol=None,
                    weight=_decimal(item.get("Weightings")),
                    shares=_decimal(item.get("Shares")),
                    market_value=_decimal(item.get("MarketValue")),
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{normalized_symbol}-{source_index}",
                    extra_data={
                        "source_symbol": raw_symbol,
                        "account": account,
                        "price": _clean(item.get("Price")),
                        "net_assets": _clean(item.get("NetAssets")),
                        "shares_outstanding": _clean(item.get("SharesOutstanding")),
                        **{key: value for key, value in item.items() if _clean(value) is not None},
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_composition_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _normalize_symbol(value: str | None) -> str | None:
        text = _clean(value)
        if text is None:
            return None
        normalized = text.strip().upper()
        if " " in normalized or _looks_like_cusip(normalized):
            return None
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,11}", normalized):
            return normalized
        return None

    @staticmethod
    def _classify_row(
        *,
        raw_symbol: str | None,
        name: str | None,
        money_market_flag: Any,
    ) -> tuple[str, str]:
        flag = (_clean(money_market_flag) or "").upper()
        text = " ".join(part.upper() for part in (raw_symbol, name) if part)
        if flag == "Y" or any(
            marker in text
            for marker in (
                "CASH",
                "MMDA",
                "MONEY MARKET",
                "SWEEP",
                "TREASURY BILL",
            )
        ):
            return "cash", "cash"
        if re.search(r"\d{6}[CP]\d{6,8}", text) or re.search(
            r"\b\d{2}/\d{2}/\d{2,4}\s+[CP]\d+",
            text,
        ):
            return "security", "option"
        return "security", "equity"


class LeutholdHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Leuthold ETF holdings from issuer-rendered product-page tables."""

    PRODUCT_PAGE_URL_TEMPLATE = "https://funds.leutholdgroup.com/etf/{symbol_upper}"

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.PRODUCT_PAGE_URL_TEMPLATE.format(symbol_upper=symbol.strip().upper())

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            raise ValueError(f"Leuthold product page route is unavailable for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_product_page(response.text, fund_symbol=symbol)
        if not rows:
            raise ValueError(f"Leuthold product page did not expose holdings rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_product_page_holdings_table",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_holdings_table",
                "snapshot_provenance": "issuer_native_product_page",
                "product_page_url": product_page_url,
            },
        )

    @classmethod
    def _parse_product_page(
        cls,
        raw_html: str,
        *,
        fund_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        parser = _HTMLTablesParser()
        parser.feed(raw_html)
        composition_date = cls._extract_as_of_date(raw_html)
        for table in parser.tables:
            if not table:
                continue
            header_values = {str(value).strip().lower() for value in table[0] if _clean(value)}
            if not {
                "percentage of net assets",
                "name",
                "identifier (cusip)",
                "shares held",
                "market value",
            } <= header_values:
                continue
            header = table[0]
            rows: list[CanonicalHoldingRow] = []
            for index, row in enumerate(table[1:], start=1):
                item = _row_dict(header, row)
                name = _clean(_first(item, ["Name"]))
                identifier = _clean(_first(item, ["Identifier (Cusip)", "Identifier"]))
                symbol, cusip = cls._parse_identifier(identifier)
                row_type, holding_type = cls._classify_row(symbol=symbol, name=name)
                if row_type != "security":
                    symbol = None
                    cusip = None
                if not any([symbol, name, cusip, _first(item, ["Percentage of Net Assets"]), _first(item, ["Market Value"])]):
                    continue
                rows.append(
                    CanonicalHoldingRow(
                        symbol=symbol,
                        name=name,
                        cusip=cusip,
                        weight=_decimal(_first(item, ["Percentage of Net Assets"])),
                        shares=_decimal(_first(item, ["Shares Held"])),
                        market_value=_decimal(_first(item, ["Market Value"])),
                        currency="USD",
                        holding_type=holding_type,
                        row_type=row_type,
                        source_row_id=f"{fund_symbol.strip().upper()}-{index}",
                        extra_data={
                            "identifier": identifier,
                            **{key: value for key, value in item.items() if _clean(value) is not None},
                        },
                    )
                )
            return rows, composition_date
        return [], composition_date

    @staticmethod
    def _parse_identifier(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if text is None:
            return None, None
        match = re.match(r"^\s*([A-Z0-9.=-]{1,12})\s*\(([0-9A-Z]{9})\)\s*$", text.strip().upper())
        if match:
            symbol = match.group(1)
            cusip = match.group(2)
            return symbol, cusip if _looks_like_cusip(cusip) else None
        if _looks_like_cusip(text):
            return None, text.strip().upper()
        normalized = text.strip().upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,11}", normalized):
            return normalized, None
        return None, None

    @staticmethod
    def _classify_row(*, symbol: str | None, name: str | None) -> tuple[str, str]:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if any(marker in text for marker in ("CASH", "MONEY MARKET", "TREASURY BILL", "U.S. DOLLAR")):
            return "cash", "cash"
        if "ETF" in text or "FUND" in text:
            return "security", "fund"
        if "BOND" in text or "TREASURY" in text:
            return "security", "fixed_income"
        return "security", "equity"

    @staticmethod
    def _extract_as_of_date(raw_html: str) -> date | None:
        for pattern in (
            r"ETF Summary\s+As of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            r"Fund Prices\s+as of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            r"As of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        ):
            match = re.search(pattern, raw_html, re.IGNORECASE)
            if not match:
                continue
            try:
                return datetime.strptime(match.group(1), "%B %d, %Y").date()
            except ValueError:
                continue
        return None


class PointBridgeHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Point Bridge MAGA ETF holdings from its public holdings table."""

    HOLDINGS_PAGE_URLS: dict[str, str] = {
        "MAGA": "https://www.investpolitically.com/maga-holdings/",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.HOLDINGS_PAGE_URLS.get(symbol.strip().upper())

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not page_url:
            raise ValueError(f"Point Bridge holdings route is unavailable for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_holdings_page(response.text, fund_symbol=symbol)
        if not rows:
            raise ValueError(f"Point Bridge holdings page did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_holdings_page_tablepress_table",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_holdings_table",
                "snapshot_provenance": "issuer_native_product_page",
                "product_page_url": page_url,
            },
        )

    @classmethod
    def _parse_holdings_page(
        cls,
        raw_html: str,
        *,
        fund_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        parser = _HTMLTablesParser()
        parser.feed(raw_html)
        for table in parser.tables:
            if not table:
                continue
            header_values = {str(value).strip().lower() for value in table[0] if _clean(value)}
            if not {"stockticker", "cusip", "securityname", "shares", "weightings", "date"} <= header_values:
                continue
            header = table[0]
            rows: list[CanonicalHoldingRow] = []
            composition_date: date | None = None
            for index, row in enumerate(table[1:], start=1):
                item = _row_dict(header, row)
                if composition_date is None:
                    composition_date = cls._parse_date(_first(item, ["Date"]))
                raw_symbol = _clean(_first(item, ["StockTicker"]))
                name = _clean(_first(item, ["SecurityName"]))
                cusip_value = _clean(_first(item, ["CUSIP"]))
                row_type, holding_type = cls._classify_row(symbol=raw_symbol, name=name)
                symbol_value = cls._normalize_symbol(raw_symbol) if row_type == "security" else None
                cusip = cusip_value.strip().upper() if _looks_like_cusip(cusip_value) else None
                if not any([symbol_value, name, cusip, _first(item, ["Shares"]), _first(item, ["Weightings"])]):
                    continue
                rows.append(
                    CanonicalHoldingRow(
                        symbol=symbol_value,
                        name=name,
                        cusip=cusip,
                        weight=_decimal(_first(item, ["Weightings"])),
                        shares=_decimal(_first(item, ["Shares"])),
                        currency="USD",
                        holding_type=holding_type,
                        row_type=row_type,
                        source_row_id=f"{fund_symbol.strip().upper()}-{index}",
                        extra_data={key: value for key, value in item.items() if _clean(value) is not None},
                    )
                )
            return rows, composition_date
        return [], None

    @staticmethod
    def _normalize_symbol(value: str | None) -> str | None:
        text = _clean(value)
        if text is None:
            return None
        normalized = text.strip().upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,11}", normalized):
            return normalized
        return None

    @staticmethod
    def _classify_row(*, symbol: str | None, name: str | None) -> tuple[str, str]:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if any(marker in text for marker in ("CASH", "MONEY MARKET", "TREASURY BILL", "U.S. DOLLAR")):
            return "cash", "cash"
        if "ETF" in text or "FUND" in text:
            return "security", "fund"
        return "security", "equity"

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None


class DiamondHillHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Diamond Hill ETF holdings from issuer-published CSV files."""

    HOLDINGS_URL_TEMPLATE = (
        "https://www.diamond-hill.com/sitefiles/live/documents/etfs/holdings/"
        "diamond-hill-{symbol_upper}-holdings.csv"
    )

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return self.HOLDINGS_URL_TEMPLATE.format(symbol_upper=symbol.strip().upper())

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"{self.adapter_key} needs a Diamond Hill holdings URL for {symbol}.")
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=_holdings_request_headers(accept="text/csv,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        composition_date, rows = self._parse_holdings_csv(response.text)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            source_url=resolved_source_url,
            source_identifier=issuer_product_id,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_symbol_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _split_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
        text = _clean(raw_symbol)
        if not text:
            return None, None
        parts = text.split()
        if len(parts) == 2:
            return parts[0].upper(), parts[1].upper()
        return text.upper(), None

    def _parse_holdings_csv(self, raw_csv: str) -> tuple[date | None, list[CanonicalHoldingRow]]:
        table_rows = [
            row
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        composition_date: date | None = None
        for row in table_rows[:5]:
            line = " ".join(str(cell) for cell in row if _clean(cell))
            match = re.search(r"as of\s+([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", line, re.I)
            if match:
                composition_date = datetime.strptime(match.group(1), "%m/%d/%Y").date()
                break
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows)
                if {"name", "security identifier", "symbol"}.issubset(
                    {str(cell).strip().lower() for cell in row}
                )
            ),
            None,
        )
        if header_index is None:
            return composition_date, []
        header = table_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        for row_index, raw_row in enumerate(table_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, raw_row)
            name = _clean(_first(raw, ["name"]))
            raw_symbol = _clean(_first(raw, ["symbol"]))
            symbol, exchange = self._split_symbol(raw_symbol)
            identifier = _clean(_first(raw, ["security identifier"]))
            cusip = identifier if _looks_like_cusip(identifier) else None
            isin = identifier if _looks_like_isin(identifier) else None
            sedol = identifier if _looks_like_sedol(identifier) else None
            row_type = "cash" if (
                symbol is None
                and (name or "").lower().startswith(("state st govt mm", "cash"))
            ) else "security"
            holding_type = "cash" if row_type == "cash" else "equity"
            if row_type == "cash":
                symbol = None
                exchange = None
            weight = _decimal_percent_points(_first(raw, ["net assets %"]))
            if weight is None:
                weight = _decimal_percent_points(_first(raw, ["market value %"]))
            if not any([name, symbol, cusip, isin, sedol, weight]):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    cusip=cusip,
                    isin=isin,
                    sedol=sedol,
                    weight=weight,
                    shares=_decimal(_first(raw, ["shares held"])),
                    market_value=_decimal(_first(raw, ["market value"])),
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(row_index),
                    extra_data={
                        "source_symbol": raw_symbol,
                        "market_price": _clean(_first(raw, ["market price"])),
                        **{key: value for key, value in raw.items() if value not in (None, "")},
                    },
                )
            )
        return composition_date, rows


class FirstEagleHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse First Eagle ETF holdings from issuer-rendered product pages."""

    PRODUCT_PAGE_SLUGS: dict[str, str] = {
        "FEGE": "global-equity-etf",
        "FEOE": "overseas-equity-etf",
        "USFE": "usfe-us-equity-etf",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        identifiers = identifiers or {}
        slug = (
            _identifier(identifiers, "first_eagle_product_slug", "product_slug", "fund_slug")
            or issuer_product_id
            or self.PRODUCT_PAGE_SLUGS.get(normalized_symbol)
        )
        if not slug:
            return None
        return f"https://www.firsteagle.com/funds/{slug}"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            raise ValueError(f"First Eagle needs an ETF product page for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=self.source_request_headers(source_url=product_page_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_first_eagle_product_page(response.text)
        if not rows:
            raise ValueError(f"First Eagle product page did not expose holdings rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(getattr(response, "url", product_page_url)),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_product_page_holdings_table",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="text/html,*/*")
        headers["Referer"] = "https://www.firsteagle.com/active-equity-etfs"
        return headers

    @classmethod
    def _parse_first_eagle_product_page(
        cls,
        raw_html: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        parser = _HTMLTablesParser()
        parser.feed(raw_html)
        required_headers = {
            "stock ticker",
            "cusip/other",
            "security name",
            "shares",
            "price",
            "market value",
            "weightings",
        }
        table: list[list[str]] = []
        for candidate in parser.tables:
            for row in candidate[:30]:
                normalized_row = {str(value).strip().lower() for value in row if _clean(value)}
                if required_headers <= normalized_row:
                    table = candidate
                    break
            if table:
                break

        normalized_rows: list[CanonicalHoldingRow] = []
        if not table:
            return normalized_rows, cls._extract_composition_date(raw_html)

        header_index = next(
            (
                index
                for index, row in enumerate(table[:30])
                if required_headers <= {str(value).strip().lower() for value in row if _clean(value)}
            ),
            None,
        )
        if header_index is None:
            return normalized_rows, cls._extract_composition_date(raw_html)

        header = table[header_index]
        for source_index, raw_values in enumerate(table[header_index + 1 :], start=1):
            raw_row = _row_dict(header, raw_values)
            name = _clean(_first(raw_row, ["security name"]))
            ticker = _clean(_first(raw_row, ["stock ticker"]))
            if not (name or ticker):
                continue
            symbol, exchange = cls._split_ticker(ticker)
            identifier = _clean(_first(raw_row, ["cusip/other"]))
            cusip = identifier if _looks_like_cusip(identifier) else None
            sedol = (
                identifier.strip().upper()
                if identifier and cusip is None and re.fullmatch(r"[A-Z0-9]{6,7}", identifier.strip().upper())
                else None
            )
            holding_type = "equity"
            row_type = "security"
            if (name or "").strip().lower() == "cash & other":
                symbol = None
                exchange = None
                cusip = None
                sedol = None
                holding_type = "cash"
                row_type = "cash"

            normalized_rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    cusip=cusip,
                    isin=None,
                    sedol=sedol,
                    weight=_decimal(_first(raw_row, ["weightings"])),
                    shares=_decimal(_first(raw_row, ["shares"])),
                    market_value=_decimal(_first(raw_row, ["market value"])),
                    currency="USD",
                    country=None,
                    exchange=exchange,
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(source_index),
                    extra_data=raw_row,
                )
            )
        return normalized_rows, cls._extract_composition_date(raw_html)

    @staticmethod
    def _split_ticker(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if not text:
            return None, None
        normalized = text.strip().upper()
        if normalized in {"CASH&OTHER", "CASH", "USD"}:
            return None, None
        parts = normalized.split()
        if len(parts) == 2 and re.fullmatch(r"[A-Z0-9.=-]{1,12}", parts[0]):
            return parts[0], parts[1]
        return normalized, None

    @staticmethod
    def _extract_composition_date(raw_html: str) -> date | None:
        match = re.search(
            r"ETF\s+Holdings\s+As\s+of\s+([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})",
            raw_html,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%b %d, %Y").date()
        except ValueError:
            return None


class DavisHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Davis ETFs holdings from issuer CSV download routes."""

    PRODUCT_SLUGS: dict[str, str] = {
        "DUSA": "us_equity",
        "DINT": "international",
        "DWLD": "worldwide",
        "DFNL": "financial",
    }
    PRODUCT_PAGE_BASE = "https://www.davisetfs.com"

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        identifiers = identifiers or {}
        slug = (
            _identifier(identifiers, "davis_product_slug", "product_slug", "issuer_product_id")
            or issuer_product_id
            or self.PRODUCT_SLUGS.get(normalized_symbol)
        )
        if not slug:
            return None
        return f"{self.PRODUCT_PAGE_BASE}/etfs/{slug}/holdings_download"

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        slug = (
            issuer_product_id
            or _identifier(identifiers or {}, "davis_product_slug", "product_slug")
            or self.PRODUCT_SLUGS.get(normalized_symbol)
        )
        if not slug:
            return None
        return f"{self.PRODUCT_PAGE_BASE}/etfs/{slug}"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(accept="text/csv,application/csv,*/*")
        headers["Referer"] = "https://www.davisetfs.com/etfs"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Davis ETFs needs a product slug for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_davis_csv(response.text)
        if not rows:
            raise ValueError(f"Davis ETFs holdings download did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={
                "source_format": "csv",
                "product_slug": self._slug_for_symbol(symbol, issuer_product_id, identifiers or {}),
            },
            source_url=str(getattr(response, "url", resolved_source_url)),
            source_identifier=issuer_product_id or self.PRODUCT_SLUGS.get(symbol.strip().upper()),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_holdings_download_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_davis_csv(cls, raw_csv: str) -> tuple[list[CanonicalHoldingRow], date | None]:
        csv_rows = list(csv.reader(StringIO(raw_csv)))
        if len(csv_rows) < 2:
            return [], None
        composition_date = cls._extract_composition_date(csv_rows[0][0] if csv_rows[0] else None)
        header = [cell.strip() for cell in csv_rows[1]]
        rows: list[CanonicalHoldingRow] = []
        for index, raw_values in enumerate(csv_rows[2:], start=1):
            if not raw_values or not any(_clean(value) for value in raw_values):
                continue
            raw = {header[column_index].strip().lower(): value for column_index, value in enumerate(raw_values[:len(header)])}
            name = _clean(raw.get("name"))
            ticker = _clean(raw.get("ticker"))
            symbol, exchange = cls._split_ticker(ticker)
            cusip = _clean(raw.get("cusip"))
            if not any([name, symbol, cusip, raw.get("weighting (%)")]):
                continue
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    weight=_decimal_percent_points(raw.get("weighting (%)")),
                    shares=_decimal(raw.get("shares")),
                    market_value=_decimal(raw.get("market value ($)")),
                    country=_clean(raw.get("country")),
                    exchange=exchange,
                    holding_type="equity",
                    row_type="security",
                    source_row_id=str(index),
                    extra_data={
                        "raw_ticker": ticker,
                        **{
                            f"extra_column_{extra_index}": value
                            for extra_index, value in enumerate(raw_values[len(header):], start=1)
                            if _clean(value)
                        },
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _extract_composition_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        match = re.search(r"\bas\s+of\s+(?P<value>\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)
        if not match:
            return None
        raw_value = match.group("value")
        for date_format in ("%m/%d/%y", "%m/%d/%Y"):
            try:
                return datetime.strptime(raw_value, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _split_ticker(value: str | None) -> tuple[str | None, str | None]:
        text = _clean(value)
        if not text:
            return None, None
        parts = text.split()
        if len(parts) == 2 and re.fullmatch(r"[A-Z0-9.=-]{1,12}", parts[0].upper()):
            return parts[0].upper(), parts[1].upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,11}", text.upper()):
            return text.upper(), None
        return None, None

    def _slug_for_symbol(
        self,
        symbol: str,
        issuer_product_id: str | None,
        identifiers: dict[str, str],
    ) -> str | None:
        return (
            _identifier(identifiers, "davis_product_slug", "product_slug", "issuer_product_id")
            or issuer_product_id
            or self.PRODUCT_SLUGS.get(symbol.strip().upper())
        )


class FMInvestmentsHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch F/M Investments ETF holdings from its public Drupal JSON route."""

    ETF_LIST_URL = "https://www.fminvest.com/etfs"
    PRODUCT_PAGE_BASE = "https://www.fminvest.com"
    API_TEMPLATE = "https://www.fminvest.com/api/v1/etfs/{node_id}/holdings"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        if "/api/v1/etfs/" in source_url:
            return {
                **_holdings_request_headers(accept="application/json,*/*"),
                "Referer": self.ETF_LIST_URL,
            }
        return _issuer_page_request_headers(accept="text/html,*/*")

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        identifiers = identifiers or {}
        node_id = (
            issuer_product_id
            or _identifier(identifiers, "fm_node_id", "node_id", "issuer_product_id")
        )
        product_page_url = source_url or _identifier(
            identifiers,
            "product_url",
            "issuer_product_url",
            "fund_url",
        )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if not product_page_url:
                listing_url, listing_text = await self._fetch_text(
                    client,
                    self.ETF_LIST_URL,
                    headers=self.source_request_headers(source_url=self.ETF_LIST_URL),
                )
                product_page_url = self._extract_product_page_url(
                    listing_text,
                    symbol=normalized_symbol,
                    base_url=listing_url,
                )
            if not product_page_url:
                raise ValueError(f"F/M Investments could not discover a product page for {symbol}.")

            if not node_id:
                _, product_text = await self._fetch_text(
                    client,
                    product_page_url,
                    headers=self.source_request_headers(source_url=product_page_url),
                )
                node_id = self._extract_node_id(product_text)
            if not node_id:
                raise ValueError(f"F/M Investments product page did not expose a node id for {symbol}.")

            api_url = self.API_TEMPLATE.format(node_id=node_id)
            holdings_url, holdings_text = await self._fetch_text(
                client,
                api_url,
                headers=self.source_request_headers(source_url=api_url),
            )

        payload = json.loads(holdings_text)
        rows, composition_date = self._parse_holdings_payload(payload)
        if not rows:
            raise ValueError(f"F/M Investments holdings API did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=holdings_text,
            raw_json={
                "source_format": "json",
                "payload": payload,
                "product_page_url": product_page_url,
            },
            source_url=holdings_url,
            source_identifier=str(node_id),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_drupal_holdings_api",
                "product_page_url": product_page_url,
                "node_id": str(node_id),
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _extract_product_page_url(cls, raw_html: str, *, symbol: str, base_url: str) -> str | None:
        normalized_symbol = re.escape(symbol.strip().lower())
        pattern = re.compile(
            rf"""href=["'](?P<url>[^"']*/etfs/{normalized_symbol}[-/][^"']*)["']""",
            re.IGNORECASE,
        )
        match = pattern.search(raw_html)
        if not match:
            return None
        return urljoin(base_url, html.unescape(match.group("url")))

    @staticmethod
    def _extract_node_id(raw_html: str) -> str | None:
        match = re.search(r'"node_id"\s*:\s*"?(?P<node_id>\d+)', raw_html, re.IGNORECASE)
        return match.group("node_id") if match else None

    async def _fetch_text(
        self,
        client: httpx.AsyncClient,
        source_url: str,
        *,
        headers: dict[str, str],
    ) -> tuple[str, str]:
        try:
            response = await client.get(
                source_url,
                headers=headers,
                follow_redirects=True,
            )
            response.raise_for_status()
            return str(getattr(response, "url", source_url)), response.text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise

        def _request() -> requests.Response:
            return requests.get(
                source_url,
                headers=headers,
                allow_redirects=True,
                timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            )

        response = await asyncio.to_thread(_request)
        response.raise_for_status()
        return str(getattr(response, "url", source_url)), response.text

    @classmethod
    def _parse_holdings_payload(
        cls,
        payload: Any,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        if not isinstance(payload, list):
            return [], None
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                continue
            if composition_date is None:
                composition_date = cls._parse_as_of_date(item.get("field_as_of_date"))

            name = cls._clean_html_text(item.get("field_name"))
            raw_symbol = cls._clean_html_text(item.get("field_symbol"))
            weight = _decimal(item.get("field_weightings"))
            shares = _decimal(item.get("field_par_value"))
            market_value = _decimal(item.get("field_market_value"))
            if not any([name, raw_symbol, weight, shares, market_value]):
                continue

            holding_type = cls._classify_holding(name=name, symbol=raw_symbol)
            row_type = "cash" if holding_type == "cash" else "security"
            symbol_value = raw_symbol.upper() if raw_symbol and cls._looks_like_ticker(raw_symbol) else None
            cusip = raw_symbol.upper() if raw_symbol and _looks_like_cusip(raw_symbol) else None
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value if row_type != "cash" else None,
                    name=name,
                    cusip=cusip,
                    weight=weight,
                    shares=shares,
                    market_value=market_value,
                    currency="USD",
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_as_of_date(value: Any) -> date | None:
        text = FMInvestmentsHoldingsAdapter._clean_html_text(value)
        if not text:
            return None
        datetime_match = re.search(r'datetime=["\'](?P<value>[^"\']+)["\']', str(value))
        if datetime_match:
            try:
                return datetime.fromisoformat(
                    datetime_match.group("value").replace("Z", "+00:00")
                ).date()
            except ValueError:
                pass
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _clean_html_text(value: Any) -> str | None:
        text = _clean(value)
        if text is None:
            return None
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return _clean(text)

    @staticmethod
    def _classify_holding(*, name: str | None, symbol: str | None) -> str:
        text = " ".join(part.upper() for part in (name, symbol) if part)
        if "CASH" in text or "OTHER" in text:
            return "cash"
        if "TREASURY" in text or "BILL" in text or "NOTE/BOND" in text or "MUNICIPAL" in text:
            return "fixed_income"
        return "equity"

    @staticmethod
    def _looks_like_ticker(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Z][A-Z0-9.=-]{0,9}", value.strip().upper()))


class TRowePriceHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch T. Rowe Price ETF holdings from its public product GraphQL API."""

    GRAPHQL_ENDPOINT = "https://api.public.troweprice.com/ds-dada/graphql"
    GRAPHQL_API_KEY = "dfalKOgR1TyFTzz9Uv35a7cUczNRrk1K"
    ETF_OVERVIEW_URL = "https://www.troweprice.com/financial-intermediary/us/en/investments/etfs.html"
    PRODUCT_PAGE_BASE = "https://www.troweprice.com"

    FULL_HOLDINGS_QUERY = """
    query getProduct($productRequest: DataRequest) {
      fetchData(req: $productRequest) {
        type
        fullHoldingsExhibit {
          effectiveDate
          tradingDate
          currencyCode
          vehicleType
          assetClass
          holdings {
            rank
            tickerSymbol
            name
            securityLongName
            cusip
            isin
            sedol
            shareQuantity
            sharesQuantity
            marketValue
            percentageTotalNetAssets
            parentBaseISOCurrencyCode
            assetClass
            sectorName
            industryName
            countryName
            investmentType
          }
        }
      }
    }
    """

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        if urlparse(source_url).netloc == "api.public.troweprice.com":
            return {
                **_holdings_request_headers(accept="application/json,*/*"),
                "apikey": self.GRAPHQL_API_KEY,
                "Origin": "https://www.troweprice.com",
                "Referer": self.ETF_OVERVIEW_URL,
            }
        return _issuer_page_request_headers(accept="text/html,*/*")

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        product_page_url = source_url or await self._discover_product_page_url(
            symbol=normalized_symbol,
            identifiers=identifiers or {},
        )
        product_code = issuer_product_id or _identifier(
            identifiers or {},
            "trowe_product_code",
            "product_code",
            "issuer_product_id",
        )
        product_page_text: str | None = None
        resolved_product_page_url = product_page_url

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if not product_code:
                if not product_page_url:
                    raise ValueError(f"T. Rowe Price ETF product page route is unavailable for {symbol}.")
                page_response = await client.get(
                    product_page_url,
                    headers=self.source_request_headers(source_url=product_page_url),
                    follow_redirects=True,
                )
                page_response.raise_for_status()
                product_page_text = page_response.text
                resolved_product_page_url = str(page_response.url)
                product_code = self._extract_product_code(page_response.text)
            if not product_code:
                raise ValueError(f"T. Rowe Price product page did not expose a product code for {symbol}.")

            response = await client.post(
                self.GRAPHQL_ENDPOINT,
                headers=self.source_request_headers(source_url=self.GRAPHQL_ENDPOINT),
                json={
                    "query": self.FULL_HOLDINGS_QUERY,
                    "variables": {
                        "productRequest": {
                            "type": "productRequest",
                            "context": {
                                "audience": "INTERMEDIARY",
                                "country": "us",
                                "language": "en",
                            },
                            "productRequest": {"productCode": product_code},
                        }
                    },
                },
                follow_redirects=True,
            )
        response.raise_for_status()
        payload = response.json()
        rows, composition_date, exhibit_metadata = self._parse_graphql_payload(payload)
        if not rows:
            raise ValueError(f"T. Rowe Price GraphQL holdings response did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=json.dumps(payload),
            raw_json={
                "source_format": "graphql_json",
                "payload": payload,
                "product_page_html": product_page_text,
            },
            source_url=str(response.url),
            source_identifier=product_code,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "graphql_json",
                "route_resolution": "issuer_public_product_graphql_full_holdings",
                "product_page_url": resolved_product_page_url,
                "product_code": product_code,
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                **exhibit_metadata,
            },
        )

    async def _discover_product_page_url(
        self,
        *,
        symbol: str,
        identifiers: dict[str, str],
    ) -> str | None:
        explicit_url = _identifier(identifiers, "product_url", "issuer_product_page_url")
        if explicit_url:
            return explicit_url
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                self.ETF_OVERVIEW_URL,
                headers=self.source_request_headers(source_url=self.ETF_OVERVIEW_URL),
                follow_redirects=True,
            )
        response.raise_for_status()
        return self._extract_product_page_url(response.text, symbol=symbol, base_url=str(response.url))

    @classmethod
    def _extract_product_page_url(cls, raw_html: str, *, symbol: str, base_url: str) -> str | None:
        normalized_symbol = re.escape(symbol.strip().upper())
        pattern = re.compile(
            rf"<h3[^>]*>\s*<a[^>]+href=[\"'](?P<href>[^\"']+)[\"'][^>]*>\s*{normalized_symbol}\s*</a>",
            re.IGNORECASE,
        )
        match = pattern.search(raw_html)
        if not match:
            return None
        return urljoin(base_url or cls.PRODUCT_PAGE_BASE, html.unescape(match.group("href")))

    @staticmethod
    def _extract_product_code(raw_html: str) -> str | None:
        match = re.search(r"productCode:\s*[\"'](?P<code>[^\"']+)[\"']", raw_html)
        if match:
            return match.group("code").strip()
        match = re.search(r'"productCode"\s*:\s*"(?P<code>[^"]+)"', raw_html)
        if match:
            return match.group("code").strip()
        return None

    @classmethod
    def _parse_graphql_payload(
        cls,
        payload: dict[str, Any],
    ) -> tuple[list[CanonicalHoldingRow], date | None, dict[str, Any]]:
        exhibits = (
            ((payload.get("data") or {}).get("fetchData") or {}).get("fullHoldingsExhibit")
            or []
        )
        if not exhibits:
            return [], None, {}
        exhibit = next((item for item in exhibits if item.get("holdings")), exhibits[0])
        composition_date = cls._parse_trowe_date(
            exhibit.get("effectiveDate") or exhibit.get("tradingDate")
        )
        rows: list[CanonicalHoldingRow] = []
        for index, holding in enumerate(exhibit.get("holdings") or [], start=1):
            name = _clean(holding.get("securityLongName") or holding.get("name"))
            symbol = _clean(holding.get("tickerSymbol"))
            holding_type, row_type = cls._classify_holding(holding)
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=_clean(holding.get("cusip")) if _looks_like_cusip(_clean(holding.get("cusip"))) else None,
                    isin=_clean(holding.get("isin")),
                    sedol=_clean(holding.get("sedol")),
                    weight=_decimal_percent_points(holding.get("percentageTotalNetAssets")),
                    shares=_decimal(holding.get("sharesQuantity") or holding.get("shareQuantity")),
                    market_value=_decimal(holding.get("marketValue")),
                    currency=_clean(
                        holding.get("parentBaseISOCurrencyCode") or exhibit.get("currencyCode")
                    ),
                    country=_clean(holding.get("countryName")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(holding.get("rank") or index),
                    extra_data={
                        key: value
                        for key, value in holding.items()
                        if value not in (None, "")
                        and key
                        not in {
                            "tickerSymbol",
                            "securityLongName",
                            "name",
                            "cusip",
                            "isin",
                            "sedol",
                            "percentageTotalNetAssets",
                            "sharesQuantity",
                            "shareQuantity",
                            "marketValue",
                            "parentBaseISOCurrencyCode",
                            "countryName",
                        }
                    },
                )
            )
        return rows, composition_date, {
            "graphql_effective_date": exhibit.get("effectiveDate"),
            "graphql_trading_date": exhibit.get("tradingDate"),
            "vehicle_type": exhibit.get("vehicleType"),
            "asset_class": exhibit.get("assetClass"),
        }

    @staticmethod
    def _parse_trowe_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for pattern in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _classify_holding(holding: dict[str, Any]) -> tuple[str, str]:
        text = " ".join(
            str(value).upper()
            for value in (
                holding.get("assetClass"),
                holding.get("investmentType"),
                holding.get("name"),
                holding.get("securityLongName"),
                holding.get("tickerSymbol"),
            )
            if value
        )
        if "CASH" in text or "CURRENCY" in text:
            return "cash", "cash"
        if "BOND" in text or "FIXED INCOME" in text:
            return "fixed_income", "security"
        if "OPTION" in text:
            return "option", "security"
        return "equity", "security"


class AbrdnHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Represent abrdn physical-metal ETF trust exposure from issuer product pages."""

    _COMMODITY_ROWS: dict[str, tuple[tuple[str, str | None], ...]] = {
        "SGOL": (("Gold Bullion", "gold"),),
        "SIVR": (("Silver Bullion", "silver"),),
        "PPLT": (("Platinum Bullion", "platinum"),),
        "PALL": (("Palladium Bullion", "palladium"),),
        "GLTR": (
            ("Gold Bullion", "gold"),
            ("Silver Bullion", "silver"),
            ("Platinum Bullion", "platinum"),
            ("Palladium Bullion", "palladium"),
        ),
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if not (issuer_product_id or symbol).strip():
            return None
        return "https://www.aberdeeninvestments.com/en-us/investor/funds/view-all-funds"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="text/html,*/*")
        headers["Referer"] = "https://www.aberdeeninvestments.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        commodity_rows = self._COMMODITY_ROWS.get(normalized_symbol)
        if not commodity_rows:
            raise ValueError(f"abrdn physical-metal ETF route is not mapped for {symbol}.")

        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            raise ValueError(f"abrdn product page route is unavailable for {symbol}.")

        headers = self.source_request_headers(source_url=product_page_url)
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            try:
                response = await client.get(
                    product_page_url,
                    headers=headers,
                    follow_redirects=True,
                )
            except httpx.HTTPError:
                response = await asyncio.to_thread(
                    requests.get,
                    product_page_url,
                    headers=headers,
                    timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
                    allow_redirects=True,
                )
        response.raise_for_status()
        page_title = self._extract_title(response.text)
        if normalized_symbol not in response.text.upper():
            raise ValueError(f"abrdn fund centre did not reference the requested ETF {symbol}.")

        rows = self._rows_for_symbol(
            normalized_symbol,
            commodity_rows=commodity_rows,
            product_page_url=str(response.url),
            page_title=page_title,
        )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json={
                "source_format": "html",
                "page_title": page_title,
                "commodity_rows": [
                    {"name": name, "commodity": commodity} for name, commodity in commodity_rows
                ],
            },
            source_url=str(response.url),
            source_identifier=issuer_product_id or normalized_symbol,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_fund_centre_physical_commodity_trust",
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_product_page_verified_physical_commodity_trust",
                "snapshot_provenance": "issuer_native_physical_commodity_trust",
            },
        )

    @classmethod
    def _rows_for_symbol(
        cls,
        symbol: str,
        *,
        commodity_rows: tuple[tuple[str, str | None], ...],
        product_page_url: str,
        page_title: str | None,
    ) -> list[CanonicalHoldingRow]:
        equal_weight = Decimal("1") if len(commodity_rows) == 1 else None
        rows: list[CanonicalHoldingRow] = []
        for index, (name, commodity) in enumerate(commodity_rows, start=1):
            rows.append(
                CanonicalHoldingRow(
                    symbol=None,
                    name=name,
                    weight=equal_weight,
                    holding_type="commodity",
                    row_type="commodity",
                    source_row_id=f"{symbol}-{index}-{commodity or 'commodity'}",
                    extra_data={
                        "commodity": commodity,
                        "source_symbol": symbol,
                        "fund_centre_url": product_page_url,
                        "page_title": page_title,
                        "weight_note": (
                            "single-commodity trust exposure"
                            if equal_weight is not None
                            else "basket product page verifies constituents but does not expose live weights"
                        ),
                    },
                )
            )
        return rows

    @staticmethod
    def _extract_title(page_text: str) -> str | None:
        match = re.search(r"<title[^>]*>(?P<title>.*?)</title>", page_text, flags=re.I | re.S)
        if not match:
            return None
        return " ".join(html.unescape(match.group("title")).split())


class CambiarHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Cambiar ETF holdings from its current product-page workbook."""

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return f"https://cambiar.com/etf/{normalized_symbol}/"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(
            accept=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                "application/octet-stream,*/*"
            )
        )
        headers["Referer"] = "https://cambiar.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        resolved_source_url = source_url or self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers or {},
        )

        product_page_text: str | None = None
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            if not resolved_source_url:
                if not product_page_url:
                    raise ValueError(f"Cambiar product page route is unavailable for {symbol}.")
                product_response = await client.get(
                    product_page_url,
                    headers=_issuer_page_request_headers(accept="text/html,*/*"),
                    follow_redirects=True,
                )
                product_response.raise_for_status()
                product_page_text = product_response.text
                resolved_source_url = self._discover_workbook_url(
                    product_page_text,
                    base_url=str(product_response.url),
                )
            if not resolved_source_url:
                raise ValueError(f"Cambiar product page did not expose a holdings workbook for {symbol}.")

            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        workbook_rows = parse_xlsx_table(response.content)
        rows, composition_date = self._parse_workbook_rows(workbook_rows, symbol=symbol)
        if not rows:
            raise ValueError(f"Cambiar holdings workbook did not expose rows for {symbol}.")

        return HoldingsFetchResult(
            rows=rows,
            raw_text=_table_to_text(workbook_rows),
            raw_json={
                "source_format": "xlsx",
                "workbook_rows": workbook_rows,
                "product_page_contains_holdings_link": product_page_text is not None,
            },
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "xlsx",
                "route_resolution": "issuer_product_page_linked_holdings_workbook",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _discover_workbook_url(product_page_text: str, *, base_url: str) -> str | None:
        matches = re.findall(
            r"""(?P<url>[^"'<>]+SEI_Cambiar_Tradedate_Holdings_\d+-viewall\.xlsx)""",
            product_page_text,
            flags=re.IGNORECASE,
        )
        if not matches:
            return None
        return urljoin(base_url, html.unescape(matches[0]))

    def _parse_workbook_rows(
        self,
        workbook_rows: list[list[Any]],
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        if not workbook_rows:
            return [], None
        header_index = next(
            (
                index
                for index, row in enumerate(workbook_rows[:20])
                if {str(value).strip().lower() for value in row if _clean(value)}
                >= {
                    "date",
                    "fund_ticker",
                    "security_isin",
                    "security_ticker",
                    "security_description",
                    "quantity",
                    "market_value",
                    "percent_of_net_assets",
                }
            ),
            None,
        )
        if header_index is None:
            return [], None

        normalized_symbol = symbol.strip().upper()
        header = [str(cell).strip() for cell in workbook_rows[header_index]]
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for row_index, raw_row in enumerate(workbook_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, raw_row)
            fund_ticker = _clean(raw.get("fund_ticker"))
            if fund_ticker and fund_ticker.upper() != normalized_symbol:
                continue
            name = _clean(raw.get("security_description"))
            symbol_value = _clean(raw.get("security_ticker"))
            isin = _clean(raw.get("security_isin"))
            if not any([name, symbol_value, isin]):
                continue

            row_date = self._parse_date(raw.get("date"))
            if composition_date is None:
                composition_date = row_date
            security_group = _clean(raw.get("security_group"))
            holding_type = self._holding_type(security_group=security_group, name=name)
            row_type = "cash" if holding_type == "cash" else "security"
            cusip = self._cusip_from_isin(isin)
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol_value if row_type != "cash" else None,
                    name=name,
                    cusip=cusip,
                    isin=isin,
                    weight=_decimal_percent_points(raw.get("percent_of_net_assets")),
                    shares=_decimal(raw.get("quantity")),
                    market_value=_decimal(raw.get("market_value")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=f"{row_index}:{isin or symbol_value or name}",
                    extra_data={key: value for key, value in raw.items() if _clean(value) is not None},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _holding_type(*, security_group: str | None, name: str | None) -> str:
        text = " ".join(part.upper() for part in (security_group, name) if part)
        if "CASH" in text:
            return "cash"
        if "STOCK" in text or "EQUITY" in text:
            return "equity"
        if "BOND" in text or "NOTE" in text or "FIXED" in text:
            return "fixed_income"
        return "security"

    @staticmethod
    def _cusip_from_isin(isin: str | None) -> str | None:
        if not isin or not isin.upper().startswith("US") or len(isin) < 11:
            return None
        candidate = isin[2:11].upper()
        return candidate if _looks_like_cusip(candidate) else None


class HartfordHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Hartford ETF holdings from public full-holdings workbooks."""

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return None
        return (
            "https://www.hartfordfunds.com/dam/en/docs/pub/funddocuments/"
            f"fullholdings/{normalized_symbol}.xlsx"
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        symbol = urlparse(source_url).path.rsplit("/", 1)[-1].split(".", 1)[0].lower()
        headers = _holdings_request_headers(
            accept=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                "application/octet-stream,*/*"
            )
        )
        headers["Referer"] = f"https://www.hartfordfunds.com/funds/{symbol}.html"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"Hartford holdings route is unavailable for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=self.source_request_headers(source_url=resolved_source_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        workbook_rows = parse_xlsx_table(response.content)
        rows, composition_date = self._parse_workbook_rows(workbook_rows)
        if not rows:
            raise ValueError(f"Hartford holdings workbook did not expose rows for {symbol}.")
        return HoldingsFetchResult(
            rows=rows,
            raw_text=_table_to_text(workbook_rows),
            raw_json={"source_format": "xlsx", "workbook_rows": workbook_rows},
            source_url=str(response.url),
            source_identifier=issuer_product_id,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "route_resolution": "issuer_symbol_full_holdings_xlsx",
                "source_format": "xlsx",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_workbook_rows(
        cls,
        workbook_rows: list[list[Any]],
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        header_index = next(
            (
                index
                for index, row in enumerate(workbook_rows[:40])
                if {
                    "as of date",
                    "security description",
                    "cusip",
                    "ticker/trace",
                    "value",
                    "% of net assets",
                }
                <= {str(cell).strip().lower() for cell in row}
            ),
            -1,
        )
        if header_index < 0:
            return [], None

        header = [str(cell).strip() for cell in workbook_rows[header_index]]
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for position, raw_row in enumerate(workbook_rows[header_index + 1 :], start=1):
            row = _row_dict(header, raw_row)
            name = _clean(row.get("Security Description"))
            if not name:
                continue
            as_of_date = cls._parse_hartford_date(row.get("As of Date"))
            if composition_date is None:
                composition_date = as_of_date
            symbol = _clean(row.get("Ticker/TRACE"))
            asset_class = _clean(row.get("Asset Class"))
            market_value = _decimal(row.get("Value"))
            holding_type = (asset_class or "security").strip().lower()
            row_type = "cash" if "cash" in holding_type else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=None if row_type == "cash" else symbol,
                    name=name,
                    cusip=_clean(row.get("CUSIP")),
                    isin=_clean(row.get("ISIN")),
                    sedol=_clean(row.get("SEDOL")),
                    weight=_decimal(row.get("% of Net Assets")),
                    shares=_decimal(row.get("Shares/Par")),
                    market_value=market_value,
                    country=_clean(row.get("Country of Issuer")),
                    holding_type="cash" if row_type == "cash" else holding_type,
                    row_type=row_type,
                    source_row_id=f"{position}:{_clean(row.get('CUSIP')) or symbol or name}",
                    extra_data={key: value for key, value in row.items() if _clean(value) is not None},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_hartford_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        for date_format in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None


class CalamosHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return None
        return f"https://www.calamos.com/download/{normalized_symbol}Holdings.xlsx"

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _holdings_request_headers(
            accept="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*"
        )
        headers["Referer"] = "https://www.calamos.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers or {},
        )
        if not resolved_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_url,
                headers=self.source_request_headers(source_url=resolved_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        workbook_rows = parse_xlsx_table(response.content)
        rows, composition_date = self._parse_workbook_rows(workbook_rows)
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=_table_to_text(workbook_rows),
            raw_json={"source_format": "xlsx", "workbook_rows": workbook_rows},
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "xlsx",
                "route_resolution": "issuer_xlsx_holdings_download",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def _parse_workbook_rows(
        self,
        workbook_rows: list[list[Any]],
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        header_index = next(
            (
                index
                for index, row in enumerate(workbook_rows[:20])
                if {str(value).strip().lower() for value in row if _clean(value)}
                >= {"ticker", "security description", "weight %"}
            ),
            None,
        )
        if header_index is None:
            return [], None

        composition_date = self._extract_as_of_date(workbook_rows[:header_index])
        header = workbook_rows[header_index]
        rows: list[CanonicalHoldingRow] = []
        for row_index, raw_row in enumerate(workbook_rows[header_index + 1 :], start=1):
            raw = _row_dict(header, raw_row)
            symbol = _clean(_first(raw, ["ticker"]))
            name = _clean(_first(raw, ["security description"]))
            if self._is_footer_row(symbol=symbol, name=name):
                continue
            weight = _decimal_percent_points(_first(raw, ["weight %"]))
            shares = _decimal(_first(raw, ["shares"]))
            market_value = _decimal(_first(raw, ["market value base"]))
            cusip = _clean(_first(raw, ["cusip"]))
            isin = _clean(_first(raw, ["isin"]))
            sedol = _clean(_first(raw, ["sedol"]))
            if not any([symbol, name, cusip, isin, sedol, weight, shares, market_value]):
                continue

            holding_type = self._holding_type(symbol=symbol, name=name)
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    isin=isin,
                    sedol=sedol,
                    weight=weight,
                    shares=shares,
                    market_value=market_value,
                    currency=_clean(_first(raw, ["local currency"])),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(row_index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _extract_as_of_date(prefix_rows: list[list[Any]]) -> date | None:
        for row in prefix_rows:
            for value in row:
                text = _clean(value)
                if not text:
                    continue
                match = re.search(r"As\s+of\s+Date:\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
                if match:
                    try:
                        return datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    except ValueError:
                        return None
        return None

    @staticmethod
    def _holding_type(*, symbol: str | None, name: str | None) -> str:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if text in {"USD", "US DOLLAR"} or "NET OTHER ASSETS" in text or text.endswith(" DOLLAR"):
            return "cash"
        if " OPTION" in text or re.search(r"\b[CP]\s+\d", text):
            return "derivative"
        return "security"

    @staticmethod
    def _is_footer_row(*, symbol: str | None, name: str | None) -> bool:
        text = " ".join(part for part in (symbol, name) if part).strip().lower()
        return (
            not text
            or text.startswith("holdings and weightings")
            or text.startswith("holdings are provided")
        )


class JanusHendersonHoldingsAdapter(IssuerCsvHoldingsAdapter):
    PRODUCT_PAGE_SLUGS: dict[str, str] = {
        "JAAA": "jaaa-aaa-clo-etf",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().upper()
        slug = self.PRODUCT_PAGE_SLUGS.get(normalized_symbol)
        if not slug:
            return None
        return f"https://www.janushenderson.com/en-us/advisor/product/{slug}/full-holdings/"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_full_holdings_html(response.text)
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_full_holdings_html_table",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def _parse_full_holdings_html(
        self,
        raw_html: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        parser = _HTMLTablesParser()
        parser.feed(raw_html)
        for table in parser.tables:
            if not table:
                continue
            header = table[0]
            header_values = {str(value).strip().lower() for value in header if _clean(value)}
            if not {"ticker", "cusip", "weight %"} <= header_values:
                continue
            composition_date = self._extract_as_of_date(header)
            normalized_table = [
                [
                    "Security Description",
                    *[self._normalize_header(value) for value in header[1:]],
                ],
                *table[1:],
            ]
            return parse_holdings_table(normalized_table), composition_date
        return [], None

    @staticmethod
    def _extract_as_of_date(header: list[Any]) -> date | None:
        for value in header:
            text = _clean(value)
            if not text:
                continue
            match = re.search(r"As\s+of\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
            if match:
                try:
                    return datetime.strptime(match.group(1), "%m/%d/%Y").date()
                except ValueError:
                    return None
        return None

    @staticmethod
    def _normalize_header(value: Any) -> str:
        text = str(value).strip()
        lowered = text.lower()
        if lowered.startswith("quantity "):
            return "Shares"
        if lowered == "weight %":
            return "Weight (%)"
        if lowered == "cusip":
            return "CUSIP"
        if lowered == "current market value":
            return "Current Market Value"
        return text


class MatthewsHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse Matthews Asia ETF holdings from server-rendered product pages."""

    PRODUCT_PAGE_PATHS: dict[str, str] = {
        "ADVE": "/funds/etfs/asia-dividend-active-etf/",
        "ASIA": "/funds/etfs/pacific-tiger-active-etf/",
        "EMSF": "/funds/etfs/emerging-markets-sustainable-future-active-etf/",
        "INDE": "/funds/etfs/india-active-etf/",
        "JPAN": "/funds/etfs/japan-active-etf/",
        "MCH": "/funds/etfs/china-active-etf/",
        "MCHS": "/funds/etfs/china-innovators-active-etf/",
        "MEM": "/funds/etfs/emerging-markets-active-equity-etf/",
        "MEMS": "/funds/etfs/emerging-markets-discovery-active-etf/",
        "MEMX": "/funds/etfs/emerging-markets-ex-china-active-etf/",
        "MINV": "/funds/etfs/asia-innovators-active-etf/",
        "MKOR": "/funds/etfs/korea-active-etf/",
    }

    def resolve_product_page_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        path = self.PRODUCT_PAGE_PATHS.get(symbol.strip().upper())
        if not path:
            return None
        return f"https://www.matthewsasia.com{path}"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = source_url or self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if not product_page_url:
            raise ValueError(f"Matthews Asia needs a product page URL for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows = parse_html_holdings_table_by_id(response.text, table_id="tblDailyTopHoldings")
        composition_date = self._extract_holdings_as_of_date(response.text)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_product_page_holdings_table",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "product_page_url": product_page_url,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _extract_holdings_as_of_date(raw_html: str) -> date | None:
        match = re.search(r'id=["\']asOfHoldings["\'][^>]*>\s*\(as of ([^)]+)\)', raw_html, re.I)
        if not match:
            return None
        text = match.group(1).strip()
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None


class NewYorkLifeHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse NYLI/IndexIQ public CSV holdings files."""

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        return f"https://data.nylim.com/M{symbol.strip().upper()}.csv"

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"New York Life needs a holdings CSV URL for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=_holdings_request_headers(
                    accept="text/csv,application/csv,text/plain,*/*"
                ),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date, fund_name = self._parse_nyli_csv(response.text)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=resolved_source_url,
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_symbol_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "fund_name": fund_name,
                "terms_note": self.config.terms_note,
            },
        )

    @classmethod
    def _parse_nyli_csv(
        cls,
        raw_csv: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None, str | None]:
        table_rows = [
            [cls._clean_csv_cell(cell) for cell in row]
            for row in csv.reader(StringIO(raw_csv.strip()))
            if any(_clean(cell) for cell in row)
        ]
        fund_name: str | None = None
        composition_date: date | None = None
        for row in table_rows[:5]:
            key = (_clean(row[0]) or "").strip().lower() if row else ""
            value = _clean(row[1]) if len(row) > 1 else None
            if key.startswith("fund name"):
                fund_name = value
            elif key.startswith("holdings"):
                composition_date = cls._parse_date(value)
        rows = parse_holdings_table(table_rows)
        for row in rows:
            row.extra_data = {
                **row.extra_data,
                **({"fund_name": fund_name} if fund_name else {}),
                **(
                    {"composition_date": composition_date.isoformat()}
                    if composition_date is not None
                    else {}
                ),
            }
        return rows, composition_date, fund_name

    @staticmethod
    def _clean_csv_cell(value: Any) -> str:
        text = "" if value is None else str(value).strip()
        if re.fullmatch(r'="\s*[^"]*"', text):
            return text[2:-1].strip()
        dollar_match = re.fullmatch(r"=DOLLAR\(([-+0-9.,]+)\)", text, re.I)
        if dollar_match:
            return dollar_match.group(1).replace(",", "")
        return text

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None


class BondBloxxHoldingsAdapter(IssuerCsvHoldingsAdapter):
    sitemap_url = "https://bondbloxxetf.com/tickers-sitemap.xml"
    KNOWN_PRODUCT_PAGES: dict[str, str] = {
        "PCMM": "https://bondbloxxetf.com/bondbloxx-private-credit-clo-etf/",
    }

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="text/html,application/xhtml+xml,*/*")
        headers["Referer"] = "https://bondbloxxetf.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        normalized_symbol = symbol.strip().upper()
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if source_url:
            product_page_url = source_url
        if not product_page_url:
            product_page_url = self.KNOWN_PRODUCT_PAGES.get(normalized_symbol)

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            candidates: list[str] = []
            if product_page_url:
                candidates.append(product_page_url)
            if normalized_symbol not in self.KNOWN_PRODUCT_PAGES:
                candidates.extend(await self._discover_product_page_urls(client))

            seen: set[str] = set()
            for candidate_url in candidates:
                if candidate_url in seen:
                    continue
                seen.add(candidate_url)
                response_url, raw_html = await self._fetch_html(client, candidate_url)
                payload = self._extract_general_data(raw_html)
                if not payload:
                    continue
                rows, composition_date = self._parse_general_data(
                    payload,
                    expected_symbol=normalized_symbol,
                )
                if not rows:
                    continue
                return HoldingsFetchResult(
                    rows=rows,
                    raw_text=raw_html,
                    raw_json=payload,
                    source_url=response_url,
                    source_identifier=normalized_symbol,
                    legal_metadata={
                        "source_access": self.config.source_access,
                        "source_provider": self.source_provider,
                        "adapter_key": self.adapter_key,
                        "source_format": "html_embedded_json",
                        "route_resolution": (
                            "issuer_product_page_embedded_general_data"
                        ),
                        "composition_date": (
                            composition_date.isoformat() if composition_date else None
                        ),
                        "as_of_date": (
                            composition_date.isoformat() if composition_date else None
                        ),
                        "terms_note": self.config.terms_note,
                    },
                )

        return await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )

    async def _fetch_html(
        self,
        client: httpx.AsyncClient,
        source_url: str,
    ) -> tuple[str, str]:
        headers = self.source_request_headers(source_url=source_url)
        try:
            response = await client.get(
                source_url,
                headers=headers,
                follow_redirects=True,
            )
            response.raise_for_status()
            return str(response.url), response.text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise

        def _request() -> requests.Response:
            return requests.get(
                source_url,
                headers=headers,
                allow_redirects=True,
                timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            )

        response = await asyncio.to_thread(_request)
        response.raise_for_status()
        return str(getattr(response, "url", source_url)), response.text

    async def _discover_product_page_urls(self, client: httpx.AsyncClient) -> list[str]:
        _, raw_xml = await self._fetch_html(client, self.sitemap_url)
        return [
            html.unescape(match.group(1)).strip()
            for match in re.finditer(r"<loc>\s*(https?://[^<]+)\s*</loc>", raw_xml)
            if "bondbloxx-" in match.group(1).lower()
            and "etf" in match.group(1).lower()
        ]

    @classmethod
    def _extract_general_data(cls, raw_html: str) -> dict[str, Any] | None:
        marker = "var generalData ="
        marker_index = raw_html.find(marker)
        if marker_index == -1:
            return None
        object_start = raw_html.find("{", marker_index)
        if object_start == -1:
            return None
        object_text = cls._extract_balanced_object(raw_html, start=object_start)
        if not object_text:
            return None
        try:
            payload = json.loads(object_text)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _extract_balanced_object(raw_text: str, *, start: int) -> str | None:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(raw_text)):
            char = raw_text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return raw_text[start : index + 1]
        return None

    @classmethod
    def _parse_general_data(
        cls,
        payload: dict[str, Any],
        *,
        expected_symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        raw_rows = payload.get("holdings")
        if not isinstance(raw_rows, list):
            return [], None

        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, raw in enumerate(raw_rows, start=1):
            if not isinstance(raw, dict):
                continue
            etf_ticker = _clean(raw.get("etfticker"))
            if expected_symbol and etf_ticker and etf_ticker.upper() != expected_symbol:
                continue
            row_date = cls._parse_date(raw.get("as_of_date"))
            if composition_date is None and row_date is not None:
                composition_date = row_date
            name = _clean(raw.get("security_name"))
            ticker = _clean(raw.get("ticker"))
            cusip = _clean(raw.get("cusip"))
            holding_type = cls._holding_type(
                name=name,
                ticker=ticker,
                cusip=cusip,
            )
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=ticker if row_type != "cash" else None,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    isin=_clean(raw.get("isin")),
                    weight=_decimal(raw.get("weight")),
                    shares=_decimal(raw.get("shares_held")),
                    market_value=_decimal(raw.get("market_value")),
                    currency=_clean(raw.get("currency")),
                    country=_clean(raw.get("country")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(raw.get("security_number") or index),
                    extra_data={
                        key: value
                        for key, value in raw.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        text = text.split("T", 1)[0]
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None

    @staticmethod
    def _holding_type(
        *,
        name: str | None,
        ticker: str | None,
        cusip: str | None,
    ) -> str:
        text = " ".join(part.upper() for part in (name, ticker, cusip) if part)
        if "CASH" in text or text in {"USD", "US DOLLAR"}:
            return "cash"
        if "FUTURE" in text or "OPTION" in text or "SWAP" in text:
            return "derivative"
        return "fixed_income"


class NorthernTrustHoldingsAdapter(IssuerCsvHoldingsAdapter):
    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        explicit = super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if explicit:
            return explicit
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            return None
        return (
            "https://www.flexshares.com/content/dam/ntflexshares/fund/"
            f"{normalized_symbol}/{normalized_symbol}-holdings.csv"
        )

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="text/csv,*/*")
        headers["Referer"] = "https://www.flexshares.com/"
        return headers

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers or {},
        )
        if not resolved_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_url,
                headers=self.source_request_headers(source_url=resolved_url),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows, composition_date = self._parse_flexshares_csv(response.text)
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_flexshares_holdings_csv",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    def _parse_flexshares_csv(
        self,
        raw_csv: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        reader = csv.reader(StringIO(raw_csv))
        table_rows = [[cell.strip() for cell in row] for row in reader if any(_clean(cell) for cell in row)]
        if not table_rows:
            return [], None
        header = table_rows[0]
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, row in enumerate(table_rows[1:], start=1):
            raw = _row_dict(header, row)
            row_date = self._parse_date(_first(raw, ["date"]))
            if composition_date is None:
                composition_date = row_date
            symbol = _clean(_first(raw, ["ticker"]))
            name = _clean(_first(raw, ["name"]))
            name = html.unescape(name) if name else None
            holding_type = self._holding_type(symbol=symbol, name=name)
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=_clean(_first(raw, ["cusip"])),
                    isin=_clean(_first(raw, ["isin"])),
                    sedol=_clean(_first(raw, ["sedol"])),
                    weight=_decimal_percent_points(_first(raw, ["fund weight %"])),
                    shares=_decimal(_first(raw, ["shares held"])),
                    market_value=_decimal(
                        _first(raw, ["market value-base", "market value-local"])
                    ),
                    country=_clean(_first(raw, ["country"])),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={key: value for key, value in raw.items() if value not in (None, "")},
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        try:
            return datetime.strptime(text, "%m/%d/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _holding_type(*, symbol: str | None, name: str | None) -> str:
        text = " ".join(part.upper() for part in (symbol, name) if part)
        if text in {"USD", "US DOLLAR"} or "CASH" in text:
            return "cash"
        if "FUTURE" in text or "OPTION" in text or "SWAP" in text:
            return "derivative"
        return "security"


class FirstTrustHoldingsAdapter(IssuerCsvHoldingsAdapter):
    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        product_page_url = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers or {},
        )
        if not product_page_url:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                product_page_url,
                headers=_issuer_page_request_headers(accept="text/html,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        rows = parse_html_holdings_table_by_headers(
            response.text,
            required_headers={
                "security name",
                "identifier",
                "cusip",
                "shares / quantity",
                "market value",
                "weighting",
            },
        )
        if not rows:
            return await super().fetch_latest(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
                identifiers=identifiers,
            )
        as_of_date = self._extract_as_of_date(response.text)
        return HoldingsFetchResult(
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "html",
                "route_resolution": "issuer_html_holdings_table",
                "composition_date": as_of_date.isoformat() if as_of_date else None,
                "as_of_date": as_of_date.isoformat() if as_of_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _extract_as_of_date(raw_html: str) -> date | None:
        match = re.search(
            r"Holdings\s+of\s+the\s+Fund\s+as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})",
            raw_html,
            re.IGNORECASE,
        )
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        except ValueError:
            return None


class FranklinHoldingsAdapter(IssuerCsvHoldingsAdapter):
    graphql_url = "https://www.franklintempleton.com/api/pds/price-and-performance"
    country_code = "US"
    language_code = "en_US"
    KNOWN_FUND_IDS: dict[str, str] = {
        "FLQL": "25773",
    }
    HOLDINGS_QUERY = """
    query Holdings($productId: String!, $countryCode: String!, $languageCode: String!) {
      Portfolio(fundid: $productId, countrycode: $countryCode, languagecode: $languageCode) {
        fundname
        producttype
        assetclass
        portfolio {
          dailyholdings {
            fundid
            asofdate
            asofdatestd
            frequency
            secticker
            isinsecnbr
            cusipnbr
            secname
            quantityshrpar
            pctofnetassets
            pctofnetassetsstd
            mktvalue
            notionalmktvalue
            assetclasscatg
            mktcurr
            contracts
          }
          fullholdings {
            fundid
            asofdate
            asofdatestd
            frequency
            secticker
            isinsecnbr
            cusipnbr
            secname
            quantityshrpar
            pctofnetassets
            pctofnetassetsstd
            mktvalue
            notionalmktvalue
            assetclasscatg
            mktcurr
            contracts
            investmentcategory
          }
        }
      }
    }
    """
    PRODUCT_LIST_QUERY = """
    query Ppss($countrycode: String!, $languagecode: String!, $productType: String!) {
      PPSS(countrycode: $countrycode, languagecode: $languagecode, productType: $productType) {
        fundid
        fundname
        webprdcttaxonomy
        producttype
        shareclass {
          shclcode
          shclname
          identifiers {
            ticker
            cusip
            isin
            sedol
          }
        }
      }
    }
    """

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        identifiers = identifiers or {}
        product_ids = self._candidate_product_ids(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )

        last_payload: dict[str, Any] | None = None
        last_text: str | None = None
        last_url: str | None = None
        product_id_used: str | None = None
        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            for product_id in product_ids:
                payload, raw_text, response_url = await self._fetch_holdings_payload(
                    client=client,
                    product_id=product_id,
                    referer=source_url,
                )
                last_payload = payload
                last_text = raw_text
                last_url = response_url
                rows, composition_date = self._parse_holdings_payload(payload)
                if rows:
                    product_id_used = product_id
                    break

            if not rows:
                resolved_product_id = await self._lookup_product_id_by_symbol(
                    client=client,
                    symbol=symbol,
                )
                if resolved_product_id and resolved_product_id not in product_ids:
                    payload, raw_text, response_url = await self._fetch_holdings_payload(
                        client=client,
                        product_id=resolved_product_id,
                        referer=source_url,
                    )
                    last_payload = payload
                    last_text = raw_text
                    last_url = response_url
                    rows, composition_date = self._parse_holdings_payload(payload)
                    if rows:
                        product_id_used = resolved_product_id

        if not rows:
            try:
                return await super().fetch_latest(
                    symbol=symbol,
                    issuer_product_id=issuer_product_id,
                    source_url=source_url,
                    identifiers=identifiers,
                )
            except ValueError as exc:
                raise ValueError(
                    f"Franklin Templeton holdings API returned no holdings for {symbol}."
                ) from exc

        return HoldingsFetchResult(
            rows=rows,
            raw_text=last_text,
            raw_json=last_payload,
            source_url=last_url,
            source_identifier=product_id_used,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "json",
                "route_resolution": "issuer_graphql_holdings",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "issuer_product_id": product_id_used,
                "terms_note": self.config.terms_note,
            },
        )

    def _candidate_product_ids(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None,
        source_url: str | None,
        identifiers: dict[str, str],
    ) -> list[str]:
        candidates = [
            self.KNOWN_FUND_IDS.get(symbol.strip().upper()),
            _identifier(identifiers, "franklin_fund_id", "fund_id", "product_id"),
            issuer_product_id,
            self._extract_product_id_from_url(source_url),
        ]
        result: list[str] = []
        for candidate in candidates:
            cleaned = _clean(candidate)
            if cleaned and cleaned not in result:
                result.append(cleaned)
        return result

    @staticmethod
    def _extract_product_id_from_url(source_url: str | None) -> str | None:
        if not source_url:
            return None
        match = re.search(r"/products/(\d+)/", source_url)
        return match.group(1) if match else None

    async def _fetch_holdings_payload(
        self,
        *,
        client: httpx.AsyncClient,
        product_id: str,
        referer: str | None,
    ) -> tuple[dict[str, Any], str, str]:
        response = await client.post(
            self.graphql_url,
            json={
                "operationName": "Holdings",
                "query": self.HOLDINGS_QUERY,
                "variables": {
                    "productId": product_id,
                    "countryCode": self.country_code,
                    "languageCode": self.language_code,
                },
            },
            headers={
                **_issuer_page_request_headers(accept="application/json,*/*"),
                "Content-Type": "application/json",
                "Origin": "https://www.franklintempleton.com",
                "Referer": referer or "https://www.franklintempleton.com/",
            },
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
        return payload, response.text, str(response.url)

    async def _lookup_product_id_by_symbol(
        self,
        *,
        client: httpx.AsyncClient,
        symbol: str,
    ) -> str | None:
        response = await client.post(
            self.graphql_url,
            json={
                "operationName": "Ppss",
                "query": self.PRODUCT_LIST_QUERY,
                "variables": {
                    "countrycode": self.country_code,
                    "languagecode": self.language_code,
                    "productType": "etf",
                },
            },
            headers={
                **_issuer_page_request_headers(accept="application/json,*/*"),
                "Content-Type": "application/json",
                "Origin": "https://www.franklintempleton.com",
                "Referer": "https://www.franklintempleton.com/",
            },
            follow_redirects=True,
        )
        response.raise_for_status()
        products = response.json().get("data", {}).get("PPSS")
        if not isinstance(products, list):
            return None
        normalized_symbol = symbol.strip().upper()
        for product in products:
            if not isinstance(product, dict):
                continue
            for share_class in product.get("shareclass") or []:
                identifiers = share_class.get("identifiers") if isinstance(share_class, dict) else None
                ticker = _clean(identifiers.get("ticker")) if isinstance(identifiers, dict) else None
                if ticker and ticker.upper() == normalized_symbol:
                    return _clean(product.get("fundid"))
        return None

    def _parse_holdings_payload(
        self,
        payload: dict[str, Any],
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        portfolio = payload.get("data", {}).get("Portfolio") if isinstance(payload, dict) else None
        if not isinstance(portfolio, dict):
            return [], None
        portfolio_data = portfolio.get("portfolio")
        if not isinstance(portfolio_data, dict):
            return [], None
        raw_rows = portfolio_data.get("fullholdings") or portfolio_data.get("dailyholdings")
        if not isinstance(raw_rows, list):
            return [], None

        rows: list[CanonicalHoldingRow] = []
        composition_date: date | None = None
        for index, item in enumerate(raw_rows, start=1):
            if not isinstance(item, dict):
                continue
            symbol = _clean(item.get("secticker"))
            name = _clean(item.get("secname"))
            cusip = _clean(item.get("cusipnbr"))
            isin = _clean(item.get("isinsecnbr"))
            if not any([symbol, name, cusip, isin]):
                continue
            row_date = self._parse_franklin_date(item.get("asofdatestd") or item.get("asofdate"))
            if composition_date is None:
                composition_date = row_date
            holding_type = self._franklin_holding_type(
                asset_class=_clean(item.get("assetclasscatg")),
                investment_category=_clean(item.get("investmentcategory")),
                name=name,
                symbol=symbol,
            )
            row_type = "cash" if holding_type == "cash" else "security"
            rows.append(
                CanonicalHoldingRow(
                    symbol=symbol if row_type != "cash" else None,
                    name=name,
                    cusip=cusip if _looks_like_cusip(cusip) else None,
                    isin=isin,
                    weight=_decimal_percent_points(
                        item.get("pctofnetassetsstd")
                        if item.get("pctofnetassetsstd") is not None
                        else item.get("pctofnetassets")
                    ),
                    shares=_decimal(item.get("quantityshrpar") or item.get("contracts")),
                    market_value=_decimal(item.get("mktvalue") or item.get("notionalmktvalue")),
                    currency=_clean(item.get("mktcurr")),
                    holding_type=holding_type,
                    row_type=row_type,
                    source_row_id=str(index),
                    extra_data={
                        key: value
                        for key, value in item.items()
                        if value not in (None, "")
                    },
                )
            )
        return rows, composition_date

    @staticmethod
    def _parse_franklin_date(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        for date_format in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _franklin_holding_type(
        *,
        asset_class: str | None,
        investment_category: str | None,
        name: str | None,
        symbol: str | None,
    ) -> str:
        text = " ".join(part.upper() for part in (asset_class, investment_category, name, symbol) if part)
        if "CASH" in text or text in {"USD", "US DOLLAR"}:
            return "cash"
        if "FUTURE" in text or "SWAP" in text or "OPTION" in text:
            return "derivative"
        if "BOND" in text or "TREASURY" in text or "FIXED INCOME" in text:
            return "fixed_income"
        return "security"


class KranesharesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    latest_lookback_days = 10

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        headers = _issuer_page_request_headers(accept="text/csv,*/*")
        headers["Referer"] = "https://kraneshares.com/"
        return headers

    def resolve_source_url(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> str | None:
        if source_url:
            return source_url.strip()
        return super().resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        if source_url:
            return await self._fetch_csv_source(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                source_url=source_url,
            )

        if not source_url:
            normalized_symbol = symbol.strip().lower()
            for days_back in range(self.latest_lookback_days + 1):
                source_date = date.today() - timedelta(days=days_back)
                candidate_url = (
                    "https://kraneshares.com/csv/"
                    f"{source_date.strftime('%m_%d_%Y')}_{normalized_symbol}_holdings.csv"
                )
                try:
                    return await self._fetch_csv_source(
                        symbol=symbol,
                        issuer_product_id=issuer_product_id,
                        source_url=candidate_url,
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in {403, 404}:
                        continue
                    raise
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        as_of_date = self._extract_as_of_date(result.raw_text)
        if as_of_date:
            result.legal_metadata = {
                **(result.legal_metadata or {}),
                "composition_date": as_of_date.isoformat(),
                "as_of_date": as_of_date.isoformat(),
            }
        return result

    async def _fetch_csv_source(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None,
        source_url: str,
    ) -> HoldingsFetchResult:
        headers = self.source_request_headers(source_url=source_url)

        def _request() -> requests.Response:
            return requests.get(
                source_url,
                headers=headers,
                allow_redirects=True,
                timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS,
            )

        response = await asyncio.to_thread(_request)
        if response.status_code >= 400:
            request = httpx.Request("GET", source_url)
            httpx_response = httpx.Response(
                response.status_code,
                request=request,
                text=response.text,
            )
            raise httpx.HTTPStatusError(
                f"Client error '{response.status_code}' for url '{source_url}'",
                request=request,
                response=httpx_response,
            )
        rows = parse_holdings_csv(response.text)
        as_of_date = self._extract_as_of_date(response.text)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=response.text,
            raw_json=None,
            source_url=str(response.url),
            source_identifier=issuer_product_id or symbol.strip().upper(),
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "csv",
                "route_resolution": "issuer_dated_csv_lookback",
                "composition_date": as_of_date.isoformat() if as_of_date else None,
                "as_of_date": as_of_date.isoformat() if as_of_date else None,
                "terms_note": self.config.terms_note,
            },
        )

    @staticmethod
    def _extract_as_of_date(raw_csv: str) -> date | None:
        match = re.search(r"\bAs\s+of\s+(\d{4}-\d{2}-\d{2})\b", raw_csv, re.IGNORECASE)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None


class SprottHoldingsAdapter(IssuerCsvHoldingsAdapter):
    sitemap_url = "https://sprottetfs.com/xml-sitemap/"

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        explicit = self.resolve_product_page_url(
            symbol=symbol,
            issuer_product_id=None,
            identifiers=identifiers,
        )
        if explicit:
            return HoldingsAdapterProbe(
                adapter_key=self.adapter_key,
                confidence=Decimal("0.8500"),
                status="ready",
                reason="ETF profile has a Sprott issuer product page for holdings-link discovery.",
                source_url=explicit,
            )
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.7500"),
            status="ready",
            reason="Sprott ETF product pages are discoverable from the public ETF sitemap.",
        )

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        identifiers = identifiers or {}
        product_page_url = (
            self.resolve_product_page_url(
                symbol=symbol,
                issuer_product_id=issuer_product_id,
                identifiers=identifiers,
            )
            or await self._discover_product_page_from_sitemap(symbol)
        )
        merged_identifiers = (
            {**identifiers, "product_url": product_page_url}
            if product_page_url
            else identifiers
        )
        return await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=merged_identifiers,
        )

    async def _discover_product_page_from_sitemap(self, symbol: str) -> str | None:
        normalized = symbol.strip().lower()
        if not normalized:
            return None
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                self.sitemap_url,
                headers=_holdings_request_headers(accept="application/xml,text/xml,*/*"),
                follow_redirects=True,
            )
        response.raise_for_status()
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            return None
        namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for node in root.findall("sm:url/sm:loc", namespace):
            url = (node.text or "").strip()
            if not url:
                continue
            path = urlparse(url).path.strip("/").lower()
            if path.startswith(f"{normalized}-sprott-") and path.endswith("-etf"):
                return url
        return None


class WorldGoldCouncilHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Parse SPDR Gold trust public archive data as a single commodity holding."""

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        resolved_source_url = self.resolve_source_url(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        if not resolved_source_url:
            raise ValueError(f"{self.adapter_key} needs a SPDR Gold archive route for {symbol}.")

        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                resolved_source_url,
                headers=_holdings_request_headers(
                    accept=(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                        "application/octet-stream,*/*"
                    )
                ),
                follow_redirects=True,
            )
        response.raise_for_status()
        workbook_rows = parse_xlsx_table(response.content, worksheet_index=2)
        rows, composition_date = self._parse_gold_archive_workbook(workbook_rows, symbol=symbol)
        return HoldingsFetchResult(
            rows=rows,
            raw_text=_table_to_text(workbook_rows),
            raw_json={"source_format": "xlsx", "workbook_rows": workbook_rows},
            source_url=resolved_source_url,
            source_identifier=issuer_product_id,
            legal_metadata={
                "source_access": self.config.source_access,
                "source_provider": self.source_provider,
                "adapter_key": self.adapter_key,
                "source_format": "xlsx",
                "route_resolution": "issuer_gold_trust_historical_archive",
                "composition_date": composition_date.isoformat() if composition_date else None,
                "as_of_date": composition_date.isoformat() if composition_date else None,
                "terms_note": self.config.terms_note,
                "source_quality": "issuer_reported_gold_trust_archive",
                "snapshot_provenance": "issuer_native_gold_trust_archive",
            },
        )

    @classmethod
    def _parse_gold_archive_workbook(
        cls,
        workbook_rows: list[list[Any]],
        *,
        symbol: str,
    ) -> tuple[list[CanonicalHoldingRow], date | None]:
        header_index = next(
            (
                index
                for index, row in enumerate(workbook_rows[:20])
                if {
                    "date",
                    "total ounces of gold in the trust",
                    "total net asset value in the trust",
                }.issubset({str(value).strip().lower() for value in row if _clean(value)})
            ),
            None,
        )
        if header_index is None:
            return [], None

        header = workbook_rows[header_index]
        latest_row: dict[str, Any] | None = None
        latest_date: date | None = None
        for raw_row in workbook_rows[header_index + 1 :]:
            row = _row_dict(header, raw_row)
            row_date = cls._parse_gold_archive_date(_first(row, ["date"]))
            total_ounces = _decimal(_first(row, ["total ounces of gold in the trust"]))
            market_value = _decimal(_first(row, ["total net asset value in the trust"]))
            if row_date is None or total_ounces is None or market_value is None:
                continue
            if latest_date is None or row_date > latest_date:
                latest_date = row_date
                latest_row = row

        if latest_row is None or latest_date is None:
            return [], None

        total_ounces = _decimal(_first(latest_row, ["total ounces of gold in the trust"]))
        market_value = _decimal(_first(latest_row, ["total net asset value in the trust"]))
        tonnes = _decimal(_first(latest_row, ["tonnes of gold"]))
        ounces_per_share = _decimal(_first(latest_row, ["ounces of gold per share"]))
        nav_per_share = _decimal(_first(latest_row, ["nav/share at 10:30am nyt"]))
        closing_price = _decimal(_first(latest_row, ["closing price"]))
        indicative_price = _decimal(
            _first(latest_row, ["indicative price per share at 4:15pm nyt"])
        )
        return [
            CanonicalHoldingRow(
                symbol=None,
                name="Gold Bullion",
                weight=Decimal("1"),
                shares=total_ounces,
                market_value=market_value,
                currency="USD",
                holding_type="commodity",
                row_type="commodity",
                source_row_id=f"{symbol.upper()}-{latest_date.isoformat()}-gold-bullion",
                extra_data={
                    "commodity": "gold",
                    "source_symbol": symbol.upper(),
                    "composition_date": latest_date.isoformat(),
                    "total_ounces_of_gold": str(total_ounces) if total_ounces is not None else None,
                    "tonnes_of_gold": str(tonnes) if tonnes is not None else None,
                    "ounces_of_gold_per_share": (
                        str(ounces_per_share) if ounces_per_share is not None else None
                    ),
                    "nav_per_share": str(nav_per_share) if nav_per_share is not None else None,
                    "closing_price": str(closing_price) if closing_price is not None else None,
                    "indicative_price_per_share": (
                        str(indicative_price) if indicative_price is not None else None
                    ),
                },
            )
        ], latest_date

    @staticmethod
    def _parse_gold_archive_date(value: Any) -> date | None:
        text = _clean(value)
        if text is None:
            return None
        for date_format in ("%d-%b-%Y", "%d-%B-%Y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None


class RenaissanceCapitalHoldingsAdapter(IssuerCsvHoldingsAdapter):
    """Fetch Renaissance Capital ETF holdings from its public workbook route."""

    product_pages = {
        "ipo": "https://etfs.renaissancecapital.com/us-ipo-etf",
        "ipos": "https://etfs.renaissancecapital.com/intl-ipo-etf",
    }

    def source_request_headers(self, *, source_url: str) -> dict[str, str]:
        symbol = urlparse(source_url).path.rstrip("/").rsplit("/", 1)[-1].lower()
        referer = self.product_pages.get(symbol, "https://etfs.renaissancecapital.com/")
        return {
            **_holdings_request_headers(
                accept=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                    "application/octet-stream,*/*"
                )
            ),
            "Referer": referer,
        }

    async def fetch_latest(
        self,
        *,
        symbol: str,
        issuer_product_id: str | None = None,
        source_url: str | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> HoldingsFetchResult:
        result = await super().fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            source_url=source_url,
            identifiers=identifiers,
        )
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "source_access": self.config.source_access,
            "source_provider": self.source_provider,
            "adapter_key": self.adapter_key,
            "route_resolution": "issuer_symbol_holdings_xlsx",
            "source_format": "xlsx",
            "terms_note": self.config.terms_note,
        }
        return result


ISSUER_ADAPTER_CONFIGS: dict[str, IssuerCsvAdapterConfig] = {
    "ishares": IssuerCsvAdapterConfig(
        adapter_key="ishares",
        source_provider="ishares",
        required_identifiers=("issuer_product_id",),
        live_tested_default_route=True,
        terms_note="iShares/BlackRock public holdings files may be subject to issuer terms.",
    ),
    "spdr": IssuerCsvAdapterConfig(
        adapter_key="spdr",
        source_provider="spdr",
        url_templates=(
            "https://www.ssga.com/us/en/intermediary/etfs/library-content/"
            "products/fund-data/etfs/us/holdings-daily-us-en-{symbol_lower}.xlsx",
        ),
        live_tested_default_route=True,
        terms_note="State Street/SPDR public holdings files may be subject to issuer terms.",
    ),
    "vanguard": IssuerCsvAdapterConfig(
        adapter_key="vanguard",
        source_provider="vanguard",
        live_tested_default_route=True,
        terms_note="Vanguard public product pages and holdings files may be subject to issuer terms.",
    ),
    "invesco": IssuerCsvAdapterConfig(
        adapter_key="invesco",
        source_provider="invesco",
        url_templates=(
            "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/"
            "{symbol_upper}/holdings/fund?idType=ticker&interval=monthly&productType=ETF",
        ),
        live_tested_default_route=True,
        terms_note="Invesco public product pages and holdings files may be subject to issuer terms.",
    ),
    "innovator": IssuerCsvAdapterConfig(
        adapter_key="innovator",
        source_provider="innovator",
        live_tested_default_route=True,
        terms_note="Innovator public ETF holdings files may be subject to issuer terms.",
    ),
    "schwab": IssuerCsvAdapterConfig(
        adapter_key="schwab",
        source_provider="schwab",
        product_page_templates=(
            "https://www.schwabassetmanagement.com/products/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Schwab public product pages and holdings files may be subject to issuer terms.",
    ),
    "ark": IssuerCsvAdapterConfig(
        adapter_key="ark",
        source_provider="ark",
        url_templates=(
            "https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
            "{holdings_file_name}.csv",
            "https://ark-funds.com/wp-content/fundsiteliterature/holdings/{holdings_file_name}.csv",
        ),
        required_identifiers=("holdings_file_name",),
        live_tested_default_route=True,
        terms_note="ARK public holdings files may be subject to issuer terms.",
    ),
    "21shares": IssuerCsvAdapterConfig(
        adapter_key="21shares",
        source_provider="21shares",
        source_access="issuer_public_product_details_api",
        url_templates=(
            "https://21sharesprimary.paradox-coworking.com/api/product_details/{symbol_upper}",
        ),
        product_page_templates=(
            "https://www.21shares.com/en-us/products-us/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="21Shares public product details API may be subject to issuer terms.",
    ),
    "abrdn": IssuerCsvAdapterConfig(
        adapter_key="abrdn",
        source_provider="abrdn",
        source_access="issuer_public_physical_commodity_product_page",
        product_page_templates=(
            "https://www.aberdeeninvestments.com/en-us/investor/funds/view-all-funds",
        ),
        live_tested_default_route=True,
        terms_note="abrdn physical-metal ETF product pages may be subject to issuer terms.",
    ),
    "allianz": IssuerCsvAdapterConfig(
        adapter_key="allianz",
        source_provider="allianz",
        source_access="issuer_public_multi_fund_holdings_csv",
        url_templates=(
            "https://www.allianzim.com/wp-content/uploads/feeds/BBH_FOR_ALZ_ETF_PVAL_WEB.csv",
        ),
        product_page_templates=(
            "https://www.allianzim.com/etfs/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="AllianzIM public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "adaptive_investments": IssuerCsvAdapterConfig(
        adapter_key="adaptive_investments",
        source_provider="adaptive_investments",
        source_access="issuer_public_fund_page_embedded_holdings",
        product_page_templates=(
            "https://adpvetf.com/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Adaptive Investments public ETF fund-page holdings payloads may be subject to issuer terms.",
    ),
    "applied_finance": IssuerCsvAdapterConfig(
        adapter_key="applied_finance",
        source_provider="applied_finance",
        source_access="issuer_public_product_page_holdings_table",
        product_page_templates=(
            "https://appliedfinancefunds.com/ETF/ETFData/{symbol_upper}",
        ),
        live_tested_default_route=True,
        terms_note="Applied Finance public ETF product pages may be subject to issuer terms.",
    ),
    "bitwise": IssuerCsvAdapterConfig(
        adapter_key="bitwise",
        source_provider="bitwise",
        product_page_templates=(
            "https://{symbol_lower}etf.com/",
        ),
        live_tested_default_route=True,
        terms_note="Bitwise public ETF product pages may be subject to issuer terms.",
    ),
    "coinshares": IssuerCsvAdapterConfig(
        adapter_key="coinshares",
        source_provider="coinshares",
        source_access="issuer_public_widgets_holdings_json",
        product_page_templates=(
            "https://coinshares.com/us/etf/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note=(
            "CoinShares/Valkyrie public ETF product pages and widget API "
            "may be subject to issuer terms."
        ),
    ),
    "cambria": IssuerCsvAdapterConfig(
        adapter_key="cambria",
        source_provider="cambria",
        live_tested_default_route=True,
        terms_note="Cambria public ETF holdings files may be subject to issuer terms.",
    ),
    "beyond_investing": IssuerCsvAdapterConfig(
        adapter_key="beyond_investing",
        source_provider="beyond_investing",
        source_access="issuer_public_multi_fund_holdings_csv",
        url_templates=(
            "https://www.veganetf-sftp.com/csvs/BeyondAdvisorsWEB.40XZ.XZ_Holdings.csv",
        ),
        product_page_templates=(
            "https://veganetf.com/",
        ),
        live_tested_default_route=True,
        terms_note="Beyond Investing/VEGN public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "castleark": IssuerCsvAdapterConfig(
        adapter_key="castleark",
        source_provider="castleark",
        source_access="issuer_public_daily_holdings_text",
        product_page_templates=(
            "http://castleark-etfs.com",
        ),
        live_tested_default_route=True,
        terms_note="CastleArk public ETF product pages and daily holdings text files may be subject to issuer terms.",
    ),
    "baron": IssuerCsvAdapterConfig(
        adapter_key="baron",
        source_provider="baron",
        source_access="issuer_public_product_page_linked_holdings_csv",
        product_page_templates=(
            "https://www.baroncapitalgroup.com/",
        ),
        live_tested_default_route=True,
        terms_note="Baron Capital public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "brandes": IssuerCsvAdapterConfig(
        adapter_key="brandes",
        source_provider="brandes",
        source_access="issuer_public_iframe_holdings_csv",
        url_templates=(
            "https://etfs.brandes.com/assets/data/6c11_Report.csv",
        ),
        product_page_templates=(
            "https://www.brandes.com/etfs/fund-detail/{issuer_product_id}",
        ),
        live_tested_default_route=True,
        terms_note="Brandes public ETF product pages and iframe holdings CSV files may be subject to issuer terms.",
    ),
    "ocean_park": IssuerCsvAdapterConfig(
        adapter_key="ocean_park",
        source_provider="ocean_park",
        source_access="issuer_public_filepoint_holdings_json",
        url_templates=(
            "https://filepoint.live/oceanpark_getholdings_cached4.php",
        ),
        product_page_templates=(
            "https://oceanparketfs.com/domestic-etf",
            "https://oceanparketfs.com/international-etf",
            "https://oceanparketfs.com/diversified-income-etf.html",
            "https://oceanparketfs.com/high-income-etf.html",
        ),
        live_tested_default_route=True,
        terms_note="Ocean Park public ETF product pages and FilePoint holdings JSON may be subject to issuer terms.",
    ),
    "cambiar": IssuerCsvAdapterConfig(
        adapter_key="cambiar",
        source_provider="cambiar",
        source_access="issuer_public_product_page_linked_holdings_workbook",
        product_page_templates=("https://cambiar.com/etf/{symbol_lower}/",),
        live_tested_default_route=True,
        terms_note="Cambiar public ETF holdings workbooks may be subject to issuer terms.",
    ),
    "simplify": IssuerCsvAdapterConfig(
        adapter_key="simplify",
        source_provider="simplify",
        product_page_templates=(
            "https://www.simplify.us/etfs",
        ),
        live_tested_default_route=True,
        terms_note="Simplify public ETF holdings files may be subject to issuer terms.",
    ),
    "neos": IssuerCsvAdapterConfig(
        adapter_key="neos",
        source_provider="neos",
        url_templates=(
            "https://neosfunds.com/wp-admin/admin-ajax.php"
            "?action=download_holdings_csv&ticker={symbol_upper}",
        ),
        live_tested_default_route=True,
        terms_note="NEOS public ETF holdings files may be subject to issuer terms.",
    ),
    "strive": IssuerCsvAdapterConfig(
        adapter_key="strive",
        source_provider="strive",
        url_templates=(
            "https://www.strivefunds.com/download-holdings?fund={symbol_upper}",
        ),
        live_tested_default_route=True,
        terms_note="Strive public ETF holdings files may be subject to issuer terms.",
    ),
    "swan_global": IssuerCsvAdapterConfig(
        adapter_key="swan_global",
        source_provider="swan_global",
        source_access="issuer_public_product_page_linked_holdings_csv",
        product_page_templates=(
            "https://etfs.swanglobalinvestments.com/hedged-equity-etf/",
        ),
        live_tested_default_route=True,
        terms_note="Swan Global public ETF product pages and holdings files may be subject to issuer terms.",
    ),
    "running_oak": IssuerCsvAdapterConfig(
        adapter_key="running_oak",
        source_provider="running_oak",
        source_access="issuer_public_filepoint_holdings_json",
        url_templates=(
            "https://filepoint.live/runningoak_holdings_{issuer_product_id}_data.json",
        ),
        product_page_templates=(
            "https://www.runningoaketfs.com/full-holdings.html",
        ),
        live_tested_default_route=True,
        terms_note="Running Oak public ETF product pages and FilePoint holdings feeds may be subject to issuer terms.",
    ),
    "global_x": IssuerCsvAdapterConfig(
        adapter_key="global_x",
        source_provider="global_x",
        product_page_templates=(
            "https://www.globalxetfs.com/funds/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Global X public product pages and holdings files may be subject to issuer terms.",
    ),
    "vaneck": IssuerCsvAdapterConfig(
        adapter_key="vaneck",
        source_provider="vaneck",
        url_templates=(
            "https://www.vaneck.com/us/en/investments/{product_slug}/downloads/holdings/",
        ),
        product_page_templates=(
            "https://www.vaneck.com/us/en/investments/{symbol_lower}/holdings/",
        ),
        live_tested_default_route=True,
        terms_note="VanEck public product pages and holdings files may be subject to issuer terms.",
    ),
    "voya": IssuerCsvAdapterConfig(
        adapter_key="voya",
        source_provider="voya",
        source_access="issuer_public_daily_holdings_csv",
        url_templates=(
            "https://vimetfs.com/{symbol_lower}/holdings",
        ),
        product_page_templates=(
            "https://vimetfs.com/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Voya Investment Management public ETF holdings files may be subject to issuer terms.",
    ),
    "lazard": IssuerCsvAdapterConfig(
        adapter_key="lazard",
        source_provider="lazard",
        source_access="issuer_public_product_api_full_holdings_json",
        product_page_templates=(
            "https://www.lazardassetmanagement.com/us/en_us/"
            "investment-solutions/how-to-invest/etfs",
        ),
        live_tested_default_route=True,
        terms_note="Lazard public ETF directory and product API responses may be subject to issuer terms.",
    ),
    "rex": IssuerCsvAdapterConfig(
        adapter_key="rex",
        source_provider="rex",
        source_access="issuer_public_product_page_posted_full_holdings_csv",
        product_page_templates=(
            "https://www.rexshares.com/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="REX Shares public ETF product pages and downloadable holdings CSV files may be subject to issuer terms.",
    ),
    "groupe_bpce": IssuerCsvAdapterConfig(
        adapter_key="groupe_bpce",
        source_provider="natixis",
        source_access="issuer_public_symbol_daily_holdings_csv",
        url_templates=(
            "https://mkt.im.natixis.com/files/etfs/{symbol_upper}_daily_full_holdings.csv",
        ),
        live_tested_default_route=True,
        terms_note="Natixis public daily ETF holdings CSV files may be subject to issuer terms.",
    ),
    "wisdomtree": IssuerCsvAdapterConfig(
        adapter_key="wisdomtree",
        source_provider="wisdomtree",
    ),
    "capital_group": IssuerCsvAdapterConfig(
        adapter_key="capital_group",
        source_provider="capital_group",
        source_access="issuer_public_daily_holdings_api",
        url_templates=(
            "https://www.capitalgroup.com/api/investments/investment-service/v1/"
            "etfs/{symbol_upper}/holdings?audience=individual&redirect=true",
        ),
        product_page_templates=(
            "https://www.capitalgroup.com/individual/investments/"
            "exchange-traded-funds/holdings?etf={symbol_upper}",
        ),
        live_tested_default_route=True,
        terms_note="Capital Group public ETF holdings API responses may be subject to issuer terms.",
    ),
    "angel_oak": IssuerCsvAdapterConfig(
        adapter_key="angel_oak",
        source_provider="angel_oak",
        source_access="issuer_public_combined_account_holdings_csv",
        url_templates=(
            "https://angeloakcapital.com/secure-gs/Angel_Oak_ETF_Holdings.csv",
        ),
        product_page_templates=(
            "https://angeloakcapital.com/investments/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Angel Oak public ETF holdings files may be subject to issuer terms.",
    ),
    "dimensional": IssuerCsvAdapterConfig(
        adapter_key="dimensional",
        source_provider="dimensional",
        source_access="issuer_public_fund_details_api_full_holdings_csv",
        product_page_templates=(
            "https://www.dimensional.com/us-en/funds/{symbol_lower}/{issuer_product_id}",
        ),
        live_tested_default_route=True,
        terms_note="Dimensional public ETF product pages and holdings downloads may be subject to issuer terms.",
    ),
    "victory": IssuerCsvAdapterConfig(
        adapter_key="victory",
        source_provider="victory",
        source_access="issuer_public_product_api_all_holdings_json",
        product_page_templates=(
            "https://advisor.vcm.com/products/victoryshares-etfs/victoryshares-etfs-list/{issuer_product_id}",
        ),
        live_tested_default_route=True,
        terms_note="Victory Capital public ETF product pages and API responses may be subject to issuer terms.",
    ),
    "doubleline": IssuerCsvAdapterConfig(
        adapter_key="doubleline",
        source_provider="doubleline",
        source_access="issuer_recent_dated_holdings_pdf",
        product_page_templates=(
            "https://doubleline.com/etfs/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="DoubleLine public ETF holdings PDFs may be subject to issuer terms.",
    ),
    "eldridge": IssuerCsvAdapterConfig(
        adapter_key="eldridge",
        source_provider="eldridge",
        source_access="issuer_public_combined_daily_holdings_csv",
        url_templates=(
            "https://clozfund.com/assets/data/"
            "FilepointPanagram.40P2.P2_Holdings.csv",
        ),
        product_page_templates=(
            "https://clozfund.com/",
        ),
        live_tested_default_route=True,
        terms_note="Eldridge public ETF daily holdings files may be subject to issuer terms.",
    ),
    "akre": IssuerCsvAdapterConfig(
        adapter_key="akre",
        source_provider="akre",
        source_access="issuer_filepoint_daily_holdings_csv",
        url_templates=(
            "https://akre.filepoint.live/assets/data/FilepointAkre.40B4.B4_ETF_Holdings.csv",
        ),
        product_page_templates=(
            "https://www.akrefund.com/fund-summary/",
        ),
        live_tested_default_route=True,
        terms_note="Akre public FilePoint ETF holdings files may be subject to issuer terms.",
    ),
    "rayliant": IssuerCsvAdapterConfig(
        adapter_key="rayliant",
        source_provider="rayliant",
        source_access="issuer_product_sitemap_full_holdings_csv",
        product_page_templates=(
            "https://funds.rayliant.com/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Rayliant public ETF product pages and full holdings CSV downloads may be subject to issuer terms.",
    ),
    "astoria": IssuerCsvAdapterConfig(
        adapter_key="astoria",
        source_provider="astoria",
        source_access="issuer_wordpress_sitemap_complete_holdings_table",
        product_page_templates=(
            "https://astoriaadvisorsetfs.com/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Astoria public ETF product pages and holdings tables may be subject to issuer terms.",
    ),
    "tortoise": IssuerCsvAdapterConfig(
        adapter_key="tortoise",
        source_provider="tortoise",
        source_access="issuer_public_product_page_daily_holdings_table",
        product_page_templates=(
            "https://tortoisecapital.com/etf/{product_slug}/",
        ),
        live_tested_default_route=True,
        terms_note="Tortoise public ETF product pages and daily holdings tables may be subject to issuer terms.",
    ),
    "zacks": IssuerCsvAdapterConfig(
        adapter_key="zacks",
        source_provider="zacks",
        source_access="issuer_public_symbol_holdings_download",
        live_tested_default_route=True,
        terms_note="Zacks ETF public holdings downloads may be subject to issuer terms.",
    ),
    "arrow": IssuerCsvAdapterConfig(
        adapter_key="arrow",
        source_provider="arrow",
        source_access="issuer_public_holdings_csv",
        url_templates=(
            "https://arrowfunds.com/ArrowSharesExport.aspx?ProductID={issuer_product_id}&type=holdings",
        ),
        product_page_templates=(
            "https://arrowfunds.com/default.aspx?menuitemid={arrow_menu_item_id}",
        ),
        live_tested_default_route=True,
        terms_note="Arrow Funds public ETF holdings exports may be subject to issuer terms.",
    ),
    "alliancebernstein": IssuerCsvAdapterConfig(
        adapter_key="alliancebernstein",
        source_provider="alliancebernstein",
        source_access="issuer_public_product_page_model_workbook",
        product_page_templates=(
            "https://www.alliancebernstein.com/us/en-us/investments/products/etf/equities/{product_slug}.-.{issuer_product_id}.html",
        ),
        live_tested_default_route=True,
        terms_note="AllianceBernstein public ETF holdings workbooks may be subject to issuer terms.",
    ),
    "allspring": IssuerCsvAdapterConfig(
        adapter_key="allspring",
        source_provider="allspring",
        source_access="issuer_public_symbol_total_holdings_csv",
        url_templates=(
            "https://www.allspringglobal.com/globalassets/data/total-holdings/{symbol_upper}.csv",
        ),
        product_page_templates=(
            "https://www.allspringglobal.com/investments/performance/etfs/",
        ),
        live_tested_default_route=True,
        terms_note="Allspring public ETF total-holdings CSV files may be subject to issuer terms.",
    ),
    "acquirers": IssuerCsvAdapterConfig(
        adapter_key="acquirers",
        source_provider="acquirers",
        source_access="issuer_public_holdings_xls",
        url_templates=(
            "https://acquirersfund.com/download-holdings-usbanks.php?fticker={symbol_upper}",
        ),
        product_page_templates=(
            "https://acquirersfund.com/",
        ),
        live_tested_default_route=True,
        terms_note="Acquirers Funds public holdings workbooks may be subject to issuer terms.",
    ),
    "clearshares": IssuerCsvAdapterConfig(
        adapter_key="clearshares",
        source_provider="clearshares",
        source_access="issuer_public_holdings_xls",
        url_templates=(
            "https://clear-shares.com/download-holdings-usbanks.php?fund={symbol_lower}",
        ),
        product_page_templates=(
            "https://clear-shares.com/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="ClearShares public holdings workbooks may be subject to issuer terms.",
    ),
    "clough": IssuerCsvAdapterConfig(
        adapter_key="clough",
        source_provider="clough",
        source_access="issuer_public_wordpress_holdings_json",
        url_templates=(
            "https://www.cloughcapital.com/wp-admin/admin-ajax.php"
            "?action=get_holdings_json&slug={symbol_lower}",
        ),
        product_page_templates=(
            "https://www.cloughcapital.com/etfs/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Clough Capital public ETF holdings JSON endpoints may be subject to issuer terms.",
    ),
    "aptus": IssuerCsvAdapterConfig(
        adapter_key="aptus",
        source_provider="aptus",
        source_access="issuer_public_product_page_holdings_table",
        product_page_templates=(
            "https://aptusetfs.com/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Aptus public ETF product pages may be subject to issuer terms.",
    ),
    "proshares": IssuerCsvAdapterConfig(
        adapter_key="proshares",
        source_provider="proshares",
        product_page_templates=(
            "https://www.proshares.com/our-etfs/leveraged-and-inverse/{symbol_lower}",
        ),
        live_tested_default_route=True,
    ),
    "roundhill": IssuerCsvAdapterConfig(
        adapter_key="roundhill",
        source_provider="roundhill",
        product_page_templates=(
            "https://www.roundhillinvestments.com/etf/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Roundhill public ETF holdings files may be subject to issuer terms.",
    ),
    "defiance": IssuerCsvAdapterConfig(
        adapter_key="defiance",
        source_provider="defiance",
        product_page_templates=(
            "https://www.defianceetfs.com/{symbol_lower}-full-holdings/",
        ),
        live_tested_default_route=True,
        terms_note="Defiance public ETF holdings pages may be subject to issuer terms.",
    ),
    "advisor_shares": IssuerCsvAdapterConfig(
        adapter_key="advisor_shares",
        source_provider="advisor_shares",
        url_templates=(
            "https://advisorshares.com/wp-content/uploads/csv/holdings/"
            "AdvisorShares_{symbol_upper}_Holdings_File.csv",
        ),
        live_tested_default_route=True,
        terms_note="AdvisorShares public ETF holdings files may be subject to issuer terms.",
    ),
    "amplify": IssuerCsvAdapterConfig(
        adapter_key="amplify",
        source_provider="amplify",
        url_templates=(
            "https://amplifyetfs.com/wp-content/uploads/feeds/"
            "AmplifyWeb.40XL.XL_Holdings.csv",
        ),
        product_page_templates=(
            "https://amplifyetfs.com/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Amplify ETFs public product pages and holdings CSV files may be subject to issuer terms.",
    ),
    "teucrium": IssuerCsvAdapterConfig(
        adapter_key="teucrium",
        source_provider="teucrium",
        url_templates=(
            "https://etfs.teucrium.com/assets/data/FilepointTeucrium.40TZ.TZ_Holdings.csv",
        ),
        live_tested_default_route=True,
        terms_note="Teucrium public ETF holdings files may be subject to issuer terms.",
    ),
    "us_global_investors": IssuerCsvAdapterConfig(
        adapter_key="us_global_investors",
        source_provider="us_global_investors",
        product_page_templates=(
            "https://usglobaletfs.com/fund/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="U.S. Global Investors public ETF holdings pages may be subject to issuer terms.",
    ),
    "volatility_shares": IssuerCsvAdapterConfig(
        adapter_key="volatility_shares",
        source_provider="volatility_shares",
        url_templates=(
            "https://www.volatilityshares.com/download-holdings-usbanks-1933.php"
            "?fund={symbol_lower}",
        ),
        product_page_templates=(
            "https://www.volatilityshares.com/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Volatility Shares public ETF holdings workbooks may be subject to issuer terms.",
    ),
    "wahed": IssuerCsvAdapterConfig(
        adapter_key="wahed",
        source_provider="wahed",
        product_page_templates=(
            "https://www.wahed.com/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Wahed public ETF product pages and linked holdings sheets may be subject to issuer terms.",
    ),
    "direxion": IssuerCsvAdapterConfig(
        adapter_key="direxion",
        source_provider="direxion",
        url_templates=(
            "https://www.direxion.com/holdings/{symbol_upper}.csv",
        ),
        live_tested_default_route=True,
        terms_note="Direxion public ETF holdings files may be subject to issuer terms.",
    ),
    "distillate": IssuerCsvAdapterConfig(
        adapter_key="distillate",
        source_provider="distillate",
        url_templates=(
            "https://distillatecapital.com/wp-content/uploads/data-feeds/"
            "DistillateWeb.{symbol_upper}_Holdings.csv",
        ),
        live_tested_default_route=True,
        terms_note="Distillate Capital public ETF holdings files may be subject to issuer terms.",
    ),
    "eventide": IssuerCsvAdapterConfig(
        adapter_key="eventide",
        source_provider="eventide",
        source_access="issuer_public_listing_page_contentful_holdings_csv",
        product_page_templates=(
            "https://www.eventideinvestments.com/etfs",
        ),
        live_tested_default_route=True,
        terms_note="Eventide public ETF pages and Contentful-hosted holdings CSV files may be subject to issuer terms.",
    ),
    "etf_architect": IssuerCsvAdapterConfig(
        adapter_key="etf_architect",
        source_provider="etf_architect",
        source_access="issuer_public_product_page_wpdatatables_holdings_table",
        product_page_templates=(
            "https://funds.alphaarchitect.com/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note=(
            "Alpha Architect / ETF Architect public ETF product-page holdings tables "
            "may be subject to issuer terms."
        ),
    ),
    "faith_investor_services": IssuerCsvAdapterConfig(
        adapter_key="faith_investor_services",
        source_provider="faith_investor_services",
        source_access="issuer_product_page_next_data_holdings_csv",
        product_page_templates=(
            "https://faithinvestorservices.com/etfs/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Faith Investor Services public ETF pages and holdings CSV files may be subject to issuer terms.",
    ),
    "federated_hermes": IssuerCsvAdapterConfig(
        adapter_key="federated_hermes",
        source_provider="federated_hermes",
        source_access="issuer_public_product_page_xhr_daily_holdings_table",
        product_page_templates=(
            "https://www.federatedhermes.com/us/products/exchange-traded-funds/{issuer_product_id}.do",
        ),
        live_tested_default_route=True,
        terms_note="Federated Hermes public ETF product pages and daily holdings tables may be subject to issuer terms.",
    ),
    "oneascent": IssuerCsvAdapterConfig(
        adapter_key="oneascent",
        source_provider="oneascent",
        source_access="issuer_product_page_ajax_holdings_csv",
        product_page_templates=(
            "https://oneascent.com/investment-solutions/public-markets/etfs/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="OneAscent public ETF product pages and holdings CSV files may be subject to issuer terms.",
    ),
    "bny_mellon": IssuerCsvAdapterConfig(
        adapter_key="bny_mellon",
        source_provider="bny_mellon",
        live_tested_default_route=True,
        terms_note="BNY Mellon public ETF product pages and holdings files may be subject to issuer terms.",
    ),
    "bondbloxx": IssuerCsvAdapterConfig(
        adapter_key="bondbloxx",
        source_provider="bondbloxx",
        source_access="issuer_public_product_page_embedded_json",
        product_page_templates=(
            "https://bondbloxxetf.com/{issuer_product_id}/",
        ),
        live_tested_default_route=True,
        terms_note="BondBloxx public product-page holdings data may be subject to issuer terms.",
    ),
    "harbor": IssuerCsvAdapterConfig(
        adapter_key="harbor",
        source_provider="harbor",
        live_tested_default_route=True,
        terms_note="Harbor Capital public ETF page-data holdings may be subject to issuer terms.",
    ),
    "howard_capital": IssuerCsvAdapterConfig(
        adapter_key="howard_capital",
        source_provider="howard_capital",
        source_access="issuer_public_symbol_holdings_csv",
        product_page_templates=(
            "https://howardcmfunds.com/fund/hcm-defender-100/",
            "https://howardcmfunds.com/fund/hcm-defender-500/",
        ),
        live_tested_default_route=True,
        terms_note="Howard Capital public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "themes": IssuerCsvAdapterConfig(
        adapter_key="themes",
        source_provider="themes",
        url_templates=(
            "https://themesetfs.com/storage/holdings/Holdings-{symbol_upper}.csv",
        ),
        live_tested_default_route=True,
        terms_note="Themes ETFs public holdings CSV files may be subject to issuer terms.",
    ),
    "tema": IssuerCsvAdapterConfig(
        adapter_key="tema",
        source_provider="tema",
        url_templates=(
            "https://temaetfs.com/hubfs/Website/Holdings/{symbol_upper}-holdings.csv",
        ),
        product_page_templates=(
            "https://temaetfs.com/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Tema ETFs public product pages and holdings CSV files may be subject to issuer terms.",
    ),
    "main_management": IssuerCsvAdapterConfig(
        adapter_key="main_management",
        source_provider="main_management",
        url_templates=(
            "https://www.mainmgtetfs.com/etfs/download-{symbol_lower}.php",
        ),
        product_page_templates=(
            "https://www.mainmgtetfs.com/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Main Management public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "procuream": IssuerCsvAdapterConfig(
        adapter_key="procuream",
        source_provider="procuream",
        product_page_templates=(
            "https://procureetfs.com/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="ProcureAM public ETF product pages and holdings CSV files may be subject to issuer terms.",
    ),
    "jpmorgan": IssuerCsvAdapterConfig(
        adapter_key="jpmorgan",
        source_provider="jpmorgan",
        live_tested_default_route=True,
        terms_note="J.P. Morgan public product-data endpoints may be subject to issuer terms.",
    ),
    "fidelity": IssuerCsvAdapterConfig(
        adapter_key="fidelity",
        source_provider="fidelity",
        source_access="issuer_public_complete_creation_basket_html",
        url_templates=(
            "https://research2.fidelity.com/fidelity/screeners/etf/etfholdings.asp"
            "?sortBy=Symbol&sortDir=asc&symbol={symbol_upper}&view=Holdings",
        ),
        live_tested_default_route=True,
        terms_note="Fidelity public ETF basket-holdings pages may be subject to issuer terms.",
    ),
    "texas_capital": IssuerCsvAdapterConfig(
        adapter_key="texas_capital",
        source_provider="texas_capital",
        source_access="issuer_public_static_holdings_json",
        url_templates=(
            "https://texascapitalbank.com/sites/default/files/documents/"
            "etf-funds-management/{issuer_product_id}/data/holdings-data.json",
        ),
        product_page_templates=(
            "https://texascapitalbank.com/etfform",
        ),
        live_tested_default_route=True,
        terms_note="Texas Capital public ETF data files may be subject to issuer terms.",
    ),
    "diamond_hill": IssuerCsvAdapterConfig(
        adapter_key="diamond_hill",
        source_provider="diamond_hill",
        source_access="issuer_public_symbol_holdings_csv",
        url_templates=(
            "https://www.diamond-hill.com/sitefiles/live/documents/etfs/holdings/"
            "diamond-hill-{symbol_upper}-holdings.csv",
        ),
        product_page_templates=(
            "https://www.diamond-hill.com/investment-strategies/us-equity/"
            "large-cap-concentrated/etf/",
        ),
        live_tested_default_route=True,
        terms_note="Diamond Hill public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "deutsche_bank": IssuerCsvAdapterConfig(
        adapter_key="deutsche_bank",
        source_provider="deutsche_bank",
        source_access="issuer_public_pdp_holdings_json",
        url_templates=(
            "https://etf.dws.com/api/pdp/en-us/etf/{symbol_upper}/holdings",
        ),
        product_page_templates=(
            "https://etf.dws.com/en-us/{symbol_upper}",
        ),
        live_tested_default_route=True,
        terms_note="DWS/Xtrackers public product-data endpoints may be subject to issuer terms.",
    ),
    "deepwater": IssuerCsvAdapterConfig(
        adapter_key="deepwater",
        source_provider="deepwater",
        source_access="issuer_public_product_page_holdings_table",
        product_page_templates=(
            "https://etfs.deepwatermgmt.com/dbsc-2/",
        ),
        live_tested_default_route=True,
        terms_note="Deepwater public ETF product pages may be subject to issuer terms.",
    ),
    "first_eagle": IssuerCsvAdapterConfig(
        adapter_key="first_eagle",
        source_provider="first_eagle",
        source_access="issuer_public_product_page_holdings_table",
        product_page_templates=(
            "https://www.firsteagle.com/funds/{product_slug}",
        ),
        live_tested_default_route=True,
        terms_note="First Eagle public ETF product pages and holdings tables may be subject to issuer terms.",
    ),
    "davis": IssuerCsvAdapterConfig(
        adapter_key="davis",
        source_provider="davis",
        source_access="issuer_public_holdings_download_csv",
        url_templates=(
            "https://www.davisetfs.com/etfs/{product_slug}/holdings_download",
        ),
        product_page_templates=(
            "https://www.davisetfs.com/etfs/{product_slug}",
        ),
        live_tested_default_route=True,
        terms_note="Davis ETFs public holdings download files may be subject to issuer terms.",
    ),
    "fm_investments": IssuerCsvAdapterConfig(
        adapter_key="fm_investments",
        source_provider="fm_investments",
        source_access="issuer_public_drupal_holdings_json",
        product_page_templates=(
            "https://www.fminvest.com/etfs/{product_slug}",
        ),
        live_tested_default_route=True,
        terms_note="F/M Investments public ETF product pages and holdings API data may be subject to issuer terms.",
    ),
    "t_rowe_price": IssuerCsvAdapterConfig(
        adapter_key="t_rowe_price",
        source_provider="t_rowe_price",
        source_access="issuer_public_product_graphql_full_holdings",
        product_page_templates=(
            "https://www.troweprice.com/financial-intermediary/us/en/investments/etfs.html",
        ),
        live_tested_default_route=True,
        terms_note="T. Rowe Price public ETF product pages and product GraphQL data may be subject to issuer terms.",
    ),
    "hartford": IssuerCsvAdapterConfig(
        adapter_key="hartford",
        source_provider="hartford",
        source_access="issuer_public_full_holdings_workbook",
        url_templates=(
            "https://www.hartfordfunds.com/dam/en/docs/pub/funddocuments/"
            "fullholdings/{symbol_upper}.xlsx",
        ),
        product_page_templates=(
            "https://www.hartfordfunds.com/funds/{symbol_lower}.html",
        ),
        live_tested_default_route=True,
        terms_note="Hartford Funds public ETF full-holdings workbooks may be subject to issuer terms.",
    ),
    "gmo": IssuerCsvAdapterConfig(
        adapter_key="gmo",
        source_provider="gmo",
        source_access="issuer_public_holdings_workbook",
        live_tested_default_route=True,
        terms_note="GMO public ETF holdings workbooks may be subject to issuer terms.",
    ),
    "calamos": IssuerCsvAdapterConfig(
        adapter_key="calamos",
        source_provider="calamos",
        url_templates=(
            "https://www.calamos.com/download/{symbol_upper}Holdings.xlsx",
        ),
        live_tested_default_route=True,
        terms_note="Calamos public ETF holdings files may be subject to issuer terms.",
    ),
    "janus_henderson": IssuerCsvAdapterConfig(
        adapter_key="janus_henderson",
        source_provider="janus_henderson",
        live_tested_default_route=True,
        terms_note="Janus Henderson public ETF holdings pages may be subject to issuer terms.",
    ),
    "matthews": IssuerCsvAdapterConfig(
        adapter_key="matthews",
        source_provider="matthews",
        product_page_templates=(
            "https://www.matthewsasia.com/funds/etfs/{product_slug}/",
        ),
        live_tested_default_route=True,
        terms_note="Matthews Asia public ETF product pages and holdings tables may be subject to issuer terms.",
    ),
    "miller_value": IssuerCsvAdapterConfig(
        adapter_key="miller_value",
        source_provider="miller_value",
        source_access="issuer_public_fund_page_embedded_holdings",
        product_page_templates=(
            "https://etf.millervaluefunds.com/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Miller Value public ETF fund-page holdings payloads may be subject to issuer terms.",
    ),
    "motley_fool": IssuerCsvAdapterConfig(
        adapter_key="motley_fool",
        source_provider="motley_fool",
        source_access="issuer_public_filepoint_multi_fund_holdings_csv",
        url_templates=(
            "https://etfs.fooletfs.com/assets/data/FilepointMotleyF.40MU.FW_Holdings.csv",
        ),
        product_page_templates=(
            "https://etfs.fooletfs.com/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note=(
            "Motley Fool Asset Management public FilePoint ETF holdings CSV files "
            "may be subject to issuer terms."
        ),
    ),
    "new_york_life": IssuerCsvAdapterConfig(
        adapter_key="new_york_life",
        source_provider="new_york_life",
        source_access="issuer_public_holdings_csv",
        url_templates=(
            "https://data.nylim.com/M{symbol_upper}.csv",
        ),
        product_page_templates=(
            "https://www.nylim.com/etf",
        ),
        live_tested_default_route=True,
        terms_note="NYLI/IndexIQ public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "northern_trust": IssuerCsvAdapterConfig(
        adapter_key="northern_trust",
        source_provider="northern_trust",
        url_templates=(
            "https://www.flexshares.com/content/dam/ntflexshares/fund/"
            "{symbol_lower}/{symbol_lower}-holdings.csv",
        ),
        live_tested_default_route=True,
        terms_note="Northern Trust/FlexShares public ETF holdings files may be subject to issuer terms.",
    ),
    "first_trust": IssuerCsvAdapterConfig(
        adapter_key="first_trust",
        source_provider="first_trust",
        product_page_templates=(
            "https://www.ftportfolios.com/Retail/Etf/EtfHoldings.aspx?Ticker={symbol_upper}",
        ),
        live_tested_default_route=True,
        terms_note="First Trust public ETF holdings pages may be subject to issuer terms.",
    ),
    "franklin": IssuerCsvAdapterConfig(
        adapter_key="franklin",
        source_provider="franklin",
        live_tested_default_route=True,
        terms_note="Franklin Templeton public product-data endpoints may be subject to issuer terms.",
    ),
    "axs": IssuerCsvAdapterConfig(
        adapter_key="axs",
        source_provider="axs",
        product_page_templates=(
            "https://www.tradretfs.com/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="AXS/Tradr public ETF holdings files may be subject to issuer terms.",
    ),
    "bahl_gaynor": IssuerCsvAdapterConfig(
        adapter_key="bahl_gaynor",
        source_provider="bahl_gaynor",
        source_access="issuer_public_product_page_linked_holdings_csv",
        product_page_templates=(
            "https://www.bahl-gaynor.com/etf/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Bahl & Gaynor public ETF product pages and holdings CSV files may be subject to issuer terms.",
    ),
    "pacer": IssuerCsvAdapterConfig(
        adapter_key="pacer",
        source_provider="pacer",
        product_page_templates=(
            "https://www.paceretfs.com/products/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Pacer public ETF product pages and holdings files may be subject to issuer terms.",
    ),
    "principal": IssuerCsvAdapterConfig(
        adapter_key="principal",
        source_provider="principal",
        source_access="issuer_public_symbol_holdings_workbook",
        url_templates=(
            "https://api.assetmgmt.principalam.com/public/files?key={symbol_upper}.xlsx",
        ),
        product_page_templates=(
            "https://www.principalam.com/us/fund/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Principal public ETF product pages and holdings workbooks may be subject to issuer terms.",
    ),
    "graniteshares": IssuerCsvAdapterConfig(
        adapter_key="graniteshares",
        source_provider="graniteshares",
        live_tested_default_route=True,
        terms_note="GraniteShares public ETF product pages and holdings files may be subject to issuer terms.",
    ),
    "grayscale": IssuerCsvAdapterConfig(
        adapter_key="grayscale",
        source_provider="grayscale",
        source_access="issuer_public_product_page_embedded_json",
        product_page_templates=(
            "https://etfs.grayscale.com/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Grayscale public ETF product-page holdings data may be subject to issuer terms.",
    ),
    "hashdex": IssuerCsvAdapterConfig(
        adapter_key="hashdex",
        source_provider="hashdex",
        source_access="issuer_public_product_page_linked_workbook",
        product_page_templates=(
            "https://hashdex-etfs.com/{symbol_upper}",
        ),
        live_tested_default_route=True,
        terms_note="Hashdex public ETF product pages and linked holdings workbooks may be subject to issuer terms.",
    ),
    "horizon_kinetics": IssuerCsvAdapterConfig(
        adapter_key="horizon_kinetics",
        source_provider="horizon_kinetics",
        url_templates=(
            "https://horizonkinetics.com/wp/wp-admin/admin-ajax.php"
            "?action=daily_holdings&ticker={symbol_upper}&prefix=Holdings",
        ),
        live_tested_default_route=True,
        terms_note="Horizon Kinetics public ETF holdings workbooks may be subject to issuer terms.",
    ),
    "hennessy": IssuerCsvAdapterConfig(
        adapter_key="hennessy",
        source_provider="hennessy",
        source_access="issuer_public_product_page_holdings_table",
        product_page_templates=(
            "https://www.hennessyetfs.com/etfs/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Hennessy Funds public ETF product-page holdings tables may be subject to issuer terms.",
    ),
    "inspire": IssuerCsvAdapterConfig(
        adapter_key="inspire",
        source_provider="inspire",
        live_tested_default_route=True,
        terms_note=(
            "Inspire public holdings pages use a public ETFLogic-backed quarterly "
            "holdings endpoint that may be subject to issuer and data-provider terms."
        ),
    ),
    "american_century": IssuerCsvAdapterConfig(
        adapter_key="american_century",
        source_provider="american_century",
        live_tested_default_route=True,
        terms_note=(
            "American Century/Avantis public ETF product pages may be subject "
            "to issuer terms."
        ),
    ),
    "kraneshares": IssuerCsvAdapterConfig(
        adapter_key="kraneshares",
        source_provider="kraneshares",
        product_page_templates=(
            "https://kraneshares.com/etf/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="KraneShares public ETF holdings files may be subject to issuer terms.",
    ),
    "sprott": IssuerCsvAdapterConfig(
        adapter_key="sprott",
        source_provider="sprott",
        live_tested_default_route=True,
        terms_note="Sprott public product pages and holdings files may be subject to issuer terms.",
    ),
    "spear": IssuerCsvAdapterConfig(
        adapter_key="spear",
        source_provider="spear",
        source_access="issuer_public_holdings_csv",
        url_templates=(
            "https://spear-funds.com/archivos/SpearAdv.40FU.FU_Holdings.csv",
        ),
        product_page_templates=(
            "https://spear-funds.com/",
        ),
        live_tested_default_route=True,
        terms_note="Spear public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "palmer_square": IssuerCsvAdapterConfig(
        adapter_key="palmer_square",
        source_provider="palmer_square",
        source_access="issuer_public_product_page_embedded_holdings_json",
        product_page_templates=(
            "https://etf.palmersquarefunds.com/funds/us-etfs/{issuer_product_id}",
        ),
        live_tested_default_route=True,
        terms_note="Palmer Square public ETF product-page holdings data may be subject to issuer terms.",
    ),
    "future_fund": IssuerCsvAdapterConfig(
        adapter_key="future_fund",
        source_provider="future_fund",
        source_access="issuer_public_symbol_holdings_csv",
        product_page_templates=(
            "https://futurefundetf.com/fund/{issuer_product_id}",
        ),
        live_tested_default_route=True,
        terms_note="Future Fund public ETF holdings CSV modules may be subject to issuer terms.",
    ),
    "counterpoint": IssuerCsvAdapterConfig(
        adapter_key="counterpoint",
        source_provider="counterpoint",
        source_access="issuer_public_symbol_holdings_csv",
        url_templates=(
            "https://counterpointfunds.com/etfdata/holdings_{symbol_lower}.csv",
        ),
        product_page_templates=(
            "https://counterpointfunds.com/quantitative-equity-etf/",
        ),
        live_tested_default_route=True,
        terms_note="Counterpoint public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "anfield": IssuerCsvAdapterConfig(
        adapter_key="anfield",
        source_provider="anfield",
        source_access="issuer_public_product_page_discovered_holdings_csv",
        product_page_templates=(
            "https://anfieldfunds.com/our-funds/anfield-enhanced-market-strategy-etf/",
        ),
        live_tested_default_route=True,
        terms_note="Anfield public ETF product pages and holdings CSV exports may be subject to issuer terms.",
    ),
    "madison": IssuerCsvAdapterConfig(
        adapter_key="madison",
        source_provider="madison",
        source_access="issuer_public_aggregate_account_holdings_csv",
        url_templates=(
            "https://madisonfunds.com/data/etf/MadisonAdvWeb.40M3.M3_ETF_Holdings.csv",
        ),
        product_page_templates=(
            "https://madisonfunds.com/etfs/",
        ),
        live_tested_default_route=True,
        terms_note="Madison public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "brookmont": IssuerCsvAdapterConfig(
        adapter_key="brookmont",
        source_provider="brookmont",
        source_access="issuer_public_product_page_all_holdings_csv",
        product_page_templates=(
            "https://www.brookstoneam.com/brookstone-active-etf",
        ),
        live_tested_default_route=True,
        terms_note="Brookmont/Brookstone public ETF product pages and holdings CSV files may be subject to issuer terms.",
    ),
    "burney": IssuerCsvAdapterConfig(
        adapter_key="burney",
        source_provider="burney",
        source_access="issuer_public_product_page_wpdatatables_holdings_table",
        product_page_templates=(
            "https://burneyetfs.com/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="Burney public ETF product-page holdings tables may be subject to issuer terms.",
    ),
    "cullen": IssuerCsvAdapterConfig(
        adapter_key="cullen",
        source_provider="cullen",
        source_access="issuer_public_srp_holdings_csv",
        product_page_templates=(
            "https://www.cullenfunds.com/US/P/ETF/{symbol_upper}/",
        ),
        live_tested_default_route=True,
        terms_note="Cullen public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "ssc": IssuerCsvAdapterConfig(
        adapter_key="ssc",
        source_provider="ssc_alps",
        source_access="issuer_public_hubspot_proxy_holdings_json",
        url_templates=(
            "https://www.alpsfunds.com/_hcms/api/getData"
            "?api_url=https%3A%2F%2Fsecure.alpsinc.com%2FMarketingAPI%2Fapi%2Fv1%2FHolding%2F{symbol_upper}%2FFull",
        ),
        product_page_templates=(
            "https://www.alpsfunds.com/exchange-traded-funds/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="SS&C/ALPS public ETF product pages and holdings API proxy may be subject to issuer terms.",
    ),
    "leuthold": IssuerCsvAdapterConfig(
        adapter_key="leuthold",
        source_provider="leuthold",
        source_access="issuer_public_product_page_holdings_table",
        product_page_templates=(
            "https://funds.leutholdgroup.com/etf/{symbol_upper}",
        ),
        live_tested_default_route=True,
        terms_note="Leuthold public ETF product-page holdings tables may be subject to issuer terms.",
    ),
    "point_bridge": IssuerCsvAdapterConfig(
        adapter_key="point_bridge",
        source_provider="point_bridge",
        source_access="issuer_public_holdings_page_table",
        product_page_templates=(
            "https://www.investpolitically.com/maga-holdings/",
        ),
        live_tested_default_route=True,
        terms_note="Point Bridge public ETF holdings pages may be subject to issuer terms.",
    ),
    "tapp": IssuerCsvAdapterConfig(
        adapter_key="tapp",
        source_provider="tapp",
        source_access="issuer_public_product_page_google_holdings_csv",
        product_page_templates=(
            "https://www.tappalphafunds.com/etfs/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="TappAlpha public ETF product pages and Google Sheets holdings CSV exports may be subject to issuer terms.",
    ),
    "tuttle": IssuerCsvAdapterConfig(
        adapter_key="tuttle",
        source_provider="tuttle",
        source_access="issuer_public_product_page_google_holdings_csv",
        product_page_templates=(
            "https://www.incomeblastetfs.com/etf/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Tuttle-managed public ETF product pages and Google Sheets holdings CSV exports may be subject to issuer terms.",
    ),
    "yorkville": IssuerCsvAdapterConfig(
        adapter_key="yorkville",
        source_provider="yorkville",
        source_access="issuer_public_product_page_google_holdings_csv",
        product_page_templates=(
            "https://www.truthsocialfunds.com/etfs/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Yorkville/Truth Social Funds public ETF product pages and Google Sheets holdings CSV exports may be subject to issuer terms.",
    ),
    "true_shares": IssuerCsvAdapterConfig(
        adapter_key="true_shares",
        source_provider="true_shares",
        source_access="issuer_public_product_page_google_holdings_csv",
        product_page_templates=(
            "https://www.true-shares.com/etf/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="TrueShares public ETF product pages and Google Sheets holdings CSV exports may be subject to issuer terms.",
    ),
    "timothy_plan": IssuerCsvAdapterConfig(
        adapter_key="timothy_plan",
        source_provider="timothy_plan",
        source_access="issuer_public_symbol_holdings_page_table",
        product_page_templates=(
            "https://timothyplan.com/our-etfs/summary-etf-{issuer_product_id}-holdings.php",
        ),
        live_tested_default_route=True,
        terms_note="Timothy Plan public ETF holdings pages may be subject to issuer terms.",
    ),
    "kurv": IssuerCsvAdapterConfig(
        adapter_key="kurv",
        source_provider="kurv",
        source_access="issuer_public_holdings_csv",
        url_templates=(
            "https://web.services.kurvinvest.com/etfdata/{symbol_upper}/holdings.csv",
        ),
        product_page_templates=(
            "https://www.kurvinvest.com/etf/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Kurv public ETF holdings CSV files may be subject to issuer terms.",
    ),
    "world_gold_council": IssuerCsvAdapterConfig(
        adapter_key="world_gold_council",
        source_provider="world_gold_council",
        source_access="issuer_public_gold_trust_archive",
        url_templates=(
            "https://api.spdrgoldshares.com/api/v1/historical-archive"
            "?product={symbol_lower}&exchange=NYSE&lang=en",
        ),
        product_page_templates=(
            "https://www.spdrgoldshares.com/usa/",
        ),
        live_tested_default_route=True,
        terms_note=(
            "SPDR Gold Shares/World Gold Trust Services public archive data "
            "may be subject to issuer terms."
        ),
    ),
    "virtus": IssuerCsvAdapterConfig(
        adapter_key="virtus",
        source_provider="virtus",
        source_access="issuer_public_product_page_positions_xls",
        product_page_templates=(
            "https://www.virtus.com/products/virtus-silvant-small-mid-growth-etf",
        ),
        live_tested_default_route=True,
        terms_note="Virtus public ETF product pages and positions workbooks may be subject to issuer terms.",
    ),
    "goldman_sachs": IssuerCsvAdapterConfig(
        adapter_key="goldman_sachs",
        source_provider="goldman_sachs",
        source_access="issuer_public_holdings_xlsx",
        url_templates=(
            "https://www.gsam.com/content/dam/gsam/xls/us/en/etf/{issuer_product_id}.xlsx",
        ),
        live_tested_default_route=True,
        terms_note="Goldman Sachs Asset Management public ETF holdings workbooks may be subject to issuer terms.",
    ),
    "renaissance_capital": IssuerCsvAdapterConfig(
        adapter_key="renaissance_capital",
        source_provider="renaissance_capital",
        source_access="issuer_public_holdings_workbook",
        url_templates=(
            "https://etfs.renaissancecapital.com/excel-downloads/holdings/{symbol_lower}",
        ),
        product_page_templates=(
            "https://etfs.renaissancecapital.com/us-ipo-etf",
        ),
        live_tested_default_route=True,
        terms_note="Renaissance Capital public ETF holdings workbooks may be subject to issuer terms.",
    ),
    "yieldmax": IssuerCsvAdapterConfig(
        adapter_key="yieldmax",
        source_provider="yieldmax",
        url_templates=(
            "https://yieldmaxetfs.com/wp-content/uploads/funds/"
            "{symbol_upper}/TidalFG_Holdings_{symbol_upper}.csv",
        ),
        product_page_templates=(
            "https://yieldmaxetfs.com/our-etfs/{symbol_lower}/",
        ),
        live_tested_default_route=True,
        terms_note="YieldMax public holdings files may be subject to issuer terms.",
    ),
    "tcw": IssuerCsvAdapterConfig(
        adapter_key="tcw",
        source_provider="tcw",
        source_access="issuer_public_combined_fixed_income_holdings_pdf",
        url_templates=(
            "https://edge.sitecorecloud.io/thetcwgroupc320-tcwweb7bc3-prod0f26-25f9/"
            "media/Downloads/TCW/Products/ETFs/Holdings/FI-ETF-Q1-Holdings.pdf?sc_lang=en",
        ),
        live_tested_default_route=True,
        terms_note="TCW public fixed-income ETF holdings PDFs may be subject to issuer terms.",
    ),
}

for _adapter_key in sorted(ETFDB_RECOGNITION_ONLY_ISSUER_HINTS):
    ISSUER_ADAPTER_CONFIGS.setdefault(
        _adapter_key,
        IssuerCsvAdapterConfig(
            adapter_key=_adapter_key,
            source_provider=_adapter_key,
        ),
    )


def _issuer_adapter_from_config(config: IssuerCsvAdapterConfig) -> ETFHoldingsAdapter:
    adapter_types: dict[str, type[IssuerCsvHoldingsAdapter]] = {
        "acquirers": AcquirersHoldingsAdapter,
        "advisor_shares": AdvisorSharesHoldingsAdapter,
        "allianz": AllianzHoldingsAdapter,
        "alliancebernstein": AllianceBernsteinHoldingsAdapter,
        "allspring": AllspringHoldingsAdapter,
        "american_century": AmericanCenturyHoldingsAdapter,
        "amplify": AmplifyHoldingsAdapter,
        "adaptive_investments": AdaptiveInvestmentsHoldingsAdapter,
        "akre": AkreHoldingsAdapter,
        "rayliant": RayliantHoldingsAdapter,
        "angel_oak": AngelOakHoldingsAdapter,
        "astoria": AstoriaHoldingsAdapter,
        "anfield": AnfieldHoldingsAdapter,
        "applied_finance": AppliedFinanceHoldingsAdapter,
        "aptus": AptusHoldingsAdapter,
        "ark": ArkHoldingsAdapter,
        "arrow": ArrowHoldingsAdapter,
        "axs": AxsHoldingsAdapter,
        "bahl_gaynor": BahlGaynorHoldingsAdapter,
        "baron": BaronHoldingsAdapter,
        "bitwise": BitwiseHoldingsAdapter,
        "bny_mellon": BnyMellonHoldingsAdapter,
        "bondbloxx": BondBloxxHoldingsAdapter,
        "beyond_investing": BeyondInvestingHoldingsAdapter,
        "brandes": BrandesHoldingsAdapter,
        "brookmont": BrookmontHoldingsAdapter,
        "burney": BurneyHoldingsAdapter,
        "cambria": CambriaHoldingsAdapter,
        "cambiar": CambiarHoldingsAdapter,
        "calamos": CalamosHoldingsAdapter,
        "capital_group": CapitalGroupHoldingsAdapter,
        "castleark": CastleArkHoldingsAdapter,
        "21shares": TwentyOneSharesHoldingsAdapter,
        "coinshares": CoinSharesHoldingsAdapter,
        "abrdn": AbrdnHoldingsAdapter,
        "ssc": AlpsHoldingsAdapter,
        "clearshares": ClearSharesHoldingsAdapter,
        "clough": CloughHoldingsAdapter,
        "davis": DavisHoldingsAdapter,
        "defiance": DefianceHoldingsAdapter,
        "deepwater": DeepwaterHoldingsAdapter,
        "deutsche_bank": DeutscheBankHoldingsAdapter,
        "diamond_hill": DiamondHillHoldingsAdapter,
        "dimensional": DimensionalHoldingsAdapter,
        "direxion": DirexionHoldingsAdapter,
        "distillate": DistillateHoldingsAdapter,
        "doubleline": DoubleLineHoldingsAdapter,
        "eldridge": EldridgeHoldingsAdapter,
        "eventide": EventideHoldingsAdapter,
        "etf_architect": ETFArchitectHoldingsAdapter,
        "faith_investor_services": FaithInvestorServicesHoldingsAdapter,
        "federated_hermes": FederatedHermesHoldingsAdapter,
        "oneascent": OneAscentHoldingsAdapter,
        "palmer_square": PalmerSquareHoldingsAdapter,
        "counterpoint": CounterpointHoldingsAdapter,
        "cullen": CullenHoldingsAdapter,
        "future_fund": FutureFundHoldingsAdapter,
        "fidelity": FidelityHoldingsAdapter,
        "first_eagle": FirstEagleHoldingsAdapter,
        "fm_investments": FMInvestmentsHoldingsAdapter,
        "first_trust": FirstTrustHoldingsAdapter,
        "franklin": FranklinHoldingsAdapter,
        "global_x": GlobalXHoldingsAdapter,
        "groupe_bpce": NatixisHoldingsAdapter,
        "gmo": GmoHoldingsAdapter,
        "goldman_sachs": GoldmanSachsHoldingsAdapter,
        "graniteshares": GraniteSharesHoldingsAdapter,
        "grayscale": GrayscaleHoldingsAdapter,
        "hartford": HartfordHoldingsAdapter,
        "hashdex": HashdexHoldingsAdapter,
        "harbor": HarborHoldingsAdapter,
        "hennessy": HennessyHoldingsAdapter,
        "horizon_kinetics": HorizonKineticsHoldingsAdapter,
        "howard_capital": HowardCapitalHoldingsAdapter,
        "inspire": InspireHoldingsAdapter,
        "innovator": InnovatorHoldingsAdapter,
        "invesco": InvescoHoldingsAdapter,
        "ishares": IsharesHoldingsAdapter,
        "janus_henderson": JanusHendersonHoldingsAdapter,
        "jpmorgan": JPMorganHoldingsAdapter,
        "kraneshares": KranesharesHoldingsAdapter,
        "kurv": KurvHoldingsAdapter,
        "lazard": LazardHoldingsAdapter,
        "leuthold": LeutholdHoldingsAdapter,
        "main_management": MainManagementHoldingsAdapter,
        "madison": MadisonHoldingsAdapter,
        "matthews": MatthewsHoldingsAdapter,
        "miller_value": MillerValueHoldingsAdapter,
        "motley_fool": MotleyFoolHoldingsAdapter,
        "neos": NeosHoldingsAdapter,
        "new_york_life": NewYorkLifeHoldingsAdapter,
        "northern_trust": NorthernTrustHoldingsAdapter,
        "ocean_park": OceanParkHoldingsAdapter,
        "pacer": PacerHoldingsAdapter,
        "point_bridge": PointBridgeHoldingsAdapter,
        "principal": PrincipalHoldingsAdapter,
        "procuream": ProcureHoldingsAdapter,
        "proshares": ProSharesHoldingsAdapter,
        "renaissance_capital": RenaissanceCapitalHoldingsAdapter,
        "rex": RexHoldingsAdapter,
        "roundhill": RoundhillHoldingsAdapter,
        "running_oak": RunningOakHoldingsAdapter,
        "schwab": SchwabHoldingsAdapter,
        "simplify": SimplifyHoldingsAdapter,
        "spdr": SpdrHoldingsAdapter,
        "spear": SpearHoldingsAdapter,
        "sprott": SprottHoldingsAdapter,
        "strive": StriveHoldingsAdapter,
        "swan_global": SwanGlobalHoldingsAdapter,
        "tapp": TappAlphaHoldingsAdapter,
        "tcw": TcwHoldingsAdapter,
        "texas_capital": TexasCapitalHoldingsAdapter,
        "tortoise": TortoiseHoldingsAdapter,
        "timothy_plan": TimothyPlanHoldingsAdapter,
        "t_rowe_price": TRowePriceHoldingsAdapter,
        "tuttle": TuttleHoldingsAdapter,
        "true_shares": TrueSharesHoldingsAdapter,
        "tema": TemaHoldingsAdapter,
        "teucrium": TeucriumHoldingsAdapter,
        "themes": ThemesHoldingsAdapter,
        "us_global_investors": USGlobalInvestorsHoldingsAdapter,
        "vaneck": VanEckHoldingsAdapter,
        "vanguard": VanguardHoldingsAdapter,
        "victory": VictoryHoldingsAdapter,
        "virtus": VirtusHoldingsAdapter,
        "volatility_shares": VolatilitySharesHoldingsAdapter,
        "voya": VoyaHoldingsAdapter,
        "wahed": WahedHoldingsAdapter,
        "wisdomtree": WisdomTreeHoldingsAdapter,
        "world_gold_council": WorldGoldCouncilHoldingsAdapter,
        "yorkville": YorkvilleHoldingsAdapter,
        "yieldmax": YieldMaxHoldingsAdapter,
        "zacks": ZacksHoldingsAdapter,
    }
    adapter_type = adapter_types.get(config.adapter_key)
    if adapter_type is None:
        adapter_type = type(
            "".join(part.title() for part in config.adapter_key.split("_"))
            + "RecognitionOnlyHoldingsAdapter",
            (IssuerCsvHoldingsAdapter,),
            {},
        )
    return adapter_type(config)


ADAPTER_REGISTRY: dict[str, ETFHoldingsAdapter] = {
    **{
        adapter_key: _issuer_adapter_from_config(config)
        for adapter_key, config in ISSUER_ADAPTER_CONFIGS.items()
    },
}


def get_holdings_adapter(adapter_key: str | None) -> ETFHoldingsAdapter | None:
    if not adapter_key:
        return None
    return ADAPTER_REGISTRY.get(adapter_key.strip().lower())


def registered_adapter_keys() -> list[str]:
    return sorted(ADAPTER_REGISTRY)


def holdings_adapter_catalog() -> list[dict[str, Any]]:
    """Describe registered ETF holdings adapters and their route requirements."""

    catalog: list[dict[str, Any]] = []
    for adapter_key in sorted(ISSUER_ADAPTER_CONFIGS):
        config = ISSUER_ADAPTER_CONFIGS[adapter_key]
        catalog.append(
            {
                "adapter_key": config.adapter_key,
                "source_provider": config.source_provider,
                "source_access": config.source_access,
                "required_identifiers": list(config.required_identifiers),
                "route_identifiers": [
                    f"{adapter_key}_discovery_feed_url",
                    f"{adapter_key}_fund_list_url",
                    f"{adapter_key}_dated_holdings_url_template",
                    "issuer_product_id",
                    "fund_id",
                    "product_id",
                    "holdings_file_name",
                    "product_url",
                    "issuer_product_url",
                    "fund_url",
                    "profile_url",
                    "etf_url",
                ],
                "url_templates": list(config.url_templates),
                "product_page_templates": list(config.product_page_templates),
                "supported_formats": ["csv", "xlsx", "zip", "json", "xml", "html"],
                "live_tested_default_route": config.live_tested_default_route,
                "supports_sec_filing_fallback": config.supports_sec_filing_fallback,
                "support_route_types": [
                    *(
                        ["issuer_native_live_route"]
                        if config.live_tested_default_route
                        else []
                    ),
                    *(
                        ["sec_edgar_filing_fallback"]
                        if config.supports_sec_filing_fallback
                        else []
                    ),
                ],
                "supports_product_page_discovery": bool(config.product_page_templates),
                "supports_issuer_product_id": "issuer_product_id" in config.required_identifiers
                or any("{issuer_product_id}" in template for template in config.url_templates)
                or any(
                    "{issuer_product_id}" in template
                    for template in config.product_page_templates
                ),
                "supports_dated_fetch": bool(
                    get_holdings_adapter(config.adapter_key).dated_url_template_aliases
                ),
                "supports_etf_discovery": True,
                "parser": "generic_holdings_table",
                "parser_confidence": "medium",
                "notes": (
                    (config.terms_note + " " if config.terms_note else "")
                    + "Provider-specific adapter; issuer-native routes are preferred when "
                    "live-backed, otherwise US ETF holdings are supported through SEC EDGAR "
                    "filing fallback when SEC identifiers are available."
                ),
            }
        )
    return catalog


def infer_adapter_key(
    *,
    issuer: str | None,
    fund_family: str | None,
    name: str,
    product_url: str | None = None,
    provider_aliases: dict[str, Any] | None = None,
) -> HoldingsAdapterProbe:
    urls = [product_url]
    if provider_aliases:
        urls.extend(
            str(value)
            for key, value in provider_aliases.items()
            if key.strip().lower() in ROUTING_URL_ALIAS_KEYS and value
        )
    for raw_url in urls:
        host = _url_host(raw_url)
        if not host:
            continue
        for adapter_key, domains in ISSUER_DOMAIN_HINTS.items():
            if any(_domain_matches(host, domain) for domain in domains):
                return HoldingsAdapterProbe(
                    adapter_key=adapter_key,
                    confidence=Decimal("0.8500"),
                    status="candidate",
                    reason="Matched issuer adapter from configured issuer/product URL domain.",
                )

    haystack = " ".join(part for part in [issuer, fund_family, name] if part).lower()
    for adapter_key, hints in ISSUER_NAME_HINTS.items():
        if any(hint in haystack for hint in hints):
            return HoldingsAdapterProbe(
                adapter_key=adapter_key,
                confidence=Decimal("0.7500"),
                status="candidate",
                reason="Matched issuer/fund-family/name hint.",
            )
    return HoldingsAdapterProbe(
        adapter_key="unresolved",
        confidence=Decimal("0"),
        status="holdings_adapter_unresolved",
        reason="No configured free issuer adapter matched this ETF identity.",
    )
