import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlmodel import select

from app.api import deals as deals_api
from app.config import CATALOG_DIR
from app.models import Bill, DealSearch, Document, Kind, Provider, Role, Subscription, UserProfile
from app.services import catalog
from app.services.deals import build_prompt, fetch_pricing_pages, run_auto_deal_searches, run_deal_search

from .conftest import as_user
from .test_ai import FakeAI

TODAY = date(2026, 11, 2)


def offers(*items, summary="Switch to Sky.") -> str:
    return "```json\n" + json.dumps({"offers": list(items), "summary": summary}) + "\n```"


@pytest.fixture
def ie(session):
    catalog.apply(session, catalog.parse((CATALOG_DIR / "ie.yaml").read_text()), bundled=True)
    session.add_all([UserProfile(id="admin", role=Role.admin, push_service="notify.mobile_app_admin"),
                     UserProfile(id="bob", push_service="notify.mobile_app_bob")])
    session.commit()


def add(session, **kw) -> Subscription:
    sub = Subscription(**({"name": "eir Fibre", "category": "broadband", "kind": Kind.contract, "price": 60,
                           "contract_end": date(2026, 12, 20), "notice_days": 30} | kw))
    session.add(sub)
    session.commit()
    return sub


# --- privacy ---

def test_prompt_shares_nothing_personal_by_default(session, ie):
    sub = add(session, plan_name="500Mb", notes="account 12345, PIN 9876", account_url="https://my.eir.ie/acc/42",
              annual_usage=4200, usage_unit="kWh", location="D14 XY12", owner_user_id="bob")
    prompt = build_prompt(session, sub, TODAY)
    assert "60.00 EUR a month" in prompt and "500Mb" in prompt and "Sky" in prompt  # catalog shortlist
    for secret in ("12345", "9876", "my.eir.ie/acc", "4200", "D14", "bob"):
        assert secret not in prompt, secret


def test_prompt_includes_usage_and_location_only_when_allowed(session, ie):
    sub = add(session, category="electricity", kind=Kind.usage, ai_share_usage=True, annual_usage=4200,
              usage_unit="kWh", location="D14 XY12")
    session.add(Bill(subscription_id=sub.id, period_start=date(2026, 1, 1), period_end=date(2026, 6, 29), amount=600,
                     usage_value=1800, usage_unit="kWh"))
    session.commit()
    prompt = build_prompt(session, sub, TODAY)
    assert "4200 kWh" in prompt and "about 3650 kWh a year" in prompt and "D14" not in prompt
    sub.ai_share_location = True
    assert "D14 XY12" in build_prompt(session, sub, TODAY)


async def test_medicines_and_switched_off_never_sent(session, ie):
    ai = FakeAI()
    for sub in (add(session, kind=Kind.refill, category="medicine"), add(session, ai_enabled=False),
                add(session, category="medicine")):
        with pytest.raises(Exception, match="never sent|switched off|off for"):
            await run_deal_search(session, ai, sub, today=TODAY)
    assert ai.requests == []


# --- search ---

async def test_offers_ranked_with_savings(session, ie):
    sub = add(session)
    ai = FakeAI(offers(
        {"provider": "Vodafone", "price": 45, "estimated_annual_cost": 540, "source_url": "https://www.vodafone.ie/x"},
        {"provider": "Sky", "price": 35, "estimated_annual_cost": 420, "source_url": "http://sky.example"},
        {"provider": "Pure", "price": 40},
    ))
    s = await run_deal_search(session, ai, sub, today=TODAY)
    assert s.status == "done" and s.current_annual_cost == 720 and s.summary == "Switch to Sky."
    assert [o["provider"] for o in s.offers] == ["Sky", "Vodafone", "Pure"]
    assert s.offers[0]["estimated_annual_saving"] == 300 and s.offers[0]["source_url"] is None
    assert "PIN" not in s.prompt


async def test_ai_failure_is_stored_not_raised(session, ie):
    s = await run_deal_search(session, FakeAI("sorry, no idea"), add(session), today=TODAY)
    assert s.status == "error" and "JSON" in s.error


async def test_no_web_search_reads_pricing_pages(session, ie):
    seen = []

    def handler(req: httpx.Request):
        seen.append(str(req.url))
        return httpx.Response(200, text="<html><script>x()</script><p>Fibre 500 for €39.99</p></html>")
    text = await fetch_pricing_pages(session, add(session), transport=httpx.MockTransport(handler))
    assert len(seen) == 5 and "Fibre 500 for €39.99" in text and "x()" not in text


# --- automatic trigger ---

