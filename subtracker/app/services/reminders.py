"""Daily reminder pass: turn upcoming schedule events into notifications on each user's reminder days."""
from datetime import date

from sqlmodel import Session, select

from ..models import MedicineDetail, SubStatus, Subscription, UserProfile
from . import schedule
from .ha import HAClient, ha as default_ha
from .notify import notify


async def run_reminders(session: Session, today: date | None = None, ha: HAClient = default_ha) -> int:
    today = today or date.today()
    users = session.exec(select(UserProfile)).all()
    sent = 0
    for sub in session.exec(select(Subscription).where(Subscription.status != SubStatus.cancelled)).all():
        med = session.get(MedicineDetail, sub.id)
        targets = [u for u in users if sub.owner_user_id in (None, u.id)] or [None]
        for ev in schedule.upcoming_events(sub, med, today):
            days = ev.days_from(today)
            if days < 0:
                continue
            base = f"{ev.kind}:{sub.id}:{ev.date.isoformat()}:{days}"
            body = f"{ev.title} on {ev.date:%d %b %Y}" + (" (today)" if days == 0 else f" ({days} days)")
            for user in targets:
                # a user's own reminder days override the subscription's; day 0 always fires
                wanted = (user.reminder_days if user and user.reminder_days else sub.reminder_days) or []
                if days != 0 and days not in wanted:
                    continue
                sent += await notify(
                    session, key=f"{base}:{user.id if user else 'all'}", persistent_id=base,
                    title=ev.title, body=body, category=sub.category,
                    owner_user_id=user.id if user else None, ha=ha,
                )
    return sent
