"""Fan-out of one alert to every recipient's chosen channels, honouring ownership, mutes and quiet hours."""
import logging
import os
from datetime import datetime, time, timedelta

from sqlmodel import Session, select

from ..config import get_options
from ..models import InboxItem, PendingDelivery, UserProfile
from .email_resend import send_resend
from .ha import HAClient, ha as default_ha

log = logging.getLogger("subtracker.notify")

# shortcut: Supervisor sets HOSTNAME to the add-on slug with dashes; good for store/local installs, read /addons/self/info if this breaks.
PANEL_URL = "/hassio/ingress/" + os.environ.get("HOSTNAME", "local-subtracker").replace("-", "_")


def _parse(t: str) -> time:
    h, m = t.split(":")
    return time(int(h), int(m))


def quiet_until(user: UserProfile, now: datetime) -> datetime | None:
    """End of the user's current quiet window, or None when they can be notified now."""
    if not (user.quiet_start and user.quiet_end):
        return None
    start, end, t = _parse(user.quiet_start), _parse(user.quiet_end), now.time()
    inside = start <= t < end if start <= end else (t >= start or t < end)  # window may cross midnight
    if not inside:
        return None
    until = datetime.combine(now.date(), end)
    return until if until > now else until + timedelta(days=1)


def recipients(session: Session, owner_user_id: str | None, category: str) -> list[UserProfile]:
    query = select(UserProfile)
    if owner_user_id:
        query = query.where(UserProfile.id == owner_user_id)
    return [u for u in session.exec(query) if category not in (u.muted_categories or [])]


async def deliver(user: UserProfile, title: str, body: str, link: str, ha: HAClient) -> None:
    ch = user.channels or {}
    url = link or PANEL_URL
    try:
        if ch.get("push") and user.push_service:
            await ha.notify(user.push_service, title, body, url)
        if ch.get("email") and user.email:
            opts = get_options()
            if opts.resend_api_key and opts.resend_from:
                await send_resend(opts.resend_api_key, opts.resend_from, user.email, title, body)
            elif opts.email_notify_service:
                await ha.call_service(opts.email_notify_service, {"title": title, "message": body, "target": [user.email]})
    except Exception:  # one failing channel must not drop the others or crash the job
        log.exception("Delivery to %s failed", user.id)


async def notify(session: Session, *, key: str, title: str, body: str, category: str = "",
                 owner_user_id: str | None = None, link: str = "", now: datetime | None = None,
                 ha: HAClient = default_ha) -> bool:
    """Send once per dedupe key. Returns False when the key was already sent."""
    if session.exec(select(InboxItem).where(InboxItem.key == key)).first():
        return False
    now = now or datetime.now()
    users = recipients(session, owner_user_id, category)
    if not users:  # nobody has opened the panel yet: keep a household inbox entry
        session.add(InboxItem(user_id=owner_user_id, key=key, title=title, body=body, link=link))
    for user in users:
        session.add(InboxItem(user_id=user.id, key=key, title=title, body=body, link=link,
                              read=not (user.channels or {}).get("inbox", True)))
        if until := quiet_until(user, now):
            session.add(PendingDelivery(user_id=user.id, title=title, body=body, link=link, not_before=until))
        else:
            await deliver(user, title, body, link, ha)
    if not users or any((u.channels or {}).get("persistent") for u in users):
        try:
            await ha.persistent(title, body, f"subtracker_{key}")
        except Exception:
            log.exception("Persistent notification failed")
    session.commit()
    return True


async def flush_pending(session: Session, now: datetime | None = None, ha: HAClient = default_ha) -> int:
    now = now or datetime.now()
    due = session.exec(select(PendingDelivery).where(PendingDelivery.not_before <= now)).all()
    for p in due:
        if user := session.get(UserProfile, p.user_id):
            await deliver(user, p.title, p.body, p.link, ha)
        session.delete(p)
    session.commit()
    return len(due)
