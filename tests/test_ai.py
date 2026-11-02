from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.api import users as users_api
from app.config import Options
from app.models import Role, UserProfile
from app.services.ai.base import AIError, AIRequest, Attachment, ask, extract_json
from app.services.ai.providers import (AnthropicProvider, HAAITaskProvider, OllamaProvider, OpenAIProvider,
                                       get_provider)
from app.services.ai.schemas import DealOffer, DealOffers, Ping, ProviderSuggestions

from .conftest import as_user


class FakeAI:
    """Stands in for any backend: returns canned text and records requests."""
    name = "fake"
    supports_web_search = True
    supports_attachments = False

    def __init__(self, *answers: str):
        self.answers, self.requests = list(answers), []

    async def complete(self, req: AIRequest) -> str:
        self.requests.append(req)
        return self.answers.pop(0)


# --- JSON extraction and validation ---

def test_extract_json_variants():
    assert extract_json('Sure!\n```json\n{"ok": true}\n```\nThanks') == {"ok": True}
    assert extract_json('```json\n{"a": 1}\n```\n```json\n{"a": 2}\n```') == {"a": 2}  # last block wins
    assert extract_json('Result: {"ok": true, "model": "x"} done') == {"ok": True, "model": "x"}
    assert extract_json("[1, 2]") == [1, 2]
    with pytest.raises(AIError):
        extract_json("I could not find anything.")


async def test_ask_validates_and_sends_schema():
    ai = FakeAI('```json\n{"ok": true, "model": "m"}\n```')
    assert (await ask(ai, AIRequest("ping"), Ping)) == Ping(ok=True, model="m")
    assert '"ok"' in ai.requests[0].prompt  # schema is part of the prompt
    with pytest.raises(AIError, match="expected format"):
        await ask(FakeAI('{"model": 3}'), AIRequest("ping"), Ping)
    with pytest.raises(AIError, match="no readable JSON"):
        await ask(FakeAI("nope"), AIRequest("ping"), Ping)
    with pytest.raises(AIError, match="cannot read"):
        await ask(FakeAI(), AIRequest("bill", attachments=[Attachment(b"%PDF", "application/pdf")]), Ping)


def test_non_https_urls_dropped():
    s = ProviderSuggestions.model_validate({"providers": [{
        "name": "X", "category": "bins", "url": "http://x.ie", "pricing_url": "javascript:alert(1)",
        "source_urls": ["https://ok.ie/a", "ftp://no", "/relative", "https://has space.ie"],
    }]}).providers[0]
    assert s.url is None and s.pricing_url is None and s.clean_sources() == ["https://ok.ie/a"]
    offer = DealOffer(provider="eir", price=40, source_url="https://www.eir.ie/x")
    assert offer.source_url == "https://www.eir.ie/x"
    with pytest.raises(ValidationError):
        DealOffer(provider="eir", price=-1)
    with pytest.raises(ValidationError):
        DealOffers(offers=[{"provider": "x", "price": 1}] * 16)


# --- providers (SDKs/HTTP faked) ---

def _msg(stop, *texts):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=t) for t in texts])


async def test_anthropic_resumes_paused_turn_and_uses_web_search():
    calls = []
    replies = [_msg("pause_turn", "searching"), _msg("end_turn", '{"ok": ', "true}")]

    async def create(**kw):
        calls.append(kw)
        return replies.pop(0)
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    out = await AnthropicProvider("k", "claude-opus-5-5", client=client).complete(AIRequest("find deals", web_search=True))
    assert out == '{"ok": true}' and len(calls) == 2
    assert calls[0]["tools"][0]["type"] == "web_search_20260209" and calls[0]["fallbacks"] == "default"
    assert calls[1]["messages"][-1]["role"] == "assistant"  # paused content sent back


async def test_anthropic_refusal_is_an_error():
    async def create(**kw):
        return _msg("refusal")
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    with pytest.raises(AIError, match="declined"):
        await AnthropicProvider("k", "m", client=client).complete(AIRequest("x"))


async def test_openai_passes_web_search_and_attachments():
    seen = {}

    async def create(**kw):
        seen.update(kw)
        return SimpleNamespace(output_text="answer")
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    req = AIRequest("read bill", web_search=True, attachments=[Attachment(b"img", "image/png")])
    assert await OpenAIProvider("k", "gpt-5", client=client).complete(req) == "answer"
    assert seen["tools"] == [{"type": "web_search"}]
    assert seen["input"][0]["content"][0]["image_url"].startswith("data:image/png;base64,")


async def test_ollama_chat_and_errors():
    def ok(req: httpx.Request):
        assert req.url.path == "/api/chat"
        return httpx.Response(200, json={"message": {"content": "hi"}})
    assert await OllamaProvider("http://ollama:11434/", "llama", httpx.MockTransport(ok)).complete(AIRequest("x")) == "hi"
    down = httpx.MockTransport(lambda r: httpx.Response(500))
    with pytest.raises(AIError, match="Ollama"):
        await OllamaProvider("http://ollama", "llama", down).complete(AIRequest("x"))


async def test_ha_ai_task(fake_ha):
    async def call_service(service, data, return_response=False):
        fake_ha.calls.append((service, data, return_response))
        return {"changed_states": [], "service_response": {"data": '{"ok": true}'}}
    fake_ha.call_service, fake_ha.live = call_service, True
    out = await HAAITaskProvider("ai_task.openai", ha=fake_ha).complete(AIRequest("x", system="be brief"))
    assert out == '{"ok": true}'
    service, data, rr = fake_ha.calls[0]
    assert service == "ai_task.generate_data" and data["entity_id"] == "ai_task.openai" and rr is True
    fake_ha.live = False
    with pytest.raises(AIError, match="inside Home Assistant"):
        await HAAITaskProvider("", ha=fake_ha).complete(AIRequest("x"))


def test_get_provider_from_options():
    assert get_provider(Options()) is None
    assert get_provider(Options(ai_provider="anthropic")) is None  # no key
    assert get_provider(Options(ai_provider="anthropic", anthropic_api_key="k")).name == "anthropic"
    assert get_provider(Options(ai_provider="openai", openai_api_key="k")).name == "openai"
    assert get_provider(Options(ai_provider="ollama", ollama_url="http://o")).name == "ollama"
    assert get_provider(Options(ai_provider="ha_ai_task")).name == "ha_ai_task"


# --- test-connection endpoint ---

@pytest.fixture
def api(client, session):
    session.add_all([UserProfile(id="admin", role=Role.admin), UserProfile(id="member")])
    session.commit()
    return client


def test_test_ai_endpoint(api, monkeypatch):
    url, admin = "/api/settings/test-ai", as_user("admin")
    assert api.post(url, headers=as_user("member")).status_code == 403
    monkeypatch.setattr(users_api, "get_options", lambda: Options())
    assert api.post(url, headers=admin).json()["ok"] is False
    monkeypatch.setattr(users_api, "get_provider", lambda opts: FakeAI('{"ok": true, "model": "fake-1"}'))
    r = api.post(url, headers=admin).json()
    assert r["ok"] is True and r["provider"] == "fake"
    monkeypatch.setattr(users_api, "get_provider", lambda opts: FakeAI("rate limited, sorry"))
    r = api.post(url, headers=admin).json()
    assert r["ok"] is False and "JSON" in r["detail"]
