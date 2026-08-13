import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import AsyncSessionLocal
from app.routers import (
    alert_history,
    alerts,
    analysis,
    auth,
    baskets,
    calendar,
    code,
    coverage,
    dashboards,
    drawings,
    etf_holdings,
    indicators,
    instrument_indicators,
    instruments,
    market_groups,
    notes,
    ohlcv,
    options,
    options_exposure,
    presets,
    providers,
    radar,
    research,
    screener,
    screener_alerts,
    strategy_lab,
    watchlists,
    workspaces,
)
from app.services.alert_engine import run_alert_check
from app.services.e2e_seed import seed_e2e_instruments, seed_e2e_market_data
from app.services.provider_runtime import seed_provider_runtime
from app.services.workstation_bootstrap import ensure_core_workstation_identities

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as db:
        await seed_provider_runtime(db)
        if settings.E2E_SEED_INSTRUMENTS:
            await seed_e2e_instruments(db)
        if settings.E2E_SEED_MARKET_DATA:
            await seed_e2e_market_data(db)
        # The curated identity bootstrap is not market-data or holdings
        # fixture data. It makes a clean deployment's immutable US Top Down
        # layout immediately navigable while provider-backed bars and
        # point-in-time holdings continue through their normal services.
        await ensure_core_workstation_identities(db)
        await db.commit()

    logger.info(f"Starting alert scheduler (every {settings.ALERT_POLL_INTERVAL}s)")
    scheduler.add_job(
        run_alert_check,
        "interval",
        seconds=settings.ALERT_POLL_INTERVAL,
        id="alert_check",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Backend ready ✓")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Charting Platform API",
    version="2.0.0",
    description="Personal trading chart platform — multi-user, indicator alerts, screener",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"
app.include_router(auth.router, prefix=PREFIX)
app.include_router(options.router, prefix=PREFIX)
app.include_router(options_exposure.router, prefix=PREFIX)
app.include_router(baskets.router, prefix=PREFIX)
app.include_router(etf_holdings.router, prefix=PREFIX)
app.include_router(instruments.router, prefix=PREFIX)
app.include_router(providers.router, prefix=PREFIX)
app.include_router(ohlcv.router, prefix=PREFIX)
app.include_router(dashboards.router, prefix=PREFIX)
app.include_router(drawings.router, prefix=PREFIX)
app.include_router(presets.router, prefix=PREFIX)
app.include_router(radar.router, prefix=PREFIX)
app.include_router(alerts.router, prefix=PREFIX)
app.include_router(alert_history.router, prefix=PREFIX)
app.include_router(screener.router, prefix=PREFIX)
app.include_router(strategy_lab.router, prefix=PREFIX)
app.include_router(indicators.router, prefix=PREFIX)
app.include_router(instrument_indicators.router, prefix=PREFIX)
app.include_router(watchlists.router, prefix=PREFIX)
app.include_router(screener_alerts.router, prefix=PREFIX)
app.include_router(calendar.router, prefix=PREFIX)
app.include_router(coverage.router, prefix=PREFIX)
app.include_router(analysis.router, prefix=PREFIX)
app.include_router(code.router, prefix=PREFIX)
app.include_router(research.router, prefix=PREFIX)
app.include_router(workspaces.router, prefix=PREFIX)
app.include_router(market_groups.router, prefix=PREFIX)
app.include_router(notes.router, prefix=PREFIX)


@app.get("/health")
async def health():
    # Keep the deployment mode observable to acceptance harnesses.  In
    # particular, board-visual tests must never mistake a persistent canonical
    # database for the deterministic seeded dataset they were launched with.
    return {
        "status": "ok",
        "version": "2.0.0",
        "e2e_seed_instruments": settings.E2E_SEED_INSTRUMENTS,
        "e2e_seed_market_data": settings.E2E_SEED_MARKET_DATA,
    }
