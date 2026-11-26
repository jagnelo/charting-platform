"""Detect and merge duplicate instruments (one real-world security, several rows).

Why duplicates exist
--------------------
Discovery providers disagree about identity and venue, and reconciliation
deliberately never merges on a ticker alone.  Two flows therefore minted a
second ``instrument`` row for a security that already had one:

* ``legacy_key_vs_figi``: an Alpaca/Nasdaq/Finnhub seed row keyed by CUSIP (or
  by nothing), later joined by a composite-FIGI row created by the SEC/Massive
  reconciliation because a new stable key "is stronger than a legacy
  ticker/venue match".  Same ticker, same venue, same type, no shared key.
* ``keyless_vs_stable``: an issuer-less or CIK-only discovery row
  (``identity_status = quarantined``) created alongside an existing stable row
  because the providers label the venue differently (NYSE vs NYSE American)
  or the exact listing lookup lost a race.
* ``separator_variant``: ``BRK.B`` vs ``BRK-B`` class-share spellings.

Merge policy (conservative, deterministic)
------------------------------------------
Rows are grouped by ``(instrument_type_id, normalised symbol)``.  The
canonical row of a group is the one with the strongest stable identity
(composite FIGI > FIGI > ISIN > CUSIP > SEDOL > none), then an issuer link,
then the lowest id.  Another row is merged into it only when

1. neither row carries a *conflicting* stable identifier (same identifier type,
   different value, or different domain keys of the same kind - e.g. two
   different CUSIPs are two share classes, never one security),
2. the display names are compatible, and
3. independent evidence says it is the same security: an identical active
   ticker/venue listing, a pure separator spelling difference, or agreeing
   daily closes on enough overlapping bars.

Everything that fails these checks is reported, never merged.

The merge itself repoints every foreign key to ``instrument`` (discovered from
the database catalog, so new child tables are covered automatically), resolves
unique-constraint collisions in favour of the canonical row, merges
``market_series`` (rewriting the series-scoped ``scope_key`` of bars), logs the
retired id in ``instrument_merge_log`` and deletes the duplicate.  Each pair is
one short transaction with a fixed lock order, a lock timeout and a global
advisory lock; running again after completion is a no-op.
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.identity_batch import names_compatible

logger = logging.getLogger(__name__)

# Instrument types whose tickers are not unique identities (contracts, pairs,
# tokenized wrappers) are never touched.
EXCLUDED_TYPE_NAMES = ("Forex Pair", "Crypto Spot", "Future", "Tokenized Security")
EXCLUDED_DOMAIN_PREFIXES = ("tokenized", "crypto-pair", "fx-pair")
EXCLUDED_STATUSES = ("retired", "verified_provider_asset")

# Identifier types that name a security; INTERNAL/CIK placeholders never count.
STABLE_IDENTIFIER_TYPES = ("COMPOSITE_FIGI", "FIGI", "ISIN", "CUSIP", "SEDOL", "LEI")

MIN_BAR_OVERLAP = 20
MIN_BAR_AGREEMENT = 0.95
BAR_TOLERANCE = 0.005

ADVISORY_LOCK_KEY = 7_340_118_221  # arbitrary, process-wide "merge in progress"
DEFAULT_LOCK_TIMEOUT = "5s"
DEFAULT_STATEMENT_TIMEOUT = "120s"

_DOMAIN_RANK = {"composite-figi": 0, "figi": 0, "isin": 1, "cusip": 2, "sedol": 3}
_SERIES_SCOPE_COLUMNS = (
    "exchange_id",
    "data_source_id",
    "feed_scope",
    "session_code",
    "timeframe",
    "adjustment_basis",
    "adjustment_version",
)
_DERIVED_SCOPE_RE = re.compile(r"^derived-d1-(\d+)$")


def normalize_symbol(symbol: str | None) -> str:
    """Spelling-insensitive ticker key: case, and ``-``/``/``/space class separators."""

    return re.sub(r"[-/ ]", ".", str(symbol or "").strip()).upper()


def _quote(identifier: str) -> str:
    """Quote a catalog-supplied identifier (``schema.table`` or bare name)."""

    return ".".join('"' + part.replace('"', '""') + '"' for part in identifier.split("."))


def _regclass_parts(regclass_text: str) -> str:
    """``regclass::text`` already quotes when needed; keep it verbatim."""

    return regclass_text


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class InstrumentRow:
    id: int
    type_id: int
    symbol: str
    name: str
    identity_status: str
    domain_key: str | None
    issuer_id: int | None

    @property
    def domain_prefix(self) -> str:
        return (self.domain_key or "").split(":", 1)[0]

    @property
    def rank(self) -> tuple[int, int, int]:
        """Lower sorts first and wins: stable key strength, issuer link, id."""

        return (
            _DOMAIN_RANK.get(self.domain_prefix, 9),
            0 if self.issuer_id is not None else 1,
            self.id,
        )


@dataclass(frozen=True, slots=True)
class MergePlan:
    canonical_id: int
    duplicate_id: int
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlanReport:
    plans: list[MergePlan] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)
    groups: int = 0


def identifier_conflict(
    canonical: InstrumentRow,
    duplicate: InstrumentRow,
    canonical_ids: Sequence[tuple[str, str]],
    duplicate_ids: Sequence[tuple[str, str]],
) -> str | None:
    """Return a reason when the rows provably name different securities."""

    if (
        canonical.domain_key
        and duplicate.domain_key
        and canonical.domain_prefix == duplicate.domain_prefix
        and canonical.domain_key.lower() != duplicate.domain_key.lower()
    ):
        return "domain_key_conflict"
    mine: dict[str, set[str]] = {}
    for kind, value in canonical_ids:
        mine.setdefault(kind.upper(), set()).add(value.strip().upper())
    theirs: dict[str, set[str]] = {}
    for kind, value in duplicate_ids:
        theirs.setdefault(kind.upper(), set()).add(value.strip().upper())
    for kind in STABLE_IDENTIFIER_TYPES:
        if kind in mine and kind in theirs and not (mine[kind] & theirs[kind]):
            return f"{kind.lower()}_conflict"
    return None


async def _candidate_groups(db: AsyncSession) -> list[list[InstrumentRow]]:
    result = await db.execute(
        text(
            """
            WITH base AS (
                SELECT i.id, i.instrument_type_id AS type_id, i.symbol, i.name,
                       i.identity_status, i.domain_key, i.issuer_id,
                       upper(regexp_replace(btrim(i.symbol), '[-/ ]', '.', 'g')) AS nsym
                FROM instrument i
                JOIN instrument_type t ON t.id = i.instrument_type_id
                WHERE NOT i.is_synthetic
                  AND i.identity_status <> ALL(:statuses)
                  AND t.name <> ALL(:type_names)
                  AND coalesce(split_part(i.domain_key, ':', 1), '') <> ALL(:prefixes)
                  AND strpos(i.symbol, '$') = 0
            ), grp AS (
                SELECT nsym, type_id FROM base GROUP BY nsym, type_id HAVING count(*) > 1
            )
            SELECT b.id, b.type_id, b.symbol, b.name, b.identity_status, b.domain_key,
                   b.issuer_id, b.nsym
            FROM base b JOIN grp g ON g.nsym = b.nsym AND g.type_id = b.type_id
            ORDER BY b.nsym, b.type_id, b.id
            """
        ),
        {
            "statuses": list(EXCLUDED_STATUSES),
            "type_names": list(EXCLUDED_TYPE_NAMES),
            "prefixes": list(EXCLUDED_DOMAIN_PREFIXES),
        },
    )
    groups: dict[tuple[str, int], list[InstrumentRow]] = {}
    for row in result.all():
        groups.setdefault((row.nsym, row.type_id), []).append(
            InstrumentRow(
                id=row.id,
                type_id=row.type_id,
                symbol=row.symbol,
                name=row.name,
                identity_status=row.identity_status,
                domain_key=row.domain_key,
                issuer_id=row.issuer_id,
            )
        )
    return list(groups.values())


async def _identifiers(db: AsyncSession, ids: Sequence[int]) -> dict[int, list[tuple[str, str]]]:
    result = await db.execute(
        text(
            "SELECT instrument_id, identifier_type::text AS kind, identifier_value AS value "
            "FROM instrument_identifier "
            "WHERE instrument_id = ANY(:ids) AND identifier_type::text = ANY(:kinds)"
        ),
        {"ids": list(ids), "kinds": list(STABLE_IDENTIFIER_TYPES)},
    )
    found: dict[int, list[tuple[str, str]]] = {instrument_id: [] for instrument_id in ids}
    for row in result.all():
        found[row.instrument_id].append((row.kind, row.value))
    return found


async def _same_listing(db: AsyncSession, canonical_id: int, duplicate_id: int) -> bool:
    return bool(
        (
            await db.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM instrument_listing a
                        JOIN instrument_listing b
                          ON b.exchange_id = a.exchange_id
                         AND upper(regexp_replace(btrim(b.ticker), '[-/ ]', '.', 'g'))
                           = upper(regexp_replace(btrim(a.ticker), '[-/ ]', '.', 'g'))
                        WHERE a.instrument_id = :w AND b.instrument_id = :l
                          AND a.exchange_id IS NOT NULL
                          AND a.is_active AND b.is_active
                          AND a.delisted_at IS NULL AND b.delisted_at IS NULL
                    )
                    """
                ),
                {"w": canonical_id, "l": duplicate_id},
            )
        ).scalar_one()
    )


