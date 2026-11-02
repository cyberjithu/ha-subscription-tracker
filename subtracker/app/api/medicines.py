"""Medicines overview: supply, run-out dates and Drug Payment Scheme style monthly totals."""
from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session, SQLModel

from ..auth import current_user
from ..db import get_session
from ..models import Country, Kind, MedicineDetail, SubStatus, Subscription, UserProfile
from ..services import schedule
from .subscriptions import SubscriptionOut, to_out, visible_query

router = APIRouter(prefix="/medicines", tags=["medicines"])


class MedicineRow(SQLModel):
    subscription: SubscriptionOut
    medicine: MedicineDetail
    remaining: float
    days_left: int | None
    run_out: date | None


class MedicinesOut(SQLModel):
    items: list[MedicineRow]
    monthly_total: float
    monthly_cap: float | None  # country scheme cap (IE: Drug Payment Scheme), from the country catalog
    currency: str


@router.get("", response_model=MedicinesOut)
def medicines(user: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    today = date.today()
    q = visible_query(user).where(Subscription.kind == Kind.refill, Subscription.status != SubStatus.cancelled)
    items = []
    for sub in session.exec(q.order_by(Subscription.name)):
        med = session.get(MedicineDetail, sub.id) or MedicineDetail(subscription_id=sub.id)
        run_out = schedule.run_out_date(med, today)
        items.append(MedicineRow(subscription=to_out(session, sub, today), medicine=med,
                                 remaining=schedule.medicine_remaining(med, today),
                                 days_left=(run_out - today).days if run_out else None, run_out=run_out))
    country = session.get(Country, items[0].subscription.country) if items else None
    cap = (country.settings or {}).get("dps_monthly_cap") if country else None
    return MedicinesOut(items=items, monthly_total=round(sum(i.subscription.monthly_cost for i in items), 2),
                        monthly_cap=cap, currency=items[0].subscription.currency if items else "EUR")
