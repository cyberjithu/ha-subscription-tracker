import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse

from .api import subscriptions
from .config import APP_DIR
from .services import jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC_DIR = APP_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    jobs.start()
    yield
    jobs.stop()


app = FastAPI(title="SubTracker", lifespan=lifespan)
api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> dict:
    return {"status": "ok"}


api.include_router(subscriptions.router)
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
