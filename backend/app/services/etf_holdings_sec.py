from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any
from xml.etree import ElementTree

from app.services.etf_holdings_adapters import CanonicalHoldingRow

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def parse_sec_nport_xml(raw_xml: str) -> tuple[date | None, list[CanonicalHoldingRow]]:
    """Parse SEC N-PORT/N-PORT-P-like XML into canonical holding rows.

    SEC filing XML has evolved and vendor wrappers differ, so this parser is
    intentionally namespace-tolerant and field-alias based. It is a reconstruction
    primitive, not a claim that every historical filing is perfectly normalized.
    """

    root = ElementTree.fromstring(raw_xml)
    report_date = _parse_date(_first_text(root, ["repPdDate", "periodOfReport", "reportDate"]))
    security_nodes = [
        node
        for node in root.iter()
        if _local_name(node.tag).lower() in {"invstorsec", "invstorsecurity", "holding"}
    ]
    rows: list[CanonicalHoldingRow] = []
    for position, node in enumerate(security_nodes, start=1):
        name = _first_text(node, ["name", "issuerName", "title"])
        cusip = _first_text(node, ["cusip"])
        isin = _identifier_text(node, "isin") or _first_text(node, ["isin"])
        sedol = _identifier_text(node, "sedol") or _first_text(node, ["sedol"])
        symbol = _first_text(node, ["ticker", "tickerSymbol", "symbol"])
        asset_type = (_first_text(node, ["assetCat", "assetCategory", "securityType"]) or "equity").lower()
        row_type = "cash" if asset_type in {"cash", "currency"} else "security"
        weight = _decimal(_first_text(node, ["pctVal", "percentageValue", "weight"]))
        if weight is not None and weight > 1:
            weight = weight / Decimal("100")
        rows.append(
            CanonicalHoldingRow(
                symbol=symbol,
                name=name,
                cusip=cusip,
                isin=isin,
                sedol=sedol,
                weight=weight,
                shares=_decimal(_first_text(node, ["balance", "shares", "quantity"])),
                market_value=_decimal(
                    _first_text(node, ["valUSD", "valueUSD", "marketValue", "value"])
                ),
                currency=_first_text(node, ["curCd", "currency", "currencyCode"]),
                country=_first_text(node, ["country", "issuerCountry"]),
                holding_type=asset_type,
                row_type=row_type,
                source_row_id=str(position),
                extra_data=_flatten_direct_children(node),
            )
        )
    return report_date, rows


def parse_sec_legacy_holdings_xml(raw_xml: str) -> tuple[date | None, list[CanonicalHoldingRow]]:
    """Parse simple legacy SEC N-Q/N-CSR-style XML or HTML holding tables.

    Older fund filings are much less standardized than N-PORT. This parser is a
    conservative reconstruction primitive for XML/table-like filings that expose
    one node per investment/security/holding with common field names.
    """

    try:
        root = ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError:
        return _parse_sec_legacy_holdings_html(raw_xml)

    report_date = _parse_date(
        _first_text(root, ["periodOfReport", "reportDate", "dateOfReport", "asOfDate"])
    )
    candidate_nodes = [
        node
        for node in root.iter()
        if _local_name(node.tag).lower()
        in {"holding", "investment", "security", "portfolioholding", "scheduleholding"}
    ]
    rows: list[CanonicalHoldingRow] = []
    for position, node in enumerate(candidate_nodes, start=1):
        name = _first_text(node, ["issuerName", "name", "securityName", "title"])
        cusip = _first_text(node, ["cusip", "cusipNumber"])
        symbol = _first_text(node, ["ticker", "tickerSymbol", "symbol"])
        market_value = _decimal(
            _first_text(
                node,
                ["value", "marketValue", "valueUSD", "fairValue", "investmentValue"],
            )
        )
        shares = _decimal(_first_text(node, ["shares", "balance", "quantity", "principalAmount"]))
        if not any([name, cusip, symbol]) or not any([market_value, shares]):
            continue
        asset_type = (
            _first_text(node, ["securityType", "assetCategory", "assetCat", "type"])
            or "equity"
        ).lower()
        row_type = "cash" if asset_type in {"cash", "currency"} else "security"
        weight = _decimal(
            _first_text(
                node,
                [
                    "percentageOfNetAssets",
                    "pctNetAssets",
                    "percentOfNetAssets",
                    "percentOfValue",
                    "weight",
                ],
            )
        )
        if weight is not None and weight > 1:
            weight = weight / Decimal("100")
        rows.append(
            CanonicalHoldingRow(
                symbol=symbol,
                name=name,
                cusip=cusip,
                isin=_identifier_text(node, "isin") or _first_text(node, ["isin"]),
                sedol=_identifier_text(node, "sedol") or _first_text(node, ["sedol"]),
                weight=weight,
                shares=shares,
                market_value=market_value,
                currency=_first_text(node, ["currency", "currencyCode", "curCd"]) or "USD",
                country=_first_text(node, ["country", "issuerCountry"]),
                holding_type=asset_type,
                row_type=row_type,
                source_row_id=str(position),
                extra_data=_flatten_direct_children(node),
            )
        )
    if rows:
        return report_date, rows
    html_report_date, html_rows = _parse_sec_legacy_holdings_html(raw_xml)
    return report_date or html_report_date, html_rows


