import pytest

from app.api import users as users_api
from app.config import Options
from app.models import Role, UserProfile

from .conftest import as_user

ADMIN, MEMBER, VIEWER = as_user("admin"), as_user("m"), as_user("v")


@pytest.fixture
def api(client, session):
    session.add_all([UserProfile(id="admin", role=Role.admin), UserProfile(id="m"), UserProfile(id="v", role=Role.viewer)])
    session.commit()
    return client


def test_me_update_and_validation(api):
    me = api.get("/api/me", headers=MEMBER).json()
    assert me["role"] == "member"
    body = me | {"display_name": "M", "theme": "dark", "quiet_start": "22:00", "quiet_end": "07:00",
                 "push_service": "notify.mobile_app_m", "muted_categories": ["streaming"], "reminder_days": [10, 2]}
    r = api.put("/api/me", json=body, headers=MEMBER)
    assert r.status_code == 200 and r.json()["theme"] == "dark" and r.json()["reminder_days"] == [10, 2]
    assert r.json()["role"] == "member"  # role is not editable through /me
    assert api.put("/api/me", json=body | {"role": "admin"}, headers=MEMBER).json()["role"] == "member"
    for bad in ({"quiet_start": "7pm"}, {"theme": "pink"}, {"push_service": "light.kitchen"}, {"email": "x"}):
        assert api.put("/api/me", json=body | bad, headers=MEMBER).status_code == 422, bad
    assert api.put("/api/me", json=body, headers=VIEWER).status_code == 200  # viewers edit own prefs


def test_roles_admin_only_and_last_admin(api):
    assert api.put("/api/users/v/role", json={"role": "member"}, headers=MEMBER).status_code == 403
    assert api.put("/api/users/v/role", json={"role": "member"}, headers=ADMIN).json()["role"] == "member"
    assert api.put("/api/users/admin/role", json={"role": "member"}, headers=ADMIN).status_code == 409
    assert api.delete("/api/users/admin", headers=ADMIN).status_code == 409
    assert api.delete("/api/users/m", headers=MEMBER).status_code == 403
    assert api.delete("/api/users/m", headers=ADMIN).status_code == 204
    assert {u["id"] for u in api.get("/api/users", headers=ADMIN).json()} == {"admin", "v"}


def test_settings_never_returns_secrets(api, monkeypatch):
    opts = Options(ai_provider="anthropic", anthropic_api_key="sk-secret", resend_api_key="re-secret")
    monkeypatch.setattr(users_api, "get_options", lambda: opts)
    member = api.get("/api/settings", headers=MEMBER).json()
    assert member == {"ai_provider": "anthropic", "ai_ready": True, "countries": ["IE"], "ha_connected": False}
    admin = api.get("/api/settings", headers=ADMIN)
    assert "secret" not in admin.text
    assert admin.json()["options"]["anthropic_api_key_set"] is True
    assert admin.json()["options"]["openai_api_key_set"] is False


def test_notify_services_dry_run_empty(api):
    assert api.get("/api/notify-services", headers=MEMBER).json() == []


def test_notify_services_lists_notify_domain(api, monkeypatch):
    async def fake_get(path):
        return [{"domain": "light", "services": {"turn_on": {}}},
                {"domain": "notify", "services": {"mobile_app_pixel": {}, "email": {}}}]
    monkeypatch.setattr(users_api.ha, "get", fake_get)
    assert api.get("/api/notify-services", headers=MEMBER).json() == ["notify.email", "notify.mobile_app_pixel"]
