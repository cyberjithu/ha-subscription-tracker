import os
import tempfile

os.environ["SUBTRACKER_DATA"] = tempfile.mkdtemp(prefix="subtracker-test-")
os.environ.pop("SUPERVISOR_TOKEN", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine):
    def override():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def as_user(uid: str, name: str = "") -> dict:
    return {"X-Remote-User-Id": uid, "X-Remote-User-Display-Name": name or uid}
