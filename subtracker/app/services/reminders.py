"""Daily reminder pass: turn upcoming schedule events into notifications on each user's reminder days."""
from datetime import date

from sqlmodel import Session, select

from ..models import MedicineDetail, SubStatus, Subscription, UserProfile
from . import schedule
from .ha import HAClient, ha as default_ha
from .notify import notify


async def run_reminders(session: Session, today: date | None = None, ha: HAClient = default_ha) -> int:
    today = today or date.today()
    users = {u.id: u for u in session.exec(select(UserProfile))}
    sent = 0
    for sub in session.exec(select(Subscription).where(Subscription.status != SubStatus.cancelled)).all():
        med = session.get(MedicineDetail, sub.id)
        # personal items go to their owner only, even when the owner's profile no longer exists
        targets = [sub.owner_user_id] if sub.owner_user_id else (list(users) or [None])
        for ev in schedule.upcoming_events(sub, med, today):
            days = ev.days_from(today)
            if days < 0:
                continue
            base = f"{ev.kind}:{sub.id}:{ev.date.isoformat()}:{days}"
            body = f"{ev.title} on {ev.date:%d %b %Y}" + (" (today)" if days == 0 else f" ({days} days)")
            for uid in targets:
                user = users.get(uid)
                # a user's own reminder days override the subscription's; day 0 always fires
                wanted = (user.reminder_days if user and user.reminder_days else sub.reminder_days) or []
                if days != 0 and (ev.kind == "contract_expired" or days not in wanted):  # the nag is its own reminder
                    continue
                sent += await notify(
                    session, key=f"{base}:{uid or 'all'}", persistent_id=base,
                    title=ev.title, body=body, category=sub.category, owner_user_id=uid,
                    personal=bool(sub.owner_user_id), ha=ha,
                )
    return sent
