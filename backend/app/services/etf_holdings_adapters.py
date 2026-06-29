from __future__ import annotations

import asyncio
import base64
import csv
import html
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from io import BytesIO, StringIO
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
    "ssc": ["ss&c", "ss and c"],
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


class WisdomTreeHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


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


class FidelityHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


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
    "bitwise": IssuerCsvAdapterConfig(
        adapter_key="bitwise",
        source_provider="bitwise",
        product_page_templates=(
            "https://{symbol_lower}etf.com/",
        ),
        live_tested_default_route=True,
        terms_note="Bitwise public ETF product pages may be subject to issuer terms.",
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
    "wisdomtree": IssuerCsvAdapterConfig(
        adapter_key="wisdomtree",
        source_provider="wisdomtree",
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
    "pacer": IssuerCsvAdapterConfig(
        adapter_key="pacer",
        source_provider="pacer",
        product_page_templates=(
            "https://www.paceretfs.com/products/{symbol_lower}",
        ),
        live_tested_default_route=True,
        terms_note="Pacer public ETF product pages and holdings files may be subject to issuer terms.",
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
        "american_century": AmericanCenturyHoldingsAdapter,
        "amplify": AmplifyHoldingsAdapter,
        "aptus": AptusHoldingsAdapter,
        "ark": ArkHoldingsAdapter,
        "arrow": ArrowHoldingsAdapter,
        "axs": AxsHoldingsAdapter,
        "baron": BaronHoldingsAdapter,
        "bitwise": BitwiseHoldingsAdapter,
        "bny_mellon": BnyMellonHoldingsAdapter,
        "bondbloxx": BondBloxxHoldingsAdapter,
        "beyond_investing": BeyondInvestingHoldingsAdapter,
        "cambria": CambriaHoldingsAdapter,
        "cambiar": CambiarHoldingsAdapter,
        "calamos": CalamosHoldingsAdapter,
        "21shares": TwentyOneSharesHoldingsAdapter,
        "abrdn": AbrdnHoldingsAdapter,
        "clearshares": ClearSharesHoldingsAdapter,
        "defiance": DefianceHoldingsAdapter,
        "direxion": DirexionHoldingsAdapter,
        "distillate": DistillateHoldingsAdapter,
        "fidelity": FidelityHoldingsAdapter,
        "fm_investments": FMInvestmentsHoldingsAdapter,
        "first_trust": FirstTrustHoldingsAdapter,
        "franklin": FranklinHoldingsAdapter,
        "global_x": GlobalXHoldingsAdapter,
        "gmo": GmoHoldingsAdapter,
        "graniteshares": GraniteSharesHoldingsAdapter,
        "grayscale": GrayscaleHoldingsAdapter,
        "hartford": HartfordHoldingsAdapter,
        "hashdex": HashdexHoldingsAdapter,
        "harbor": HarborHoldingsAdapter,
        "hennessy": HennessyHoldingsAdapter,
        "horizon_kinetics": HorizonKineticsHoldingsAdapter,
        "inspire": InspireHoldingsAdapter,
        "innovator": InnovatorHoldingsAdapter,
        "invesco": InvescoHoldingsAdapter,
        "ishares": IsharesHoldingsAdapter,
        "janus_henderson": JanusHendersonHoldingsAdapter,
        "jpmorgan": JPMorganHoldingsAdapter,
        "kraneshares": KranesharesHoldingsAdapter,
        "kurv": KurvHoldingsAdapter,
        "main_management": MainManagementHoldingsAdapter,
        "matthews": MatthewsHoldingsAdapter,
        "neos": NeosHoldingsAdapter,
        "new_york_life": NewYorkLifeHoldingsAdapter,
        "northern_trust": NorthernTrustHoldingsAdapter,
        "pacer": PacerHoldingsAdapter,
        "procuream": ProcureHoldingsAdapter,
        "proshares": ProSharesHoldingsAdapter,
        "renaissance_capital": RenaissanceCapitalHoldingsAdapter,
        "roundhill": RoundhillHoldingsAdapter,
        "running_oak": RunningOakHoldingsAdapter,
        "schwab": SchwabHoldingsAdapter,
        "simplify": SimplifyHoldingsAdapter,
        "spdr": SpdrHoldingsAdapter,
        "sprott": SprottHoldingsAdapter,
        "strive": StriveHoldingsAdapter,
        "swan_global": SwanGlobalHoldingsAdapter,
        "tapp": TappAlphaHoldingsAdapter,
        "t_rowe_price": TRowePriceHoldingsAdapter,
        "tema": TemaHoldingsAdapter,
        "teucrium": TeucriumHoldingsAdapter,
        "themes": ThemesHoldingsAdapter,
        "us_global_investors": USGlobalInvestorsHoldingsAdapter,
        "vaneck": VanEckHoldingsAdapter,
        "vanguard": VanguardHoldingsAdapter,
        "volatility_shares": VolatilitySharesHoldingsAdapter,
        "wahed": WahedHoldingsAdapter,
        "wisdomtree": WisdomTreeHoldingsAdapter,
        "world_gold_council": WorldGoldCouncilHoldingsAdapter,
        "yieldmax": YieldMaxHoldingsAdapter,
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