async def test_auto_search_fires_once_per_decision_window(session, ie, fake_ha):
    sub = add(session)  # notice deadline 2026-11-20
    other = add(session, name="Far away", contract_end=date(2027, 12, 1))
    ai = FakeAI(offers({"provider": "Sky", "price": 35, "estimated_annual_cost": 420}), offers())
    assert await run_auto_deal_searches(session, ai, 45, TODAY, ha=fake_ha) == 1
    assert await run_auto_deal_searches(session, ai, 45, TODAY + timedelta(days=3), ha=fake_ha) == 0
    assert [s.subscription_id for s in session.exec(select(DealSearch))] == [sub.id]
    assert other.id not in [s.subscription_id for s in session.exec(select(DealSearch))]
    notes = fake_ha.of("notify")
    assert len(notes) == 2 and "saves about 300 EUR a year" in notes[0][3]  # shared sub: everyone hears


async def test_auto_search_skips_ineligible_and_respects_gap(session, ie, fake_ha):
    add(session, kind=Kind.refill, category="medicine", next_renewal=TODAY + timedelta(days=5))
    netflix = add(session, name="Netflix", category="streaming", kind=Kind.fixed, price=18, contract_end=None,
                  notice_days=None, next_renewal=TODAY + timedelta(days=10))
    session.add(DealSearch(subscription_id=netflix.id, trigger="auto", ran_at=datetime.now(UTC) - timedelta(days=40)))
    session.commit()
    ai = FakeAI()
    assert await run_auto_deal_searches(session, ai, 45, TODAY, ha=fake_ha) == 0  # medicine skipped, Netflix searched 40 days ago
    assert ai.requests == []


# --- API ---

@pytest.fixture
def api(client, session, ie):
    return client


ADMIN, BOB = as_user("admin"), as_user("bob")


def test_preview_and_search_api(api, session, monkeypatch):
    sub = add(session, notes="secret note")
    monkeypatch.setattr(deals_api, "get_provider", lambda opts: FakeAI(offers({"provider": "Sky", "price": 35, "estimated_annual_cost": 420})))
    pv = api.get(f"/api/subscriptions/{sub.id}/deal-preview", headers=BOB).json()
    assert pv["eligible"] and pv["provider"] == "fake" and "secret" not in pv["prompt"]
    r = api.post(f"/api/subscriptions/{sub.id}/deals", headers=BOB).json()
    assert r["offers"][0]["provider"] == "Sky"
    assert len(api.get(f"/api/subscriptions/{sub.id}/deals", headers=BOB).json()) == 1
    rows = api.get("/api/deals", headers=BOB).json()
    assert rows[0]["search"]["offers"][0]["provider"] == "Sky" and rows[0]["decide_by"] == "2026-11-20"
    med = add(session, kind=Kind.refill, category="medicine")
    assert api.post(f"/api/subscriptions/{med.id}/deals", headers=BOB).status_code == 422
    assert med.id not in [r["subscription_id"] for r in api.get("/api/deals", headers=BOB).json()]
    mine = add(session, owner_user_id="admin")
    assert api.get(f"/api/subscriptions/{mine.id}/deal-preview", headers=BOB).status_code == 404


def test_bill_extract(api, session, monkeypatch, tmp_path):
    sub = add(session, kind=Kind.usage, category="electricity")
    pdf = tmp_path / "bill.pdf"
    pdf.write_bytes(b"%PDF-1.4 bill")
    doc = Document(subscription_id=sub.id, filename="bill.pdf", path=str(pdf), content_type="application/pdf")
    heic = Document(subscription_id=sub.id, filename="b.heic", path=str(pdf), content_type="image/heic")
    session.add_all([doc, heic])
    session.commit()
    url = f"/api/subscriptions/{sub.id}/documents/{doc.id}/extract"
    reader = FakeAI('{"provider": "Electric Ireland", "period_start": "2026-09-01", "period_end": "2026-10-31", "amount": 131.75, "usage_value": 1310, "usage_unit": "kWh"}')
    reader.supports_attachments = True
    monkeypatch.setattr(deals_api, "get_provider", lambda opts: reader)
    out = api.post(url, headers=BOB).json()
    assert out["amount"] == 131.75 and out["period_end"] == "2026-10-31"
    assert reader.requests[0].attachments[0].data == b"%PDF-1.4 bill"
    assert session.exec(select(Bill)).all() == []  # nothing saved: the user confirms in the form
    assert api.post(f"/api/subscriptions/{sub.id}/documents/{heic.id}/extract", headers=BOB).status_code == 415
    monkeypatch.setattr(deals_api, "get_provider", lambda opts: FakeAI())  # no attachment support
    assert api.post(url, headers=BOB).status_code == 400


def test_delete_subscription_removes_deal_searches(api, session):
    sub = add(session)
    session.add(DealSearch(subscription_id=sub.id))
    session.commit()
    assert api.delete(f"/api/subscriptions/{sub.id}", headers=BOB).status_code == 204
    assert session.exec(select(DealSearch)).all() == []
    assert session.exec(select(Provider)).first() is not None
