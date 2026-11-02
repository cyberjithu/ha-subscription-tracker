from datetime import date

from app.models import Bill, Cycle, DealSearch, Kind, MedicineDetail, PriceChange, Role, SubStatus, Subscription, UserProfile
from app.services import dashboard as d

from .conftest import as_user

TODAY = date(2026, 11, 2)


def test_month_starts_and_bill_proration():
    months = d.month_starts(TODAY)
    assert months[0] == date(2025, 12, 1) and months[-1] == date(2026, 11, 1) and len(months) == 12
    bill = Bill(subscription_id=1, period_start=date(2026, 1, 15), period_end=date(2026, 2, 14), amount=310)  # 31 days
    assert round(d.bill_spend_in_month([bill], date(2026, 1, 1)), 2) == 170.0  # 17 days in January
    assert round(d.bill_spend_in_month([bill], date(2026, 2, 1)), 2) == 140.0
    assert d.bill_spend_in_month([bill], date(2026, 3, 1)) == 0


def test_price_history_and_start_date_shape_the_trend():
    sub = Subscription(id=1, name="Netflix", category="streaming", price=20, start_date=date(2026, 3, 10))
    changes = [PriceChange(subscription_id=1, price=15, effective_date=date(2026, 3, 10)),
               PriceChange(subscription_id=1, price=20, effective_date=date(2026, 7, 1))]
    assert d.monthly_in(sub, date(2026, 2, 1), [], changes, None) == 0  # not started yet
    assert d.monthly_in(sub, date(2026, 3, 1), [], changes, None) == 15
    assert d.monthly_in(sub, date(2026, 7, 1), [], changes, None) == 20
    yearly = Subscription(id=2, name="Bins", category="bins", price=300, cycle=Cycle.year, start_date=date(2025, 1, 1))
    assert d.monthly_in(yearly, date(2026, 5, 1), [], [], None) == 25


def test_build_totals_owner_split_and_upcoming(session):
    session.add(UserProfile(id="alice", display_name="Alice"))
    subs = [
        Subscription(name="Netflix", category="streaming", price=18, start_date=date(2025, 1, 1), next_renewal=date(2026, 11, 9)),
        Subscription(name="Bins", category="bins", price=300, cycle=Cycle.year, start_date=date(2025, 1, 1), next_renewal=date(2027, 3, 1)),
        Subscription(name="Claude", category="software", price=18, start_date=date(2025, 1, 1), owner_user_id="alice"),
        Subscription(name="Old", category="streaming", price=99, status=SubStatus.cancelled),
        Subscription(name="Gas", category="gas", kind=Kind.usage, start_date=date(2025, 1, 1)),
        Subscription(name="Statin", category="medicine", kind=Kind.refill, start_date=date(2025, 1, 1)),
    ]
    session.add_all(subs)
    session.commit()
    session.add(Bill(subscription_id=subs[4].id, period_start=date(2026, 10, 1), period_end=date(2026, 10, 31), amount=93))
    session.add(MedicineDetail(subscription_id=subs[5].id, qty_on_hand=10, daily_dose=1, pack_size=28, cost_per_fill=28,
                               qty_updated=TODAY, refill_lead_days=3))
    session.commit()
    out = d.build(session, subs, {"alice": "Alice"}, TODAY)
    gas_monthly = 93 / 31 * 365.25 / 12
    med_monthly = 365.25 / 12
    assert out["active_count"] == 5
    assert out["monthly_total"] == round(18 + 25 + 18 + gas_monthly + med_monthly, 2)
    assert out["by_category"][0]["category"] in ("medicine", "gas")  # largest first
    assert {r["name"]: r["monthly"] for r in out["by_owner"]}["Alice"] == 18
    assert out["trend"][-2]["month"] == "2026-10" and round(out["trend"][-2]["total"], 2) == round(18 + 25 + 18 + 93 + med_monthly, 2)
    kinds = [(e["name"], e["kind"]) for e in out["upcoming"]]
    assert ("Netflix", "renewal") in kinds and ("Statin", "refill") in kinds and all(e["days"] <= 30 for e in out["upcoming"])
    assert "Bins" not in [e["name"] for e in out["upcoming"]]


def test_dashboard_api_visibility_and_savings(client, session):
    session.add_all([UserProfile(id="admin", role=Role.admin), UserProfile(id="bob")])
    shared = Subscription(name="eir", category="broadband", price=60)
    mine = Subscription(name="Private", category="health", price=40, owner_user_id="admin")
    session.add_all([shared, mine])
    session.commit()
    session.add(DealSearch(subscription_id=shared.id, offers=[{"estimated_annual_saving": 120}, {"estimated_annual_saving": 300}]))
    session.add(DealSearch(subscription_id=shared.id, status="error"))
    session.commit()
    bob = client.get("/api/dashboard", headers=as_user("bob")).json()
    assert bob["monthly_total"] == 60 and bob["possible_yearly_savings"] == 300
    assert client.get("/api/dashboard", headers=as_user("admin")).json()["monthly_total"] == 100
