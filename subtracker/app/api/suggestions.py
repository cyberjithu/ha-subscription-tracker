"""Review queue for AI-proposed providers. Admin only: nothing reaches the catalog without an accept."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, SQLModel, select

from ..auth import admin_only
from ..db import engine, get_session
from ..models import Category, Country, Provider, Suggestion, SuggestionStatus, UserProfile
from ..services.ai.base import AIError
from ..services.ai.providers import get_provider
from ..services.ai_settings import effective_options
from ..services.ai.schemas import ProviderSuggestion
from ..services.discovery import discover, run_discovery, slugify

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


class DiscoverIn(SQLModel):
    country: str
    category: str | None = None  # None = every AI-enabled category, run in the background


@router.get("", response_model=list[Suggestion])
def list_suggestions(status: SuggestionStatus | None = SuggestionStatus.pending, _: UserProfile = Depends(admin_only),
                     session: Session = Depends(get_session)):
    q = select(Suggestion).order_by(Suggestion.created_at.desc())
    if status:
        q = q.where(Suggestion.status == status)
    return session.exec(q.limit(200)).all()


def _pending(session: Session, sid: int) -> Suggestion:
    s = session.get(Suggestion, sid)
    if not s:
        raise HTTPException(404, "Suggestion not found")
    if s.status != SuggestionStatus.pending:
        raise HTTPException(409, f"Already {s.status}")
    return s


@router.put("/{sid}", response_model=Suggestion)
def edit_suggestion(sid: int, body: ProviderSuggestion, _: UserProfile = Depends(admin_only),
                    session: Session = Depends(get_session)):
    s = _pending(session, sid)
    s.payload = body.model_dump(exclude={"source_urls"}) | {"category": s.category}
    session.commit()
    session.refresh(s)
    return s


@router.post("/{sid}/accept", response_model=Provider)
def accept(sid: int, user: UserProfile = Depends(admin_only), session: Session = Depends(get_session)):
    s = _pending(session, sid)
    p = ProviderSuggestion.model_validate(s.payload)  # re-validate: stored payload is still AI/user input
    slug = slugify(p.name) or s.slug
    exists = session.exec(select(Provider).where(Provider.country == s.country, Provider.category == s.category,
                                                 Provider.slug == slug)).first()
    if exists:
        raise HTTPException(409, f"{exists.name} is already in the catalog")
    provider = Provider(
        country=s.country, category=s.category, slug=slug, name=p.name, url=p.url or "", pricing_url=p.pricing_url or "",
        coverage=p.coverage, source="ai-accepted",
        switching={"contract_lengths": p.contract_lengths, "notice_days": p.notice_days, "cancel_method": p.cancel_method},
    )
    session.add(provider)
    s.status, s.decided_by = SuggestionStatus.accepted, user.id
    session.commit()
    session.refresh(provider)
    return provider


@router.post("/{sid}/reject", response_model=Suggestion)
def reject(sid: int, user: UserProfile = Depends(admin_only), session: Session = Depends(get_session)):
    s = _pending(session, sid)
    s.status, s.decided_by = SuggestionStatus.rejected, user.id  # kept so it is never suggested again
    session.commit()
    session.refresh(s)
    return s


async def _discover_all(code: str) -> None:
    with Session(engine) as session:
        if ai := get_provider(effective_options(session)):
            await run_discovery(session, ai, [code])


@router.post("/discover")
async def discover_now(body: DiscoverIn, tasks: BackgroundTasks, _: UserProfile = Depends(admin_only),
                       session: Session = Depends(get_session)) -> dict:
    ai = get_provider(effective_options(session))
    if ai is None:
        raise HTTPException(400, "No AI provider is set up. An admin can add one in Settings.")
    country = session.get(Country, body.country)
    if country is None:
        raise HTTPException(404, "Country not found")
    if body.category is None:
        tasks.add_task(_discover_all, body.country)  # several AI web searches: don't hold the request open
        return {"started": True}
    category = session.get(Category, body.category)
    if category is None or not category.ai_deals:
        raise HTTPException(422, "AI suggestions are not available for this category")
    try:
        created = await discover(session, ai, country, category)
    except AIError as e:
        raise HTTPException(502, str(e)) from e
    return {"found": len(created)}
