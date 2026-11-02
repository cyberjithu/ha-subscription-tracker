"""Identity comes from Home Assistant Ingress headers; roles live in UserProfile."""
import os

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from .db import get_session
from .models import Role, UserProfile

INGRESS_PROXY = "172.30.32.2"  # fixed Supervisor Ingress address


def current_user(request: Request, session: Session = Depends(get_session)) -> UserProfile:
    uid = request.headers.get("X-Remote-User-Id")
    if os.environ.get("SUPERVISOR_TOKEN"):
        # running as add-on: identity headers are only trustworthy when the Ingress proxy sent them
        if not uid or not request.client or request.client.host != INGRESS_PROXY:
            raise HTTPException(401, "Open SubTracker from the Home Assistant sidebar")
    elif not uid:
        uid = os.environ.get("SUBTRACKER_DEV_USER", "dev")
    user = session.get(UserProfile, uid)
    if user is None:
        first = session.exec(select(UserProfile)).first() is None
        name = request.headers.get("X-Remote-User-Display-Name") or request.headers.get("X-Remote-User-Name") or uid
        user = UserProfile(id=uid, display_name=name, role=Role.admin if first else Role.member)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def require_role(*roles: Role):
    def dep(user: UserProfile = Depends(current_user)) -> UserProfile:
        if user.role not in roles:
            raise HTTPException(403, "Not allowed for your role")
        return user
    return dep


writer = require_role(Role.admin, Role.member)
admin_only = require_role(Role.admin)