async def _bar_agreement(db: AsyncSession, canonical_id: int, duplicate_id: int) -> tuple[int, int]:
    row = (
        await db.execute(
            text(
                """
                SELECT count(DISTINCT a.ts) AS overlap,
                       count(DISTINCT a.ts) FILTER (
                           WHERE abs(a.close - b.close)
                                 <= :tol * greatest(abs(a.close), abs(b.close))
                       ) AS agree
                FROM ohlcv_bar a
                JOIN ohlcv_bar b
                  ON b.timeframe = a.timeframe AND b.ts = a.ts AND b.is_adjusted = a.is_adjusted
                WHERE a.instrument_id = :w AND b.instrument_id = :l
                  AND a.timeframe::text = 'D1'
                """
            ),
            {"w": canonical_id, "l": duplicate_id, "tol": BAR_TOLERANCE},
        )
    ).one()
    return int(row.overlap or 0), int(row.agree or 0)


def classify_cause(canonical: InstrumentRow, duplicate: InstrumentRow) -> str:
    if normalize_symbol(canonical.symbol) == normalize_symbol(duplicate.symbol) and (
        canonical.symbol.strip().upper() != duplicate.symbol.strip().upper()
    ):
        return "separator_variant"
    if duplicate.domain_key and duplicate.domain_prefix in {"cusip", "isin", "sedol"}:
        return "legacy_key_vs_figi"
    if not duplicate.domain_key:
        return "keyless_vs_stable"
    return "other"


