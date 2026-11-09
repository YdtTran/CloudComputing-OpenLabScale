from __future__ import annotations

import asyncio
import fcntl
import os
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request as HTTPRequest, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .engine import Engine
from .models import Request, Session, Settings, State, now
from .scheduler import Entry, Scheduler
from .terminal import bridge


def create_app(settings: Optional[Settings] = None, engine=None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        lock = None
        manager = engine
        try:
            if manager is None:
                if not os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock").startswith("unix://"):
                    raise RuntimeError("OpenLabScale requires a local Unix Docker socket")
                directory = Path.home() / ".cache" / "openlabscale"
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                lock = (directory / (settings.deployment + ".lock")).open("a")
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                pending = directory / settings.deployment
                pending.mkdir(mode=0o700, exist_ok=True)
                manager = await asyncio.to_thread(Engine, settings, pending=pending)
            await asyncio.to_thread(manager.reconcile)
            if engine is None:
                await asyncio.to_thread(manager.check_runtime)
            scheduler = Scheduler(settings, manager)
            app.state.scheduler = scheduler
            app.state.stats_lock = asyncio.Lock()
            app.state.previous_host = None
            worker = asyncio.create_task(scheduler.run())
            app.state.worker = worker
            try:
                yield
            finally:
                scheduler.stopping = True
                scheduler.wake.set()
                await worker
        finally:
            if engine is None and manager is not None:
                await asyncio.to_thread(manager.client.close)
            if lock:
                lock.close()

    app = FastAPI(title="OpenLabScale", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: HTTPRequest, error: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": "Invalid request", "errors": [
            {"location": list(item["loc"]), "message": item["msg"]} for item in error.errors()
        ]})

    def identity(request: HTTPRequest) -> str:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        owner = settings.tokens.get(token) if scheme.lower() == "bearer" else None
        if owner is None:
            raise HTTPException(401, "Valid demo bearer token required", headers={"WWW-Authenticate": "Bearer"})
        return owner

    def owned(request: HTTPRequest, session_id: str) -> Entry:
        owner = identity(request)
        entry = app.state.scheduler.sessions.get(session_id)
        if entry is None or entry.session.owner != owner:
            raise HTTPException(404, "Session not found")
        return entry

    @app.post("/sessions", response_model=Session, status_code=202)
    async def submit(body: Request, request: HTTPRequest):
        owner = identity(request)
        scheduler = app.state.scheduler
        if not scheduler.healthy or app.state.worker.done():
            raise HTTPException(503, "Docker unavailable")
        try:
            return scheduler.submit(owner, body)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.get("/sessions", response_model=list[Session])
    async def sessions(request: HTTPRequest):
        owner = identity(request)
        scheduler = app.state.scheduler
        return [scheduler.snapshot(entry) for entry in scheduler.sessions.values() if entry.session.owner == owner]

    @app.get("/sessions/{session_id}", response_model=Session)
    async def session(session_id: str, request: HTTPRequest):
        return app.state.scheduler.snapshot(owned(request, session_id))

    @app.delete("/sessions/{session_id}", response_model=Session, status_code=202)
    async def release(session_id: str, request: HTTPRequest):
        entry = owned(request, session_id)
        app.state.scheduler.release(entry)
        return app.state.scheduler.snapshot(entry)

    @app.get("/health")
    async def health():
        scheduler = app.state.scheduler
        if not scheduler.healthy or scheduler.stopping or app.state.worker.done():
            raise HTTPException(503, "Scheduler unavailable")
        return {"status": "ok"}

    @app.get("/stats")
    async def stats(request: HTTPRequest):
        if identity(request) != settings.admin:
            raise HTTPException(403, "Administrator required")
        scheduler = app.state.scheduler
        async with app.state.stats_lock:
            telemetry = await asyncio.to_thread(scheduler.docker.telemetry)
            host = telemetry.get("host")
            if host and host.get("available"):
                previous = app.state.previous_host
                current = host["cpu_total_ticks"], host["cpu_idle_ticks"]
                app.state.previous_host = current
                host["cpu_utilization_pct"] = None
                if previous and current[0] > previous[0]:
                    total = current[0] - previous[0]
                    idle = current[1] - previous[1]
                    if 0 <= idle <= total:
                        host["cpu_utilization_pct"] = 100 * (total - idle) / total
        counts = Counter(e.session.state for e in scheduler.sessions.values())
        return {
            "sampled_at": now(), "total_sessions": len(scheduler.sessions),
            "counts": {state.value: counts[state] for state in State},
            "queue": list(scheduler.queue),
            "sessions": [scheduler.snapshot(entry) for entry in scheduler.sessions.values()],
            "headroom": {"cpu_millis": settings.headroom_cpu_millis, "memory_mib": settings.headroom_memory_mib},
            **scheduler.capacity(), **telemetry,
        }

    @app.websocket("/sessions/{session_id}/terminal")
    async def terminal(websocket: WebSocket, session_id: str):
        scheduler = app.state.scheduler
        protocols = websocket.scope["subprotocols"]
        credential = next((p.removeprefix("auth.") for p in protocols if p.startswith("auth.")), "")
        owner = settings.tokens.get(credential)
        entry = scheduler.sessions.get(session_id)
        origin = websocket.headers.get("origin")
        if ("openlabscale" not in protocols or owner is None or entry is None
                or owner != entry.session.owner or entry.session.state != State.RUNNING
                or entry.terminal_attached or (origin is not None and origin != settings.terminal_origin)):
            await websocket.close(code=1008)
            return
        entry.terminal_attached = True
        await bridge(websocket, entry, scheduler.docker)

    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")

    return app
