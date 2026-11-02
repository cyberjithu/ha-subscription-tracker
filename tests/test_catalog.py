import pytest
from pydantic import ValidationError
from sqlmodel import select

from app.config import CATALOG_DIR
from app.models import Category, Country, Provider
from app.services import catalog

IE = (CATALOG_DIR / "ie.yaml").read_text()


def providers(session):
    return {(p.category, p.slug): p for p in session.exec(select(Provider))}


def test_bundled_ie_catalog_is_valid():
    cat = catalog.parse(IE)
    assert cat.country.code == "IE" and cat.country.settings["dps_monthly_cap"] == 80
    keys = [(p.category, p.slug) for p in cat.providers]
    assert len(keys) == len(set(keys)), "duplicate provider in ie.yaml"
    cats = {c.slug for c in cat.categories}
    assert {p.category for p in cat.providers} <= cats
    assert all(p.url.startswith("https://") and p.pricing_url.startswith("https://") for p in cat.providers)
    assert {"broadband", "electricity", "gas", "bins", "streaming"} <= {p.category for p in cat.providers}


def test_load_is_idempotent(session):
    first = catalog.apply(session, catalog.parse(IE), bundled=True)
    again = catalog.apply(session, catalog.parse(IE), bundled=True)
    assert first["added"] > 40 and again["added"] == 0
    assert len(providers(session)) == first["added"]
    assert session.get(Category, "medicine").ai_deals is False


def test_user_changes_survive_reload(session):
    catalog.apply(session, catalog.parse(IE), bundled=True)
    p = providers(session)
    p[("broadband", "eir")].name, p[("broadband", "eir")].source = "eir (my edit)", "edited"
    p[("bins", "panda")].hidden = True
    session.add(Provider(country="IE", category="bins", slug="local-bins", name="Local Bins", source="manual"))
    session.get(Country, "IE").settings = {**session.get(Country, "IE").settings, "dps_monthly_cap": 90}
    p[("broadband", "sky")].name = "stale bundled name"  # untouched bundled: refreshed from the file
    session.commit()
    counts = catalog.apply(session, catalog.parse(IE), bundled=True)
    p = providers(session)
    assert p[("broadband", "eir")].name == "eir (my edit)"
    assert p[("bins", "panda")].hidden is True
    assert ("bins", "local-bins") in p
    assert p[("broadband", "sky")].name == "Sky"
    assert session.get(Country, "IE").settings["dps_monthly_cap"] == 90
    assert counts["kept"] == 2


def test_import_wins_and_export_roundtrips(session):
    catalog.apply(session, catalog.parse(IE), bundled=True)
    p = providers(session)
    p[("bins", "panda")].hidden = True
    session.commit()
    exported = catalog.export(session, "IE")
    assert "panda" not in exported  # hidden providers are not exported
    cat = catalog.parse(exported)
    cat.providers[0].name = "Imported name"
    first = (cat.providers[0].category, cat.providers[0].slug)
    catalog.apply(session, catalog.parse(IE), bundled=False)  # re-import the bundled file: un-hides
    catalog.apply(session, cat, bundled=False)
    p = providers(session)
    assert p[("bins", "panda")].hidden is False
    assert p[first].name == "Imported name" and p[first].source == "edited"
    catalog.apply(session, catalog.parse(IE), bundled=True)  # next add-on start keeps the import
    assert providers(session)[first].name == "Imported name"


@pytest.mark.parametrize("bad", [
    "country: {code: ireland, name: X}",
    "country: {code: IE, name: X}\nproviders: [{slug: Bad Slug, name: X, category: bins}]",
    "country: {code: IE, name: X}\nproviders: [{slug: x, name: X, category: bins, url: 'http://insecure.ie'}]",
    "country: {code: IE, name: X}\nproviders: [{slug: x, name: X, category: bins, url: 'javascript:alert(1)'}]",
])
def test_invalid_catalog_rejected(bad):
    with pytest.raises(ValidationError):
        catalog.parse(bad)


# --- API ---

