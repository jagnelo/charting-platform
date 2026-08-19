import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def refresh_etf_holdings_task(ctx: dict) -> dict:
    """Scheduled ETF holdings refresh entry point.

    The baseline subsystem ships the persisted ingestion surface and adapter contract.
    Concrete issuer adapters can register behind this task without changing API/UI callers.
    """

    if not getattr(settings, "ETF_HOLDINGS_REFRESH_ENABLED", False):
        logger.info("ETF holdings refresh disabled; skipping")
        return {"skipped": True, "reason": "refresh disabled"}

    from app.database import AsyncSessionLocal
    from app.services.etf_holdings_refresh import refresh_all_known_etf_holdings

    async with AsyncSessionLocal() as db:
        summary = await refresh_all_known_etf_holdings(db)
        await db.commit()
        return summary


async def backfill_sec_nport_holdings_task(ctx: dict) -> dict:
    """Scheduled SEC N-PORT backfill entry point for ETF profiles with CIKs."""

    if not getattr(settings, "ETF_HOLDINGS_SEC_BACKFILL_ENABLED", False):
        logger.info("ETF holdings SEC backfill disabled; skipping")
        return {"skipped": True, "reason": "SEC backfill disabled"}

    from app.database import AsyncSessionLocal
    from app.services.etf_holdings_edgar import backfill_all_sec_nport_holdings
    from app.services.top_down_taxonomy import benchmark_family_proxy_symbols

    async with AsyncSessionLocal() as db:
        summary = await backfill_all_sec_nport_holdings(
            db,
            priority_symbols=list(benchmark_family_proxy_symbols()),
            max_profiles=settings.ETF_HOLDINGS_SEC_BACKFILL_MAX_PROFILES,
            max_filings_per_etf=settings.ETF_HOLDINGS_SEC_BACKFILL_MAX_FILINGS_PER_ETF,
        )
        await db.commit()
        return summary


async def reconcile_etf_holdings_classifications_task(ctx: dict) -> dict:
    """Resume bounded free-source classification enrichment for ETF snapshots."""

    if not getattr(settings, "ETF_HOLDINGS_CLASSIFICATION_REFRESH_ENABLED", False):
        logger.info("ETF holdings classification refresh disabled; skipping")
        return {"skipped": True, "reason": "classification refresh disabled"}

    from app.database import AsyncSessionLocal
    from app.services.etf_holdings_refresh import reconcile_all_etf_holdings_classifications

    async with AsyncSessionLocal() as db:
        summary = await reconcile_all_etf_holdings_classifications(
            db,
            max_profiles=settings.ETF_HOLDINGS_CLASSIFICATION_MAX_PROFILES,
            max_enrichments_per_profile=settings.ETF_HOLDINGS_CLASSIFICATION_MAX_ENRICHMENTS_PER_PROFILE,
        )
        await db.commit()
        return summary


async def refresh_benchmark_family_holdings_task(ctx: dict) -> dict:
    """Refresh bounded dated snapshots for every configured family role.

    This is an opt-in maintenance task. It uses completed month-end candidates
    rather than pretending that all providers expose the same official rebalance
    calendar, and it never runs from an interactive source/map request.
    """

    if not getattr(settings, "BENCHMARK_FAMILY_HOLDINGS_REFRESH_ENABLED", False):
        logger.info("Benchmark family dated holdings refresh disabled; skipping")
        return {"skipped": True, "reason": "benchmark family refresh disabled"}

    from app.database import AsyncSessionLocal
    from app.services.benchmark_family_history import queue_snapshot_member_history
    from app.services.benchmark_family_holdings_runs import completed_month_end_dates
    from app.services.etf_holdings_refresh import refresh_all_benchmark_family_holdings_for_dates

    requested_dates = completed_month_end_dates(
        count=settings.BENCHMARK_FAMILY_HOLDINGS_REFRESH_LOOKBACK_DATES
    )
    async with AsyncSessionLocal() as db:
        summary = await refresh_all_benchmark_family_holdings_for_dates(
            db,
            requested_dates=requested_dates,
        )
        snapshot_ids = [
            int(leg["snapshot_id"])
            for run in summary.get("runs", [])
            for family in run.get("families", [])
            for leg in family.get("legs", [])
            if isinstance(leg, dict)
            and leg.get("status") == "refreshed"
            and leg.get("snapshot_id") is not None
        ]
        history_queue = await queue_snapshot_member_history(
            db,
            ctx.get("redis"),
            snapshot_ids,
        )
        await db.commit()
        return {
            "requested_dates": [value.isoformat() for value in requested_dates],
            "family_keys": summary.get("family_keys", []),
            "roles": summary.get("roles", []),
            "refreshed": summary.get("refreshed", 0),
            "unavailable": summary.get("unavailable", 0),
            "failed": summary.get("failed", 0),
            "snapshot_ids": snapshot_ids,
            "history_queue": history_queue,
            "runs": summary.get("runs", []),
        }
