"""One interface over every AI backend. Providers return raw text; `ask` extracts and validates JSON.

AI output is untrusted: it only ever becomes data after it passes a Pydantic schema (see schemas.py),
and it is never written to the catalog directly (suggestions need an admin's accept).
"""
import json
import re
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


@dataclass
class Attachment:
    data: bytes
    media_type: str  # image/png, image/jpeg, image/webp, application/pdf
    filename: str = "file"


@dataclass
class AIRequest:
    prompt: str
    system: str = ""
    web_search: bool = False
    attachments: list[Attachment] = field(default_factory=list)


class AIError(Exception):
    """Anything that went wrong talking to or understanding the AI. Message is safe to show users."""


class AIProvider(Protocol):
    name: str
    supports_web_search: bool
    supports_attachments: bool

    async def complete(self, req: AIRequest) -> str: ...


def extract_json(text: str) -> object:
    """Last ```json fenced block, else the outermost {...} or [...] span."""
    candidates = list(reversed(re.findall(r"```(?:json)?\s*(.+?)```", text, re.S)))
    for open_, close in (("{", "}"), ("[", "]")):
        start, end = text.find(open_), text.rfind(close)
        if start != -1 and end > start:
            candidates.append(text[start:end + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise AIError("The AI answer contained no readable JSON")


async def ask(provider: AIProvider, req: AIRequest, model: type[T]) -> T:
    if req.attachments and not provider.supports_attachments:
        raise AIError(f"{provider.name} cannot read documents or images")
    schema = json.dumps(model.model_json_schema())
    prompt = f"{req.prompt}\n\nReply with one JSON object that matches this JSON Schema, in a ```json fenced block:\n{schema}"
    text = await provider.complete(AIRequest(prompt, req.system, req.web_search, req.attachments))
    try:
        return model.model_validate(extract_json(text))
    except ValidationError as e:
        raise AIError(f"The AI answer did not match the expected format ({e.error_count()} problem(s))") from e
