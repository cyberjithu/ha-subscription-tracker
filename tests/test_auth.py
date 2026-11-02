import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import current_user, writer
from app.models import Role, UserProfile

from .conftest import as_user

probe = FastAPI()


@pytest.fixture
def pclient(client):
    from app.main import app
    probe.dependency_overrides = app.dependency_overrides
    return TestClient(probe)


@probe.post("/api/_test/write")
def _write(user: UserProfile = Depends(writer)) -> dict:
    return {"ok": user.id}


@probe.get("/api/_test/me")
def _me(user: UserProfile = Depends(current_user)) -> dict:
    return {"id": user.id, "role": user.role, "name": user.display_name}


def test_health(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_first_user_admin_then_member(pclient: TestClient):
    a = pclient.get("/api/_test/me", headers=as_user("u1", "Jithin")).json()
    b = pclient.get("/api/_test/me", headers=as_user("u2")).json()
    assert a == {"id": "u1", "role": "admin", "name": "Jithin"}
    assert b["role"] == "member"


def test_viewer_cannot_write(pclient: TestClient, session):
    session.add(UserProfile(id="v", role=Role.viewer))
    session.commit()
    assert pclient.post("/api/_test/write", headers=as_user("v")).status_code == 403
    assert pclient.post("/api/_test/write", headers=as_user("m")).status_code == 200


def test_no_header_under_supervisor_rejected(pclient: TestClient, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "x")
    assert pclient.get("/api/_test/me").status_code == 401


def test_unknown_api_path_404(client: TestClient):
    assert client.get("/api/nope").status_code == 404