async def plan_duplicate_merges(db: AsyncSession) -> PlanReport:
    """Return every provable duplicate pair; never writes."""

    report = PlanReport()
    groups = await _candidate_groups(db)
    report.groups = len(groups)
    for group in groups:
        ordered = sorted(group, key=lambda row: row.rank)
        canonical = ordered[0]
        identifiers = await _identifiers(db, [row.id for row in ordered])
        for duplicate in ordered[1:]:
            conflict = identifier_conflict(
                canonical, duplicate, identifiers[canonical.id], identifiers[duplicate.id]
            )
            if conflict is not None:
                report.skipped[conflict] += 1
                continue
            if not names_compatible(duplicate.name, canonical.name, canonical.symbol):
                report.skipped["name_mismatch"] += 1
                continue
            detail: dict[str, Any] = {
                "canonical_symbol": canonical.symbol,
                "duplicate_status": duplicate.identity_status,
                "duplicate_domain_key": duplicate.domain_key,
                "canonical_domain_key": canonical.domain_key,
            }
            if canonical.symbol.strip().upper() != duplicate.symbol.strip().upper():
                evidence = "separator_spelling"
            elif await _same_listing(db, canonical.id, duplicate.id):
                evidence = "same_listing"
            else:
                overlap, agree = await _bar_agreement(db, canonical.id, duplicate.id)
                detail.update(bar_overlap=overlap, bar_agree=agree)
                if overlap >= MIN_BAR_OVERLAP and agree / overlap >= MIN_BAR_AGREEMENT:
                    evidence = "bar_agreement"
                else:
                    report.skipped["insufficient_evidence"] += 1
                    continue
            detail["evidence"] = evidence
            report.plans.append(
                MergePlan(
                    canonical_id=canonical.id,
                    duplicate_id=duplicate.id,
                    reason=classify_cause(canonical, duplicate),
                    detail=detail,
                )
            )
    return report


