"""Background jobs. Each job opens its own DB session."""
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session

from ..db import engine
from .notify import flush_pending
from .reminders import run_reminders

log = logging.getLogger("subtracker.jobs")
scheduler = AsyncIOScheduler()


async def reminders_job() -> None:
    with Session(engine) as session:
        log.info("Reminders sent: %s", await run_reminders(session))


async def flush_job() -> None:
    with Session(engine) as session:
        await flush_pending(session)


def start() -> None:
    if scheduler.running:
        return
    # coalesce + next_run_time=now: a missed 08:00 run (add-on was stopped) still happens once at startup
    scheduler.add_job(reminders_job, "cron", hour=8, id="reminders", coalesce=True, next_run_time=datetime.now(),
                      replace_existing=True)
    scheduler.add_job(flush_job, "interval", minutes=5, id="flush", replace_existing=True)
    scheduler.start()


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
