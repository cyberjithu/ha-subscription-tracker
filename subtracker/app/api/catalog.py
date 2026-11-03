"""Country catalog: browse for everyone, edit/import for admins. AI suggestions arrive separately (C10)."""
import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from typing import Annotated

from pydantic import Field as PField
from sqlmodel import Session, SQLModel, select

from ..auth import admin_only, current_user
from ..config import CATALOG_DIR
from ..db import get_session
from ..models import Category, Country, Provider, ProviderBase, UserProfile
from ..services import catalog

router = APIRouter(prefix="/catalog", tags=["catalog"])


class ProviderIn(ProviderBase):
    country: str


class CountrySettingsIn(SQLModel):
    settings: dict


class CountryIn(SQLModel):
    code: Annotated[str, PField(pattern=r"^[A-Z]{2}$")]
    name: Annotated[str, PField(min_length=2, max_length=60)]
    currency: Annotated[str, PField(pattern=r"^[A-Z]{3}$")] = "EUR"


class CountryOut(SQLModel):
    code: str
    name: str
    currency: str
    settings: dict
    provider_count: int
    builtin: bool  # ships with the add-on (a catalogs/<code>.yaml exists)


@router.get("/countries", response_model=list[CountryOut])
def countries(_: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    """Every country with a catalog: bundled ones appear on their own once their YAML ships, custom ones once added."""
    out = []
    for c in session.exec(select(Country).order_by(Country.name)):
        count = len(session.exec(select(Provider.id).where(Provider.country == c.code, Provider.hidden.is_(False))).all())
        out.append(CountryOut(**c.model_dump(), provider_count=count, builtin=(CATALOG_DIR / f"{c.code.lower()}.yaml").exists()))
    return out


@router.post("/countries", response_model=Country, status_code=201)
def add_country(body: CountryIn, _: UserProfile = Depends(admin_only), session: Session = Depends(get_session)):
    """A country without a bundled catalog: starts empty, filled by hand, by import or by AI suggestions."""
    if session.get(Country, body.code):
        raise HTTPException(409, f"{body.code} already exists")
    country = Country(code=body.code, name=body.name, currency=body.currency, settings={})
    session.add(country)
    session.commit()
    session.refresh(country)
    return country


@router.put("/countries/{code}", response_model=Country)
def update_country(code: str, body: CountrySettingsIn, _: UserProfile = Depends(admin_only),
                   session: Session = Depends(get_session)):
    country = session.get(Country, code)
    if not country:
        raise HTTPException(404, "Country not found")
    cap = body.settings.get("dps_monthly_cap")
    if cap is not None and (not isinstance(cap, int | float) or cap < 0):
        raise HTTPException(422, "dps_monthly_cap must be a number ≥ 0")
    country.settings = body.settings
    session.commit()
    session.refresh(country)
    return country


@router.get("/categories", response_model=list[Category])
def categories(_: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    return session.exec(select(Category).order_by(Category.name)).all()


@router.get("/providers", response_model=list[Provider])
def providers(country: str | None = None, category: str | None = None, include_hidden: bool = False,
              _: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    q = select(Provider).order_by(Provider.category, Provider.name)
    if country:
        q = q.where(Provider.country == country)
    if category:
        q = q.where(Provider.category == category)
    if not include_hidden:
        q = q.where(Provider.hidden.is_(False))
    return session.exec(q).all()


def _save(session: Session, row: Provider) -> Provider:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, f"{row.country}/{row.category}/{row.slug} already exists") from None
    session.refresh(row)
    return row


@router.post("/providers", response_model=Provider, status_code=201)
def add_provider(body: ProviderIn, _: UserProfile = Depends(admin_only), session: Session = Depends(get_session)):
    if not session.get(Country, body.country):
        raise HTTPException(422, f"Unknown country {body.country}")
    row = Provider(**body.model_dump(), source="manual")
    session.add(row)
    return _save(session, row)


@router.put("/providers/{provider_id}", response_model=Provider)
def update_provider(provider_id: int, body: ProviderBase, _: UserProfile = Depends(admin_only),
                    session: Session = Depends(get_session)):
    row = session.get(Provider, provider_id)
    if not row:
        raise HTTPException(404, "Provider not found")
    row.sqlmodel_update(body.model_dump())
    if row.source == "bundled":
        row.source = "edited"  # keep the change when the bundled catalog reloads
    return _save(session, row)


@router.post("/providers/{provider_id}/restore", response_model=Provider)
def restore_provider(provider_id: int, _: UserProfile = Depends(admin_only), session: Session = Depends(get_session)):
    row = session.get(Provider, provider_id)
    if not row:
        raise HTTPException(404, "Provider not found")
    row.hidden = False
    return _save(session, row)


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: int, _: UserProfile = Depends(admin_only), session: Session = Depends(get_session)):
    row = session.get(Provider, provider_id)
    if not row:
        raise HTTPException(404, "Provider not found")
    if row.source in ("bundled", "edited"):
        row.hidden = True  # bundled entries would come back on the next load if deleted
    else:
        session.delete(row)
    session.commit()


@router.get("/export/{code}", response_class=PlainTextResponse)
def export(code: str, _: UserProfile = Depends(current_user), session: Session = Depends(get_session)):
    try:
        text = catalog.export(session, code)
    except KeyError:
        raise HTTPException(404, "Country not found") from None
    return PlainTextResponse(text, media_type="application/x-yaml",
                             headers={"Content-Disposition": f'attachment; filename="{code.lower()}.yaml"'})


MAX_IMPORT = 1_000_000


@router.post("/import")
async def import_catalog(request: Request, _: UserProfile = Depends(admin_only),
                         session: Session = Depends(get_session)) -> dict:
    """Body: the YAML text itself (Content-Type: application/x-yaml)."""
    raw = await request.body()
    if len(raw) > MAX_IMPORT:
        raise HTTPException(413, "Catalog file larger than 1 MB")
    try:
        cat = catalog.parse(raw.decode())
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(x) for x in first["loc"])
        raise HTTPException(422, f"Catalog is not valid: {e.error_count()} problem(s); {where}: {first['msg']}") from e
    except (yaml.YAMLError, UnicodeDecodeError, AttributeError, TypeError) as e:
        raise HTTPException(422, f"Not a readable catalog YAML file: {e}") from e
    return catalog.apply(session, cat, bundled=False)
