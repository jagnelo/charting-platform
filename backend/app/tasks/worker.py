"""
ARQ worker entrypoint.
Run with: arq app.tasks.worker.WorkerSettings
"""

from arq import cron
from arq.connections import RedisSettings

from app.config import settings
from app.tasks import alert_tasks, data_tasks, instrument_sync_tasks, screener_tasks


class WorkerSettings:
    functions = [
        data_tasks.fetch_instrument_history,
        data_tasks.fetch_all_instruments_history,
        data_tasks.enqueue_core_refresh_jobs,
        data_tasks.process_refresh_jobs,
        data_tasks.run_market_data_shadow_report,
        instrument_sync_tasks.seed_universe_task,
        instrument_sync_tasks.sync_instruments_task,
        instrument_sync_tasks.bootstrap_ids_task,
        screener_tasks.run_screener_task,
        screener_tasks.run_all_scheduled_screeners,
        alert_tasks.check_all_alerts,
    ]
    cron_jobs = (
        [
            cron(instrument_sync_tasks.scheduled_weekly_seed, weekday=6, hour=2, minute=0),
            cron(instrument_sync_tasks.scheduled_daily_metadata_sync, hour=3, minute=0),
            cron(instrument_sync_tasks.scheduled_daily_id_bootstrap, hour=4, minute=0),
        ]
        if settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED
        else []
    )
    if settings.MARKET_DATA_REFRESH_SCHEDULE_ENABLED:
        cron_jobs += (
            cron(data_tasks.enqueue_core_refresh_jobs, hour=22, minute=0),
            cron(data_tasks.process_refresh_jobs, minute={0, 15, 30, 45}),
        )
    if settings.MARKET_DATA_SHADOW_REPORT_ENABLED:
        cron_jobs += (cron(data_tasks.run_market_data_shadow_report, hour=23, minute=30),)
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 600  # 10 minutes max per job
    keep_result = 3600  # keep results for 1 hour
    on_startup = None
    on_shutdown = None
