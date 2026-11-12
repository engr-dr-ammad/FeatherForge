import asyncio
import contextlib
import json
import os
import secrets
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from .store import Store
from .runtime import Runtime
from .providers import ROLES

ROOT = Path(__file__).resolve().parent.parent
store = Store(os.getenv("FORGE_DATA", str(ROOT / "data")))
runtime = Runtime(store)
TOKEN = os.getenv("FORGE_TOKEN", "")


@contextlib.asynccontextmanager
async def lifespan(app):
    # Single application process required: do not start uvicorn with multiple workers.
    import fcntl

    lock = open(store.root / "worker.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for t in [
        x
        for p in projects()
        for x in store.project(p["id"])["tasks"]
        if x["state"] == "running"
    ]:
        runtime.runner.cancel(t)
    store.recover()
    with store.db() as db:
        for name, instructions in ROLES.items():
            db.execute(
                "INSERT OR IGNORE INTO roles(name,instructions) VALUES(?,?)",
                (name, instructions),
            )
    thread = threading.Thread(target=runtime.loop, daemon=True)
    thread.start()
    app.state.worker = thread
    yield
    runtime.stop.set()
    thread.join(timeout=3)
    for p in projects():
        for t in store.project(p["id"])["tasks"]:
            if t["state"] == "running":
                runtime.cancel(t["id"])
    runtime.pool.shutdown(wait=False, cancel_futures=True)
    lock.close()


app = FastAPI(title="FeatherForge", lifespan=lifespan)


