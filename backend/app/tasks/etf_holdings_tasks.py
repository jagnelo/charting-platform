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

    from app.services.benchmark_family_history import normalize_family_keys, normalize_family_roles
    from app.services.benchmark_family_holdings_runs import completed_month_end_dates

    requested_dates = completed_month_end_dates(
        count=settings.BENCHMARK_FAMILY_HOLDINGS_REFRESH_LOOKBACK_DATES
    )
    family_keys = normalize_family_keys(None)
    roles = normalize_family_roles(None)
    redis = ctx.get("redis")
    if redis is None:
        return {
            "requested_dates": [value.isoformat() for value in requested_dates],
            "family_keys": family_keys,
            "roles": roles,
            "queued": 0,
            "already_queued": 0,
            "queue_unavailable": True,
        }

    queued = already_queued = 0
    queue_errors: list[dict[str, str]] = []
    for requested_date in requested_dates:
        for family_key in family_keys:
            try:
                job = await redis.enqueue_job(
                    "task_refresh_scheduled_benchmark_family_holdings_unit",
                    family_key,
                    requested_date.isoformat(),
                    roles,
                    _job_id=(
                        f"benchmark-family-scheduled:{family_key}:{requested_date.isoformat()}"
                    ),
                    _expires=86_400,
                )
            except Exception as exc:  # noqa: BLE001 - retain bounded per-root evidence.
                queue_errors.append(
                    {
                        "family_key": family_key,
                        "requested_date": requested_date.isoformat(),
                        "error": str(exc) or "Benchmark family unit queue failed.",
                    }
                )
                continue
            if job is None:
                already_queued += 1
            else:
                queued += 1
    return {
        "requested_dates": [value.isoformat() for value in requested_dates],
        "family_keys": family_keys,
        "roles": roles,
        "queued": queued,
        "already_queued": already_queued,
        "queue_errors": queue_errors,
        "queue_error_count": len(queue_errors),
        "queue_unavailable": False,
    }
