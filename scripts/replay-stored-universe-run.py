#!/usr/bin/env python3
"""Reconcile a complete persisted universe scan without contacting its provider.

This is an operator recovery tool for a run whose raw discovery pages were
durably stored but whose normalization/materialization failed. It requires an
exact run ID, validates the complete page sequence before writes, reuses those
same discovery-snapshot rows, and replaces provider transport with a local
reader. It never fetches a provider response.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, select

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.data_source import DataSource  # noqa: E402
from app.models.market_data_foundation import MarketUniverseReconciliationRun  # noqa: E402
from app.models.provider_observation import UniverseDiscoverySnapshot  # noqa: E402
from app.services import market_universe  # noqa: E402
from app.services.exchange_catalog import normalize_exchange_mic  # noqa: E402


def _verified_pages(
    run: MarketUniverseReconciliationRun,
    snapshots: list[UniverseDiscoverySnapshot],
) -> tuple[list[dict[str, Any]], str | None]:
    provenance = run.provenance if isinstance(run.provenance, dict) else {}
    snapshot_ids = provenance.get("discovery_snapshot_ids")
    if not isinstance(snapshot_ids, list) or not snapshot_ids:
        raise ValueError("run does not identify durable discovery pages")
    if len(snapshots) != len(snapshot_ids):
        raise ValueError("one or more referenced discovery pages are missing")

    pages: list[dict[str, Any]] = []
    seen_listing_keys: set[tuple[str, str | None, str]] = set()
    expected_offset = 0
    declared_total: int | None = None
    total_scope: str | None = None
    source_snapshot_date: str | None = None
    terminal = False
    for index, snapshot in enumerate(snapshots):
        if snapshot.offset != expected_offset:
            raise ValueError(
                f"stored page sequence has a gap: expected offset {expected_offset}, "
                f"found {snapshot.offset}"
            )
        payload = snapshot.payload if isinstance(snapshot.payload, dict) else {}
        page = payload.get("page")
        if not isinstance(page, dict):
            raise ValueError(f"stored page {snapshot.id} has no page object")
        quotes = page.get("quotes")
        if not isinstance(quotes, list) or any(
            not isinstance(row, dict) for row in quotes
        ):
            raise ValueError(f"stored page {snapshot.id} has malformed quote rows")
        if page.get("validation_errors"):
            raise ValueError(
                f"stored page {snapshot.id} contains provider validation errors"
            )
        page_total = page.get("total")
        if page_total is not None:
            if (
                isinstance(page_total, bool)
                or not isinstance(page_total, int)
                or page_total < 0
            ):
                raise ValueError(f"stored page {snapshot.id} has an invalid total")
            if declared_total is not None and declared_total != page_total:
                raise ValueError("stored pages disagree on the declared total")
            declared_total = page_total
        page_scope = page.get("total_scope", "filtered")
        if page_scope not in {"filtered", "raw"}:
            raise ValueError(f"stored page {snapshot.id} has an invalid total scope")
        if total_scope is not None and total_scope != page_scope:
            raise ValueError("stored pages disagree on total scope")
        total_scope = page_scope
        page_date = str(page.get("source_snapshot_date") or "").strip() or None
        if page_date:
            if source_snapshot_date is not None and source_snapshot_date != page_date:
                raise ValueError("stored pages contain different source snapshot dates")
            source_snapshot_date = page_date

        for row in quotes:
            symbol = market_universe._row_symbol(
                row, preserve_case=provenance.get("provider") == "cta_plan"
            )
            if not symbol:
                raise ValueError(
                    f"stored page {snapshot.id} contains a row without a symbol"
                )
            key = market_universe._listing_key(
                symbol,
                normalize_exchange_mic(row.get("exchange")),
                market_universe._row_type(row, run.quote_type),
            )
            if key in seen_listing_keys:
                raise ValueError("stored pages contain duplicate listing rows")
            seen_listing_keys.add(key)

        pages.append(page)
        next_offset = page.get("next_offset")
        next_url = page.get("next_url")
        if next_offset is not None:
            if (
                isinstance(next_offset, bool)
                or not isinstance(next_offset, int)
                or next_offset <= snapshot.offset
            ):
                raise ValueError(
                    f"stored page {snapshot.id} has an invalid next offset"
                )
            expected_offset = next_offset
            terminal = False
        elif next_url:
            expected_offset = snapshot.offset + len(quotes)
            terminal = False
        else:
            expected_offset = snapshot.offset + len(quotes)
            is_last = index == len(snapshots) - 1
            terminal = bool(
                is_last
                and (
                    page.get("complete") is True
                    or (
                        declared_total is not None and expected_offset >= declared_total
                    )
                )
            )
    row_count = sum(len(page["quotes"]) for page in pages)
    if not terminal:
        raise ValueError("stored page sequence has no complete terminal page")
    if declared_total is not None and row_count != declared_total:
        raise ValueError(
            f"stored pages contain {row_count} rows but declare {declared_total}"
        )
    if total_scope == "raw" and pages[-1].get("complete") is not True:
        raise ValueError("raw-total source omitted explicit completion evidence")
    return pages, source_snapshot_date


async def replay(run_id: int, *, dry_run: bool = False) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        original = await db.get(MarketUniverseReconciliationRun, run_id)
        if original is None:
            raise ValueError(f"universe reconciliation run {run_id} does not exist")
        if original.status not in {"running", "failed"}:
            raise ValueError(
                f"run {run_id} has status {original.status!r}; only running/failed runs may replay"
            )
        provenance = (
            original.provenance if isinstance(original.provenance, dict) else {}
        )
        provider_name = str(provenance.get("provider") or "").strip()
        if not provider_name:
            raise ValueError("run does not identify its provider")
        snapshot_ids = provenance.get("discovery_snapshot_ids")
        if not isinstance(snapshot_ids, list) or not snapshot_ids:
            raise ValueError("run has no referenced stored discovery pages")
        ids = [value for value in snapshot_ids if isinstance(value, int) and value > 0]
        snapshots = (
            (
                await db.execute(
                    select(UniverseDiscoverySnapshot)
                    .where(
                        UniverseDiscoverySnapshot.id.in_(ids),
                        UniverseDiscoverySnapshot.data_source_id
                        == original.data_source_id,
                        UniverseDiscoverySnapshot.quote_type == original.quote_type,
                    )
                    .order_by(UniverseDiscoverySnapshot.offset.asc())
                )
            )
            .scalars()
            .all()
        )
        pages, source_snapshot_date = _verified_pages(original, list(snapshots))
        source = await db.get(DataSource, original.data_source_id)
        if source is None:
            raise ValueError("run's data source no longer exists")
        prior_replay_id = provenance.get("offline_replayed_as_run_id")
        if isinstance(prior_replay_id, int) and prior_replay_id > 0:
            prior_replay = await db.get(
                MarketUniverseReconciliationRun, prior_replay_id
            )
            if (
                prior_replay is None
                or prior_replay.status != "complete"
                or prior_replay.data_source_id != original.data_source_id
                or prior_replay.quote_type != original.quote_type
            ):
                raise ValueError(
                    "run's recorded offline replay is missing or not complete"
                )
            return {
                "prior_run_id": run_id,
                "replay_run_id": prior_replay.id,
                "provider": provider_name,
                "status": "already_replayed",
                "expected_count": prior_replay.expected_count,
                "observed_count": prior_replay.observed_count,
                "new_count": prior_replay.new_count,
                "updated_count": prior_replay.updated_count,
                "missing_count": prior_replay.missing_count,
                "quarantined_count": prior_replay.quarantined_count,
                "page_count": len(pages),
                "source_snapshot_date": source_snapshot_date,
                "provider_http_requests": 0,
                "writes_performed": False,
            }
        if dry_run:
            return {
                "run_id": run_id,
                "provider": provider_name,
                "status": "stored_pages_verified",
                "page_count": len(pages),
                "row_count": sum(len(page["quotes"]) for page in pages),
                "source_snapshot_date": source_snapshot_date,
                "provider_http_requests": 0,
                "writes_performed": False,
            }

        snapshots_by_offset = {snapshot.offset: snapshot for snapshot in snapshots}
        page_by_offset = {
            snapshot.offset: page
            for snapshot, page in zip(snapshots, pages, strict=True)
        }
        resolved = SimpleNamespace(provider_name=provider_name, data_source=source)
        fake_provider = SimpleNamespace(
            supported_discovery_types=lambda: [original.quote_type]
        )
        latest_run_id = await db.scalar(
            select(func.max(MarketUniverseReconciliationRun.id)).where(
                MarketUniverseReconciliationRun.data_source_id == source.id,
                MarketUniverseReconciliationRun.quote_type == original.quote_type,
            )
        )
        latest_run_id = int(latest_run_id or 0)
        originals = {
            "resolve_provider_chain": market_universe.resolve_provider_chain,
            "get_discovery_provider": market_universe.get_discovery_provider,
            "execute_provider_call": market_universe.execute_provider_call,
            "store_universe_discovery_snapshot": market_universe.store_universe_discovery_snapshot,
        }

        async def resolved_chain(*_args, **_kwargs):
            return [resolved]

        async def no_transport(
            _db, _capability, operation, *, provider_name, **_kwargs
        ):
            operation_offset = int(operation.rsplit(":", 1)[-1])
            if (
                provider_name != resolved.provider_name
                or operation_offset not in page_by_offset
            ):
                raise RuntimeError(
                    "offline replay requested a page not in the verified archive"
                )
            return SimpleNamespace(
                result=page_by_offset[operation_offset], data_source=source
            )

        async def reuse_stored_snapshot(_db, *, offset, page, **_kwargs):
            snapshot = snapshots_by_offset.get(offset)
            if snapshot is None or snapshot.payload.get("page") != page:
                raise RuntimeError(
                    "offline replay page does not match its stored snapshot"
                )
            return snapshot

        try:
            market_universe.resolve_provider_chain = resolved_chain
            market_universe.get_discovery_provider = lambda _name: fake_provider
            market_universe.execute_provider_call = no_transport
            market_universe.store_universe_discovery_snapshot = reuse_stored_snapshot
            result = await market_universe.reconcile_us_universe(
                db,
                provider_name=provider_name,
                quote_types=[original.quote_type],
            )
            if result.get("status") != "complete":
                raise RuntimeError(
                    "offline reconciliation did not complete: "
                    f"{result.get('status', 'unknown')}"
                )
        finally:
            for name, value in originals.items():
                setattr(market_universe, name, value)

        replay_run = (
            (
                await db.execute(
                    select(MarketUniverseReconciliationRun)
                    .where(
                        MarketUniverseReconciliationRun.data_source_id == source.id,
                        MarketUniverseReconciliationRun.quote_type
                        == original.quote_type,
                        MarketUniverseReconciliationRun.id > latest_run_id,
                    )
                    .order_by(MarketUniverseReconciliationRun.id.asc())
                )
            )
            .scalars()
            .all()
        )
        replay_runs = [
            item
            for item in replay_run
            if isinstance(item.provenance, dict)
            and item.provenance.get("provider") == provider_name
        ]
        if len(replay_runs) != 1:
            raise RuntimeError(
                "offline reconciliation did not create exactly one isolated replay run"
            )
        replay_run = replay_runs[0]
        original = await db.get(MarketUniverseReconciliationRun, run_id)
        if original is not None:
            if original.status == "running":
                original.status = "failed"
                original.error = f"derived replay completed as run {replay_run.id}; raw pages retained"
                original.finished_at = datetime.now(UTC)
            original.provenance = {
                **(original.provenance or {}),
                "offline_replayed_as_run_id": replay_run.id,
            }
            await db.commit()
        return {
            "prior_run_id": run_id,
            "replay_run_id": replay_run.id,
            "provider": provider_name,
            "status": replay_run.status,
            "expected_count": replay_run.expected_count,
            "observed_count": replay_run.observed_count,
            "new_count": replay_run.new_count,
            "updated_count": replay_run.updated_count,
            "missing_count": replay_run.missing_count,
            "quarantined_count": replay_run.quarantined_count,
            "page_count": len(pages),
            "source_snapshot_date": source_snapshot_date,
            "provider_http_requests": 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="verify complete stored pages without writing or calling providers",
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(replay(args.run_id, dry_run=args.dry_run))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, default=str))
    return (
        0
        if result.get("status")
        in {"stored_pages_verified", "complete", "already_replayed"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
