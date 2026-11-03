import pytest
from pydantic import ValidationError
from sqlmodel import select

from app.config import CATALOG_DIR
from app.models import Category, Country, Provider
from app.services import catalog

IE = (CATALOG_DIR / "ie.yaml").read_text()


def providers(session):
    return {(p.category, p.slug): p for p in session.exec(select(Provider))}


@pytest.mark.parametrize("path", sorted(CATALOG_DIR.glob("*.yaml")), ids=lambda p: p.name)
def test_bundled_catalog_is_valid(path):
    cat = catalog.parse(path.read_text())
    assert cat.country.code == path.stem.upper()
    keys = [(p.category, p.slug) for p in cat.providers]
    assert len(keys) == len(set(keys)), f"duplicate provider in {path.name}"
    assert {p.category for p in cat.providers} <= {c.slug for c in cat.categories}
    assert all(p.url.startswith("https://") and p.pricing_url.startswith("https://") for p in cat.providers)
    assert {"broadband", "mobile", "electricity", "gas", "streaming"} <= {p.category for p in cat.providers}
    medicine = next(c for c in cat.categories if c.slug == "medicine")
    assert medicine.ai_deals is False  # medicines are never sent to AI, in every country


def test_country_specifics():
    ie = catalog.parse(IE)
    assert ie.country.settings["dps_monthly_cap"] == 80
    de = catalog.parse((CATALOG_DIR / "de.yaml").read_text())
    assert "dps_monthly_cap" not in de.country.settings and "Zuzahlung" in de.country.settings["medicine_note"]
    fee = next(c for c in de.categories if c.slug == "broadcast-fee")
    assert fee.ai_deals is False


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


# --- household country ---

def test_household_country_default_and_choice(session):
    assert catalog.household_country(session) == "IE"  # nothing loaded yet: sensible default
    for f in ("de.yaml", "ie.yaml"):
        catalog.apply(session, catalog.parse((CATALOG_DIR / f).read_text()), bundled=True)
    assert catalog.household_country(session) == "IE"
    catalog.set_household_country(session, "DE")
    assert catalog.household_country(session) == "DE"


def test_choose_and_add_country_api(api, session):
    catalog.apply(session, catalog.parse((CATALOG_DIR / "de.yaml").read_text()), bundled=True)
    rows = {c["code"]: c for c in api.get("/api/catalog/countries", headers=MEMBER).json()}
    assert rows["DE"]["builtin"] and rows["DE"]["provider_count"] > 30 and rows["IE"]["builtin"]
    assert api.put("/api/settings/country", json={"code": "DE"}, headers=MEMBER).status_code == 403
    assert api.put("/api/settings/country", json={"code": "FR"}, headers=ADMIN).status_code == 404
    assert api.put("/api/settings/country", json={"code": "DE"}, headers=ADMIN).json() == {"country": "DE"}
    assert api.get("/api/settings", headers=MEMBER).json()["country"] == "DE"
    # a country with no bundled catalog: created empty, then selectable
    for bad in ({"code": "fr", "name": "France"}, {"code": "FR", "name": "F"}, {"code": "FR", "name": "France", "currency": "eur"}):
        assert api.post("/api/catalog/countries", json=bad, headers=ADMIN).status_code == 422, bad
    assert api.post("/api/catalog/countries", json={"code": "FR", "name": "France"}, headers=MEMBER).status_code == 403
    fr = api.post("/api/catalog/countries", json={"code": "FR", "name": "France"}, headers=ADMIN)
    assert fr.status_code == 201 and fr.json()["currency"] == "EUR"
    assert api.post("/api/catalog/countries", json={"code": "FR", "name": "France"}, headers=ADMIN).status_code == 409
    rows = {c["code"]: c for c in api.get("/api/catalog/countries", headers=MEMBER).json()}
    assert rows["FR"]["builtin"] is False and rows["FR"]["provider_count"] == 0
    assert api.put("/api/settings/country", json={"code": "FR"}, headers=ADMIN).status_code == 200
