import pytest
from fastapi.testclient import TestClient

from app.api import subscriptions as subs_api
from app.models import Role, UserProfile

from .conftest import as_user

ADMIN, ALICE, BOB, VIEWER = as_user("admin"), as_user("alice"), as_user("bob"), as_user("viewer")


@pytest.fixture
def api(client: TestClient, session, tmp_path, monkeypatch):
    monkeypatch.setattr(subs_api, "DOCS_DIR", tmp_path)
    session.add_all([UserProfile(id="admin", role=Role.admin), UserProfile(id="alice"), UserProfile(id="bob"),
                     UserProfile(id="viewer", role=Role.viewer)])
    session.commit()
    return client


def create(api, headers=ALICE, **kw):
    body = {"name": "Netflix", "category": "streaming", "price": 17.99, "start_date": "2026-01-01",
            "next_renewal": "2026-01-15"} | kw
    r = api.post("/api/subscriptions", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_each_kind(api):
    fixed = create(api)
    assert fixed["monthly_cost"] == 17.99 and fixed["next_event"]["kind"] == "renewal"
    contract = create(api, name="eir", category="broadband", kind="contract", price=60,
                      contract_end="2027-03-01", notice_days=30)
    assert contract["notice_deadline"] == "2027-01-30"
    usage = create(api, name="Electric Ireland", category="electricity", kind="usage", price=0, cycle="month")
    assert usage["kind"] == "usage"
    refill = create(api, name="Metformin", category="medicine", kind="refill", price=0)
    assert api.get(f"/api/subscriptions/{refill['id']}/medicine", headers=ALICE).status_code == 200


def test_visibility_shared_and_personal(api):
    shared = create(api)
    mine = create(api, name="Claude", category="software", personal=True)
    assert mine["owner_user_id"] == "alice"
    bob_ids = {s["id"] for s in api.get("/api/subscriptions", headers=BOB).json()}
    assert shared["id"] in bob_ids and mine["id"] not in bob_ids
    assert api.get(f"/api/subscriptions/{mine['id']}", headers=BOB).status_code == 404
    assert api.put(f"/api/subscriptions/{mine['id']}", json={"name": "x", "category": "x"}, headers=BOB).status_code == 404
    assert len(api.get("/api/subscriptions", headers=ADMIN).json()) == 2
    assert [s["id"] for s in api.get("/api/subscriptions?scope=mine", headers=ALICE).json()] == [mine["id"]]
    assert [s["id"] for s in api.get("/api/subscriptions?scope=shared", headers=ALICE).json()] == [shared["id"]]


def test_viewer_read_only(api):
    s = create(api)
    assert api.get("/api/subscriptions", headers=VIEWER).status_code == 200
    assert api.post("/api/subscriptions", json={"name": "x", "category": "x"}, headers=VIEWER).status_code == 403
    assert api.delete(f"/api/subscriptions/{s['id']}", headers=VIEWER).status_code == 403


def test_price_change_history(api):
    s = create(api)
    body = {k: v for k, v in s.items() if k not in ("id", "owner_user_id", "monthly_cost", "notice_deadline", "next_event")}
    api.put(f"/api/subscriptions/{s['id']}", json=body | {"price": 19.99}, headers=ALICE)
    api.put(f"/api/subscriptions/{s['id']}", json=body | {"price": 19.99, "notes": "same price"}, headers=ALICE)
    prices = [p["price"] for p in api.get(f"/api/subscriptions/{s['id']}/prices", headers=ALICE).json()]
    assert prices == [17.99, 19.99]


def test_copy_to_mine_and_make_shared(api):
    shared = create(api)
    copy = api.post(f"/api/subscriptions/{shared['id']}/copy-to-mine", headers=BOB).json()
    assert copy["owner_user_id"] == "bob" and copy["id"] != shared["id"]
    back = api.post(f"/api/subscriptions/{copy['id']}/make-shared", headers=BOB).json()
    assert back["owner_user_id"] is None


def test_bills_drive_usage_cost(api):
    s = create(api, name="Bord Gais", category="gas", kind="usage", price=0)
    url = f"/api/subscriptions/{s['id']}/bills"
    api.post(url, json={"period_start": "2026-01-01", "period_end": "2026-02-28", "amount": 200}, headers=ALICE)
    assert api.post(url, json={"period_start": "2026-03-01", "period_end": "2026-02-01", "amount": 1},
                    headers=ALICE).status_code == 422
    out = api.get(f"/api/subscriptions/{s['id']}", headers=ALICE).json()
    assert out["monthly_cost"] == round(200 / 59 * 365.25 / 12, 2)


def test_medicine_detail_and_refill_event(api):
    s = create(api, name="Statin", category="medicine", kind="refill", price=0)
    url = f"/api/subscriptions/{s['id']}/medicine"
    r = api.put(url, json={"qty_on_hand": 28, "daily_dose": 1, "pack_size": 28, "cost_per_fill": 20,
                           "refill_lead_days": 7, "script_expiry": "2027-01-01", "pharmacy": "Boots"}, headers=ALICE)
    assert r.status_code == 200 and r.json()["pharmacy"] == "Boots"
    out = api.get(f"/api/subscriptions/{s['id']}", headers=ALICE).json()
    assert out["next_event"]["kind"] == "refill" and out["monthly_cost"] == round(20 * 365.25 / 12 / 28, 2)
    fixed = create(api)
    assert api.get(f"/api/subscriptions/{fixed['id']}/medicine", headers=ALICE).status_code == 400


def test_documents_upload_limits(api):
    s = create(api)
    url = f"/api/subscriptions/{s['id']}/documents"
    ok = api.post(url, files={"file": ("bill.pdf", b"%PDF-1.4 test", "application/pdf")}, headers=ALICE)
    assert ok.status_code == 201
    assert api.get(f"{url}/{ok.json()['id']}", headers=ALICE).content == b"%PDF-1.4 test"
    assert api.post(url, files={"file": ("x.exe", b"MZ", "application/octet-stream")}, headers=ALICE).status_code == 415
    big = b"0" * (subs_api.MAX_UPLOAD + 1)
    assert api.post(url, files={"file": ("big.pdf", big, "application/pdf")}, headers=ALICE).status_code == 413
    assert api.delete(f"{url}/{ok.json()['id']}", headers=ALICE).status_code == 204
    assert api.get(url, headers=ALICE).json() == []


def test_delete_cascades(api):
    s = create(api, kind="usage")
    api.post(f"/api/subscriptions/{s['id']}/bills",
             json={"period_start": "2026-01-01", "period_end": "2026-01-31", "amount": 5}, headers=ALICE)
    assert api.delete(f"/api/subscriptions/{s['id']}", headers=ALICE).status_code == 204
    assert api.get(f"/api/subscriptions/{s['id']}", headers=ALICE).status_code == 404


def test_medicine_qty_change_resets_count_date(api):
    from datetime import date
    s = create(api, name="Statin", category="medicine", kind="refill", price=0)
    url = f"/api/subscriptions/{s['id']}/medicine"
    stale = {"qty_on_hand": 30, "daily_dose": 1, "qty_updated": "2026-01-01"}
    assert api.put(url, json=stale, headers=ALICE).json()["qty_updated"] == date.today().isoformat()
    same = api.put(url, json=stale | {"pharmacy": "Boots"}, headers=ALICE).json()
    assert same["qty_updated"] == "2026-01-01"  # count unchanged: caller's date kept


def test_input_validation(api):
    for bad in ({"price": -1}, {"notice_days": -5}, {"reminder_days": ["soon"]}, {"reminder_days": [400]},
                {"cycle": "custom", "cycle_days": 0}, {"name": ""}):
        r = api.post("/api/subscriptions", json={"name": "X", "category": "c"} | bad, headers=ALICE)
        assert r.status_code == 422, bad
    s = create(api, kind="usage")
    r = api.post(f"/api/subscriptions/{s['id']}/bills",
                 json={"period_start": "2026-01-01", "period_end": "2026-01-31", "amount": -3}, headers=ALICE)
    assert r.status_code == 422
    m = create(api, name="Med", category="medicine", kind="refill", price=0)
    assert api.put(f"/api/subscriptions/{m['id']}/medicine", json={"daily_dose": -1}, headers=ALICE).status_code == 422
