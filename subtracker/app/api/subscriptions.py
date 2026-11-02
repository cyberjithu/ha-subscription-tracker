"""Subscriptions plus their price history, bills, medicine details and documents."""
import shutil
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, SQLModel, delete, or_, select

from ..auth import current_user, writer
from ..config import DATA_DIR
from ..db import get_session
from ..models import (Bill, BillBase, Document, Kind, MedicineBase, MedicineDetail, PriceChange, Role,
                      SubStatus, Subscription, SubscriptionBase, UserProfile)
from ..services import schedule

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

DOCS_DIR = DATA_DIR / "docs"
MAX_UPLOAD = 15 * 1024 * 1024
ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp", "image/heic"}


class SubscriptionIn(SubscriptionBase):
    personal: bool = False  # True = only on the creator's own list


class NextEvent(SQLModel):
    kind: str
    date: date
    days: int


class EventOut(NextEvent):
    title: str


class SubscriptionOut(SubscriptionBase):
    id: int
    owner_user_id: str | None
    monthly_cost: float
    notice_deadline: date | None
    next_event: NextEvent | None


def visible_query(user: UserProfile):
    q = select(Subscription)
    if user.role != Role.admin:
        q = q.where(or_(Subscription.owner_user_id.is_(None), Subscription.owner_user_id == user.id))
    return q


def get_visible(session: Session, sub_id: int, user: UserProfile) -> Subscription:
    sub = session.get(Subscription, sub_id)
    if not sub or (sub.owner_user_id not in (None, user.id) and user.role != Role.admin):
        raise HTTPException(404, "Subscription not found")
    return sub


def to_out(session: Session, sub: Subscription, today: date | None = None) -> SubscriptionOut:
    today = today or date.today()
    bills = session.exec(select(Bill).where(Bill.subscription_id == sub.id)).all() if sub.kind == Kind.usage else []
    med = session.get(MedicineDetail, sub.id) if sub.kind == Kind.refill else None
    ev = schedule.next_event(sub, med, today)
    return SubscriptionOut(
        **sub.model_dump(),
        monthly_cost=round(schedule.monthly_cost(sub, bills, med), 2),
        notice_deadline=schedule.notice_deadline(sub, today),
        next_event=NextEvent(kind=ev.kind, date=ev.date, days=ev.days_from(today)) if ev else None,
    )


@router.get("", response_model=list[SubscriptionOut])
def list_subscriptions(scope: str = "all", category: str | None = None, kind: Kind | None = None,
                       status: SubStatus | None = None, user: UserProfile = Depends(current_user),
                       session: Session = Depends(get_session)):
    q = visible_query(user)
    if scope == "shared":
        q = q.where(Subscription.owner_user_id.is_(None))
    elif scope == "mine":
        q = q.where(Subscription.owner_user_id == user.id)
    if category:
        q = q.where(Subscription.category == category)
    if kind:
        q = q.where(Subscription.kind == kind)
    if status:
        q = q.where(Subscription.status == status)
    return [to_out(session, s) for s in session.exec(q.order_by(Subscription.name))]


@router.post("", response_model=SubscriptionOut, status_code=201)
def create_subscription(body: SubscriptionIn, user: UserProfile = Depends(writer),
                        session: Session = Depends(get_session)):
    sub = Subscription(**body.model_dump(exclude={"personal"}), owner_user_id=user.id if body.personal else None)
    if sub.kind == Kind.refill and sub.reminder_days == [30, 14, 7, 1]:
        sub.reminder_days = [3, 1]  # refill dates are short-range; the contract default makes no sense here
    session.add(sub)
    session.flush()
    if sub.price:
        session.add(PriceChange(subscription_id=sub.id, price=sub.price, effective_date=sub.start_date or date.today()))
    if sub.kind == Kind.refill:
        session.add(MedicineDetail(subscription_id=sub.id))
    session.commit()
    session.refresh(sub)
    return to_out(session, sub)


