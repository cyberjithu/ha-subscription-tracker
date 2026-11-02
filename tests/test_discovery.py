import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from app.api import suggestions as sugg_api
from app.config import CATALOG_DIR
from app.models import Category, Country, InboxItem, Provider, Role, Suggestion, UserProfile
from app.services import catalog
from app.services.ai.base import AIError
from app.services.discovery import discover, due_countries, run_discovery, slugify

from .conftest import as_user
from .test_ai import FakeAI


def answer(*providers) -> str:
    return "```json\n" + json.dumps({"providers": list(providers)}) + "\n```"


SIRO = {"name": "SIRO Fibre Retail", "category": "broadband", "url": "https://siro.ie", "source_urls": ["https://siro.ie", "http://x"]}


@pytest.fixture
def ie(session):
    catalog.apply(session, catalog.parse((CATALOG_DIR / "ie.yaml").read_text()), bundled=True)
    session.add_all([UserProfile(id="admin", role=Role.admin, push_service="notify.mobile_app_admin"),
                     UserProfile(id="member", push_service="notify.mobile_app_member")])
    session.commit()
    return session.get(Country, "IE")


def count_providers(session):
    return len(session.exec(select(Provider)).all())


async def test_discover_stores_only_new_pending_suggestions(session, ie):
    before = count_providers(session)
    ai = FakeAI(answer(
        SIRO,
        {"name": "eir", "category": "broadband"},  # already in the catalog
        {"name": "SIRO Fibre Retail", "category": "broadband"},  # duplicate in the same answer
        {"name": "Moved Elsewhere", "category": "bins", "url": "javascript:alert(1)"},  # AI may not move categories
    ))
    created = await discover(session, ai, ie, session.get(Category, "broadband"))
    assert [s.slug for s in created] == ["siro-fibre-retail", "moved-elsewhere"]
    assert all(s.status == "pending" and s.category == "broadband" for s in created)
    assert created[0].source_urls == ["https://siro.ie"] and created[1].payload["url"] is None
    assert count_providers(session) == before  # nothing reaches the catalog without an accept
    assert "eir" in ai.requests[0].prompt and ai.requests[0].web_search


async def test_rejected_and_hidden_are_never_resuggested(session, ie):
    await discover(session, FakeAI(answer(SIRO)), ie, session.get(Category, "broadband"))
    s = session.exec(select(Suggestion)).one()
    s.status = "rejected"
    sky = session.exec(select(Provider).where(Provider.slug == "sky", Provider.category == "broadband")).one()
    sky.hidden = True
    session.commit()
    again = await discover(session, FakeAI(answer(SIRO, {"name": "Sky", "category": "broadband"})), ie,
                           session.get(Category, "broadband"))
    assert again == []


async def test_run_discovery_continues_after_errors_and_notifies_admins(session, ie, fake_ha):
    answers = iter([answer(SIRO)])

    class Flaky(FakeAI):
        async def complete(self, req):
            try:
                return next(answers)
            except StopIteration:
                raise AIError("rate limited") from None
    out = await run_discovery(session, Flaky(), ["IE", "XX"], categories=["broadband", "bins", "medicine"], ha=fake_ha)
    assert out["found"] == 1
    assert sum("rate limited" in e for e in out["errors"]) == 1 and any(e.startswith("XX") for e in out["errors"])
    assert not any("medicine" in e for e in out["errors"])  # medicines are never sent to AI
    assert [c[1] for c in fake_ha.of("notify")] == ["notify.mobile_app_admin"]
    assert session.exec(select(InboxItem.user_id)).all() == ["admin"]
    assert "last_discovery" in session.get(Country, "IE").settings


def test_due_countries(session, ie):
    now = datetime(2026, 11, 2, tzinfo=UTC)
    assert due_countries(session, ["IE", "XX"], 30, now) == ["IE"]
    ie.settings = {**ie.settings, "last_discovery": (now - timedelta(days=10)).isoformat()}
    session.commit()
    assert due_countries(session, ["IE"], 30, now) == []
    assert due_countries(session, ["IE"], 7, now) == ["IE"]
    assert due_countries(session, ["IE"], 0, now) == []  # switched off


def test_slugify():
    assert slugify("Bord Gáis Energy") == "bord-gais-energy" and slugify("Disney+") == "disney"


# --- API ---

@pytest.fixture
def api(client, ie, session):
    session.add(Suggestion(country="IE", category="broadband", slug="siro-fibre-retail",
                           payload={**SIRO, "notice_days": 30, "contract_lengths": [12], "source_urls": []}))
    session.add(Suggestion(country="IE", category="broadband", slug="eir", payload={"name": "eir", "category": "broadband"}))
    session.commit()
    return client


ADMIN, MEMBER = as_user("admin"), as_user("member")


def test_member_cannot_review(api):
    assert api.get("/api/suggestions", headers=MEMBER).status_code == 403
    assert api.post("/api/suggestions/1/accept", headers=MEMBER).status_code == 403


def test_edit_then_accept_creates_provider(api, session):
    pending = api.get("/api/suggestions", headers=ADMIN).json()
    siro = next(s for s in pending if s["slug"] == "siro-fibre-retail")
    body = {**siro["payload"], "coverage": "Towns on the SIRO network"}
    assert api.put(f"/api/suggestions/{siro['id']}", json=body, headers=ADMIN).json()["payload"]["coverage"] == "Towns on the SIRO network"
    p = api.post(f"/api/suggestions/{siro['id']}/accept", headers=ADMIN).json()
    assert p["source"] == "ai-accepted" and p["switching"]["notice_days"] == 30 and p["coverage"] == "Towns on the SIRO network"
    assert api.post(f"/api/suggestions/{siro['id']}/accept", headers=ADMIN).status_code == 409  # already accepted
    assert session.get(Suggestion, siro["id"]).decided_by == "admin"


def test_accept_existing_provider_conflicts_and_reject(api):
    eir = next(s for s in api.get("/api/suggestions", headers=ADMIN).json() if s["slug"] == "eir")
    assert api.post(f"/api/suggestions/{eir['id']}/accept", headers=ADMIN).status_code == 409
    assert api.post(f"/api/suggestions/{eir['id']}/reject", headers=ADMIN).json()["status"] == "rejected"
    assert eir["id"] not in [s["id"] for s in api.get("/api/suggestions", headers=ADMIN).json()]
    assert eir["id"] in [s["id"] for s in api.get("/api/suggestions?status=rejected", headers=ADMIN).json()]


def test_discover_endpoint(api, monkeypatch):
    url = "/api/suggestions/discover"
    monkeypatch.setattr(sugg_api, "get_provider", lambda opts: None)
    assert api.post(url, json={"country": "IE", "category": "bins"}, headers=ADMIN).status_code == 400
    monkeypatch.setattr(sugg_api, "get_provider", lambda opts: FakeAI(answer({"name": "Local Bins Co", "category": "bins"})))
    assert api.post(url, json={"country": "IE", "category": "bins"}, headers=ADMIN).json() == {"found": 1}
    assert api.post(url, json={"country": "IE", "category": "medicine"}, headers=ADMIN).status_code == 422
    assert api.post(url, json={"country": "XX", "category": "bins"}, headers=ADMIN).status_code == 404
    monkeypatch.setattr(sugg_api, "get_provider", lambda opts: FakeAI("not json"))
    bad = api.post(url, json={"country": "IE", "category": "bins"}, headers=ADMIN)
    assert bad.status_code == 502 and "JSON" in bad.json()["detail"]