class _HTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized == "table":
            self._current_table = []
        elif normalized == "tr" and self._current_table is not None:
            self._current_row = []
        elif normalized in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            text = data.strip()
            if text:
                self._current_cell.append(text)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"td", "th"} and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append(" ".join(self._current_cell).strip())
            self._current_cell = None
        elif normalized == "tr" and self._current_row is not None:
            if self._current_table is not None and any(_clean(value) for value in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
        elif normalized == "table" and self._current_table is not None:
            if self._current_table:
                self.tables.append(self._current_table)
            self._current_table = None


def _parse_sec_legacy_holdings_html(raw_html: str) -> tuple[date | None, list[CanonicalHoldingRow]]:
    parser = _HTMLTableParser()
    parser.feed(raw_html)
    report_date = _parse_date(_first_date_like_text(raw_html))
    rows: list[CanonicalHoldingRow] = []
    for table in parser.tables:
        parsed = _parse_legacy_table_rows(table)
        if len(parsed) > len(rows):
            rows = parsed
    return report_date, rows


def _parse_legacy_table_rows(table_rows: list[list[str]]) -> list[CanonicalHoldingRow]:
    header_index = next(
        (index for index, row in enumerate(table_rows[:20]) if _looks_like_legacy_header(row)),
        None,
    )
    if header_index is None:
        return []
    header = table_rows[header_index]
    parsed: list[CanonicalHoldingRow] = []
    pending_identity: dict[str, str] | None = None
    for position, row in enumerate(table_rows[header_index + 1 :], start=1):
        raw = _row_dict(header, row)
        name = _first_table_value(
            raw,
            [
                "issuer",
                "issuer name",
                "name",
                "security",
                "security name",
                "description",
                "name of issuer",
                "title of issue",
            ],
        )
        symbol = _first_table_value(raw, ["ticker", "ticker symbol", "symbol"])
        cusip = _first_table_value(raw, ["cusip", "cusip number"]) or _extract_cusip(name)
        market_value_item = _first_table_item(
            raw,
            [
                "value",
                "value (000)",
                "value (000s)",
                "value in thousands",
                "market value",
                "market value (000)",
                "market value (000s)",
                "fair value",
                "investment value",
            ],
        )
        market_value_key, market_value_text = market_value_item or (None, None)
        market_value = _decimal(market_value_text)
        if market_value is not None and market_value_key and _value_header_is_thousands(
            market_value_key
        ):
            market_value *= Decimal("1000")
        shares = _decimal(
            _first_table_value(
                raw,
                [
                    "shares",
                    "shares held",
                    "quantity",
                    "principal amount",
                    "shares or principal amount",
                    "shares/par value",
                ],
            )
        )
        has_identity = any([name, symbol, cusip])
        has_position = any([market_value, shares])
        if has_identity and not has_position:
            pending_identity = raw
            continue
        if not has_identity and has_position and pending_identity is not None:
            raw = {**pending_identity, **{key: value for key, value in raw.items() if _clean(value)}}
            name = _first_table_value(
            raw,
            [
                "issuer",
                "issuer name",
                "name",
                "security",
                "security name",
                "description",
                "name of issuer",
                "title of issue",
            ],
        )
            symbol = _first_table_value(raw, ["ticker", "ticker symbol", "symbol"])
            cusip = _first_table_value(raw, ["cusip", "cusip number"]) or _extract_cusip(name)
        pending_identity = None
        if not any([name, symbol, cusip]) or not any([market_value, shares]):
            continue
        asset_type = (
            _first_table_value(raw, ["security type", "asset category", "asset class", "type"])
            or "equity"
        ).lower()
        weight = _decimal(
            _first_table_value(
                raw,
                [
                    "percentage of net assets",
                    "percent of net assets",
                    "% of net assets",
                    "% net assets",
                    "percent of value",
                    "weight",
                ],
            )
        )
        if weight is not None and weight > 1:
            weight = weight / Decimal("100")
        parsed.append(
            CanonicalHoldingRow(
                symbol=symbol,
                name=name,
                cusip=cusip,
                isin=_first_table_value(raw, ["isin"]),
                sedol=_first_table_value(raw, ["sedol"]),
                weight=weight,
                shares=shares,
                market_value=market_value,
                currency=_first_table_value(raw, ["currency", "currency code"]) or "USD",
                holding_type=asset_type,
                row_type="cash" if asset_type in {"cash", "currency"} else "security",
                source_row_id=str(position),
                extra_data=raw,
            )
        )
    return parsed


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _first_text(root: ElementTree.Element, names: list[str]) -> str | None:
    wanted = {name.lower() for name in names}
    for node in root.iter():
        if _local_name(node.tag).lower() in wanted:
            return _clean(node.text)
    return None


def _first_date_like_text(raw_text: str) -> str | None:
    match = re.search(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", raw_text)
    if match:
        return match.group(0)
    match = re.search(r"\b(19|20)\d{2}/\d{2}/\d{2}\b", raw_text)
    if match:
        return match.group(0).replace("/", "-")
    match = re.search(
        r"\b("
        + "|".join(_MONTHS)
        + r")\s+([0-3]?\d),\s*((?:19|20)\d{2})\b",
        raw_text,
        flags=re.IGNORECASE,
    )
    if match:
        month = _MONTHS[match.group(1).lower()]
        day = int(match.group(2))
        year = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("\xa0", " "))


def _extract_cusip(value: str | None) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    explicit = re.search(r"\bCUSIP[:\s]*([0-9A-Z]{8}[0-9A-Z])\b", text.upper())
    if explicit:
        return explicit.group(1)
    for token in re.findall(r"\b[0-9A-Z]{8}[0-9A-Z]\b", text.upper()):
        if any(char.isdigit() for char in token):
            return token
    return None


def _looks_like_legacy_header(row: list[str]) -> bool:
    columns = {_normalize_header(value) for value in row if _clean(value)}
    if not columns:
        return False
    has_identity = bool(
        columns
        & {
            "issuer",
            "issuer name",
            "name",
            "security",
            "security name",
            "description",
            "name of issuer",
            "title of issue",
            "ticker",
            "ticker symbol",
            "symbol",
            "cusip",
            "cusip number",
        }
    )
    has_position = bool(
        columns
        & {
            "shares",
            "shares held",
            "quantity",
            "principal amount",
            "shares or principal amount",
            "shares/par value",
            "value",
            "market value",
            "value (000)",
            "value (000s)",
            "value in thousands",
            "market value (000)",
            "market value (000s)",
            "fair value",
            "investment value",
        }
    )
    return has_identity and has_position


def _row_dict(header: list[str], row: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for index, column in enumerate(header):
        key = _normalize_header(column) if _clean(column) else f"__column_{index + 1}"
        value = row[index] if index < len(row) else ""
        result[key] = value.strip()
    return result


def _first_table_value(row: dict[str, str], aliases: list[str]) -> str | None:
    item = _first_table_item(row, aliases)
    return item[1] if item is not None else None


def _first_table_item(row: dict[str, str], aliases: list[str]) -> tuple[str, str] | None:
    for alias in aliases:
        key = _normalize_header(alias)
        value = row.get(key)
        if _clean(value):
            return key, _clean(value) or ""
    return None


def _value_header_is_thousands(header: str) -> bool:
    normalized = _normalize_header(header)
    return any(token in normalized for token in ["(000)", "(000s)", "thousands"])


def _identifier_text(root: ElementTree.Element, identifier_type: str) -> str | None:
    target = identifier_type.lower()
    for node in root.iter():
        if _local_name(node.tag).lower() != "identifier":
            continue
        id_type = _first_text(node, ["identifierType", "type"])
        if id_type and id_type.strip().lower() == target:
            return _first_text(node, ["identifierValue", "value"])
    return None


def _decimal(value: str | None) -> Decimal | None:
    text = _clean(value)
    if text is None:
        return None
    normalized = text.replace(",", "").replace("$", "").replace("\u2212", "-").strip()
    is_parenthesized_negative = normalized.startswith("(") and normalized.endswith(")")
    if is_parenthesized_negative:
        normalized = normalized[1:-1].strip()
    is_percent = normalized.endswith("%")
    if is_percent:
        normalized = normalized[:-1]
    try:
        parsed = Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None
    if is_parenthesized_negative:
        parsed = -parsed
    return parsed / Decimal("100") if is_percent else parsed


def _parse_date(value: str | None) -> date | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _flatten_direct_children(root: ElementTree.Element) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for child in list(root):
        key = _local_name(child.tag)
        value = _clean(child.text)
        if value is not None and key not in flattened:
            flattened[key] = value
    return flattened
