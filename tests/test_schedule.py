from datetime import date

from app.models import Bill, Cycle, Kind, MedicineDetail, Subscription
from app.services import schedule as s


def sub(**kw) -> Subscription:
    return Subscription(id=1, name="X", category="c", **kw)


def test_add_months_clamps_month_end_and_leap_year():
    assert s.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert s.add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert s.add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert s.add_cycle(date(2028, 2, 29), Cycle.year) == date(2029, 2, 28)


def test_roll_forward_keeps_anchor_day():
    # Jan 31 anchor: Feb 28, then back to Mar 31 (no drift to the 28th)
    assert s.roll_forward(date(2026, 1, 31), Cycle.month, None, date(2026, 3, 1)) == date(2026, 3, 31)
    assert s.roll_forward(date(2026, 1, 1), Cycle.week, None, date(2026, 1, 9)) == date(2026, 1, 15)
    assert s.roll_forward(date(2026, 1, 1), Cycle.custom, 10, date(2026, 1, 11)) == date(2026, 1, 11)
    assert s.roll_forward(date(2026, 6, 1), Cycle.month, None, date(2026, 1, 1)) == date(2026, 6, 1)


def test_notice_deadline():
    t = date(2026, 11, 1)
    c = sub(kind=Kind.contract, contract_end=date(2027, 3, 1), notice_days=30)
    assert s.notice_deadline(c, t) == date(2027, 1, 30)
    assert s.notice_deadline(sub(kind=Kind.contract, contract_end=date(2027, 3, 1)), t) is None
    f = sub(kind=Kind.fixed, next_renewal=date(2026, 12, 1), notice_days=1)
    assert s.notice_deadline(f, t) == date(2026, 11, 30)


def test_notice_deadline_rolls_with_recurring_renewal():
    # anchor long past: deadline follows the next renewal, not the stale stored one
    f = sub(next_renewal=date(2026, 1, 15), notice_days=5)
    assert s.notice_deadline(f, date(2026, 11, 2)) == date(2026, 11, 10)
    # this cycle's deadline already passed (renewal in 3 days): next cycle's deadline
    assert s.notice_deadline(f, date(2026, 11, 12)) == date(2026, 12, 10)
    assert s.next_event(f, None, date(2026, 11, 2)).kind == "notice_deadline"


def test_refill_run_out():
    med = MedicineDetail(subscription_id=1, qty_on_hand=30, daily_dose=2, qty_updated=date(2026, 1, 1))
    assert s.medicine_remaining(med, date(2026, 1, 6)) == 20
    assert s.run_out_date(med, date(2026, 1, 6)) == date(2026, 1, 16)
    assert s.medicine_remaining(med, date(2026, 3, 1)) == 0
    assert s.run_out_date(MedicineDetail(subscription_id=1, daily_dose=0), date(2026, 1, 1)) is None


def test_monthly_cost():
    assert s.monthly_cost(sub(price=120, cycle=Cycle.year)) == 10
    assert round(s.monthly_cost(sub(price=12, cycle=Cycle.week)), 2) == 52.0
    bills = [Bill(subscription_id=1, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31), amount=62),
             Bill(subscription_id=1, period_start=date(2026, 2, 1), period_end=date(2026, 3, 2), amount=60)]
    assert round(s.monthly_cost(sub(kind=Kind.usage), bills), 4) == round(122 / 61 * 365.25 / 12, 4)
    med = MedicineDetail(subscription_id=1, daily_dose=1, pack_size=28, cost_per_fill=28)
    assert round(s.monthly_cost(sub(kind=Kind.refill), med=med), 4) == round(365.25 / 12, 4)


def test_events_order_and_kinds():
    c = sub(kind=Kind.contract, contract_end=date(2027, 3, 1), notice_days=30)
    evs = s.upcoming_events(c, None, date(2026, 11, 1))
    assert [e.kind for e in evs] == ["notice_deadline", "contract_end"]
    med = MedicineDetail(subscription_id=1, qty_on_hand=10, daily_dose=1, qty_updated=date(2026, 11, 1),
                         refill_lead_days=3, script_expiry=date(2027, 1, 1))
    evs = s.upcoming_events(sub(kind=Kind.refill), med, date(2026, 11, 1))
    assert [(e.kind, e.date) for e in evs] == [("refill", date(2026, 11, 8)), ("script_expiry", date(2027, 1, 1))]
    assert s.next_event(sub(kind=Kind.fixed), None, date(2026, 1, 1)) is None


def test_refill_inside_lead_window_reminds_today():
    med = MedicineDetail(subscription_id=1, qty_on_hand=3, daily_dose=1, refill_lead_days=7, qty_updated=date(2026, 11, 2))
    ev = s.next_event(sub(kind=Kind.refill), med, date(2026, 11, 2))
    assert (ev.kind, ev.date) == ("refill", date(2026, 11, 2))


def test_expired_contract_nags_weekly():
    c = sub(kind=Kind.contract, contract_end=date(2026, 10, 20), notice_days=30)
    assert s.next_event(c, None, date(2026, 10, 27)).date == date(2026, 10, 27)  # 7 days after: today
    ev = s.next_event(c, None, date(2026, 10, 28))
    assert (ev.kind, ev.date) == ("contract_expired", date(2026, 11, 3))
