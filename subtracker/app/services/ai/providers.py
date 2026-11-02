"""Concrete AI backends. Each turns an AIRequest into plain text; `get_provider` picks one from the add-on options."""
import base64
import json

import anthropic
import httpx
import openai

from ...config import Options
from ..ha import HAClient, ha as default_ha
from .base import AIError, AIProvider, AIRequest


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode()


class AnthropicProvider:
    name = "anthropic"
    supports_web_search = True
    supports_attachments = True

    def __init__(self, api_key: str, model: str, client: anthropic.AsyncAnthropic | None = None):
        self.client = client or anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def complete(self, req: AIRequest) -> str:
        content: list[dict] = [
            {"type": "document" if a.media_type == "application/pdf" else "image",
             "source": {"type": "base64", "media_type": a.media_type, "data": _b64(a.data)}}
            for a in req.attachments
        ]
        content.append({"type": "text", "text": req.prompt})
        messages: list[dict] = [{"role": "user", "content": content}]
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}] if req.web_search else anthropic.omit
        for _ in range(5):  # web search may pause a long turn; send it back to let the model continue
            try:
                resp = await self.client.beta.messages.create(
                    model=self.model, max_tokens=16000, system=req.system or anthropic.omit, messages=messages,
                    tools=tools, output_config={"effort": "medium"},
                    # a refusal is retried on a fallback model server-side instead of failing the search
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                )
            except anthropic.AuthenticationError as e:
                raise AIError("Anthropic rejected the API key") from e
            except anthropic.RateLimitError as e:
                raise AIError("Anthropic rate limit reached; try again later") from e
            except anthropic.APIStatusError as e:
                raise AIError(f"Anthropic API error {e.status_code}: {e.message}") from e
            except anthropic.APIConnectionError as e:
                raise AIError("Cannot reach the Anthropic API") from e
            if resp.stop_reason == "refusal":
                raise AIError("The model declined this request")
            if resp.stop_reason != "pause_turn":
                return "".join(b.text for b in resp.content if b.type == "text")
            messages.append({"role": "assistant", "content": resp.content})
        raise AIError("Anthropic web search did not finish")


class OpenAIProvider:
    name = "openai"
    supports_web_search = True
    supports_attachments = True

    def __init__(self, api_key: str, model: str, client: openai.AsyncOpenAI | None = None):
        self.client = client or openai.AsyncOpenAI(api_key=api_key)
        self.model = model

    async def complete(self, req: AIRequest) -> str:
        parts: list[dict] = []
        for a in req.attachments:
            url = f"data:{a.media_type};base64,{_b64(a.data)}"
            parts.append({"type": "input_file", "filename": a.filename, "file_data": url}
                         if a.media_type == "application/pdf" else {"type": "input_image", "image_url": url})
        parts.append({"type": "input_text", "text": req.prompt})
        try:
            resp = await self.client.responses.create(
                model=self.model, instructions=req.system or None, input=[{"role": "user", "content": parts}],
                tools=[{"type": "web_search"}] if req.web_search else [],
            )
        except openai.AuthenticationError as e:
            raise AIError("OpenAI rejected the API key") from e
        except openai.OpenAIError as e:
            raise AIError(f"OpenAI error: {e}") from e
        return resp.output_text


class OllamaProvider:
    """Local models. No web search: callers give it page text from catalog pricing URLs instead."""
    name = "ollama"
    supports_web_search = False
    supports_attachments = False

    def __init__(self, url: str, model: str, transport: httpx.AsyncBaseTransport | None = None):
        self.url, self.model, self.transport = url.rstrip("/"), model, transport

    async def complete(self, req: AIRequest) -> str:
        messages = ([{"role": "system", "content": req.system}] if req.system else []) + [{"role": "user", "content": req.prompt}]
        try:
            async with httpx.AsyncClient(timeout=300, transport=self.transport) as c:
                r = await c.post(f"{self.url}/api/chat", json={"model": self.model, "messages": messages, "stream": False})
                r.raise_for_status()
                return r.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise AIError(f"Ollama error: {e}") from e


class HAAITaskProvider:
    """The AI agent configured in Home Assistant (ai_task.generate_data). Web access depends on that agent."""
    name = "ha_ai_task"
    supports_web_search = True
    supports_attachments = False

    def __init__(self, entity_id: str, ha: HAClient = default_ha):
        self.entity_id, self.ha = entity_id, ha

    async def complete(self, req: AIRequest) -> str:
        if not self.ha.live:
            raise AIError("Home Assistant AI Task only works when SubTracker runs inside Home Assistant")
        data = {"task_name": "subtracker", "instructions": f"{req.system}\n\n{req.prompt}".strip()}
        if self.entity_id:
            data["entity_id"] = self.entity_id
        try:
            res = await self.ha.call_service("ai_task.generate_data", data, return_response=True)
        except httpx.HTTPError as e:
            raise AIError(f"Home Assistant AI Task error: {e}") from e
        out = ((res or {}).get("service_response") or {}).get("data", "")
        return out if isinstance(out, str) else json.dumps(out)


def get_provider(opts: Options) -> AIProvider | None:
    """The configured backend, or None when AI is off or not set up."""
    match opts.ai_provider:
        case "anthropic" if opts.anthropic_api_key:
            return AnthropicProvider(opts.anthropic_api_key, opts.anthropic_model)
        case "openai" if opts.openai_api_key:
            return OpenAIProvider(opts.openai_api_key, opts.openai_model)
        case "ollama" if opts.ollama_url:
            return OllamaProvider(opts.ollama_url, opts.ollama_model)
        case "ha_ai_task":
            return HAAITaskProvider(opts.ha_ai_task_entity)
    return None
