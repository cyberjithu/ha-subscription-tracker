"""Pure date and cost math. No DB, no I/O: every function takes plain values so it is easy to test."""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from ..models import Bill, Cycle, Kind, MedicineDetail, Subscription

DAYS_PER_MONTH = 365.25 / 12


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def add_cycle(d: date, cycle: Cycle, cycle_days: int | None = None, n: int = 1) -> date:
    match cycle:
        case Cycle.week:
            return d + timedelta(weeks=n)
        case Cycle.month:
            return add_months(d, n)
        case Cycle.quarter:
            return add_months(d, 3 * n)
        case Cycle.year:
            return add_months(d, 12 * n)
        case Cycle.custom:
            return d + timedelta(days=(cycle_days or 30) * n)


def roll_forward(renewal: date, cycle: Cycle, cycle_days: int | None, today: date) -> date:
    """First renewal on or after today. Counts cycles from the anchor so month-end days don't drift."""
    n = 0
    while (d := add_cycle(renewal, cycle, cycle_days, n)) < today:
        n += 1
    return d


def term_end(sub: Subscription) -> date | None:
    """Date the current commitment ends: contract end for contracts, else next renewal."""
    if sub.kind == Kind.contract and sub.contract_end:
        return sub.contract_end
    return sub.next_renewal


def notice_deadline(sub: Subscription) -> date | None:
    end = term_end(sub)
    if end is None or not sub.notice_days:
        return None
    return end - timedelta(days=sub.notice_days)


def medicine_remaining(med: MedicineDetail, today: date) -> float:
    used = max((today - med.qty_updated).days, 0) * med.daily_dose
    return max(med.qty_on_hand - used, 0)


def run_out_date(med: MedicineDetail, today: date) -> date | None:
    if med.daily_dose <= 0:
        return None
    return today + timedelta(days=int(medicine_remaining(med, today) // med.daily_dose))


def cycle_monthly_factor(cycle: Cycle, cycle_days: int | None) -> float:
    return {
        Cycle.week: 52 / 12,
        Cycle.month: 1,
        Cycle.quarter: 1 / 3,
        Cycle.year: 1 / 12,
        Cycle.custom: DAYS_PER_MONTH / (cycle_days or 30),
    }[cycle]


def monthly_cost(sub: Subscription, bills: list[Bill] = (), med: MedicineDetail | None = None) -> float:
    """Monthly-equivalent spend. Usage subs average their bills (by days covered) when there are any."""
    if sub.kind == Kind.usage and bills:
        days = sum((b.period_end - b.period_start).days + 1 for b in bills)
        return sum(b.amount for b in bills) / days * DAYS_PER_MONTH if days else 0
    if sub.kind == Kind.refill and med and med.pack_size and med.cost_per_fill:
        return med.cost_per_fill * med.daily_dose * DAYS_PER_MONTH / med.pack_size
    return sub.price * cycle_monthly_factor(sub.cycle, sub.cycle_days)


@dataclass
class Event:
    kind: str  # notice_deadline | renewal | contract_end | refill | script_expiry
    date: date
    subscription_id: int
    title: str

    def days_from(self, today: date) -> int:
        return (self.date - today).days


def upcoming_events(sub: Subscription, med: MedicineDetail | None, today: date) -> list[Event]:
    sid = sub.id or 0
    events: list[Event] = []
    if sub.kind == Kind.refill and med:
        if out := run_out_date(med, today):
            events.append(Event("refill", out - timedelta(days=med.refill_lead_days), sid, f"Refill {sub.name}"))
        if med.script_expiry:
            events.append(Event("script_expiry", med.script_expiry, sid, f"Prescription for {sub.name} expires"))
    else:
        if nd := notice_deadline(sub):
            events.append(Event("notice_deadline", nd, sid, f"Last day to give notice for {sub.name}"))
        if sub.kind == Kind.contract and sub.contract_end:
            events.append(Event("contract_end", sub.contract_end, sid, f"{sub.name} contract ends"))
        if sub.next_renewal and sub.kind != Kind.contract:
            events.append(Event("renewal", roll_forward(sub.next_renewal, sub.cycle, sub.cycle_days, today), sid, f"{sub.name} renews"))
    return sorted(events, key=lambda e: e.date)


def next_event(sub: Subscription, med: MedicineDetail | None, today: date) -> Event | None:
    return next((e for e in upcoming_events(sub, med, today) if e.date >= today), None)
