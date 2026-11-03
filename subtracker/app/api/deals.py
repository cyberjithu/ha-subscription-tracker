"""Deal search per subscription, the latest results across the household, and reading bills with AI."""
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel, select

from ..auth import current_user, writer
from ..db import get_session
from ..models import Category, DealSearch, Document, SubStatus, Subscription, UserProfile
from ..services.ai.base import AIError, AIRequest, Attachment, ask
from ..services.ai.providers import get_provider
from ..services.ai_settings import effective_options
from ..services.ai.schemas import BillExtract
from ..services.deals import build_prompt, decision_date, ineligible_reason, run_deal_search
from .subscriptions import get_visible, visible_query

router = APIRouter(tags=["deals"])
VISION_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp"}


class DealPreview(SQLModel):
    eligible: bool
    reason: str | None
    provider: str | None
    web_search: bool
    prompt: str


class DealRow(SQLModel):
    subscription_id: int
    name: str
    category: str
    decide_by: date | None
    search: DealSearch | None


@router.get("/subscriptions/{sub_id}/deal-preview", response_model=DealPreview)
def preview(sub_id: int, user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    """Exactly what would be sent, so people can check it before running a search."""
    sub = get_visible(session, sub_id, user)
    reason = ineligible_reason(sub, session.get(Category, sub.category))
    ai = get_provider(effective_options(session))
    return DealPreview(eligible=reason is None, reason=reason, provider=ai.name if ai else None,
                       web_search=bool(ai and ai.supports_web_search),
                       prompt="" if reason else build_prompt(session, sub, date.today()))


@router.post("/subscriptions/{sub_id}/deals", response_model=DealSearch)
async def search_now(sub_id: int, user: UserProfile = Depends(writer), session: Session = Depends(get_session)):
    sub = get_visible(session, sub_id, user)
    ai = get_provider(effective_options(session))
    if ai is None:
        raise HTTPException(400, "No AI provider is set up. An admin can add one in Settings.")
    try:
        return await run_deal_search(session, ai, sub)
    except AIError as e:  # not eligible; AI failures are stored on the search row instead
        raise HTTPException(422, str(e)) from e


@router.get("/subscriptions/{sub_id}/deals", response_model=list[DealSearch])
def history(sub_id: int, user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    get_visible(session, sub_id, user)
    return session.exec(select(DealSearch).where(DealSearch.subscription_id == sub_id)
                        .order_by(DealSearch.ran_at.desc()).limit(20)).all()


@router.get("/deals", response_model=list[DealRow])
def overview(user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    """Every subscription that can be searched, with its latest search, soonest decision first."""
    today = date.today()
    rows = []
    for sub in session.exec(visible_query(user).where(Subscription.status != SubStatus.cancelled)):
        if ineligible_reason(sub, session.get(Category, sub.category)):
            continue
        last = session.exec(select(DealSearch).where(DealSearch.subscription_id == sub.id)
                            .order_by(DealSearch.ran_at.desc())).first()
        rows.append(DealRow(subscription_id=sub.id, name=sub.name, category=sub.category,
                            decide_by=decision_date(sub, today), search=last))
    return sorted(rows, key=lambda r: (r.decide_by is None, r.decide_by or today))


@router.post("/subscriptions/{sub_id}/documents/{doc_id}/extract", response_model=BillExtract)
async def extract_bill(sub_id: int, doc_id: int, user: UserProfile = Depends(writer), session: Session = Depends(get_session)):
    """Read an uploaded bill with AI and return the fields for the bill form. Nothing is saved here."""
    sub = get_visible(session, sub_id, user)
    doc = session.get(Document, doc_id)
    if not doc or doc.subscription_id != sub_id:
        raise HTTPException(404, "Document not found")
    if reason := ineligible_reason(sub, session.get(Category, sub.category)):
        raise HTTPException(422, reason)  # same rule as deals: no medicines, respect the AI switch
    if doc.content_type not in VISION_TYPES:
        raise HTTPException(415, "Only PDF, PNG, JPEG or WebP bills can be read")
    ai = get_provider(effective_options(session))
    if ai is None or not ai.supports_attachments:
        raise HTTPException(400, "The configured AI cannot read documents. Use Claude or OpenAI for this.")
    prompt = ("Read this utility or subscription bill. Extract the billing period, total amount due for that period, "
              "currency, usage and its unit (kWh, m3, GB) if shown, provider and plan name. Leave unknown fields empty.")
    try:
        return await ask(ai, AIRequest(prompt, attachments=[Attachment(Path(doc.path).read_bytes(), doc.content_type, doc.filename)]),
                         BillExtract)
    except AIError as e:
        raise HTTPException(502, str(e)) from e
