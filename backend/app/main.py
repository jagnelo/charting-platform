import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import (
    alerts,
    auth,
    calendar,
    dashboards,
    drawings,
    indicators,
    instrument_indicators,
    instruments,
    ohlcv,
    presets,
    screener,
    screener_alerts,
    watchlists,
)
from app.services.alert_engine import run_alert_check

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Creating DB tables…")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
app.include_router(instruments.router, prefix=PREFIX)
app.include_router(ohlcv.router, prefix=PREFIX)
app.include_router(dashboards.router, prefix=PREFIX)
app.include_router(drawings.router, prefix=PREFIX)
app.include_router(presets.router, prefix=PREFIX)
app.include_router(alerts.router, prefix=PREFIX)
app.include_router(screener.router, prefix=PREFIX)
app.include_router(indicators.router, prefix=PREFIX)
app.include_router(instrument_indicators.router, prefix=PREFIX)
app.include_router(watchlists.router, prefix=PREFIX)
app.include_router(screener_alerts.router, prefix=PREFIX)
app.include_router(calendar.router, prefix=PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
