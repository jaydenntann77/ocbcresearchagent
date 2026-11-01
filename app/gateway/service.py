"""User-facing gateway (port 8000, bound to 127.0.0.1).

Serves the frontend and proxies a fixed set of routes:
  /api/chat, /api/meta, /api/conversations*  -> conversation API (orchestrator)
  /api/docs/*                                -> document viewer
  /api/admin/*                               -> ingestion admin
There is no route to the specialist or validator services, so specialist
output can reach the user only after the orchestrator has validated it."""
from __future__ import annotations

from app.common import config, guard

guard.install(guard.Policy(
    role="gateway",
    denied_roots=[config.DATA_DIR],
    allowed_hosts=set(),
    allowed_loopback_ports={config.PORTS["orchestrator"], config.PORTS["docs"], config.PORTS["ingestion"]},
))

import re  # noqa: E402

import httpx  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, Response, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

app = FastAPI(title="Research workspace gateway", docs_url=None, redoc_url=None, openapi_url=None)
client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0))
ORCH = config.service_url("orchestrator")
DOCS = config.service_url("docs")
ADMIN = config.service_url("ingestion")
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; frame-src 'self'; object-src 'self'; "
       "connect-src 'self'; base-uri 'none'; form-action 'self'")


@app.middleware("http")
async def headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/static/") or request.url.path in ("/", "/admin"):
        resp.headers["Cache-Control"] = "no-cache"
    if not request.url.path.startswith("/api/docs/"):
        resp.headers["X-Frame-Options"] = "DENY"
    return resp


async def _proxy(request: Request, url: str, token: str | None, stream: bool = False):
    body = await request.body()
    headers = {"Authorization": f"Bearer {token or ''}"}
    if request.headers.get("content-type"):
        headers["Content-Type"] = request.headers["content-type"]
    try:
        req = client.build_request(request.method, url, content=body, headers=headers, params=request.query_params)
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError:
        raise HTTPException(503, "service unavailable")
    if stream:
        async def gen():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()
        return StreamingResponse(gen(), status_code=upstream.status_code,
                                 media_type=upstream.headers.get("content-type"),
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    content = await upstream.aread()
    await upstream.aclose()
    keep = {k: v for k, v in upstream.headers.items() if k.lower() in ("content-type", "content-disposition", "cache-control")}
    return Response(content, status_code=upstream.status_code, headers=keep)


@app.post("/api/chat")
async def chat(request: Request):
    return await _proxy(request, f"{ORCH}/v1/chat", config.TOKEN_GATEWAY_ORCH, stream=True)


@app.get("/api/meta")
async def meta(request: Request):
    return await _proxy(request, f"{ORCH}/v1/meta", config.TOKEN_GATEWAY_ORCH)


@app.api_route("/api/conversations", methods=["GET"])
@app.api_route("/api/conversations/{cid}", methods=["GET", "DELETE"])
async def convs(request: Request, cid: str | None = None):
    if cid and not re.fullmatch(r"c-[a-f0-9]{12}", cid):
        raise HTTPException(400, "invalid id")
    return await _proxy(request, f"{ORCH}/v1/conversations" + (f"/{cid}" if cid else ""), config.TOKEN_GATEWAY_ORCH)


@app.get("/api/docs/{path:path}")
async def docs(request: Request, path: str):
    if not re.fullmatch(r"[a-z0-9\-]+(/pdf|/pages/\d{1,4}\.png)?", path):
        raise HTTPException(400, "invalid path")
    return await _proxy(request, f"{DOCS}/v1/documents/{path}", config.TOKEN_GATEWAY_DOCS)


@app.api_route("/api/admin/{path}", methods=["GET", "POST", "PUT"])
async def admin(request: Request, path: str):
    if path not in ("status", "ingest", "schedule"):
        raise HTTPException(404, "not found")
    return await _proxy(request, f"{ADMIN}/v1/{path}", config.TOKEN_ADMIN)


@app.get("/")
@app.get("/admin")
async def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")
