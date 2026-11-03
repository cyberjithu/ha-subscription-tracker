"""AI settings changed in the app. They override the add-on options, so keys can be set without leaving the panel.

API keys are encrypted (Fernet) before they reach the database. The encryption key lives in its own file in /data,
readable only by the add-on, so a copied database or a shared screenshot of it gives nothing away. Keys are never
returned by the API: only whether one is set and its last four characters.
"""
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import Session

from ..config import DATA_DIR, Options, get_options
from ..models import AppSetting

log = logging.getLogger("subtracker.ai_settings")

KEY_FILE = DATA_DIR / ".secret.key"
PLAIN_FIELDS = ("ai_provider", "anthropic_model", "openai_model", "ollama_url", "ollama_model", "ha_ai_task_entity")
SECRET_FIELDS = ("anthropic_api_key", "openai_api_key")
PROVIDERS = ("none", "anthropic", "openai", "ollama", "ha_ai_task")


def _fernet() -> Fernet:
    if not KEY_FILE.exists():
        try:  # O_EXCL: two workers starting at once must not write different keys
            fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(Fernet.generate_key())
        except FileExistsError:
            pass
    return Fernet(KEY_FILE.read_bytes())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:  # key file replaced or data restored without it: treat as not set, never crash
        log.warning("A stored AI key could not be decrypted; set it again in Settings")
        return ""


def _stored(session: Session) -> dict:
    row = session.get(AppSetting, "ai")
    return dict(row.value) if row else {}


def effective_options(session: Session) -> Options:
    """Add-on options with anything set in the app on top."""
    stored = _stored(session)
    update = {k: stored[k] for k in PLAIN_FIELDS if stored.get(k) not in (None, "")}
    for k in SECRET_FIELDS:
        if token := stored.get(f"{k}_enc"):
            update[k] = decrypt(token)
    return get_options().model_copy(update=update)


def save(session: Session, plain: dict, secrets: dict[str, str | None]) -> None:
    """plain: values to store ("" clears back to the add-on option). secrets: None = keep, "" = remove, text = set."""
    stored = _stored(session)
    stored.update(plain)
    for k, v in secrets.items():
        if v is None:
            continue
        if v:
            stored[f"{k}_enc"] = encrypt(v)
        else:
            stored.pop(f"{k}_enc", None)
    row = session.get(AppSetting, "ai") or AppSetting(key="ai")
    row.value = stored
    session.add(row)
    session.commit()


def describe(session: Session) -> dict:
    """What the Settings page may see: plain values and, for keys, only set/where/last four characters."""
    stored, addon, eff = _stored(session), get_options(), effective_options(session)
    keys = {}
    for k in SECRET_FIELDS:
        value = getattr(eff, k)
        source = "app" if stored.get(f"{k}_enc") and value else "addon" if getattr(addon, k) else None
        keys[k] = {"set": bool(value), "source": source, "hint": f"…{value[-4:]}" if len(value) >= 8 else ""}
    return {**{k: getattr(eff, k) for k in PLAIN_FIELDS}, "keys": keys}
