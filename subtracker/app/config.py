"""Add-on options. Supervisor writes /data/options.json; env vars override for local dev."""
import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

DATA_DIR = Path(os.environ.get("SUBTRACKER_DATA", "./.data"))
APP_DIR = Path(__file__).parent
CATALOG_DIR = APP_DIR.parent / "catalogs"


class Options(BaseModel):
    ai_provider: str = "none"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-5"
    ollama_url: str = ""
    ollama_model: str = "llama3.1"
    ha_ai_task_entity: str = ""
    discovery_interval_days: int = 30
    deal_search_lead_days: int = 45
    resend_api_key: str = ""
    resend_from: str = ""
    email_notify_service: str = ""
    install_lovelace_card: bool = True


@lru_cache
def get_options() -> Options:
    path = DATA_DIR / "options.json"
    raw = json.loads(path.read_text()) if path.exists() else {}
    for key in Options.model_fields:
        if (env := os.environ.get(f"SUBTRACKER_{key.upper()}")) is not None:
            raw[key] = env
    return Options(**raw)
