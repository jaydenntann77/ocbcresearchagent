"""Hosted-mode gateway rules: password login, signed session cookies,
read-only admin in public mode, login throttling. Runs the gateway app in a
subprocess (its process policy must not leak into the test process)."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROBE = r'''
import json
from fastapi.testclient import TestClient
from app.gateway.service import app
c = TestClient(app, base_url="http://testserver")
r = {}
r["session_anon"] = c.get("/api/session").json()
r["conversations_anon"] = c.get("/api/conversations").status_code
r["meta_anon"] = c.get("/api/meta").status_code
r["wrong_pw"] = c.post("/api/login", json={"password": "nope"}).status_code
r["right_pw"] = c.post("/api/login", json={"password": "s3cret-demo"}).status_code
r["cookie_set"] = "ra_session" in c.cookies
r["session_after"] = c.get("/api/session").json()
r["admin_ingest"] = c.post("/api/admin/ingest", json={}).status_code
r["admin_schedule"] = c.put("/api/admin/schedule", json={"cron": "0 8 * * *"}).status_code
r["demo_toggle"] = c.post("/api/demo", json={"enabled": True}).status_code
r["model_switch"] = c.post("/api/conversations/c-0123456789ab/messages/m-0123456789ab/model-switch",
                         json={"confirm": True}).status_code
r["model_button"] = c.post("/api/model", json={"enabled": True}).status_code
forged = TestClient(app, base_url="http://testserver", cookies={"ra_session": "abc.deadbeef"})
r["forged_cookie"] = forged.get("/api/conversations").status_code
other = TestClient(app, base_url="http://testserver")
codes = [other.post("/api/login", json={"password": "x"}).status_code for _ in range(11)]
r["throttle_last"] = codes[-1]
r["index_public"] = c.get("/").status_code
r["memory_save"] = c.post("/api/memory/confirm", json={"name": "a", "company": "b", "description": "c",
                                                     "time": "d"}).status_code
print(json.dumps(r))
'''


def test_public_mode_gateway_rules():
    env = dict(os.environ, RA_PUBLIC_MODE="1", APP_PASSWORD="s3cret-demo", RA_SESSION_SECRET="test-secret",
               RA_TOKEN_ADMIN="a", RA_TOKEN_GATEWAY_ORCH="b", RA_TOKEN_GATEWAY_DOCS="c")
    proc = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    r = json.loads(proc.stdout.strip().splitlines()[-1])
    assert r["session_anon"] == {"authenticated": False, "password_required": True, "public_mode": True}
    assert r["conversations_anon"] == 401 and r["meta_anon"] == 401
    assert r["wrong_pw"] == 401
    assert r["right_pw"] == 200 and r["cookie_set"]
    assert r["session_after"]["authenticated"] is True
    assert r["admin_ingest"] == 403 and r["admin_schedule"] == 403  # read-only corpus when hosted
    assert r["demo_toggle"] == 403  # demo mode (pattern clients) cannot be switched on when hosted
    assert r["model_switch"] == 403  # the Claude API switch cannot be used when hosted
    assert r["model_button"] == 403
    assert r["forged_cookie"] == 401
    assert r["throttle_last"] == 429
    assert r["index_public"] == 200  # the login page itself loads
    assert r["memory_save"] == 403  # client memory stays off on the hosted demo unless enabled


MEMORY_PROBE = r'''
import json
from fastapi.testclient import TestClient
from app.gateway.service import app
with TestClient(app, base_url="http://testserver") as c:  # one event loop for every request
    c.post("/api/login", json={"password": "s3cret-demo"})
    body = {"name": "Jimmy", "company": "Harbourline", "description": "USD/SGD forecast", "time": "now"}
    resps = [c.post("/api/memory/confirm", json=body) for _ in range(4)]
    codes = [x.status_code for x in resps]
    details = [(x.json() or {}).get("detail", "") if x.headers.get("content-type", "").startswith("application/json")
               else "" for x in resps]
    r = {"codes": codes, "details": details, "demo": c.post("/api/demo", json={"enabled": True}).status_code,
         "model": c.post("/api/model", json={"enabled": True}).status_code}
print(json.dumps(r))
'''


def test_hosted_memory_opt_in_is_capped():
    """With RA_HOSTED_MEMORY=1 the gateway forwards saves up to the per-visitor cap, then answers 429. What
    the orchestrator replies depends on whether one is running (none: 503; a live one with other tokens: 403),
    so the test checks that the gateway itself did not refuse. Demo mode and the Claude switch stay blocked."""
    env = dict(os.environ, RA_PUBLIC_MODE="1", APP_PASSWORD="s3cret-demo", RA_SESSION_SECRET="test-secret",
               RA_HOSTED_MEMORY="1", RA_MEMORY_SAVES_PER_HOUR="3",
               RA_TOKEN_ADMIN="a", RA_TOKEN_GATEWAY_ORCH="b", RA_TOKEN_GATEWAY_DOCS="c")
    proc = subprocess.run([sys.executable, "-c", MEMORY_PROBE], cwd=ROOT, env=env, capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    r = json.loads(proc.stdout.strip().splitlines()[-1])
    for code, detail in zip(r["codes"][:3], r["details"][:3]):
        assert code != 429 and "disabled on the hosted demo" not in detail, r
    assert r["codes"][3] == 429, r
    assert r["demo"] == 403 and r["model"] == 403
