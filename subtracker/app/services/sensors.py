"""Mirror subscriptions into Home Assistant as sensor states (REST-set states vanish on HA restart, so re-push often)."""
import re
from collections import Counter, defaultdict
from datetime import date

from sqlmodel import Session, select

from ..models import Bill, Kind, MedicineDetail, SubStatus, Subscription, UserProfile
from . import schedule
from .ha import HAClient, ha as default_ha

# shortcut: in-memory only, so a subscription deleted while the add-on is stopped stays in HA until HA restarts.
_pushed: set[str] = set()  # entity ids pushed last run, so removed subscriptions get cleared


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "item"


async def push_sensors(session: Session, today: date | None = None, ha: HAClient = default_ha) -> dict[str, tuple]:
    today = today or date.today()
    names = {u.id: u.display_name for u in session.exec(select(UserProfile))}
    subs = session.exec(select(Subscription).where(Subscription.status != SubStatus.cancelled)
                        .order_by(Subscription.id)).all()
    states: dict[str, tuple] = {}
    totals: dict[str, float] = defaultdict(float)
    currencies: Counter = Counter()
    upcoming = []
    for sub in subs:
        med = session.get(MedicineDetail, sub.id) if sub.kind == Kind.refill else None
        bills = session.exec(select(Bill).where(Bill.subscription_id == sub.id)).all() if sub.kind == Kind.usage else []
        monthly = round(schedule.monthly_cost(sub, bills, med), 2)
        totals[sub.category] += monthly
        currencies[sub.currency] += 1
        events = [e for e in schedule.upcoming_events(sub, med, today) if e.date >= today]
        upcoming += [(e, sub) for e in events]
        ev = events[0] if events else None
        entity = f"sensor.subtracker_{slugify(sub.name)}"
        if entity in states:
            entity = f"{entity}_{sub.id}"
        states[entity] = (ev.days_from(today) if ev else "unknown", {
            "friendly_name": sub.name, "icon": "mdi:calendar-sync", "unit_of_measurement": "d",
            "subscription_id": sub.id, "category": sub.category, "kind": sub.kind.value, "status": sub.status.value,
            "owner": names.get(sub.owner_user_id, sub.owner_user_id) if sub.owner_user_id else "shared",
            "price": sub.price, "currency": sub.currency, "monthly_cost": monthly,
            "next_event": ev.kind if ev else None, "next_event_date": ev.date.isoformat() if ev else None,
            "notice_deadline": d.isoformat() if (d := schedule.notice_deadline(sub)) else None,
            "contract_end": sub.contract_end.isoformat() if sub.contract_end else None,
        })
    currency = currencies.most_common(1)[0][0] if currencies else "EUR"
    states["sensor.subtracker_monthly_total"] = (round(sum(totals.values()), 2), {
        "friendly_name": "Subscriptions monthly total", "icon": "mdi:cash-multiple", "unit_of_measurement": currency,
        "device_class": "monetary", "state_class": "total", "by_category": {k: round(v, 2) for k, v in totals.items()},
        "count": len(subs),
    })
    upcoming.sort(key=lambda x: x[0].date)
    first = upcoming[0] if upcoming else None
    states["sensor.subtracker_next_deadline"] = (first[0].date.isoformat() if first else "unknown", {
        "friendly_name": "Next subscription deadline", "icon": "mdi:calendar-alert", "device_class": "date",
        "subscription": first[1].name if first else None, "event": first[0].kind if first else None,
        "days": first[0].days_from(today) if first else None,
        "upcoming": [{"name": s.name, "event": e.kind, "title": e.title, "date": e.date.isoformat(),
                      "days": e.days_from(today)} for e, s in upcoming[:10]],
    })
    for entity, (state, attrs) in states.items():
        await ha.set_state(entity, state, attrs)
    for gone in _pushed - states.keys():
        await ha.delete_state(gone)
    _pushed.clear()
    _pushed.update(states)
    return states
