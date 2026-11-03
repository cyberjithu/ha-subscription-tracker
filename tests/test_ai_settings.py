import json
import stat

import pytest

from app.config import Options
from app.models import AppSetting, Role, UserProfile
from app.services import ai_settings
from app.services.ai.providers import get_provider

from .conftest import as_user

KEY = "sk-ant-api03-" + "A" * 40 + "wxyz"
OPENAI = "sk-proj-" + "B" * 40 + "1234"
ADMIN, MEMBER = as_user("admin"), as_user("member")


@pytest.fixture
def api(client, session, tmp_path, monkeypatch):
    monkeypatch.setattr(ai_settings, "KEY_FILE", tmp_path / ".secret.key")
    monkeypatch.setattr(ai_settings, "get_options", lambda: Options())
    session.add_all([UserProfile(id="admin", role=Role.admin), UserProfile(id="member")])
    session.commit()
    return client


def test_encryption_roundtrip_and_key_file_private(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_settings, "KEY_FILE", tmp_path / ".secret.key")
    token = ai_settings.encrypt(KEY)
    assert KEY not in token and ai_settings.decrypt(token) == KEY
    assert stat.S_IMODE((tmp_path / ".secret.key").stat().st_mode) == 0o600
    (tmp_path / ".secret.key").unlink()  # key lost (e.g. restored database without it)
    assert ai_settings.decrypt(token) == ""  # treated as not set, no crash


def test_set_key_never_stored_or_returned_in_plain_text(api, session):
    r = api.put("/api/settings/ai", json={"ai_provider": "anthropic", "anthropic_api_key": KEY}, headers=ADMIN)
    assert r.status_code == 200 and KEY not in r.text
    assert r.json()["keys"]["anthropic_api_key"] == {"set": True, "source": "app", "hint": "…wxyz"}
    stored = json.dumps(session.get(AppSetting, "ai").value)
    assert KEY not in stored and "anthropic_api_key_enc" in stored
    for path in ("/api/settings/ai", "/api/settings"):
        assert KEY not in api.get(path, headers=ADMIN).text
    provider = get_provider(ai_settings.effective_options(session))
    assert provider.name == "anthropic"  # the app value is what the AI code uses


def test_keep_replace_remove_semantics(api, session):
    api.put("/api/settings/ai", json={"ai_provider": "openai", "openai_api_key": OPENAI, "openai_model": "gpt-5-mini"}, headers=ADMIN)
    r = api.put("/api/settings/ai", json={"openai_model": "gpt-5"}, headers=ADMIN).json()  # key omitted: kept
    assert r["keys"]["openai_api_key"]["set"] and r["openai_model"] == "gpt-5"
    r = api.put("/api/settings/ai", json={"openai_api_key": ""}, headers=ADMIN).json()  # "" removes
    assert r["keys"]["openai_api_key"] == {"set": False, "source": None, "hint": ""}
    assert get_provider(ai_settings.effective_options(session)) is None


def test_app_overrides_addon_option_and_clearing_falls_back(api, monkeypatch, session):
    monkeypatch.setattr(ai_settings, "get_options", lambda: Options(ai_provider="ollama", ollama_url="http://ollama:11434",
                                                                   anthropic_api_key="sk-ant-from-addon-" + "C" * 30))
    r = api.get("/api/settings/ai", headers=ADMIN).json()
    assert r["ai_provider"] == "ollama" and r["keys"]["anthropic_api_key"]["source"] == "addon"
    api.put("/api/settings/ai", json={"ai_provider": "anthropic"}, headers=ADMIN)
    assert ai_settings.effective_options(session).ai_provider == "anthropic"
    api.put("/api/settings/ai", json={"ai_provider": "none"}, headers=ADMIN)
    assert get_provider(ai_settings.effective_options(session)) is None


@pytest.mark.parametrize("bad", [
    {"ai_provider": "gemini"}, {"anthropic_api_key": "short"}, {"anthropic_api_key": "has spaces " + "x" * 30},
    {"ollama_url": "ftp://x"}, {"ha_ai_task_entity": "light.kitchen"}, {"openai_model": "gpt 5; drop"},
])
def test_validation(api, bad):
    assert api.put("/api/settings/ai", json=bad, headers=ADMIN).status_code == 422


def test_admin_only(api):
    assert api.get("/api/settings/ai", headers=MEMBER).status_code == 403
    assert api.put("/api/settings/ai", json={"ai_provider": "none"}, headers=MEMBER).status_code == 403
