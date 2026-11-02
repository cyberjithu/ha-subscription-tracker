"""Better-deal search before a renewal. What reaches the AI is decided here, field by field:
no notes, account links, owner or medicines; usage and location only when the subscription allows it."""
import logging
import re
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlmodel import Session, select

from ..models import Bill, Category, Country, DealSearch, Kind, Provider, SubStatus, Subscription
from . import schedule
from .ai.base import AIError, AIProvider, AIRequest, ask
from .ai.schemas import DealOffers
from .ha import HAClient, ha as default_ha
from .notify import notify

log = logging.getLogger("subtracker.deals")

SYSTEM = (
    "You compare consumer offers for a household. Only use current, publicly advertised prices from the "
    "providers' own sites or reputable comparison sites, and give the page you used as source_url. Convert every "
    "offer to an estimated annual cost including setup fees and the price after any introductory period. "
    "If you cannot verify a price, leave the offer out. Never invent URLs."
)
MIN_AUTO_GAP = timedelta(days=90)  # monthly subscriptions have a renewal every month; don't search every month


def ineligible_reason(sub: Subscription, category: Category | None) -> str | None:
    if sub.kind == Kind.refill:
        return "Medicines are never sent to AI."
    if category is not None and not category.ai_deals:
        return f"Deal search is off for {category.name}."
    if not sub.ai_enabled:
        return "Deal search is switched off for this subscription."
    if sub.status == SubStatus.cancelled:
        return "This subscription is cancelled."
    return None


def decision_date(sub: Subscription, today: date) -> date | None:
    """When the household has to decide: the notice deadline, else the contract end / next renewal."""
    if nd := schedule.notice_deadline(sub, today):
        return nd
    if sub.kind == Kind.contract and sub.contract_end:
        return sub.contract_end
    if sub.next_renewal:
        return schedule.roll_forward(sub.next_renewal, sub.cycle, sub.cycle_days, today)
    return None


def build_prompt(session: Session, sub: Subscription, today: date) -> str:
    bills = session.exec(select(Bill).where(Bill.subscription_id == sub.id)).all() if sub.kind == Kind.usage else []
    monthly = schedule.monthly_cost(sub, bills)
    country = session.get(Country, sub.country)
    provider = session.get(Provider, sub.provider_id) if sub.provider_id else None
    shortlist = session.exec(select(Provider).where(Provider.country == sub.country, Provider.category == sub.category,
                                                    Provider.hidden.is_(False))).all()
    lines = [
        f"Country: {country.name if country else sub.country}. Currency: {sub.currency}.",
        f"Category: {sub.category}.",
        f"Current provider: {provider.name if provider else sub.name}" + (f", plan: {sub.plan_name}" if sub.plan_name else "") + ".",
        f"Current cost: about {monthly:.2f} {sub.currency} a month ({monthly * 12:.2f} a year).",
    ]
    if sub.kind == Kind.contract and sub.contract_end:
        lines.append(f"Current contract ends {sub.contract_end.isoformat()}" + ("" if sub.auto_renew else " and does not roll over") + ".")
    if sub.notice_days:
        lines.append(f"Notice period: {sub.notice_days} days.")
    if sub.ai_share_usage:
        if sub.annual_usage:
            lines.append(f"Yearly usage: {sub.annual_usage:g} {sub.usage_unit}.")
        used = [b for b in bills if b.usage_value is not None]
        if used:
            days = sum((b.period_end - b.period_start).days + 1 for b in used)
            yearly = sum(b.usage_value for b in used) / days * 365
            lines.append(f"Usage from recent bills: about {yearly:.0f} {used[0].usage_unit} a year.")
    if sub.ai_share_location and sub.location:
        lines.append(f"Location (for coverage): {sub.location}.")
    if shortlist:
        lines.append("Known providers to check first: " + "; ".join(
            f"{p.name} ({p.pricing_url or p.url})" if (p.pricing_url or p.url) else p.name for p in shortlist) + ".")
    lines.append(f"Today is {today.isoformat()}. Find up to 6 offers that would suit this household, cheapest per year first, "
                 "including the current provider's best retention or new-customer offer, and summarise the advice in 2-3 sentences.")
    return "\n".join(lines)


