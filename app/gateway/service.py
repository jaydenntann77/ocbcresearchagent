"""User-facing gateway (port 8000; 0.0.0.0:7860 when hosted).

Serves the frontend and proxies a fixed set of routes:
  /api/chat, /api/meta, /api/conversations*  -> conversation API (orchestrator),
                                               incl. picking the client and logging a confirmed
                                               client interaction
  /api/memory/confirm                        -> client memory save (orchestrator)
  /api/docs/*                                -> document viewer
  /api/admin/*                               -> ingestion admin
There is no route to the specialist or validator services, so specialist
output can reach the user only after the orchestrator has validated it.

Visitor access: an optional shared password (APP_PASSWORD) behind a login
form, a signed session cookie that scopes conversation history to each
visitor, per-visitor chat rate limits, and - in public mode - a read-only
admin view (no crawling or schedule changes)."""
from __future__ import annotations

from app.common import config, guard

guard.install(guard.Policy(
    role="gateway",
    denied_roots=[config.DATA_DIR],
    allowed_hosts=set(),
    allowed_loopback_ports={config.PORTS["orchestrator"], config.PORTS["docs"], config.PORTS["ingestion"]},
))

import hashlib  # noqa: E402
import hmac  # noqa: E402
import re  # noqa: E402
import secrets  # noqa: E402
import time  # noqa: E402
from collections import defaultdict, deque  # noqa: E402

import httpx  # noqa: E402
from fastapi import Body, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

app = FastAPI(title="Research workspace gateway", docs_url=None, redoc_url=None, openapi_url=None)
client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0))
ORCH = config.service_url("orchestrator")
DOCS = config.service_url("docs")
ADMIN = config.service_url("ingestion")
SESSION_KEY = (config.SESSION_SECRET or secrets.token_urlsafe(32)).encode()
COOKIE = "ra_session"
OPEN_PATHS = {"/api/session", "/api/login", "/api/logout"}
# Hugging Face shows a Space inside an iframe on huggingface.co; allow that
# embedding only in public mode.
FRAME_ANCESTORS = "'self' https://huggingface.co https://*.hf.space" if config.PUBLIC_MODE else "'none'"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; frame-src 'self'; object-src 'self'; "
       f"connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors {FRAME_ANCESTORS}")

_chat_hits: dict[str, deque] = defaultdict(deque)
_login_failures: dict[str, deque] = defaultdict(deque)


# ------------------------------------------------------------------ sessions
def _sign(sid: str) -> str:
    return hmac.new(SESSION_KEY, sid.encode(), hashlib.sha256).hexdigest()[:32]


def _session(request: Request) -> str | None:
    raw = request.cookies.get(COOKIE) or ""
    sid, _, sig = raw.partition(".")
    if sid and sig and hmac.compare_digest(sig, _sign(sid)):
        return sid
    return None


