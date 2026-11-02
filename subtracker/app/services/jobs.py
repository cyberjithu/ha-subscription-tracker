"""Background jobs. Each job opens its own DB session."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


def start() -> None:
    if not scheduler.running:
        scheduler.start()


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
