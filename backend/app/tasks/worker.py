"""
ARQ worker entrypoint.
Run with: arq app.tasks.worker.WorkerSettings
"""

from arq.connections import RedisSettings

from app.config import settings
from app.tasks import alert_tasks, data_tasks, screener_tasks


class WorkerSettings:
    functions = [
        data_tasks.fetch_instrument_history,
        data_tasks.fetch_all_instruments_history,
        screener_tasks.run_screener_task,
        screener_tasks.run_all_scheduled_screeners,
        alert_tasks.check_all_alerts,
    ]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 600  # 10 minutes max per job
    keep_result = 3600  # keep results for 1 hour
    on_startup = None
    on_shutdown = None
