import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import AsyncSessionLocal, Base, engine
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
from app.services.e2e_seed import seed_e2e_instruments
from app.services.provider_runtime import seed_provider_runtime
from app.services.top_down_taxonomy import seed_top_down_taxonomy

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Creating DB tables…")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        await seed_provider_runtime(db)
        if settings.E2E_SEED_INSTRUMENTS:
            await seed_e2e_instruments(db)
        await seed_top_down_taxonomy(db)
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
    return {"status": "ok", "version": "2.0.0"}
