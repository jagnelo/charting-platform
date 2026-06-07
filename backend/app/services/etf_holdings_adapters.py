from __future__ import annotations

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
from urllib.parse import urljoin, urlparse

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


def _first(row: dict[str, Any], aliases: list[str]) -> Any:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in aliases:
        if alias.lower() in lowered:
            return lowered[alias.lower()]
    return None


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
        weight = _decimal(
            _first(
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
        )
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


def _discover_holdings_download_url(product_page_url: str, html: str) -> str | None:
    """Find the most likely linked holdings table from an issuer product page."""

    candidates: list[tuple[int, str]] = []
    discovered = [
        match.group("url").strip()
        for match in _URL_ATTRIBUTE_RE.finditer(html)
    ]
    discovered.extend(
        match.group("url").strip()
        for match in _QUOTED_FILE_URL_RE.finditer(html)
    )
    for href in discovered:
        if not href:
            continue
        if not (
            _SUPPORTED_HOLDINGS_FILE_RE.search(href)
            or _HOLDINGS_DOWNLOAD_HINT_RE.search(href)
        ):
            continue
        if not (
            _HOLDINGS_LINK_HINT_RE.search(href)
            or _HOLDINGS_DOWNLOAD_HINT_RE.search(href)
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
        candidates.append((score, url))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


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
    """Adapter for issuer/public holdings CSV URLs configured on an ETF profile.

    Issuer-specific adapters can subclass or replace this when URL discovery or
    schema quirks become concrete. The registry still gives routing/health code
    one stable adapter interface from day one.
    """

    def __init__(self, adapter_key: str, source_provider: str | None = None) -> None:
        self.adapter_key = adapter_key
        self.source_provider = source_provider or adapter_key

    def probe(self, *, symbol: str, name: str, identifiers: dict[str, str]) -> HoldingsAdapterProbe:
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.5000"),
            status="candidate",
            reason="ETF profile has a configured public holdings CSV route.",
            issuer_product_id=identifiers.get("issuer_product_id"),
            source_url=identifiers.get("holdings_url"),
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
        async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                source_url,
                headers=_holdings_request_headers(),
                follow_redirects=True,
            )
        response.raise_for_status()
        raw_content = getattr(response, "content", None)
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
                raw_content = response.text.encode()
            rows, raw_text, raw_json = parse_holdings_zip(raw_content)
        elif source_format == "xlsx":
            if not isinstance(raw_content, bytes):
                raw_content = response.text.encode()
            workbook_rows = parse_xlsx_table(raw_content)
            rows = parse_holdings_table(workbook_rows)
            raw_text = _table_to_text(workbook_rows)
            raw_json = {"source_format": "xlsx", "workbook_rows": workbook_rows}
        else:
            rows = parse_holdings_csv(response.text)
            raw_text = response.text
            if not rows and self.adapter_key == "ishares":
                rows = _parse_ishares_inline_top_holdings(response.text)
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
    terms_note: str | None = None


class IssuerCsvHoldingsAdapter(PublicCsvHoldingsAdapter):
    """Issuer-aware CSV adapter driven by ETF identity/profile metadata.

    Free issuer files are useful but brittle. This adapter deliberately avoids
    guessing URLs from only a ticker. Instead it resolves routes from explicit
    ETF profile identifiers: a source URL, a profile-specific URL template, or
    issuer-specific template inputs such as a holdings file name.
    """

    source_url_aliases = (
        "holdings_url",
        "issuer_holdings_url",
        "holdings_csv_url",
        "latest_holdings_url",
        "holdings_download_url",
    )
    url_template_aliases = (
        "holdings_url_template",
        "issuer_holdings_url_template",
        "latest_holdings_url_template",
    )
    dated_url_template_aliases = (
        "dated_holdings_url_template",
        "holdings_date_url_template",
        "historical_holdings_url_template",
        "issuer_historical_holdings_url_template",
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
        return HoldingsAdapterProbe(
            adapter_key=self.adapter_key,
            confidence=Decimal("0.6500"),
            status="needs_issuer_route",
            reason=(
                "ETF matched this issuer, but no source URL, URL template, or required "
                "issuer route identifiers are configured yet."
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
                required = ", ".join(probe.required_identifiers) or "holdings_url_template"
                raise ValueError(
                    f"{self.adapter_key} needs issuer route metadata for {symbol}; "
                    f"configure one of: holdings_url, holdings_url_template, product_url, {required}."
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
                "configure one of: dated_holdings_url_template, "
                "holdings_date_url_template, historical_holdings_url_template, "
                "issuer_historical_holdings_url_template."
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


ISSUER_ADAPTER_CONFIGS: dict[str, IssuerCsvAdapterConfig] = {
    "ishares": IssuerCsvAdapterConfig(
        adapter_key="ishares",
        source_provider="ishares",
        url_templates=(
            "https://www.ishares.com/us/products/{issuer_product_id}/"
            "?fileType=csv&fileName={symbol}_holdings&dataType=fund",
        ),
        required_identifiers=("issuer_product_id",),
        terms_note="iShares/BlackRock public holdings files may be subject to issuer terms.",
    ),
    "spdr": IssuerCsvAdapterConfig(
        adapter_key="spdr",
        source_provider="spdr",
        url_templates=(
            "https://www.ssga.com/us/en/intermediary/etfs/library-content/"
            "products/fund-data/etfs/us/holdings-daily-us-en-{symbol_lower}.xlsx",
        ),
        terms_note="State Street/SPDR public holdings files may be subject to issuer terms.",
    ),
    "vanguard": IssuerCsvAdapterConfig(
        adapter_key="vanguard",
        source_provider="vanguard",
        product_page_templates=(
            "https://investor.vanguard.com/investment-products/etfs/profile/{symbol_lower}",
        ),
        terms_note="Vanguard public product pages and holdings files may be subject to issuer terms.",
    ),
    "invesco": IssuerCsvAdapterConfig(
        adapter_key="invesco",
        source_provider="invesco",
        product_page_templates=(
            "https://www.invesco.com/us/financial-products/etfs/holdings"
            "?audienceType=Investor&ticker={symbol}",
        ),
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
            "https://ark-funds.com/wp-content/fundsiteliterature/holdings/{holdings_file_name}.csv",
        ),
        required_identifiers=("holdings_file_name",),
        terms_note="ARK public holdings files may be subject to issuer terms.",
    ),
    "global_x": IssuerCsvAdapterConfig(
        adapter_key="global_x",
        source_provider="global_x",
        product_page_templates=(
            "https://www.globalxetfs.com/funds/{symbol_lower}/",
        ),
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
        terms_note="VanEck public product pages and holdings files may be subject to issuer terms.",
    ),
    "wisdomtree": IssuerCsvAdapterConfig(
        adapter_key="wisdomtree",
        source_provider="wisdomtree",
        required_identifiers=("holdings_url_template", "issuer_product_id"),
    ),
    "proshares": IssuerCsvAdapterConfig(
        adapter_key="proshares",
        source_provider="proshares",
        required_identifiers=("holdings_url_template", "issuer_product_id"),
    ),
    "direxion": IssuerCsvAdapterConfig(
        adapter_key="direxion",
        source_provider="direxion",
        required_identifiers=("holdings_url_template", "issuer_product_id"),
    ),
    "jpmorgan": IssuerCsvAdapterConfig(
        adapter_key="jpmorgan",
        source_provider="jpmorgan",
        required_identifiers=("holdings_url_template", "issuer_product_id"),
    ),
    "fidelity": IssuerCsvAdapterConfig(
        adapter_key="fidelity",
        source_provider="fidelity",
        required_identifiers=("holdings_url_template", "issuer_product_id"),
    ),
    "franklin": IssuerCsvAdapterConfig(
        adapter_key="franklin",
        source_provider="franklin",
        required_identifiers=("holdings_url_template", "issuer_product_id"),
    ),
}


ADAPTER_REGISTRY: dict[str, ETFHoldingsAdapter] = {
    "configured_csv_url": PublicCsvHoldingsAdapter("configured_csv_url", "issuer_csv"),
    **{
        adapter_key: IssuerCsvHoldingsAdapter(config)
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

    catalog: list[dict[str, Any]] = [
        {
            "adapter_key": "configured_csv_url",
            "source_provider": "issuer_csv",
            "source_access": "configured_public_holdings_file",
            "required_identifiers": ["holdings_url"],
            "route_identifiers": [
                "holdings_url",
                "issuer_holdings_url",
                "holdings_csv_url",
                "latest_holdings_url",
                "holdings_download_url",
            ],
            "url_templates": [],
            "product_page_templates": [],
            "supported_formats": ["csv", "xlsx", "zip"],
            "supports_product_page_discovery": False,
            "supports_issuer_product_id": False,
            "supports_dated_fetch": False,
            "supports_etf_discovery": False,
            "parser": "generic_holdings_table",
            "parser_confidence": "medium",
            "notes": "Uses an explicitly configured public holdings file URL.",
        }
    ]
    for adapter_key in sorted(ISSUER_ADAPTER_CONFIGS):
        config = ISSUER_ADAPTER_CONFIGS[adapter_key]
        catalog.append(
            {
                "adapter_key": config.adapter_key,
                "source_provider": config.source_provider,
                "source_access": config.source_access,
                "required_identifiers": list(config.required_identifiers),
                "route_identifiers": [
                    "holdings_url",
                    "issuer_holdings_url",
                    "holdings_csv_url",
                    "latest_holdings_url",
                    "holdings_download_url",
                    "holdings_url_template",
                    "issuer_holdings_url_template",
                    "latest_holdings_url_template",
                    "dated_holdings_url_template",
                    "holdings_date_url_template",
                    "historical_holdings_url_template",
                    "issuer_historical_holdings_url_template",
                    "discovery_feed_url",
                    "issuer_fund_list_url",
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
                "supports_product_page_discovery": True,
                "supports_issuer_product_id": "issuer_product_id" in config.required_identifiers
                or any("{issuer_product_id}" in template for template in config.url_templates)
                or any(
                    "{issuer_product_id}" in template
                    for template in config.product_page_templates
                ),
                "supports_dated_fetch": True,
                "supports_etf_discovery": True,
                "parser": "generic_holdings_table",
                "parser_confidence": "medium",
                "notes": (
                    (config.terms_note + " " if config.terms_note else "")
                    + "Supports explicit issuer fund-list discovery feeds; does not crawl issuer sites automatically."
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