from app.models import Role, UserProfile  # noqa: E402

from .conftest import as_user  # noqa: E402

ADMIN, MEMBER = as_user("admin"), as_user("member")


@pytest.fixture
def api(client, session):
    session.add_all([UserProfile(id="admin", role=Role.admin), UserProfile(id="member")])
    catalog.apply(session, catalog.parse(IE), bundled=True)
    return client


def test_browse_and_filter(api):
    rows = api.get("/api/catalog/providers?country=IE&category=bins", headers=MEMBER).json()
    assert {r["slug"] for r in rows} >= {"panda", "greyhound"} and all(r["category"] == "bins" for r in rows)
    assert api.get("/api/catalog/countries", headers=MEMBER).json()[0]["settings"]["dps_monthly_cap"] == 80


def test_member_cannot_edit(api):
    pid = api.get("/api/catalog/providers?category=bins", headers=MEMBER).json()[0]["id"]
    assert api.delete(f"/api/catalog/providers/{pid}", headers=MEMBER).status_code == 403
    assert api.post("/api/catalog/import", content=IE, headers=MEMBER).status_code == 403


def test_admin_edit_hide_restore_add(api, session):
    panda = next(r for r in api.get("/api/catalog/providers?category=bins", headers=ADMIN).json() if r["slug"] == "panda")
    body = {k: panda[k] for k in ("category", "slug", "name", "url", "pricing_url", "plans", "switching", "coverage")}
    r = api.put(f"/api/catalog/providers/{panda['id']}", json=body | {"name": "Panda Recycling"}, headers=ADMIN)
    assert r.json()["source"] == "edited"
    assert api.put(f"/api/catalog/providers/{panda['id']}", json=body | {"url": "http://x.ie"}, headers=ADMIN).status_code == 422
    api.delete(f"/api/catalog/providers/{panda['id']}", headers=ADMIN)
    assert "panda" not in {r["slug"] for r in api.get("/api/catalog/providers?category=bins", headers=ADMIN).json()}
    assert api.post(f"/api/catalog/providers/{panda['id']}/restore", headers=ADMIN).json()["hidden"] is False
    new = {"country": "IE", "category": "bins", "slug": "local-bins", "name": "Local Bins", "url": "https://local.ie"}
    created = api.post("/api/catalog/providers", json=new, headers=ADMIN)
    assert created.status_code == 201 and created.json()["source"] == "manual"
    assert api.post("/api/catalog/providers", json=new, headers=ADMIN).status_code == 409
    assert api.delete(f"/api/catalog/providers/{created.json()['id']}", headers=ADMIN).status_code == 204
    assert session.get(Provider, created.json()["id"]) is None  # manual entries are really deleted


def test_export_import_api(api):
    exported = api.get("/api/catalog/export/IE", headers=MEMBER)
    assert exported.status_code == 200 and "ie.yaml" in exported.headers["content-disposition"]
    r = api.post("/api/catalog/import", content=exported.text, headers=ADMIN | {"content-type": "application/x-yaml"})
    assert r.status_code == 200 and r.json()["added"] == 0
    bad = api.post("/api/catalog/import", content="country: [", headers=ADMIN)
    assert bad.status_code == 422 and "YAML" in bad.json()["detail"]
    invalid = api.post("/api/catalog/import", content="country: {code: ie, name: x}", headers=ADMIN)
    assert invalid.status_code == 422 and "country.code" in invalid.json()["detail"]
    assert api.get("/api/catalog/export/XX", headers=MEMBER).status_code == 404


def test_country_settings_admin(api):
    assert api.put("/api/catalog/countries/IE", json={"settings": {"dps_monthly_cap": 90}}, headers=ADMIN).json()["settings"] == {"dps_monthly_cap": 90}
    assert api.put("/api/catalog/countries/IE", json={"settings": {"dps_monthly_cap": -1}}, headers=ADMIN).status_code == 422
    assert api.put("/api/catalog/countries/IE", json={"settings": {}}, headers=MEMBER).status_code == 403
