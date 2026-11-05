"""Strict, content-addressed issuer product catalog parsing and cache access."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.etf_holdings import ETFIssuerCatalogCache
from app.models.provider_runtime import ProviderCapability, ProviderRequestLog

ISHARES_US_CATALOG_KEY = "ishares_us_etf_products_v1"
ISHARES_US_CATALOG_URL = "https://www.ishares.com/us/products/etf-investments"
ISHARES_US_CATALOG_CACHE_TTL = timedelta(hours=24)
ISHARES_US_CATALOG_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
ISHARES_US_CATALOG_MAX_REDIRECTS = 3
_PRODUCT_PATH = re.compile(
    r"^/us/products/([0-9]+)(?:/([A-Za-z0-9]+(?:(?:-|%20)+[A-Za-z0-9]+)*))?/?$"
)
_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,11}$")
_REPORTED_TOTAL = re.compile(
    r"\b(?:showing\s+)?(\d+)\s+of\s+(\d+)(?:\s+total)?\s+funds?\b", re.IGNORECASE
)
_SUPPORTED_ENCODINGS = frozenset({"utf-8", "utf-8-sig", "iso8859-1", "cp1252"})


class IssuerCatalogError(ValueError):
    """Catalog content cannot support an exact, trustworthy product match."""


@dataclass(frozen=True, slots=True)
class IssuerCatalogProduct:
    ticker: str
    name: str
    product_id: str
    product_url: str

    def as_json(self) -> dict[str, str]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "product_id": self.product_id,
            "product_url": self.product_url,
        }


@dataclass(frozen=True, slots=True)
class ParsedIssuerCatalog:
    entries: tuple[IssuerCatalogProduct, ...]
    reported_total: int | None
    complete: bool

    def product_for(self, ticker: str) -> IssuerCatalogProduct | None:
        exact = str(ticker or "").strip().upper()
        return next((entry for entry in self.entries if entry.ticker == exact), None)


@dataclass(frozen=True, slots=True)
class CachedIssuerCatalog:
    cache_id: int
    catalog: ParsedIssuerCatalog
    content_sha256: str
    retrieved_at: datetime
    request_log_ids: tuple[int, ...]
    source_url: str
    final_url: str


@dataclass(slots=True)
class _Cell:
    text: list[str]
    hrefs: list[str]


class _CatalogHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[_Cell]]] = []
        self.table_categories: list[str | None] = []
        self.table_contexts: list[str] = []
        self.page_text: list[str] = []
        self._table_depth = 0
        self._table: list[list[_Cell]] = []
        self._row: list[_Cell] | None = None
        self._cell: _Cell | None = None
        self._last_category: str | None = None
        self._capturing_category = False
        self._category_text: list[str] = []
        self._collecting_table_context = False
        self._table_context_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attributes = dict(attrs)
        if lowered == "div" and "category-title" in (attributes.get("class") or "").split():
            self._capturing_category = True
            self._category_text = []
            self._collecting_table_context = True
            self._table_context_text = []
        if lowered == "table":
            if self._table_depth == 0:
                self._table = []
                self.table_categories.append(self._last_category)
                context = (
                    " ".join(self._table_context_text)
                    if self._last_category is not None
                    else " ".join(self.page_text[-12:])
                )
                self.table_contexts.append(context)
                self._collecting_table_context = False
                self._last_category = None
            self._table_depth += 1
        elif self._table_depth and lowered == "tr":
            self._row = []
        elif self._row is not None and lowered in {"td", "th"}:
            self._cell = _Cell(text=[], hrefs=[])
        elif self._cell is not None and lowered == "a":
            href = dict(attrs).get("href")
            if href is not None:
                self._cell.hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "div" and self._capturing_category:
            self._last_category = " ".join(" ".join(self._category_text).split())
            self._capturing_category = False
        elif lowered in {"td", "th"} and self._cell is not None and self._row is not None:
            self._cell.text = [" ".join("".join(self._cell.text).split())]
            self._row.append(self._cell)
            self._cell = None
        elif lowered == "tr" and self._row is not None:
            if any("".join(cell.text).strip() or cell.hrefs for cell in self._row):
                self._table.append(self._row)
            self._row = None
        elif lowered == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0:
                if self._table:
                    self.tables.append(self._table)
                self._table = []

    def handle_data(self, data: str) -> None:
        self.page_text.append(data)
        if self._collecting_table_context:
            self._table_context_text.append(data)
        if self._capturing_category:
            self._category_text.append(data)
        if self._cell is not None:
            self._cell.text.append(data)


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise IssuerCatalogError("Catalog product links must use an HTTPS issuer origin.")
    port = parsed.port
    return "https", parsed.hostname.lower(), None if port == 443 else port


def _product_link(href: str, *, page_url: str) -> tuple[str, str | None, str]:
    resolved = urljoin(page_url, href.strip())
    parsed = urlsplit(resolved)
    if _origin(resolved) != _origin(page_url) or parsed.query or parsed.fragment:
        raise IssuerCatalogError("Catalog product links must remain on the exact page origin.")
    match = _PRODUCT_PATH.fullmatch(parsed.path)
    if not match or int(match.group(1)) <= 0:
        raise IssuerCatalogError("Catalog product links must use a numeric US product path.")
    return match.group(1), match.group(2), resolved


def _identity_name_tokens(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def is_ishares_canonical_name_hint(value: str | None) -> bool:
    """Treat an iShares brand in canonical metadata as a catalog hint only."""

    return bool(re.match(r"^\s*iShares\b", str(value or ""), re.IGNORECASE))


def catalog_product_matches_canonical_fund(
    *, product: IssuerCatalogProduct, ticker: str, canonical_name: str | None
) -> bool:
    """Require exact selected ticker and full canonical fund-name agreement.

    Punctuation/case differences are normalized, and one leading or trailing
    exact ticker label is permitted. No fuzzy token or substring matching is
    used to turn the canonical provider result into issuer identity.
    """

    normalized_ticker = str(ticker or "").strip().upper()
    candidate_name = str(canonical_name or "").strip()
    if product.ticker != normalized_ticker or not candidate_name:
        return False
    candidate_variants = {candidate_name}
    candidate_variants.add(
        re.sub(
            rf"^\s*{re.escape(normalized_ticker)}\s*(?:[-:|—–]+\s*)",
            "",
            candidate_name,
            flags=re.IGNORECASE,
        )
    )
    candidate_variants.add(
        re.sub(
            rf"\s*\(\s*{re.escape(normalized_ticker)}\s*\)\s*$",
            "",
            candidate_name,
            flags=re.IGNORECASE,
        )
    )
    official_tokens = _identity_name_tokens(product.name)
    return bool(
        official_tokens
        and official_tokens in {_identity_name_tokens(value) for value in candidate_variants}
    )


def parse_ishares_us_product_catalog(
    raw_html: str,
    *,
    page_url: str = ISHARES_US_CATALOG_URL,
) -> ParsedIssuerCatalog:
    """Parse exact Ticker/Name rows and product URLs from one iShares US catalog page."""

    if _origin(page_url) != _origin(ISHARES_US_CATALOG_URL):
        raise IssuerCatalogError("iShares catalog response left its reviewed US page origin.")
    parser = _CatalogHTMLParser()
    parser.feed(raw_html)
    matching_tables: list[tuple[str | None, str, list[IssuerCatalogProduct]]] = []
    for table_index, table in enumerate(parser.tables):
        for row_index, row in enumerate(table):
            headers = [" ".join(cell.text).strip().casefold() for cell in row]
            if "ticker" in headers and "name" in headers:
                ticker_column = headers.index("ticker")
                name_column = headers.index("name")
                entries: list[IssuerCatalogProduct] = []
                tickers: set[str] = set()
                product_ids: set[str] = set()
                for data_row in table[row_index + 1 :]:
                    if max(ticker_column, name_column) >= len(data_row):
                        raise IssuerCatalogError(
                            "Catalog product row is missing a Ticker or Name cell."
                        )
                    ticker_cell = data_row[ticker_column]
                    name_cell = data_row[name_column]
                    ticker = " ".join(ticker_cell.text).strip().upper()
                    name = " ".join(name_cell.text).strip()
                    if not ticker and not name:
                        continue
                    if not _TICKER.fullmatch(ticker) or not name:
                        raise IssuerCatalogError(
                            "Catalog contains a malformed ticker or fund name."
                        )
                    if len(ticker_cell.hrefs) != 1 or len(name_cell.hrefs) != 1:
                        raise IssuerCatalogError(
                            "Ticker and Name must each link to one exact product page."
                        )
                    ticker_product = _product_link(ticker_cell.hrefs[0], page_url=page_url)
                    name_product = _product_link(name_cell.hrefs[0], page_url=page_url)
                    if ticker_product[0] != name_product[0] or (
                        ticker_product[1] is not None
                        and name_product[1] is not None
                        and ticker_product[1] != name_product[1]
                    ):
                        raise IssuerCatalogError(
                            "Ticker and Name links conflict on their product identity."
                        )
                    product_id = ticker_product[0]
                    product_url = (
                        ticker_product[2]
                        if ticker_product[1] is not None
                        else name_product[2]
                        if name_product[1] is not None
                        else ticker_product[2]
                    )
                    if ticker in tickers:
                        raise IssuerCatalogError("Catalog contains duplicate ticker rows.")
                    if product_id in product_ids:
                        raise IssuerCatalogError(
                            "Catalog assigns one product ID to multiple ticker rows."
                        )
                    tickers.add(ticker)
                    product_ids.add(product_id)
                    entries.append(
                        IssuerCatalogProduct(
                            ticker=ticker,
                            name=name,
                            product_id=product_id,
                            product_url=product_url,
                        )
                    )
                if not entries:
                    raise IssuerCatalogError("Catalog product table contains no valid fund rows.")
                matching_tables.append(
                    (
                        parser.table_categories[table_index],
                        parser.table_contexts[table_index],
                        entries,
                    )
                )
                break

    if not matching_tables:
        raise IssuerCatalogError("Catalog contains no Ticker/Name product table.")

    # The official page can contain separate ETF and mutual-fund product
    # tables, each with its own truthful total. Only the ETF section is in
    # scope. Older/minimal layouts without a section label remain supported
    # through their table-local result count.
    categories = [
        table[0].strip().casefold() if table[0] is not None else None for table in matching_tables
    ]
    if any(category is not None for category in categories):
        recognized_categories = {"etf", "etfs", "mutual funds"}
        if any(
            category is None or category not in recognized_categories for category in categories
        ):
            raise IssuerCatalogError("Catalog contains an unclassified product table.")
    labeled_etf_tables = [
        table
        for table in matching_tables
        if table[0] is not None and table[0].strip().casefold() in {"etf", "etfs"}
    ]
    selected_tables = labeled_etf_tables or [table for table in matching_tables if table[0] is None]
    if not selected_tables:
        raise IssuerCatalogError("Catalog has no identified ETF product table.")
    table_totals: list[int | None] = []
    for _category, context, _entries in selected_tables:
        local_totals = {
            int(total) for _visible, total in _REPORTED_TOTAL.findall(context) if int(total) > 0
        }
        if len(local_totals) > 1:
            raise IssuerCatalogError("ETF catalog table has conflicting reported totals.")
        table_totals.append(next(iter(local_totals), None))

    def merge_tables(
        tables: list[list[IssuerCatalogProduct]],
    ) -> tuple[IssuerCatalogProduct, ...]:
        by_ticker: dict[str, IssuerCatalogProduct] = {}
        product_id_to_ticker: dict[str, str] = {}
        for table_entries in tables:
            for product in table_entries:
                prior_id_ticker = product_id_to_ticker.get(product.product_id)
                if prior_id_ticker is not None and prior_id_ticker != product.ticker:
                    raise IssuerCatalogError(
                        "Catalog assigns one product ID to multiple ticker rows."
                    )
                product_id_to_ticker[product.product_id] = product.ticker
                prior = by_ticker.get(product.ticker)
                if prior is None:
                    by_ticker[product.ticker] = product
                    continue
                prior_slug = urlsplit(prior.product_url).path.rstrip("/").rsplit("/", 1)[-1]
                product_slug = urlsplit(product.product_url).path.rstrip("/").rsplit("/", 1)[-1]
                if (
                    not prior_slug.isdigit()
                    and not product_slug.isdigit()
                    and prior_slug != product_slug
                ):
                    raise IssuerCatalogError(
                        "Catalog contains conflicting product slugs for one ticker."
                    )
                if prior.product_id != product.product_id or _identity_name_tokens(
                    prior.name
                ) != _identity_name_tokens(product.name):
                    raise IssuerCatalogError(
                        "Catalog contains conflicting product identities for one ticker."
                    )
                if prior_slug.isdigit() and not product_slug.isdigit():
                    by_ticker[product.ticker] = product
        return tuple(by_ticker.values())

    table_entries = [entries for _category, _context, entries in selected_tables]
    # Repeated tables may show the same product rows, but a conflicting ticker,
    # name, product ID, or slug anywhere in the response makes the catalog
    # ambiguous even when another table happens to match the reported total.
    merged_entries = merge_tables(table_entries)
    if len(table_entries) == 1:
        entries = table_entries[0]
        reported_total = table_totals[0]
    else:
        known_totals = {value for value in table_totals if value is not None}
        if len(known_totals) > 1:
            raise IssuerCatalogError("ETF catalog tables have conflicting reported totals.")
        reported_total = next(iter(known_totals), None)
        identity_sets = [
            {(item.ticker, item.product_id, _identity_name_tokens(item.name)) for item in candidate}
            for candidate in table_entries
        ]
        matching_totals = [
            candidate
            for candidate, local_total in zip(table_entries, table_totals, strict=True)
            if local_total is not None and len(candidate) == local_total
        ]
        if len(matching_totals) == 1 and len(merged_entries) == reported_total:
            entries = tuple(matching_totals[0])
        elif all(candidate == identity_sets[0] for candidate in identity_sets[1:]):
            entries = merged_entries
        elif reported_total is not None and len(merged_entries) == reported_total:
            # Some official pages split one catalog over multiple tables. Merge
            # only when exact row identity and the issuer's reported total make
            # the union unambiguous.
            entries = merged_entries
        else:
            raise IssuerCatalogError(
                "Catalog has ambiguous Ticker/Name tables or an incomplete product union."
            )

    # A total label alone is insufficient. Every row in the selected table or
    # exact merged fragments was parsed and linked to one same-origin product.
    complete = reported_total is not None and len(entries) == reported_total
    return ParsedIssuerCatalog(tuple(entries), reported_total, complete)


def catalog_response_bytes(response: Any) -> tuple[bytes, str, str]:
    """Return bounded exact response bytes, approved text encoding and final URL."""

    body = bytes(getattr(response, "content", b"") or b"")
    if not body or len(body) > ISHARES_US_CATALOG_MAX_RESPONSE_BYTES:
        raise IssuerCatalogError("iShares catalog response is empty or exceeds its byte limit.")
    content_type = str(getattr(response, "headers", {}).get("content-type", "")).casefold()
    if "text/html" not in content_type:
        raise IssuerCatalogError("iShares product catalog response is not HTML.")
    encoding = str(getattr(response, "encoding", None) or "utf-8").strip().lower()
    normalized_encoding = encoding.replace("_", "-")
    canonical_encoding = {
        "utf-8": "utf-8",
        "utf-8-sig": "utf-8-sig",
        "iso-8859-1": "iso8859-1",
        "latin-1": "iso8859-1",
        "windows-1252": "cp1252",
        "cp1252": "cp1252",
    }.get(normalized_encoding)
    if canonical_encoding not in _SUPPORTED_ENCODINGS:
        raise IssuerCatalogError("iShares catalog uses an unsupported text encoding.")
    try:
        body.decode(canonical_encoding, errors="strict")
    except UnicodeDecodeError as exc:
        raise IssuerCatalogError(
            "iShares catalog HTML is not valid in its declared encoding."
        ) from exc
    final_url = str(getattr(response, "url", ISHARES_US_CATALOG_URL))
    if _origin(final_url) != _origin(ISHARES_US_CATALOG_URL):
        raise IssuerCatalogError("iShares catalog response redirected outside its page origin.")
    return body, canonical_encoding, final_url


def _catalog_log_facts_are_trusted(
    *,
    logs: list[ProviderRequestLog],
    request_log_ids: list[int],
    request_urls: list[str],
    source_id: int,
    requested_symbol: str,
    retrieved_at: datetime | None,
) -> bool:
    if (
        not request_log_ids
        or len(request_log_ids) != len(request_urls)
        or len(set(request_log_ids)) != len(request_log_ids)
        or {row.id for row in logs} != set(request_log_ids)
    ):
        return False
    by_id = {row.id: row for row in logs}
    ordered = [by_id[log_id] for log_id in request_log_ids]
    if not request_urls or request_urls[0] != ISHARES_US_CATALOG_URL:
        return False
    try:
        if any(_origin(url) != _origin(ISHARES_US_CATALOG_URL) for url in request_urls):
            return False
    except IssuerCatalogError:
        return False
    completed = [row.completed_at for row in ordered]
    if retrieved_at is None or any(value is None for value in completed):
        return False
    if max(_aware_utc(value) for value in completed if value is not None) != _aware_utc(
        retrieved_at
    ):
        return False
    return all(
        row.data_source_id == source_id
        and row.capability == ProviderCapability.ETF_HOLDINGS
        and row.operation == "fetch_etf_holdings_latest"
        and row.instrument_id is not None
        and row.instrument_id > 0
        and (row.provider_symbol or "").strip().upper() == requested_symbol
        and row.success
        for row in ordered
    )


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _validated_cached_catalog_content(
    candidate: ETFIssuerCatalogCache,
    *,
    now: datetime,
) -> tuple[bytes, ParsedIssuerCatalog] | None:
    """Validate cache identity, time, exact bytes, and their parsed projection."""

    if (
        candidate.provider_name != "ishares"
        or candidate.catalog_key != ISHARES_US_CATALOG_KEY
        or candidate.source_url != ISHARES_US_CATALOG_URL
        or not isinstance(candidate.final_url, str)
        or not isinstance(candidate.requested_symbol, str)
        or not _TICKER.fullmatch(candidate.requested_symbol)
        or not isinstance(candidate.response_bytes, int)
        or isinstance(candidate.response_bytes, bool)
        or candidate.response_bytes <= 0
        or candidate.response_bytes > ISHARES_US_CATALOG_MAX_RESPONSE_BYTES
        or not isinstance(candidate.content_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", candidate.content_sha256)
        or not isinstance(candidate.fetched_at, datetime)
    ):
        return None
    try:
        fetched_at = _aware_utc(candidate.fetched_at)
        if fetched_at > now or now - fetched_at > ISHARES_US_CATALOG_CACHE_TTL:
            return None
        body = base64.b64decode(candidate.raw_body_base64, validate=True)
        if (
            len(body) != candidate.response_bytes
            or hashlib.sha256(body).hexdigest() != candidate.content_sha256
        ):
            return None
        html = body.decode(candidate.response_encoding, errors="strict")
        parsed = parse_ishares_us_product_catalog(html, page_url=candidate.final_url)
    except (IssuerCatalogError, ValueError, TypeError, UnicodeDecodeError, LookupError):
        return None
    if (
        [entry.as_json() for entry in parsed.entries] != candidate.parsed_entries
        or parsed.reported_total != candidate.reported_total
        or parsed.complete != candidate.catalog_complete
    ):
        return None
    return body, parsed


async def load_cached_ishares_catalog(
    db: AsyncSession,
    *,
    ticker: str,
    now: datetime | None = None,
) -> CachedIssuerCatalog | None:
    """Load a recent cache only when its raw bytes, parse, and Provider lineage agree."""

    normalized = str(ticker or "").strip().upper()
    if not _TICKER.fullmatch(normalized):
        return None
    source = await db.scalar(select(DataSource).where(DataSource.name == "ishares"))
    if source is None:
        return None
    candidates = list(
        (
            await db.scalars(
                select(ETFIssuerCatalogCache)
                .where(
                    ETFIssuerCatalogCache.provider_name == "ishares",
                    ETFIssuerCatalogCache.catalog_key == ISHARES_US_CATALOG_KEY,
                    ETFIssuerCatalogCache.data_source_id == source.id,
                )
                .order_by(ETFIssuerCatalogCache.fetched_at.desc(), ETFIssuerCatalogCache.id.desc())
                .limit(8)
            )
        ).all()
    )
    current = _aware_utc(now or datetime.now(UTC))
    for candidate in candidates:
        validated = _validated_cached_catalog_content(candidate, now=current)
        if validated is None:
            continue
        _body, parsed = validated
        try:
            ids = candidate.provider_request_log_ids
            urls = candidate.request_urls
            if (
                not isinstance(ids, list)
                or any(
                    not isinstance(value, int) or isinstance(value, bool) or value <= 0
                    for value in ids
                )
                or not isinstance(urls, list)
                or any(not isinstance(value, str) for value in urls)
            ):
                continue
            logs = list(
                (
                    await db.scalars(
                        select(ProviderRequestLog).where(ProviderRequestLog.id.in_(ids))
                    )
                ).all()
            )
            if not _catalog_log_facts_are_trusted(
                logs=logs,
                request_log_ids=ids,
                request_urls=urls,
                source_id=source.id,
                requested_symbol=candidate.requested_symbol,
                retrieved_at=candidate.fetched_at,
            ):
                continue
            product = parsed.product_for(normalized)
            if product is None and not parsed.complete:
                # Absence from partial content is never cached as a negative.
                continue
            return CachedIssuerCatalog(
                cache_id=candidate.id,
                catalog=parsed,
                content_sha256=candidate.content_sha256,
                retrieved_at=_aware_utc(candidate.fetched_at),
                request_log_ids=tuple(ids),
                source_url=candidate.source_url,
                final_url=candidate.final_url,
            )
        except (ValueError, TypeError, UnicodeDecodeError):
            continue
    return None


async def store_ishares_catalog_response(
    db: AsyncSession,
    *,
    response: Any,
    ticker: str,
    request_log_ids: list[int],
    request_urls: list[str],
) -> CachedIssuerCatalog:
    """Retain exact catalog bytes and a parsed positive/complete catalog for reuse."""

    normalized = str(ticker or "").strip().upper()
    if not _TICKER.fullmatch(normalized):
        raise IssuerCatalogError("Catalog request is not bound to one exact selected ticker.")
    body, encoding, final_url = catalog_response_bytes(response)
    html = body.decode(encoding, errors="strict")
    catalog = parse_ishares_us_product_catalog(html, page_url=final_url)
    sha256 = hashlib.sha256(body).hexdigest()
    engine_or_connection = db.bind
    if engine_or_connection is None:
        raise IssuerCatalogError("Catalog cache has no durable application database binding.")

    from sqlalchemy.ext.asyncio import AsyncSession as SQLAlchemyAsyncSession

    cache_db = SQLAlchemyAsyncSession(bind=engine_or_connection, expire_on_commit=False)
    try:
        source = await cache_db.scalar(select(DataSource).where(DataSource.name == "ishares"))
        if source is None:
            raise IssuerCatalogError("iShares catalog cache requires its registered data source.")
        logs = list(
            (
                await cache_db.scalars(
                    select(ProviderRequestLog).where(ProviderRequestLog.id.in_(request_log_ids))
                )
            ).all()
        )
        completed_logs = [log.completed_at for log in logs if log.completed_at is not None]
        completion_log = max(completed_logs, key=_aware_utc) if completed_logs else None
        if not _catalog_log_facts_are_trusted(
            logs=logs,
            request_log_ids=request_log_ids,
            request_urls=request_urls,
            source_id=source.id,
            requested_symbol=normalized,
            retrieved_at=completion_log,
        ):
            raise IssuerCatalogError(
                "Catalog response is missing exact successful Provider lineage."
            )

        existing = await cache_db.scalar(
            select(ETFIssuerCatalogCache).where(
                ETFIssuerCatalogCache.catalog_key == ISHARES_US_CATALOG_KEY,
                ETFIssuerCatalogCache.content_sha256 == sha256,
            )
        )
        if completion_log is None:
            raise IssuerCatalogError("Catalog request logs lack a completion timestamp.")
        retrieved_at = _aware_utc(completion_log)
        if existing is None:
            existing = ETFIssuerCatalogCache(
                provider_name="ishares",
                catalog_key=ISHARES_US_CATALOG_KEY,
                data_source_id=source.id,
                source_url=ISHARES_US_CATALOG_URL,
                final_url=final_url,
                content_sha256=sha256,
                response_bytes=len(body),
                response_encoding=encoding,
                raw_body_base64=base64.b64encode(body).decode("ascii"),
                parsed_entries=[entry.as_json() for entry in catalog.entries],
                reported_total=catalog.reported_total,
                catalog_complete=catalog.complete,
                requested_symbol=normalized,
                provider_request_log_ids=list(request_log_ids),
                request_urls=list(request_urls),
                fetched_at=_aware_utc(completion_log),
            )
            cache_db.add(existing)
            await cache_db.commit()
            await cache_db.refresh(existing)
        else:
            try:
                existing_body = base64.b64decode(existing.raw_body_base64, validate=True)
            except (ValueError, TypeError):
                existing_body = b""
            if (
                existing.provider_name != "ishares"
                or existing.data_source_id != source.id
                or existing.source_url != ISHARES_US_CATALOG_URL
                or existing.response_bytes != len(body)
                or existing_body != body
            ):
                raise IssuerCatalogError(
                    "Existing iShares catalog content-addressed cache row is inconsistent."
                )
            await cache_db.commit()
        return CachedIssuerCatalog(
            cache_id=existing.id,
            catalog=catalog,
            content_sha256=sha256,
            # When the body already exists, retain its cache row but describe
            # the just-admitted retrieval in this acquisition's lineage.
            retrieved_at=retrieved_at,
            request_log_ids=tuple(request_log_ids),
            source_url=ISHARES_US_CATALOG_URL,
            final_url=final_url,
        )
    except BaseException:
        await cache_db.rollback()
        raise
    finally:
        await cache_db.close()
