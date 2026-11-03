"""Background jobs. Each job opens its own DB session."""
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session

from ..config import get_options
from ..db import engine
from . import catalog
from .ai.providers import get_provider
from .deals import run_auto_deal_searches
from .discovery import due_countries, run_discovery
from .notify import flush_pending
from .reminders import run_reminders
from .sensors import push_sensors

log = logging.getLogger("subtracker.jobs")
scheduler = AsyncIOScheduler()


async def reminders_job() -> None:
    with Session(engine) as session:
        log.info("Reminders sent: %s", await run_reminders(session))


async def sensors_job() -> None:
    with Session(engine) as session:
        try:
            await push_sensors(session)
        except Exception:  # HA may be restarting; next run retries
            log.exception("Sensor push failed")


async def flush_job() -> None:
    with Session(engine) as session:
        await flush_pending(session)


async def discovery_job() -> None:
    opts = get_options()
    ai = get_provider(opts)
    if ai is None:
        return
    with Session(engine) as session:
        if codes := due_countries(session, [catalog.household_country(session)], opts.discovery_interval_days):
            log.info("Provider discovery for %s: %s", codes, await run_discovery(session, ai, codes))


async def deals_job() -> None:
    opts = get_options()
    ai = get_provider(opts)
    if ai is None:
        return
    with Session(engine) as session:
        log.info("Automatic deal searches run: %s", await run_auto_deal_searches(session, ai, opts.deal_search_lead_days))


def start() -> None:
    if scheduler.running:
        return
    # coalesce + next_run_time=now: a missed 08:00 run (add-on was stopped) still happens once at startup
    scheduler.add_job(reminders_job, "cron", hour=8, id="reminders", coalesce=True, next_run_time=datetime.now(),
                      replace_existing=True)
    scheduler.add_job(sensors_job, "interval", minutes=10, id="sensors", next_run_time=datetime.now(),
                      replace_existing=True)
    # daily check; the interval itself is tracked per country, so add-on restarts don't reset it
    scheduler.add_job(discovery_job, "cron", hour=3, id="discovery", coalesce=True, replace_existing=True)
    scheduler.add_job(deals_job, "cron", hour=4, id="deals", coalesce=True, replace_existing=True)
    scheduler.add_job(flush_job, "interval", minutes=5, id="flush", replace_existing=True)
    scheduler.start()


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
