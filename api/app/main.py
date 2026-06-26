from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, ORJSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .clients.zabbix import ZabbixClient
from .config import get_settings
from .database import SessionLocal, create_tables, dispose_database, init_database
from .routes import router
from .services.sync import run_zabbix_sync

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    init_database(settings)
    if settings.auto_create_tables:
        await create_tables()
    app.state.http = httpx.AsyncClient()
    app.state.zabbix = ZabbixClient(settings=settings, client=app.state.http)
    app.state.sync_task = None
    app.state.sync_lock = asyncio.Lock()
    if settings.auto_sync_enabled and settings.zabbix_configured():
        app.state.sync_task = asyncio.create_task(sync_loop(app))
    try:
        yield
    finally:
        if app.state.sync_task:
            app.state.sync_task.cancel()
            try:
                await app.state.sync_task
            except asyncio.CancelledError:
                pass
        await app.state.http.aclose()
        await dispose_database()


async def sync_loop(app: FastAPI) -> None:
    settings = get_settings()
    while True:
        try:
            if SessionLocal is not None:
                async with app.state.sync_lock:
                    async with SessionLocal() as session:
                        await run_zabbix_sync(session, app.state.zabbix, settings)
        except Exception:
            logger.exception("Automatic Zabbix sync failed")
        await asyncio.sleep(settings.sync_interval_sec)


app = FastAPI(default_response_class=ORJSONResponse, lifespan=lifespan, title="Switch Topology")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(router, prefix="/network")

if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
if (STATIC_DIR / "assets").exists():
    app.mount("/network/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="network-assets")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/api/health")
async def api_health() -> dict[str, str]:
    return {"ok": "true"}


def index_response() -> FileResponse:
    return FileResponse(
        INDEX_FILE,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/")
async def index() -> Response:
    if INDEX_FILE.exists():
        return index_response()
    return HTMLResponse("<!doctype html><title>Switch Topology</title><h1>Switch Topology API</h1>")


@app.get("/network")
@app.get("/network/{path:path}")
async def network_spa(path: str = "") -> Response:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    if path.startswith("assets/"):
        raise HTTPException(status_code=404, detail="Not found")
    if INDEX_FILE.exists():
        return index_response()
    return HTMLResponse("<!doctype html><title>Switch Topology</title><h1>Switch Topology API</h1>")


@app.get("/{path:path}")
async def spa_fallback(path: str) -> Response:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    if INDEX_FILE.exists():
        return index_response()
    raise HTTPException(status_code=404, detail="Static frontend has not been built")