def page_text(html: str, limit: int = 15000) -> str:
    """Crude HTML-to-text so models without web search can read pricing pages."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)[:limit]


async def fetch_pricing_pages(session: Session, sub: Subscription, transport: httpx.AsyncBaseTransport | None = None) -> str:
    # shortcut: first 5 catalog pricing pages, no JavaScript rendering; good enough for local models, upgrade with a headless browser if prices hide behind JS
    urls = [p.pricing_url for p in session.exec(select(Provider).where(
        Provider.country == sub.country, Provider.category == sub.category, Provider.hidden.is_(False))) if p.pricing_url][:5]
    parts = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, transport=transport,
                                 headers={"User-Agent": "Mozilla/5.0 SubTracker"}) as c:
        for url in urls:
            try:
                r = await c.get(url)
                r.raise_for_status()
                parts.append(f"--- {url} ---\n{page_text(r.text)}")
            except httpx.HTTPError as e:
                log.info("Could not fetch %s: %s", url, e)
    return "\n\n".join(parts)


async def run_deal_search(session: Session, ai: AIProvider, sub: Subscription, trigger: str = "manual",
                          today: date | None = None) -> DealSearch:
    today = today or date.today()
    if reason := ineligible_reason(sub, session.get(Category, sub.category)):
        raise AIError(reason)
    prompt = build_prompt(session, sub, today)
    request_prompt = prompt
    if not ai.supports_web_search:
        request_prompt += "\n\nCurrent pricing pages:\n" + (await fetch_pricing_pages(session, sub) or "(none could be fetched)")
    bills = session.exec(select(Bill).where(Bill.subscription_id == sub.id)).all() if sub.kind == Kind.usage else []
    current = round(schedule.monthly_cost(sub, bills) * 12, 2)
    row = DealSearch(subscription_id=sub.id, trigger=trigger, ai_provider=ai.name, prompt=prompt, current_annual_cost=current)
    try:
        result = await ask(ai, AIRequest(request_prompt, SYSTEM, web_search=ai.supports_web_search), DealOffers)
        offers = []
        for o in result.offers:
            if o.estimated_annual_saving is None and o.estimated_annual_cost is not None:
                o.estimated_annual_saving = round(current - o.estimated_annual_cost, 2)
            offers.append(o.model_dump())
        offers.sort(key=lambda o: (o["estimated_annual_cost"] is None, o["estimated_annual_cost"] or 0))
        row.offers, row.summary = offers, result.summary
    except AIError as e:
        row.status, row.error = "error", str(e)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def best_saving(search: DealSearch) -> float:
    return max((o.get("estimated_annual_saving") or 0 for o in search.offers), default=0)


async def run_auto_deal_searches(session: Session, ai: AIProvider, lead_days: int, today: date | None = None,
                                 ha: HAClient = default_ha) -> int:
    """Search once when a subscription enters its decision window (decision date - lead_days)."""
    today = today or date.today()
    ran = 0
    for sub in session.exec(select(Subscription).where(Subscription.status == SubStatus.active)).all():
        if ineligible_reason(sub, session.get(Category, sub.category)):
            continue
        deadline = decision_date(sub, today)
        if deadline is None or not (deadline - timedelta(days=lead_days) <= today <= deadline):
            continue
        window_start = datetime.combine(deadline - timedelta(days=lead_days), datetime.min.time(), tzinfo=UTC)
        last = session.exec(select(DealSearch).where(DealSearch.subscription_id == sub.id, DealSearch.trigger == "auto")
                            .order_by(DealSearch.ran_at.desc())).first()
        if last and (last.ran_at.replace(tzinfo=last.ran_at.tzinfo or UTC) >= window_start
                     or datetime.now(UTC) - last.ran_at.replace(tzinfo=last.ran_at.tzinfo or UTC) < MIN_AUTO_GAP):
            continue
        search = await run_deal_search(session, ai, sub, "auto", today)
        ran += 1
        saving = best_saving(search)
        if search.status == "done":
            body = (f"Best offer saves about {saving:.0f} {sub.currency} a year. Decide by {deadline:%d %b %Y}."
                    if saving > 0 else f"No cheaper offer found. Decide by {deadline:%d %b %Y}.")
            await notify(session, key=f"deal:{search.id}", title=f"Deal check: {sub.name}", body=body, category=sub.category,
                         owner_user_id=sub.owner_user_id, personal=bool(sub.owner_user_id), ha=ha)
    return ran
