"""Shapes the AI must answer in. Validation here is the trust boundary for model output."""
from datetime import date
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field


def _https_or_none(v: object) -> str | None:
    # model output may invent javascript:, http: or relative links; anything but a plain https URL is dropped
    return v if isinstance(v, str) and v.startswith("https://") and " " not in v and len(v) <= 500 else None


HttpsUrl = Annotated[str | None, BeforeValidator(_https_or_none)]
Text = Annotated[str, Field(max_length=500)]


class Ping(BaseModel):
    ok: bool
    model: str = ""


class ProviderSuggestion(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    category: str
    url: HttpsUrl = None
    pricing_url: HttpsUrl = None
    coverage: Text = ""
    notice_days: Annotated[int, Field(ge=0, le=365)] | None = None
    contract_lengths: list[Annotated[int, Field(ge=0, le=60)]] = []
    cancel_method: Text = ""
    reason: Text = ""  # why it belongs in the catalog
    source_urls: list[HttpsUrl] = []

    def clean_sources(self) -> list[str]:
        return [u for u in self.source_urls if u]


class ProviderSuggestions(BaseModel):
    providers: list[ProviderSuggestion] = Field(default=[], max_length=30)


class DealOffer(BaseModel):
    provider: Annotated[str, Field(min_length=1, max_length=120)]
    plan: Text = ""
    price: Annotated[float, Field(ge=0)]
    currency: str = "EUR"
    cycle: str = "month"  # month | year | week | one-off
    contract_months: Annotated[int, Field(ge=0, le=60)] | None = None
    estimated_annual_cost: Annotated[float, Field(ge=0)] | None = None
    estimated_annual_saving: float | None = None
    source_url: HttpsUrl = None
    caveats: Text = ""


class DealOffers(BaseModel):
    offers: list[DealOffer] = Field(default=[], max_length=15)
    summary: Annotated[str, Field(max_length=2000)] = ""


class BillExtract(BaseModel):
    provider: str = ""
    plan_name: str = ""
    period_start: date | None = None
    period_end: date | None = None
    amount: Annotated[float, Field(ge=0)] | None = None
    currency: str = "EUR"
    usage_value: Annotated[float, Field(ge=0)] | None = None
    usage_unit: str = ""
