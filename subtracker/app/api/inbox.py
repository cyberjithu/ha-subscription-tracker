from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel, or_, select

from ..auth import current_user
from ..db import get_session
from ..models import InboxItem, UserProfile

router = APIRouter(prefix="/inbox", tags=["inbox"])


class InboxOut(SQLModel):
    unread: int
    items: list[InboxItem]


def _mine(user: UserProfile):
    return select(InboxItem).where(or_(InboxItem.user_id == user.id, InboxItem.user_id.is_(None)))


@router.get("", response_model=InboxOut)
def list_inbox(limit: int = 100, user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    items = session.exec(_mine(user).order_by(InboxItem.created_at.desc()).limit(limit)).all()
    unread = len(session.exec(_mine(user).where(InboxItem.read.is_(False))).all())
    return InboxOut(unread=unread, items=items)


@router.post("/{item_id}/read", status_code=204)
def mark_read(item_id: int, user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    item = session.get(InboxItem, item_id)
    if not item or item.user_id not in (None, user.id):
        raise HTTPException(404, "Not found")
    item.read = True
    session.commit()


@router.post("/read-all", status_code=204)
def mark_all_read(user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    for item in session.exec(_mine(user).where(InboxItem.read.is_(False))):
        item.read = True
    session.commit()
