from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import Field as PField, StringConstraints

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def json_col(default: Any = None) -> Any:
    factory = (lambda: list(default)) if isinstance(default, list) else (lambda: dict(default or {}))
    return Field(default_factory=factory, sa_column=Column(JSON, nullable=False))


class Kind(StrEnum):
    fixed = "fixed"          # flat recurring price (Netflix)
    contract = "contract"    # term with end date + notice (broadband, energy)
    usage = "usage"          # bill amount varies (gas, electricity)
    refill = "refill"        # stock based (medicines)


class Cycle(StrEnum):
    week = "week"
    month = "month"
    quarter = "quarter"
    year = "year"
    custom = "custom"


class Role(StrEnum):
    admin = "admin"
    member = "member"
    viewer = "viewer"


class SubStatus(StrEnum):
    active = "active"
    switching = "switching"
    cancelled = "cancelled"


def Pattern(regex: str) -> Any:
    return Annotated[str, StringConstraints(pattern=regex)]


NonNeg = Annotated[float, PField(ge=0)]
DayCount = Annotated[int, PField(ge=0, le=3650)]
ReminderDays = list[Annotated[int, PField(ge=0, le=365)]]

HHMM = Pattern(r"^([01]\d|2[0-3]):[0-5]\d$")


class UserPrefs(SQLModel):
    """Fields a user may edit on their own profile."""
    display_name: str = Field(default="", max_length=80)
    avatar_color: Pattern(r"^#[0-9a-fA-F]{6}$") = "#6366f1"
    theme: Pattern(r"^(ha|light|dark)$") = "ha"
    default_view: str = "dashboard"
    date_format: str = "en-IE"  # locale used for dates and money in the UI
    language: str = "en"
    push_service: Pattern(r"^(notify\.[a-z0-9_]+)?$") = ""  # e.g. notify.mobile_app_pixel
    email: Pattern(r"^([^@\s]+@[^@\s]+\.[^@\s]+)?$") = ""
    channels: dict = json_col({"push": True, "persistent": True, "inbox": True, "email": False})
    quiet_start: HHMM | None = None
    quiet_end: HHMM | None = None
    reminder_days: ReminderDays | None = Field(default=None, sa_column=Column(JSON))
    muted_categories: list[str] = json_col([])


class UserProfile(UserPrefs, table=True):
    id: str = Field(primary_key=True)  # HA user id from Ingress header
    role: Role = Role.member
    created_at: datetime = Field(default_factory=utcnow)


class SubscriptionBase(SQLModel):
    name: str = Field(min_length=1, max_length=120)
    category: str
    kind: Kind = Kind.fixed
    country: str = "IE"
    provider_id: int | None = Field(default=None, foreign_key="provider.id")
    plan_name: str = ""
    price: NonNeg = 0
    currency: str = "EUR"
    cycle: Cycle = Cycle.month
    cycle_days: Annotated[int, PField(ge=1, le=3650)] | None = None  # for Cycle.custom
    start_date: date | None = None
    next_renewal: date | None = None
    contract_end: date | None = None
    auto_renew: bool = True
    notice_days: DayCount | None = None
    reminder_days: ReminderDays = json_col([30, 14, 7, 1])
    ai_enabled: bool = True
    ai_share_usage: bool = False
    ai_share_location: bool = False
    annual_usage: NonNeg | None = None
    usage_unit: str = ""
    location: str = ""  # Eircode / county, only sent to AI when ai_share_location
    account_url: str = ""
    notes: str = ""
    status: SubStatus = SubStatus.active


class Subscription(SubscriptionBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: str | None = Field(default=None, index=True)  # None = household shared
    created_at: datetime = Field(default_factory=utcnow)


class PriceChange(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    subscription_id: int = Field(foreign_key="subscription.id", index=True)
    price: float
    effective_date: date


class BillBase(SQLModel):
    period_start: date
    period_end: date
    amount: NonNeg
    usage_value: NonNeg | None = None
    usage_unit: str = ""


class Bill(BillBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    subscription_id: int = Field(foreign_key="subscription.id", index=True)


class MedicineBase(SQLModel):
    qty_on_hand: NonNeg = 0
    qty_updated: date = Field(default_factory=date.today)
    daily_dose: NonNeg = 1
    pack_size: NonNeg = 0
    refill_lead_days: DayCount = 7
    script_expiry: date | None = None
    pharmacy: str = ""
    cost_per_fill: NonNeg = 0


class MedicineDetail(MedicineBase, table=True):
    subscription_id: int = Field(foreign_key="subscription.id", primary_key=True)


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    subscription_id: int = Field(foreign_key="subscription.id", index=True)
    filename: str
    path: str
    content_type: str = ""
    kind: str = "bill"  # bill | contract | other
    uploaded_at: datetime = Field(default_factory=utcnow)


class Country(SQLModel, table=True):
    code: str = Field(primary_key=True)
    name: str
    currency: str = "EUR"
    settings: dict = json_col({})


class Category(SQLModel, table=True):
    slug: str = Field(primary_key=True)
    name: str
    icon: str = "mdi:tag"
    ai_deals: bool = True


HttpsUrl = Pattern(r"^(https://\S+)?$")


class ProviderBase(SQLModel):
    """Editable catalog fields; also the shape of a provider in a country YAML file."""
    category: Pattern(r"^[a-z0-9_-]+$")
    slug: Pattern(r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=120)
    url: HttpsUrl = ""
    pricing_url: HttpsUrl = ""
    plans: list = json_col([])
    plans_captured_at: date | None = None
    switching: dict = json_col({})  # contract_lengths, notice_days, cancel_method, switch_site, regulator
    coverage: str = ""


class Provider(ProviderBase, table=True):
    __table_args__ = (UniqueConstraint("country", "category", "slug", name="uq_provider_country_category_slug"),)
    id: int | None = Field(default=None, primary_key=True)
    country: str = Field(index=True)
    source: str = "manual"  # bundled | edited (bundled, changed by a user) | manual | ai-accepted
    hidden: bool = False  # bundled providers are hidden, not deleted, so the next catalog load doesn't revive them


class SuggestionStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class Suggestion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    country: str
    category: str
    slug: str = Field(index=True)
    payload: dict = json_col({})
    source_urls: list = json_col([])
    status: SuggestionStatus = SuggestionStatus.pending
    ai_provider: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    decided_by: str | None = None


class DealSearch(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    subscription_id: int = Field(foreign_key="subscription.id", index=True)
    ran_at: datetime = Field(default_factory=utcnow)
    trigger: str = "manual"  # manual | auto
    ai_provider: str = ""
    prompt: str = ""
    offers: list = json_col([])  # DealOffer dicts, cheapest first
    summary: str = ""
    current_annual_cost: float | None = None  # what the subscription costs now, for comparing offers
    status: str = "done"  # done | error
    error: str = ""


class InboxItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str | None = Field(default=None, index=True)  # None = everyone
    key: str = Field(index=True)  # dedupe key, e.g. "notice:12:2026-12-01:7"
    title: str
    body: str = ""
    link: str = ""
    read: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class PendingDelivery(SQLModel, table=True):
    """Notification held back by a user's quiet hours."""
    id: int | None = Field(default=None, primary_key=True)
    user_id: str
    title: str
    body: str
    link: str = ""
    channels: list = json_col([])
    not_before: datetime
