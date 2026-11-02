from collections.abc import Iterator

from sqlmodel import Session, create_engine

from .config import DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_URL = f"sqlite:///{DATA_DIR / 'subtracker.db'}"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