@app.middleware("http")
async def boundary(request: Request, call_next):
    if request.url.path.startswith("/api"):
        if TOKEN:
            supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
            if not secrets.compare_digest(supplied, TOKEN):
                return __import__(
                    "starlette.responses", fromlist=["JSONResponse"]
                ).JSONResponse({"detail": "Authentication required"}, 401)
        elif request.client and request.client.host not in (
            "127.0.0.1",
            "::1",
            "testclient",
        ):
            return __import__(
                "starlette.responses", fromlist=["JSONResponse"]
            ).JSONResponse({"detail": "Remote access requires FORGE_TOKEN"}, 403)
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return __import__(
                    "starlette.responses", fromlist=["JSONResponse"]
                ).JSONResponse({"detail": "Cross-origin mutation denied"}, 403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if "/artifact/" in request.url.path:
        response.headers["Content-Security-Policy"] = (
            "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'"
        )
    return response


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return __import__("starlette.responses", fromlist=["JSONResponse"]).JSONResponse(
        {"detail": str(exc)}, 400
    )


class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    brief: str = Field(min_length=10, max_length=12000)
    provider: str = "scripted"
    idempotency_key: str = Field(min_length=8, max_length=120)


@app.get("/")
def index():
    return FileResponse(ROOT / "static/index.html")


@app.get("/health")
def health():
    worker = getattr(app.state, "worker", None)
    running = bool(worker and worker.is_alive())
    return {
        "status": "ok" if running else "degraded",
        "worker_alive": running,
        "version": "0.1.0",
        "milestone": "local prototype",
    }


def display_endpoint():
    try:
        value = urlsplit(os.getenv("FORGE_MODEL_URL", "http://127.0.0.1:11434/v1"))
        host = value.hostname or ""
        if ":" in host:
            host = "[" + host + "]"
        if value.port:
            host += ":" + str(value.port)
        return urlunsplit((value.scheme, host, value.path, "", ""))
    except ValueError:
        return "[invalid endpoint]"


@app.get("/api/config")
def config():
    with store.db() as db:
        roles = [dict(r) for r in db.execute("SELECT * FROM roles")]
    return {
        "roles": roles,
        "model": os.getenv("FORGE_MODEL", "qwen2.5-coder:7b"),
        "model_url": display_endpoint(),
        "concurrency": runtime.pool._max_workers,
        "retry_limit": 2,
        "executor": runtime.runner.image,
        "starter": os.getenv("FORGE_STARTER"),
        "training_collection": False,
        "featherlm": "experimental, evaluation-only; not qualified for implementation",
    }


@app.get("/api/projects")
def projects():
    with store.db() as db:
        return [
            dict(r) for r in db.execute("SELECT * FROM projects ORDER BY created DESC")
        ]


@app.post("/api/projects")
def create(body: ProjectIn):
    if body.provider not in ("scripted", "local"):
        raise ValueError("Unknown provider")
    pid = store.create(body.title, body.brief, body.provider, body.idempotency_key)
    return store.project(pid)


@app.get("/api/projects/{pid}")
def project(pid: str):
    return store.project(pid)


@app.post("/api/projects/{pid}/plan")
def plan(pid: str):
    return runtime.plan(pid)


@app.post("/api/projects/{pid}/approve")
def approve(pid: str):
    runtime.approve(pid)
    return store.project(pid)


@app.post("/api/projects/{pid}/pause")
def pause(pid: str):
    p = store.project(pid)
    with store.db() as db:
        db.execute(
            "UPDATE projects SET paused=? WHERE id=?", (int(not p["paused"]), pid)
        )
        store.event(
            db,
            pid,
            None,
            "pause",
            "Scheduling "
            + ("resumed" if p["paused"] else "paused; in-flight tasks continue"),
        )
    return store.project(pid)


class TaskEdit(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    role: str
    acceptance: list[str] = Field(min_length=1, max_length=20)


@app.patch("/api/tasks/{tid}")
def edit(tid: str, body: TaskEdit):
    t = store.task(tid)
    p = store.project(t["project"])
    if p["approved"]:
        raise ValueError(
            "Task scope is frozen after approval; create a revised project to resolve requirement changes"
        )
    if body.role not in ROLES:
        raise ValueError("Unknown role")
    if (
        t["kind"] == "qa"
        and body.role != "qa"
        or t["kind"] == "review"
        and body.role != "reviewer"
    ):
        raise ValueError("QA and review permissions require their dedicated roles")
    if t["kind"] == "implementation" and body.role not in ("frontend", "backend"):
        raise ValueError("Implementation requires frontend or backend role")
    store.update(tid, title=body.title, role=body.role, acceptance=body.acceptance)
    return store.task(tid)


@app.post("/api/tasks/{tid}/{action}")
def action(tid: str, action: str):
    if action == "cancel":
        runtime.cancel(tid)
    elif action == "retry":
        runtime.retry(tid)
    else:
        raise ValueError("Unknown action")
    return store.task(tid)


class RoleEdit(BaseModel):
    enabled: bool
    instructions: str = Field(min_length=1, max_length=6000)


@app.put("/api/roles/{name}")
def role(name: str, body: RoleEdit):
    if name not in ROLES:
        raise ValueError("Unknown role")
    with store.db() as db:
        db.execute(
            "UPDATE roles SET enabled=?,instructions=? WHERE name=?",
            (int(body.enabled), body.instructions, name),
        )
    return {"name": name, **body.model_dump()}


@app.get("/api/tasks/{tid}/artifact/{filename:path}")
def artifact(tid: str, filename: str):
    t = store.task(tid)
    if not t["workspace"]:
        raise HTTPException(404, "No deliverable yet")
    base = Path(t["workspace"]).resolve()
    path = (base / filename).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(path)


@app.get("/api/projects/{pid}/events")
async def events(pid: str, request: Request):
    store.project(pid)

    async def stream():
        last = 0
        while not await request.is_disconnected():
            with store.db() as db:
                rows = [
                    dict(r)
                    for r in db.execute(
                        "SELECT * FROM events WHERE project=? AND id>? ORDER BY id",
                        (pid, last),
                    )
                ]
            for row in rows:
                last = row["id"]
                yield "data: " + json.dumps(row) + "\n\n"
            if not rows:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream")
