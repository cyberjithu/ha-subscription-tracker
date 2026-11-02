"""AI provider discovery. The AI only proposes: results land in Suggestion rows and reach the
catalog solely through an admin's accept (see api/suggestions.py)."""
import logging
import re
import unicodedata
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from ..models import Category, Country, Provider, Role, Suggestion, UserProfile
from .ai.base import AIError, AIProvider, AIRequest, ask
from .ai.schemas import ProviderSuggestions
from .ha import HAClient, ha as default_ha
from .notify import notify

log = logging.getLogger("subtracker.discovery")

SYSTEM = (
    "You research consumer service providers for a household budgeting app. Only list real companies that "
    "currently sell to households in the given country and take new customers. Use official websites. "
    "Never invent URLs: leave a URL empty if you are not sure. Do not repeat providers the user already has."
)


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


async def discover(session: Session, ai: AIProvider, country: Country, category: Category) -> list[Suggestion]:
    """Ask the AI for providers missing from one country/category and store the new ones as pending."""
    known_providers = session.exec(select(Provider).where(Provider.country == country.code,
                                                          Provider.category == category.slug)).all()
    known_suggestions = session.exec(select(Suggestion).where(Suggestion.country == country.code,
                                                              Suggestion.category == category.slug)).all()
    # hidden providers and rejected suggestions count as known, so they are never proposed again
    known = {p.slug for p in known_providers} | {s.slug for s in known_suggestions}
    names = ", ".join(sorted(p.name for p in known_providers)) or "none yet"
    prompt = (
        f"Country: {country.name} ({country.code}). Category: {category.name}.\n"
        f"Providers already in the catalog: {names}.\n"
        f"List up to 8 other {category.name.lower()} providers for households in {country.name}. "
        "For each give the official website, a prices page if there is one, coverage limits, usual contract "
        "lengths in months (0 = no contract), notice period in days, how to cancel or switch, one sentence on "
        "why it is worth listing, and the https pages you used as sources."
    )
    result = await ask(ai, AIRequest(prompt, SYSTEM, web_search=ai.supports_web_search), ProviderSuggestions)
    created = []
    for s in result.providers:
        slug = slugify(s.name)
        if not slug or slug in known:
            continue
        known.add(slug)
        payload = s.model_dump(exclude={"source_urls"}) | {"category": category.slug}  # AI may not move categories
        row = Suggestion(country=country.code, category=category.slug, slug=slug, payload=payload,
                         source_urls=s.clean_sources(), ai_provider=ai.name)
        session.add(row)
        created.append(row)
    session.commit()
    return created


async def run_discovery(session: Session, ai: AIProvider, codes: list[str], categories: list[str] | None = None,
                        ha: HAClient = default_ha) -> dict:
    """Discover for each country and category (all AI-enabled ones unless given). One failing category
    does not stop the rest. Admins get one notification for the whole run."""
    cats = [c for c in session.exec(select(Category).order_by(Category.slug)) if c.ai_deals
            and (categories is None or c.slug in categories)]
    found, errors = 0, []
    for code in codes:
        country = session.get(Country, code)
        if country is None:
            errors.append(f"{code}: no catalog for this country")
            continue
        for cat in cats:
            try:
                found += len(await discover(session, ai, country, cat))
            except AIError as e:
                session.rollback()
                errors.append(f"{code}/{cat.slug}: {e}")
                log.warning("Discovery %s/%s failed: %s", code, cat.slug, e)
        country.settings = {**country.settings, "last_discovery": datetime.now(UTC).isoformat()}
        session.commit()
    if found:
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M")
        for admin in session.exec(select(UserProfile).where(UserProfile.role == Role.admin)):
            await notify(session, key=f"discovery:{stamp}:{admin.id}", persistent_id=f"discovery:{stamp}",
                         owner_user_id=admin.id, title=f"{found} new provider{'s' if found != 1 else ''} suggested",
                         body="Review them in SubTracker → Suggestions before they are added to the catalog.",
                         link="", ha=ha)
    return {"found": found, "errors": errors}


def due_countries(session: Session, codes: list[str], interval_days: int, now: datetime | None = None) -> list[str]:
    """Countries whose last discovery is older than the interval (0 = discovery switched off)."""
    if interval_days <= 0:
        return []
    now = now or datetime.now(UTC)
    due = []
    for code in codes:
        country = session.get(Country, code)
        last = (country.settings or {}).get("last_discovery") if country else None
        if country and (not last or now - datetime.fromisoformat(last) >= timedelta(days=interval_days)):
            due.append(code)
    return due
