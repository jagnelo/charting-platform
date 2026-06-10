from __future__ import annotations

import base64
import csv
import html
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from string import Formatter
from typing import Any, Protocol
from urllib.parse import unquote_to_bytes, urlencode, urljoin, urlparse

import httpx

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
        },
        {
            "name",
            "holding name",
            "security name",
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
            "% of fund",
            "percent of fund",
            "percentage of fund",
            "% net assets",
            "% of net assets",
        },
        {
            "shares",
            "shares held",
            "quantity",
            "shares/par value",
            "shares or principal amount",
            "par value",
        },
        {
            "market value",
            "market_value",
            "market value ($)",
            "market value usd",
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
                    "description",
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
            or (symbol or "").upper() in {"CASH", "USD", "US DOLLAR"}
            or (name or "").strip().lower() in {"cash", "us dollar", "u.s. dollar"}
        ) else "security"
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
                "% net assets",
                "% of net assets",
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
                    "shares/par value",
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
                    "market value usd",
                    "notional value",
                    "value",
                    "value usd",
                ],
            )
        )
        identity_value = _clean(_first(raw, ["cusip", "isin", "sedol"])) or cusip
        if not any([symbol, identity_value]) and not any(
            [weight, shares, market_value]
        ):
            continue
        rows.append(
            CanonicalHoldingRow(
                symbol=symbol,
                name=name,
                cusip=cusip,
                isin=_clean(_first(raw, ["isin"])),
                sedol=_clean(_first(raw, ["sedol"])),
                weight=weight,
                shares=shares,
                market_value=market_value,
                currency=_clean(_first(raw, ["currency", "local currency"])),
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


def parse_xlsx_table(raw_workbook: bytes) -> list[list[str]]:
    """Extract the first worksheet from an XLSX workbook using stdlib OpenXML parsing."""

    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(BytesIO(raw_workbook)) as workbook:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("main:si", namespace):
                texts = [node.text or "" for node in item.findall(".//main:t", namespace)]
                shared_strings.append("".join(texts))

        worksheet_name = "xl/worksheets/sheet1.xml"
        if worksheet_name not in workbook.namelist():
            worksheet_name = next(
                name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet")
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
}

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
                    headers=_holdings_request_headers(),
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
        ) else "xlsx" if (
            source_url.lower().endswith((".xlsx", ".xlsm"))
            or "spreadsheetml" in content_type
            or "excel" in content_type
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
                "ETF matched this issuer, but this provider-specific holdings route "
                "is not implemented and live-backed yet."
                if not has_known_route_shape
                else (
                    "ETF matched this issuer, but the provider-specific route "
                    "metadata required by this adapter is not configured yet."
                )
            ),
            issuer_product_id=normalized.get("issuer_product_id"),
            required_identifiers=missing or list(self.config.required_identifiers),
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
                probe = self.probe(symbol=symbol, name="", identifiers=identifiers or {})
                required = ", ".join(probe.required_identifiers) or "provider-specific route"
                raise ValueError(
                    f"{self.adapter_key} needs issuer route metadata for {symbol}; "
                    f"configure the adapter-specific route fields: product_url, {required}."
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
                headers=_holdings_request_headers(accept="text/html,*/*"),
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
    pass


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
    pass


class GlobalXHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class VanEckHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class WisdomTreeHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class ProSharesHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class DirexionHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class JPMorganHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class FidelityHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


class FranklinHoldingsAdapter(IssuerCsvHoldingsAdapter):
    pass


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
    "schwab": IssuerCsvAdapterConfig(
        adapter_key="schwab",
        source_provider="schwab",
        product_page_templates=(
            "https://www.schwabassetmanagement.com/products/{symbol_lower}",
        ),
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
    "proshares": IssuerCsvAdapterConfig(
        adapter_key="proshares",
        source_provider="proshares",
    ),
    "direxion": IssuerCsvAdapterConfig(
        adapter_key="direxion",
        source_provider="direxion",
    ),
    "jpmorgan": IssuerCsvAdapterConfig(
        adapter_key="jpmorgan",
        source_provider="jpmorgan",
    ),
    "fidelity": IssuerCsvAdapterConfig(
        adapter_key="fidelity",
        source_provider="fidelity",
    ),
    "franklin": IssuerCsvAdapterConfig(
        adapter_key="franklin",
        source_provider="franklin",
    ),
    "sprott": IssuerCsvAdapterConfig(
        adapter_key="sprott",
        source_provider="sprott",
        live_tested_default_route=True,
        terms_note="Sprott public product pages and holdings files may be subject to issuer terms.",
    ),
}


def _issuer_adapter_from_config(config: IssuerCsvAdapterConfig) -> ETFHoldingsAdapter:
    adapter_types: dict[str, type[IssuerCsvHoldingsAdapter]] = {
        "ark": ArkHoldingsAdapter,
        "direxion": DirexionHoldingsAdapter,
        "fidelity": FidelityHoldingsAdapter,
        "franklin": FranklinHoldingsAdapter,
        "global_x": GlobalXHoldingsAdapter,
        "invesco": InvescoHoldingsAdapter,
        "ishares": IsharesHoldingsAdapter,
        "jpmorgan": JPMorganHoldingsAdapter,
        "proshares": ProSharesHoldingsAdapter,
        "schwab": SchwabHoldingsAdapter,
        "spdr": SpdrHoldingsAdapter,
        "sprott": SprottHoldingsAdapter,
        "vaneck": VanEckHoldingsAdapter,
        "vanguard": VanguardHoldingsAdapter,
        "wisdomtree": WisdomTreeHoldingsAdapter,
    }
    adapter_type = adapter_types.get(config.adapter_key)
    if adapter_type is None:
        raise ValueError(f"No provider-specific ETF holdings adapter for {config.adapter_key}.")
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
                "supported_formats": ["csv", "xlsx", "zip"],
                "live_tested_default_route": config.live_tested_default_route,
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
                    + "Provider-specific adapter; support is only claimed when live-backed routes pass."
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
