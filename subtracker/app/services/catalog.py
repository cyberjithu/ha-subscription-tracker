"""Country catalogs: load the bundled YAML files, import/export YAML, without clobbering what users changed."""
import logging
from datetime import date

import yaml
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..config import CATALOG_DIR
from ..models import Category, Country, Provider, ProviderBase

log = logging.getLogger("subtracker.catalog")


class CountryIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z]{2}$")
    name: str
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    settings: dict = {}


class CategoryIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9_-]+$")
    name: str
    icon: str = "mdi:tag"
    ai_deals: bool = True


class CatalogFile(BaseModel):
    """One country's catalog. Unknown top-level keys (e.g. YAML anchor blocks) are ignored."""
    captured_at: date | None = None
    country: CountryIn
    categories: list[CategoryIn] = []
    providers: list[ProviderBase] = []


def parse(text: str) -> CatalogFile:
    return CatalogFile.model_validate(yaml.safe_load(text))


def apply(session: Session, cat: CatalogFile, *, bundled: bool) -> dict[str, int]:
    """Upsert a catalog.

    bundled=True (add-on start): add new entries, refresh untouched bundled providers, never touch
    anything a user edited, added or hidden; country settings only gain missing keys.
    bundled=False (admin import): the file wins for everything it lists, hidden providers come back.
    """
    counts = {"added": 0, "updated": 0, "kept": 0}
    c = cat.country
    country = session.get(Country, c.code)
    if country is None:
        session.add(Country(code=c.code, name=c.name, currency=c.currency, settings=c.settings))
    else:
        country.settings = {**country.settings, **c.settings} if not bundled else {**c.settings, **country.settings}
        if not bundled:
            country.name, country.currency = c.name, c.currency
    for ci in cat.categories:
        existing = session.get(Category, ci.slug)
        if existing is None:
            session.add(Category(**ci.model_dump()))
        elif not bundled:
            existing.sqlmodel_update(ci.model_dump())
    for pi in cat.providers:
        data = pi.model_dump()
        if cat.captured_at and data["plans"] and not data["plans_captured_at"]:
            data["plans_captured_at"] = cat.captured_at
        row = session.exec(select(Provider).where(Provider.country == c.code, Provider.category == pi.category,
                                                  Provider.slug == pi.slug)).first()
        if row is None:
            session.add(Provider(**data, country=c.code, source="bundled" if bundled else "manual"))
            counts["added"] += 1
        elif bundled and (row.source != "bundled" or row.hidden):
            counts["kept"] += 1
        else:
            row.sqlmodel_update(data)
            if not bundled:
                row.hidden = False
                if row.source == "bundled":
                    row.source = "edited"  # stop the next add-on start from overwriting the import
            counts["updated"] += 1
    session.commit()
    return counts


def load_bundled(session: Session) -> None:
    for path in sorted(CATALOG_DIR.glob("*.yaml")):
        try:
            counts = apply(session, parse(path.read_text()), bundled=True)
            log.info("Catalog %s: %s", path.name, counts)
        except Exception:  # a broken bundled file must not stop the add-on
            session.rollback()
            log.exception("Could not load catalog %s", path.name)


def export(session: Session, code: str) -> str:
    country = session.get(Country, code)
    if country is None:
        raise KeyError(code)
    providers = session.exec(select(Provider).where(Provider.country == code, Provider.hidden.is_(False))
                             .order_by(Provider.category, Provider.name)).all()
    used = {p.category for p in providers}
    categories = [c for c in session.exec(select(Category).order_by(Category.slug)) if c.slug in used]
    doc = {
        "captured_at": date.today(),
        "country": {"code": country.code, "name": country.name, "currency": country.currency, "settings": country.settings},
        "categories": [CategoryIn.model_validate(c, from_attributes=True).model_dump() for c in categories],
        "providers": [ProviderBase.model_validate(p).model_dump(exclude_defaults=True) for p in providers],
    }
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