# --------------------------------------------------------------------------- #
# Catalog introspection
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ForeignKeyColumn:
    table: str  # regclass text, already quoted when needed
    column: str


async def _foreign_key_columns(db: AsyncSession, target: str) -> list[ForeignKeyColumn]:
    rows = (
        await db.execute(
            text(
                """
                SELECT c.conrelid::regclass::text AS tbl, a.attname AS col,
                       array_length(c.conkey, 1) AS width
                FROM pg_constraint c
                JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
                WHERE c.contype = 'f' AND c.confrelid = to_regclass(:target)
                ORDER BY 1, 2
                """
            ),
            {"target": target},
        )
    ).all()
    columns: list[ForeignKeyColumn] = []
    for row in rows:
        if row.width != 1:
            raise RuntimeError(f"composite foreign key from {row.tbl} to {target} is unsupported")
        columns.append(ForeignKeyColumn(table=row.tbl, column=row.col))
    return columns


async def _unique_indexes_with(
    db: AsyncSession, table: str, column: str
) -> list[tuple[list[str], str | None]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT ARRAY(
                           SELECT a.attname
                           FROM unnest(i.indkey::int2[]) WITH ORDINALITY k(attnum, ord)
                           JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                           ORDER BY k.ord
                       ) AS cols,
                       pg_get_expr(i.indpred, i.indrelid) AS pred,
                       (0 = ANY(i.indkey::int2[])) AS has_expression
                FROM pg_index i
                WHERE i.indrelid = to_regclass(:tbl) AND i.indisunique AND NOT i.indisprimary
                """
            ),
            {"tbl": table},
        )
    ).all()
    indexes: list[tuple[list[str], str | None]] = []
    for row in rows:
        if column not in row.cols:
            continue
        if row.has_expression:
            raise RuntimeError(f"expression unique index on {table} is unsupported")
        indexes.append((list(row.cols), row.pred))
    return indexes


async def _repoint(
    db: AsyncSession,
    fk: ForeignKeyColumn,
    old_id: int,
    new_id: int,
    *,
    extra_where: str = "",
) -> tuple[int, int]:
    """Move ``fk`` rows from ``old_id`` to ``new_id``; return (moved, dropped).

    A row that would violate a unique index because ``new_id`` already holds
    the same key is dropped (the canonical side wins), which makes the result
    the union of both sides without duplicates.
    """

    table = fk.table
    column = _quote(fk.column)
    dropped = 0
    for cols, pred in await _unique_indexes_with(db, table, fk.column):
        others = [c for c in cols if c != fk.column]
        pred_sql = f" AND ({pred})" if pred else ""
        join_on = " AND ".join(f"d.{_quote(c)} = c.{_quote(c)}" for c in others) or "TRUE"
        result = await db.execute(
            text(
                f"""
                DELETE FROM {table} WHERE ctid IN (
                    SELECT d.ctid
                    FROM (SELECT ctid, * FROM {table}
                          WHERE {column} = :old{pred_sql}{extra_where}) d
                    JOIN (SELECT * FROM {table}
                          WHERE {column} = :new{pred_sql}) c ON {join_on}
                )
                """
            ),
            {"old": old_id, "new": new_id},
        )
        dropped += result.rowcount or 0
    moved = (
        await db.execute(
            text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old{extra_where}"),
            {"old": old_id, "new": new_id},
        )
    ).rowcount or 0
    return moved, dropped


# --------------------------------------------------------------------------- #
# Merge
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class MergeResult:
    status: str  # merged | already_merged | skipped_open_lease | skipped_invalid
    canonical_id: int
    duplicate_id: int
    moved: dict[str, int] = field(default_factory=dict)
    dropped: dict[str, int] = field(default_factory=dict)


async def _merge_series(
    db: AsyncSession, canonical_id: int, duplicate_id: int, result: MergeResult
) -> None:
    cols = ", ".join(_SERIES_SCOPE_COLUMNS)
    canonical_rows = (
        await db.execute(
            text(f"SELECT id, {cols} FROM market_series WHERE instrument_id = :i ORDER BY id"),
            {"i": canonical_id},
        )
    ).all()
    duplicate_rows = (
        await db.execute(
            text(f"SELECT id, {cols} FROM market_series WHERE instrument_id = :i ORDER BY id"),
            {"i": duplicate_id},
        )
    ).all()

    def scope(row: Any, feed_scope: str | None = None) -> tuple:
        values = [getattr(row, column) for column in _SERIES_SCOPE_COLUMNS]
        if feed_scope is not None:
            values[_SERIES_SCOPE_COLUMNS.index("feed_scope")] = feed_scope
        return tuple(values)

    canonical_by_scope = {scope(row): row.id for row in canonical_rows}
    mapping: dict[int, int] = {}
    # Plain series first; derived series name their source D1 series in
    # ``feed_scope`` so they can only be matched once that mapping is known.
    for row in duplicate_rows:
        if _DERIVED_SCOPE_RE.match(row.feed_scope or ""):
            continue
        target = canonical_by_scope.get(scope(row))
        if target is not None:
            mapping[row.id] = target
    for row in duplicate_rows:
        match = _DERIVED_SCOPE_RE.match(row.feed_scope or "")
        if match is None or int(match.group(1)) not in mapping:
            continue
        target = canonical_by_scope.get(scope(row, f"derived-d1-{mapping[int(match.group(1))]}"))
        if target is not None:
            mapping[row.id] = target

    series_children = await _foreign_key_columns(db, "market_series")
    for old_series, new_series in mapping.items():
        for child in series_children:
            if child.table.strip('"') in {"ohlcv_bar", "market_bar_observation"}:
                # ``scope_key`` embeds the series id; rewrite it so the bars
                # collide with (and de-duplicate against) the canonical ones.
                moved = (
                    await db.execute(
                        text(
                            f"UPDATE {child.table} SET market_series_id = :new, "
                            "scope_key = 'series:' || :new_text || "
                            "substr(scope_key, length('series:' || :old_text) + 1) "
                            "WHERE market_series_id = :old AND instrument_id = :dup "
                            "AND scope_key LIKE 'series:' || :old_text || ':%'"
                        ),
                        {
                            "new": new_series,
                            "old": old_series,
                            "new_text": str(new_series),
                            "old_text": str(old_series),
                            "dup": duplicate_id,
                        },
                    )
                ).rowcount or 0
                result.moved[f"{child.table}.scope_key"] = (
                    result.moved.get(f"{child.table}.scope_key", 0) + moved
                )
            moved, dropped = await _repoint(db, child, old_series, new_series)
            if moved:
                result.moved[child.table] = result.moved.get(child.table, 0) + moved
            if dropped:
                result.dropped[child.table] = result.dropped.get(child.table, 0) + dropped
        await db.execute(text("DELETE FROM market_series WHERE id = :id"), {"id": old_series})
        result.dropped["market_series"] = result.dropped.get("market_series", 0) + 1
    # Series without a canonical twin simply move with the instrument.
    moved = (
        await db.execute(
            text("UPDATE market_series SET instrument_id = :new WHERE instrument_id = :old"),
            {"old": duplicate_id, "new": canonical_id},
        )
    ).rowcount or 0
    if moved:
        result.moved["market_series"] = moved


async def _merge_identity_children(
    db: AsyncSession, canonical_id: int, duplicate_id: int, result: MergeResult
) -> None:
    # Placeholder identifiers carry no information (``instrument:<id>``).
    deleted = (
        await db.execute(
            text(
                "DELETE FROM instrument_identifier "
                "WHERE instrument_id = :dup AND identifier_type::text = 'INTERNAL'"
            ),
            {"dup": duplicate_id},
        )
    ).rowcount or 0
    if deleted:
        result.dropped["instrument_identifier.INTERNAL"] = deleted
    # Exactly one primary row per owner after the move.
    await db.execute(
        text("UPDATE instrument_identifier SET is_primary = FALSE WHERE instrument_id = :dup"),
        {"dup": duplicate_id},
    )
    # A listing the canonical row already holds is not carried over twice.
    deleted = (
        await db.execute(
            text(
                """
                DELETE FROM instrument_listing d
                USING instrument_listing c
                WHERE d.instrument_id = :dup AND c.instrument_id = :canon
                  AND d.exchange_id IS NOT DISTINCT FROM c.exchange_id
                  AND upper(d.ticker) = upper(c.ticker)
                """
            ),
            {"dup": duplicate_id, "canon": canonical_id},
        )
    ).rowcount or 0
    if deleted:
        result.dropped["instrument_listing"] = deleted
    await db.execute(
        text(
            "UPDATE instrument_listing SET is_primary = FALSE WHERE instrument_id = :dup "
            "AND EXISTS (SELECT 1 FROM instrument_listing WHERE instrument_id = :canon "
            "AND is_primary)"
        ),
        {"dup": duplicate_id, "canon": canonical_id},
    )
    await db.execute(
        text(
            "UPDATE instrument_provider_symbol p SET is_primary = FALSE "
            "WHERE p.instrument_id = :dup AND EXISTS (SELECT 1 FROM instrument_provider_symbol c "
            "WHERE c.instrument_id = :canon AND c.is_primary "
            "AND c.data_source_id = p.data_source_id)"
        ),
        {"dup": duplicate_id, "canon": canonical_id},
    )


async def _rewrite_job_payloads(db: AsyncSession, canonical_id: int, duplicate_id: int) -> None:
    """Queued work carries the instrument id inside its JSON payload too."""

    for path in (["data_preparation_child", "instrument_id"], ["instrument_id"]):
        await db.execute(
            text(
                "UPDATE market_refresh_job SET metadata_payload = "
                "jsonb_set(metadata_payload::jsonb, CAST(:path AS text[]), "
                "to_jsonb(CAST(:new AS integer)))::json "
                "WHERE instrument_id = :dup "
                "AND (metadata_payload::jsonb #>> CAST(:path AS text[])) = :dup_text"
            ),
            {"path": path, "new": canonical_id, "dup": duplicate_id, "dup_text": str(duplicate_id)},
        )


async def _enrich_canonical(db: AsyncSession, canonical_id: int, duplicate_id: int) -> None:
    # The partial unique ISIN index requires the duplicate to release it first.
    await db.execute(
        text(
            "UPDATE instrument c SET "
            "currency = coalesce(c.currency, d.currency), "
            "description = coalesce(c.description, d.description), "
            "issuer_id = coalesce(c.issuer_id, d.issuer_id), "
            "is_active = (c.is_active OR d.is_active) "
            "FROM instrument d WHERE c.id = :canon AND d.id = :dup"
        ),
        {"canon": canonical_id, "dup": duplicate_id},
    )
    isin = (
        await db.execute(text("SELECT isin FROM instrument WHERE id = :dup"), {"dup": duplicate_id})
    ).scalar_one_or_none()
    if isin:
        await db.execute(
            text("UPDATE instrument SET isin = NULL WHERE id = :dup"), {"dup": duplicate_id}
        )
        await db.execute(
            text("UPDATE instrument SET isin = :isin WHERE id = :canon AND isin IS NULL"),
            {"isin": isin, "canon": canonical_id},
        )


async def merge_instrument_pair(
    db: AsyncSession,
    plan: MergePlan,
    *,
    lock_timeout: str = DEFAULT_LOCK_TIMEOUT,
    statement_timeout: str = DEFAULT_STATEMENT_TIMEOUT,
) -> MergeResult:
    """Merge ``plan.duplicate_id`` into ``plan.canonical_id`` inside the caller's transaction.

    The caller owns commit/rollback so a failure leaves both rows untouched.
    """

    canonical_id, duplicate_id = plan.canonical_id, plan.duplicate_id
    result = MergeResult("merged", canonical_id, duplicate_id)
    await db.execute(text(f"SET LOCAL lock_timeout = '{lock_timeout}'"))
    await db.execute(text(f"SET LOCAL statement_timeout = '{statement_timeout}'"))
    # Fixed lock order (ascending id) so concurrent merges cannot deadlock.
    locked = {
        row.id: row
        for row in (
            await db.execute(
                text(
                    "SELECT id, instrument_type_id AS type_id, symbol, name, identity_status, "
                    "domain_key, issuer_id FROM instrument WHERE id = ANY(:ids) "
                    "ORDER BY id FOR UPDATE"
                ),
                {"ids": [canonical_id, duplicate_id]},
            )
        ).all()
    }
    if duplicate_id not in locked:
        result.status = "already_merged"
        return result
    if canonical_id not in locked or locked[canonical_id].type_id != locked[duplicate_id].type_id:
        result.status = "skipped_invalid"
        return result
    leased = (
        await db.execute(
            text(
                "SELECT count(*) FROM market_refresh_job "
                "WHERE instrument_id = :dup AND status = 'leased'"
            ),
            {"dup": duplicate_id},
        )
    ).scalar_one()
    if leased:
        result.status = "skipped_open_lease"
        return result
    identifiers = await _identifiers(db, [canonical_id, duplicate_id])
    recheck = identifier_conflict(
        _row(locked[canonical_id]),
        _row(locked[duplicate_id]),
        identifiers[canonical_id],
        identifiers[duplicate_id],
    )
    if recheck is not None:
        result.status = "skipped_invalid"
        return result

    await _merge_series(db, canonical_id, duplicate_id, result)
    await _merge_identity_children(db, canonical_id, duplicate_id, result)
    await _rewrite_job_payloads(db, canonical_id, duplicate_id)
    await _enrich_canonical(db, canonical_id, duplicate_id)
    for fk in await _foreign_key_columns(db, "instrument"):
        moved, dropped = await _repoint(db, fk, duplicate_id, canonical_id)
        key = f"{fk.table}.{fk.column}"
        if moved:
            result.moved[key] = moved
        if dropped:
            result.dropped[key] = result.dropped.get(key, 0) + dropped
    await db.execute(
        text(
            "INSERT INTO instrument_merge_log "
            "(duplicate_instrument_id, canonical_instrument_id, duplicate_symbol, reason, detail) "
            "VALUES (:dup, :canon, :symbol, :reason, CAST(:detail AS json))"
        ),
        {
            "dup": duplicate_id,
            "canon": canonical_id,
            "symbol": locked[duplicate_id].symbol,
            "reason": plan.reason,
            "detail": _json({**plan.detail, "moved": result.moved, "dropped": result.dropped}),
        },
    )
    await db.execute(text("DELETE FROM instrument WHERE id = :dup"), {"dup": duplicate_id})
    return result


def _row(row: Any) -> InstrumentRow:
    return InstrumentRow(
        id=row.id,
        type_id=row.type_id,
        symbol=row.symbol,
        name=row.name,
        identity_status=row.identity_status,
        domain_key=row.domain_key,
        issuer_id=row.issuer_id,
    )


def _json(value: Any) -> str:
    import json

    return json.dumps(value, default=str, sort_keys=True)


# --------------------------------------------------------------------------- #
# Batch runner (worker task entry point)
# --------------------------------------------------------------------------- #


async def merge_duplicate_instruments(
    session_factory: Any,
    *,
    max_pairs: int = 25,
    max_seconds: float = 240.0,
    dry_run: bool = False,
    evidence: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Merge up to ``max_pairs`` provable duplicates, one transaction per pair.

    Idempotent and resumable: every pass re-plans from current data, so an
    interrupted run simply continues, and a finished run plans nothing.
    """

    started = time.monotonic()
    async with session_factory() as db:
        report = await plan_duplicate_merges(db)
    if evidence is not None:
        # Merging deletes rows, so only the enabled evidence tiers act; the
        # others stay visible in the summary for review before enabling them.
        enabled = {str(item).strip() for item in evidence if str(item).strip()}
        kept = []
        for plan in report.plans:
            if plan.detail.get("evidence") in enabled:
                kept.append(plan)
            else:
                report.skipped[f"evidence_not_enabled:{plan.detail.get('evidence')}"] += 1
        report.plans = kept
    summary: dict[str, Any] = {
        "groups": report.groups,
        "planned": len(report.plans),
        "skipped": dict(report.skipped),
        "causes": dict(Counter(plan.reason for plan in report.plans)),
        "merged": 0,
        "failed": 0,
        "deferred": 0,
    }
    if dry_run:
        summary["dry_run"] = True
        return summary
    for plan in report.plans[:max_pairs]:
        if time.monotonic() - started > max_seconds:
            break
        async with session_factory() as db:
            try:
                locked = (
                    await db.execute(
                        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
                    )
                ).scalar_one()
                if not locked:
                    summary["deferred"] += 1
                    summary["stopped"] = "another merge pass holds the lock"
                    break
                outcome = await merge_instrument_pair(db, plan)
                await db.commit()
            except Exception:
                await db.rollback()
                summary["failed"] += 1
                logger.exception(
                    "duplicate instrument merge failed (%s -> %s)",
                    plan.duplicate_id,
                    plan.canonical_id,
                )
                continue
        if outcome.status == "merged":
            summary["merged"] += 1
        else:
            summary["deferred"] += 1
    summary["remaining"] = max(0, len(report.plans) - summary["merged"])
    return summary
