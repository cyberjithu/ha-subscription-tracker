"""Own profile, household user management (admin), add-on settings without secrets."""
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field as PField
from sqlmodel import Session, SQLModel, select

from ..auth import admin_only, current_user
from ..db import get_session
from ..models import Country, Role, UserPrefs, UserProfile
from ..services.ai.base import AIError, AIRequest, ask
from ..services import ai_settings
from ..services.ai.providers import get_provider
from ..services.ai_settings import effective_options
from ..services.ai.schemas import Ping
from ..services import catalog
from ..services.ha import ha

router = APIRouter(tags=["users"])
SECRET_FIELDS = {"anthropic_api_key", "openai_api_key", "resend_api_key"}


class Me(UserPrefs):
    id: str
    role: Role


class UserSummary(SQLModel):
    id: str
    display_name: str
    avatar_color: str
    role: Role


class CountryChoice(SQLModel):
    code: str


Model = Annotated[str, PField(max_length=100, pattern=r"^[A-Za-z0-9._:/-]*$")]
Key = Annotated[str, PField(max_length=400, pattern=r"^(\S{20,})?$")]  # "" removes; otherwise no spaces, 20+ chars


class AISettingsIn(SQLModel):
    """Only the fields sent are changed. Empty text clears an app value back to the add-on option."""
    ai_provider: Literal["none", "anthropic", "openai", "ollama", "ha_ai_task"] | None = None
    anthropic_model: Model | None = None
    openai_model: Model | None = None
    ollama_url: Annotated[str, PField(max_length=200, pattern=r"^(https?://\S+)?$")] | None = None
    ollama_model: Model | None = None
    ha_ai_task_entity: Annotated[str, PField(max_length=100, pattern=r"^(ai_task\.[a-z0-9_]+)?$")] | None = None
    anthropic_api_key: Key | None = None  # None = keep, "" = remove
    openai_api_key: Key | None = None


class RoleIn(SQLModel):
    role: Role


@router.get("/me", response_model=Me)
def get_me(user: UserProfile = Depends(current_user)):
    return user


@router.put("/me", response_model=Me)
def update_me(body: UserPrefs, user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    user.sqlmodel_update(body.model_dump())  # viewers may edit their own prefs too
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.get("/users", response_model=list[UserSummary])
def list_users(_: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    return session.exec(select(UserProfile).order_by(UserProfile.display_name)).all()


@router.put("/users/{user_id}/role", response_model=UserSummary)
def set_role(user_id: str, body: RoleIn, _: UserProfile = Depends(admin_only), session: Session = Depends(get_session)):
    target = session.get(UserProfile, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    admins = session.exec(select(UserProfile).where(UserProfile.role == Role.admin)).all()
    if target.role == Role.admin and body.role != Role.admin and len(admins) == 1:
        raise HTTPException(409, "Cannot remove the last admin")
    target.role = body.role
    session.commit()
    session.refresh(target)
    return target


@router.delete("/users/{user_id}", status_code=204)
def remove_user(user_id: str, me: UserProfile = Depends(admin_only), session: Session = Depends(get_session)):
    """Forget a profile. The HA user gets a fresh member profile on next visit; their personal items stay theirs."""
    if user_id == me.id:
        raise HTTPException(409, "You cannot remove yourself")
    target = session.get(UserProfile, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    session.delete(target)
    session.commit()


@router.get("/notify-services", response_model=list[str])
async def notify_services(_: UserProfile = Depends(current_user)):
    """HA notify.* services, for the push target picker."""
    services = await ha.get("/services") or []
    return sorted(f"notify.{name}" for d in services if d.get("domain") == "notify" for name in d.get("services", {}))


@router.get("/settings")
def settings(user: UserProfile = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    opts = effective_options(session)
    provider = get_provider(opts)
    ai_ready = provider is not None and (provider.name != "ha_ai_task" or ha.live)
    public = {"ai_provider": opts.ai_provider, "ai_ready": ai_ready, "country": catalog.household_country(session),
              "ha_connected": ha.live}
    if user.role != Role.admin:
        return public
    full = opts.model_dump(exclude=SECRET_FIELDS)
    full.update({f"{k}_set": bool(getattr(opts, k)) for k in SECRET_FIELDS})
    return public | {"options": full}


@router.post("/settings/test-ai")
async def test_ai(_: UserProfile = Depends(admin_only), session: Session = Depends(get_session)) -> dict:
    """One tiny round trip through the configured AI, to check keys and model names."""
    provider = get_provider(effective_options(session))
    if provider is None:
        return {"ok": False, "detail": "No AI provider is set up. Choose one and add its key above."}
    started = time.monotonic()
    try:
        await ask(provider, AIRequest('Connectivity check. Answer with ok=true and the name of the model you are.'), Ping)
    except AIError as e:
        return {"ok": False, "provider": provider.name, "detail": str(e)}
    return {"ok": True, "provider": provider.name, "detail": "Connected", "ms": round((time.monotonic() - started) * 1000)}


@router.put("/settings/country")
def choose_country(body: CountryChoice, _: UserProfile = Depends(admin_only), session: Session = Depends(get_session)) -> dict:
    """The household's country: default for new subscriptions, the catalog shown first, and where AI looks."""
    if not session.get(Country, body.code):
        raise HTTPException(404, "No catalog for this country yet. Add it as a custom country first.")
    catalog.set_household_country(session, body.code)
    return {"country": body.code}


@router.get("/settings/ai")
def get_ai_settings(_: UserProfile = Depends(admin_only), session: Session = Depends(get_session)) -> dict:
    return ai_settings.describe(session)


@router.put("/settings/ai")
def put_ai_settings(body: AISettingsIn, _: UserProfile = Depends(admin_only), session: Session = Depends(get_session)) -> dict:
    sent = body.model_dump(exclude_unset=True)
    plain = {k: v for k, v in sent.items() if k in ai_settings.PLAIN_FIELDS and v is not None}
    secrets = {k: sent.get(k) for k in ai_settings.SECRET_FIELDS}
    ai_settings.save(session, plain, secrets)
    return ai_settings.describe(session)
