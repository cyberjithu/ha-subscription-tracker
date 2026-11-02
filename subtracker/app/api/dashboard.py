from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..auth import current_user
from ..db import get_session
from ..models import DealSearch, UserProfile
from ..services import dashboard
from ..services.deals import best_saving
from .subscriptions import visible_query

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def get_dashboard(user: UserProfile = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    subs = session.exec(visible_query(user)).all()
    names = {u.id: u.display_name or u.id for u in session.exec(select(UserProfile))}
    out = dashboard.build(session, subs, names)
    savings = 0.0
    for s in subs:
        last = session.exec(select(DealSearch).where(DealSearch.subscription_id == s.id, DealSearch.status == "done")
                            .order_by(DealSearch.ran_at.desc())).first()
        savings += best_saving(last) if last and s.status != "cancelled" else 0
    out["possible_yearly_savings"] = round(savings, 2)
    return out