@router.get("/{sub_id}", response_model=SubscriptionOut)
def get_subscription(sub_id: int, user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    return to_out(session, get_visible(session, sub_id, user))


@router.put("/{sub_id}", response_model=SubscriptionOut)
def update_subscription(sub_id: int, body: SubscriptionBase, user: UserProfile = Depends(writer),
                        session: Session = Depends(get_session)):
    sub = get_visible(session, sub_id, user)
    if body.price != sub.price:
        session.add(PriceChange(subscription_id=sub.id, price=body.price, effective_date=date.today()))
    sub.sqlmodel_update(body.model_dump())
    if sub.kind == Kind.refill and not session.get(MedicineDetail, sub.id):
        session.add(MedicineDetail(subscription_id=sub.id))
    session.commit()
    session.refresh(sub)
    return to_out(session, sub)


@router.delete("/{sub_id}", status_code=204)
def delete_subscription(sub_id: int, user: UserProfile = Depends(writer), session: Session = Depends(get_session)):
    sub = get_visible(session, sub_id, user)
    for table in (PriceChange, Bill, MedicineDetail, Document):
        session.exec(delete(table).where(table.subscription_id == sub.id))
    session.delete(sub)
    session.commit()
    shutil.rmtree(DOCS_DIR / str(sub_id), ignore_errors=True)


@router.post("/{sub_id}/copy-to-mine", response_model=SubscriptionOut, status_code=201)
def copy_to_mine(sub_id: int, user: UserProfile = Depends(writer), session: Session = Depends(get_session)):
    src = get_visible(session, sub_id, user)
    body = SubscriptionIn(**SubscriptionBase.model_validate(src).model_dump(), personal=True)
    return create_subscription(body, user, session)


@router.post("/{sub_id}/make-shared", response_model=SubscriptionOut)
def make_shared(sub_id: int, user: UserProfile = Depends(writer), session: Session = Depends(get_session)):
    sub = get_visible(session, sub_id, user)
    sub.owner_user_id = None
    session.commit()
    session.refresh(sub)
    return to_out(session, sub)


@router.get("/{sub_id}/events", response_model=list[EventOut])
def list_events(sub_id: int, user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    sub = get_visible(session, sub_id, user)
    today = date.today()
    events = schedule.upcoming_events(sub, session.get(MedicineDetail, sub.id), today)
    return [EventOut(kind=e.kind, date=e.date, days=e.days_from(today), title=e.title) for e in events if e.date >= today]


@router.get("/{sub_id}/prices", response_model=list[PriceChange])
def price_history(sub_id: int, user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    get_visible(session, sub_id, user)
    return session.exec(select(PriceChange).where(PriceChange.subscription_id == sub_id)
                        .order_by(PriceChange.effective_date)).all()


# --- bills (usage kind) ---

@router.get("/{sub_id}/bills", response_model=list[Bill])
def list_bills(sub_id: int, user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    get_visible(session, sub_id, user)
    return session.exec(select(Bill).where(Bill.subscription_id == sub_id).order_by(Bill.period_start)).all()


def _check_period(body: BillBase) -> None:
    if body.period_end < body.period_start:
        raise HTTPException(422, "period_end is before period_start")


def _bill(session: Session, sub_id: int, bill_id: int, user: UserProfile) -> Bill:
    get_visible(session, sub_id, user)
    bill = session.get(Bill, bill_id)
    if not bill or bill.subscription_id != sub_id:
        raise HTTPException(404, "Bill not found")
    return bill


@router.post("/{sub_id}/bills", response_model=Bill, status_code=201)
def add_bill(sub_id: int, body: BillBase, user: UserProfile = Depends(writer), session: Session = Depends(get_session)):
    get_visible(session, sub_id, user)
    _check_period(body)
    bill = Bill(**body.model_dump(), subscription_id=sub_id)
    session.add(bill)
    session.commit()
    session.refresh(bill)
    return bill


@router.put("/{sub_id}/bills/{bill_id}", response_model=Bill)
def update_bill(sub_id: int, bill_id: int, body: BillBase, user: UserProfile = Depends(writer),
                session: Session = Depends(get_session)):
    bill = _bill(session, sub_id, bill_id, user)
    _check_period(body)
    bill.sqlmodel_update(body.model_dump())
    session.commit()
    session.refresh(bill)
    return bill


@router.delete("/{sub_id}/bills/{bill_id}", status_code=204)
def delete_bill(sub_id: int, bill_id: int, user: UserProfile = Depends(writer), session: Session = Depends(get_session)):
    session.delete(_bill(session, sub_id, bill_id, user))
    session.commit()


# --- medicine (refill kind) ---

def _medicine(session: Session, sub_id: int, user: UserProfile) -> MedicineDetail:
    sub = get_visible(session, sub_id, user)
    if sub.kind != Kind.refill:
        raise HTTPException(400, "Only refill subscriptions have medicine details")
    return session.get(MedicineDetail, sub_id) or MedicineDetail(subscription_id=sub_id)


@router.get("/{sub_id}/medicine", response_model=MedicineDetail)
def get_medicine(sub_id: int, user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    return _medicine(session, sub_id, user)


@router.put("/{sub_id}/medicine", response_model=MedicineDetail)
def put_medicine(sub_id: int, body: MedicineBase, user: UserProfile = Depends(writer),
                 session: Session = Depends(get_session)):
    med = _medicine(session, sub_id, user)
    if body.qty_on_hand != med.qty_on_hand:
        body.qty_updated = date.today()  # the count is "as of now"; a stale echo would skew the run-out date
    med.sqlmodel_update(body.model_dump())
    session.add(med)
    session.commit()
    session.refresh(med)
    return med


# --- documents ---

@router.get("/{sub_id}/documents", response_model=list[Document])
def list_documents(sub_id: int, user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    get_visible(session, sub_id, user)
    return session.exec(select(Document).where(Document.subscription_id == sub_id)).all()


@router.post("/{sub_id}/documents", response_model=Document, status_code=201)
async def upload_document(sub_id: int, file: UploadFile, kind: str = "bill", user: UserProfile = Depends(writer),
                          session: Session = Depends(get_session)):
    get_visible(session, sub_id, user)
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Only PDF and images are allowed")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File larger than 15 MB")
    folder = DOCS_DIR / str(sub_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / uuid.uuid4().hex  # never trust the client filename on disk
    path.write_bytes(data)
    doc = Document(subscription_id=sub_id, filename=(file.filename or "file")[:200], path=str(path),
                   content_type=file.content_type, kind=kind)
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def _document(session: Session, sub_id: int, doc_id: int, user: UserProfile) -> Document:
    get_visible(session, sub_id, user)
    doc = session.get(Document, doc_id)
    if not doc or doc.subscription_id != sub_id:
        raise HTTPException(404, "Document not found")
    return doc


@router.get("/{sub_id}/documents/{doc_id}")
def download_document(sub_id: int, doc_id: int, user: UserProfile = Depends(current_user),
                      session: Session = Depends(get_session)):
    doc = _document(session, sub_id, doc_id, user)
    return FileResponse(doc.path, media_type=doc.content_type, filename=doc.filename)


@router.delete("/{sub_id}/documents/{doc_id}", status_code=204)
def delete_document(sub_id: int, doc_id: int, user: UserProfile = Depends(writer),
                    session: Session = Depends(get_session)):
    doc = _document(session, sub_id, doc_id, user)
    session.delete(doc)
    session.commit()
    Path(doc.path).unlink(missing_ok=True)