def _set_session(resp: Response, request: Request, sid: str):
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    resp.set_cookie(COOKIE, f"{sid}.{_sign(sid)}", max_age=7 * 24 * 3600, httponly=True, path="/",
                    secure=https, samesite="none" if https else "lax")


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _hit(bucket: dict, key: str, window: float, limit: int) -> bool:
    """Record a hit; return False when `limit` hits already fall inside `window` seconds."""
    now = time.monotonic()
    q = bucket[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


@app.middleware("http")
async def access_and_headers(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in OPEN_PATHS:
        sid = _session(request)
        if sid is None and config.APP_PASSWORD:
            return JSONResponse({"detail": "login required"}, status_code=401)
        request.state.sid = sid
    resp = await call_next(request)
    if path.startswith("/api/") and path not in OPEN_PATHS and getattr(request.state, "new_sid", None):
        _set_session(resp, request, request.state.new_sid)
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if path.startswith("/static/") or path in ("/", "/admin"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def _sid(request: Request) -> str:
    """Visitor session id; anonymous visitors (no password configured) get one on first use."""
    sid = getattr(request.state, "sid", None)
    if not sid:
        sid = secrets.token_hex(12)
        request.state.sid = sid
        request.state.new_sid = sid
    return sid


@app.get("/api/session")
async def session(request: Request):
    return {"authenticated": bool(_session(request)) or not config.APP_PASSWORD,
            "password_required": bool(config.APP_PASSWORD), "public_mode": config.PUBLIC_MODE}


@app.post("/api/login")
async def login(request: Request, payload: dict = Body(...)):
    ip = _client_ip(request)
    if not config.APP_PASSWORD:
        resp = JSONResponse({"ok": True})
        _set_session(resp, request, _session(request) or secrets.token_hex(12))
        return resp
    now = time.monotonic()
    fails = _login_failures[ip]
    while fails and now - fails[0] > 900:
        fails.popleft()
    if len(fails) >= 10:
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    if not hmac.compare_digest(str(payload.get("password", "")).encode(), config.APP_PASSWORD.encode()):
        fails.append(now)
        raise HTTPException(401, "Incorrect password.")
    resp = JSONResponse({"ok": True})
    _set_session(resp, request, secrets.token_hex(12))
    return resp


@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


async def _proxy(request: Request, url: str, token: str | None, stream: bool = False):
    body = await request.body()
    headers = {"Authorization": f"Bearer {token or ''}", "X-RA-Session": _sid(request)}
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
    limit = config.CHAT_RATE_PER_HOUR
    if config.PUBLIC_MODE and not (_hit(_chat_hits, "sid:" + _sid(request), 3600, limit)
                                   and _hit(_chat_hits, "ip:" + _client_ip(request), 3600, limit * 3)):
        raise HTTPException(429, f"Question limit reached ({limit} per hour). Please try again later.")
    return await _proxy(request, f"{ORCH}/v1/chat", config.TOKEN_GATEWAY_ORCH, stream=True)


@app.get("/api/meta")
async def meta(request: Request):
    return await _proxy(request, f"{ORCH}/v1/meta", config.TOKEN_GATEWAY_ORCH)

@app.post("/api/memory/confirm")
async def memory_confirm(request: Request):
    if config.PUBLIC_MODE:
        raise HTTPException(403, "Client memory is disabled on the hosted demo.")
    return await _proxy(request, f"{ORCH}/v1/memory/confirm", config.TOKEN_GATEWAY_ORCH)

@app.api_route("/api/conversations", methods=["GET"])
@app.api_route("/api/conversations/{cid}", methods=["GET", "DELETE"])
async def convs(request: Request, cid: str | None = None):
    if cid and not re.fullmatch(r"c-[a-f0-9]{12}", cid):
        raise HTTPException(400, "invalid id")
    return await _proxy(request, f"{ORCH}/v1/conversations" + (f"/{cid}" if cid else ""), config.TOKEN_GATEWAY_ORCH)


@app.post("/api/model")
async def model_mode(request: Request):
    """Extractive / Claude API mode button (local only; the switch does not exist when hosted)."""
    if config.PUBLIC_MODE:
        raise HTTPException(403, "Switching the Claude API is not available on the hosted demo.")
    return await _proxy(request, f"{ORCH}/v1/model", config.TOKEN_GATEWAY_ORCH)


@app.api_route("/api/demo", methods=["GET", "POST"])
async def demo(request: Request):
    """Demo mode (pattern clients T01-T04). Local only: switching it is refused when hosted."""
    if config.PUBLIC_MODE and request.method != "GET":
        raise HTTPException(403, "Demo mode is not available on the hosted demo.")
    return await _proxy(request, f"{ORCH}/v1/demo", config.TOKEN_GATEWAY_ORCH)


@app.post("/api/conversations/{cid}/messages/{mid}/{action}")
async def client_action(request: Request, cid: str, mid: str, action: str):
    if action not in ("client-log", "client-pick", "model-switch"):
        raise HTTPException(404, "not found")
    if action == "model-switch" and config.PUBLIC_MODE:
        raise HTTPException(403, "Switching the Claude API is not available on the hosted demo.")
    if not (re.fullmatch(r"c-[a-f0-9]{12}", cid) and re.fullmatch(r"m-[a-f0-9]{12}", mid)):
        raise HTTPException(400, "invalid id")
    return await _proxy(request, f"{ORCH}/v1/conversations/{cid}/messages/{mid}/{action}", config.TOKEN_GATEWAY_ORCH)


@app.get("/api/docs/{path:path}")
async def docs(request: Request, path: str):
    if not re.fullmatch(r"[a-z0-9\-]+(/pdf|/pages/\d{1,4}\.png)?", path):
        raise HTTPException(400, "invalid path")
    return await _proxy(request, f"{DOCS}/v1/documents/{path}", config.TOKEN_GATEWAY_DOCS)


@app.api_route("/api/admin/{path}", methods=["GET", "POST", "PUT"])
async def admin(request: Request, path: str):
    if path not in ("status", "ingest", "schedule"):
        raise HTTPException(404, "not found")
    if config.PUBLIC_MODE and request.method != "GET":
        raise HTTPException(403, "Ingestion and scheduling are disabled on the hosted demo; the corpus is read-only.")
    return await _proxy(request, f"{ADMIN}/v1/{path}", config.TOKEN_ADMIN)


@app.get("/")
@app.get("/admin")
async def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")
