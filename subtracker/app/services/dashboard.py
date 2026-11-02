"""Spending aggregates for the dashboard. All amounts are monthly equivalents (a yearly bill counts 1/12 each month)."""
import calendar
from collections import defaultdict
from datetime import date

from sqlmodel import Session, select

from ..models import Bill, Kind, MedicineDetail, PriceChange, SubStatus, Subscription
from . import schedule


def month_starts(today: date, n: int = 12) -> list[date]:
    """First day of the last n months, oldest first, ending with the current month."""
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(date(y, m, 1))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def bill_spend_in_month(bills: list[Bill], start: date) -> float:
    """Bill amounts prorated by the days of each bill period that fall in the month."""
    end = month_end(start)
    total = 0.0
    for b in bills:
        days = (b.period_end - b.period_start).days + 1
        overlap = (min(end, b.period_end) - max(start, b.period_start)).days + 1
        if days > 0 and overlap > 0:
            total += b.amount * overlap / days
    return total


def price_at(changes: list[PriceChange], day: date) -> float | None:
    """Price in effect on a day; None before the first recorded price."""
    current = None
    for c in sorted(changes, key=lambda c: c.effective_date):
        if c.effective_date <= day:
            current = c.price
    return current


def monthly_in(sub: Subscription, start: date, bills: list[Bill], changes: list[PriceChange],
               med: MedicineDetail | None) -> float:
    """What a subscription contributed to one calendar month."""
    end = month_end(start)
    if sub.kind == Kind.usage and bills:
        return bill_spend_in_month(bills, start)
    began = sub.start_date or (min((c.effective_date for c in changes), default=None)) or sub.created_at.date()
    if began > end:
        return 0.0
    if sub.kind == Kind.refill:
        return schedule.monthly_cost(sub, [], med)
    price = price_at(changes, end)
    if price is None:  # no history recorded (e.g. created without a price): use today's price
        price = sub.price
    return price * schedule.cycle_monthly_factor(sub.cycle, sub.cycle_days)


def build(session: Session, subs: list[Subscription], names: dict[str, str], today: date | None = None) -> dict:
    today = today or date.today()
    active = [s for s in subs if s.status != SubStatus.cancelled]
    months = month_starts(today)
    by_cat: dict[str, float] = defaultdict(float)
    by_owner: dict[str | None, float] = defaultdict(float)
    trend = [0.0] * len(months)
    upcoming = []
    currencies: dict[str, int] = defaultdict(int)
    for s in active:
        bills = session.exec(select(Bill).where(Bill.subscription_id == s.id)).all()
        changes = session.exec(select(PriceChange).where(PriceChange.subscription_id == s.id)).all()
        med = session.get(MedicineDetail, s.id) if s.kind == Kind.refill else None
        monthly = schedule.monthly_cost(s, bills, med)
        by_cat[s.category] += monthly
        by_owner[s.owner_user_id] += monthly
        currencies[s.currency] += 1
        for i, m in enumerate(months):
            trend[i] += monthly_in(s, m, bills, changes, med)
        for ev in schedule.upcoming_events(s, med, today):
            if 0 <= ev.days_from(today) <= 30:
                upcoming.append({"subscription_id": s.id, "name": s.name, "kind": ev.kind, "title": ev.title,
                                 "date": ev.date.isoformat(), "days": ev.days_from(today)})
    total = sum(by_cat.values())
    return {
        "currency": max(currencies, key=currencies.get) if currencies else "EUR",
        "monthly_total": round(total, 2),
        "yearly_total": round(total * 12, 2),
        "active_count": len(active),
        "by_category": sorted(({"category": k, "monthly": round(v, 2)} for k, v in by_cat.items()),
                              key=lambda r: -r["monthly"]),
        "by_owner": sorted(({"owner_id": k, "name": names.get(k, k) if k else "Household", "monthly": round(v, 2)}
                            for k, v in by_owner.items()), key=lambda r: -r["monthly"]),
        "trend": [{"month": m.strftime("%Y-%m"), "total": round(t, 2)} for m, t in zip(months, trend)],
        "upcoming": sorted(upcoming, key=lambda e: e["days"]),
    }
