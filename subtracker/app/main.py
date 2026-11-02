import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse

from .api import inbox, medicines, subscriptions, users
from .config import APP_DIR
from .services import jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC_DIR = APP_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_jobs = not os.environ.get("SUBTRACKER_NO_JOBS")  # tests drive jobs directly
    if run_jobs:
        jobs.start()
    yield
    if run_jobs:
        jobs.stop()


app = FastAPI(title="SubTracker", lifespan=lifespan)
api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> dict:
    return {"status": "ok"}


api.include_router(subscriptions.router)
api.include_router(inbox.router)
api.include_router(medicines.router)
api.include_router(users.router)
app.include_router(api)


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> FileResponse:
    """Serve built SPA files; unknown paths fall back to index.html for client-side routing."""
    if path.startswith("api/"):
        raise HTTPException(404)
    file = (STATIC_DIR / path).resolve()
    if path and file.is_file() and file.is_relative_to(STATIC_DIR.resolve()):
        return FileResponse(file)
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(503, "Frontend not built")
    return FileResponse(index)
