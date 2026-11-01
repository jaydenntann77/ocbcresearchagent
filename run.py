"""Launch every service as a separate process with per-launch credentials.

    python run.py            # start all services; open http://127.0.0.1:8000
    python run.py --check    # start, wait for health checks, then exit
    python run.py --stop     # stop services started by a previous launch

Each process receives only the tokens it needs:
  gateway      -> orchestrator, docs, admin tokens
  orchestrator -> gateway->orch token (to verify), research task token, validator token, model key (if any)
  research     -> research task token, evidence signing key
  validator    -> validator token, evidence signing key
  docs         -> docs token
  ingestion    -> admin token
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time

import httpx

from app.common import config

SERVICES = ["research", "validator", "docs", "ingestion", "orchestrator", "gateway"]
MODULES = {
    "research": "app.research.service:app", "validator": "app.validator.service:app", "docs": "app.docs.service:app",
    "ingestion": "app.ingestion.service:app", "orchestrator": "app.orchestrator.service:app",
    "gateway": "app.gateway.service:app",
}
SECRETS_FOR = {
    "gateway": ["RA_TOKEN_GATEWAY_ORCH", "RA_TOKEN_GATEWAY_DOCS", "RA_TOKEN_ADMIN", "RA_SESSION_SECRET", "APP_PASSWORD"],
    "orchestrator": ["RA_TOKEN_GATEWAY_ORCH", "RA_TOKEN_ORCH_RESEARCH", "RA_TOKEN_ORCH_VALIDATOR", "ANTHROPIC_API_KEY",
                     "ANTHROPIC_AUTH_TOKEN"],
    "research": ["RA_TOKEN_ORCH_RESEARCH", "RA_EVIDENCE_SIGNING_KEY"],
    "validator": ["RA_TOKEN_ORCH_VALIDATOR", "RA_EVIDENCE_SIGNING_KEY"],
    "docs": ["RA_TOKEN_GATEWAY_DOCS"],
    "ingestion": ["RA_TOKEN_ADMIN"],
}
ALL_SECRETS = {s for v in SECRETS_FOR.values() for s in v}


PID_FILE = config.DATA_DIR / "run.pids"


def stop_previous() -> int:
    """Stop service processes recorded by an earlier launch (on Windows,
    killing run.py does not stop its children)."""
    if not PID_FILE.exists():
        return 0
    n = 0
    for line in PID_FILE.read_text().split():
        try:
            pid = int(line)
            if os.name == "nt":
                r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
                n += r.returncode == 0
            else:
                os.kill(pid, 15)
                n += 1
        except (ValueError, OSError):
            pass
    PID_FILE.unlink(missing_ok=True)
    return n


def port_busy(port: int) -> bool:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    if "--stop" in sys.argv:
        print(f"stopped {stop_previous()} service process(es)")
        return
    check_only = "--check" in sys.argv
    stop_previous()
    for _ in range(20):  # give stopped processes time to release their ports
        busy = [f"{n}:{config.PORTS[n]}" for n in SERVICES if port_busy(config.PORTS[n])]
        if not busy:
            break
        time.sleep(0.5)
    if busy:
        raise SystemExit(f"ports already in use ({', '.join(busy)}). Stop the other instance (python run.py --stop) "
                         f"or change RA_*_PORT in .env.")
    secrets_env = {k: secrets.token_urlsafe(32) for k in ALL_SECRETS if k.startswith("RA_")}
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "APP_PASSWORD"):
        if os.environ.get(k):
            secrets_env[k] = os.environ[k]
    procs = {}

    def launch(name):
        env = {k: v for k, v in os.environ.items() if k not in ALL_SECRETS}
        env.update({k: secrets_env[k] for k in SECRETS_FOR[name] if k in secrets_env})
        env["HF_HUB_OFFLINE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        host = config.GATEWAY_HOST if name == "gateway" else "127.0.0.1"  # only the gateway may face the network
        cmd = [sys.executable, "-m", "uvicorn", MODULES[name], "--host", host, "--port",
               str(config.PORTS[name]), "--log-level", "warning"]
        procs[name] = subprocess.Popen(cmd, env=env, cwd=str(config.ROOT))
        print(f"started {name:<12} pid={procs[name].pid} port={config.PORTS[name]}")
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Supervisor first, so --stop can take down the whole tree before it
        # gets a chance to restart a service.
        PID_FILE.write_text(" ".join([str(os.getpid())] + [str(p.pid) for p in procs.values()]))

    for name in SERVICES:
        launch(name)
    deadline = time.time() + 90
    healthy = set()
    while time.time() < deadline and len(healthy) < len(SERVICES):
        for name in SERVICES:
            if name in healthy:
                continue
            if procs[name].poll() is not None:
                print(f"!! {name} exited with code {procs[name].returncode}")
                healthy.add(name)
                continue
            try:
                path = "/" if name == "gateway" else "/v1/health"
                if httpx.get(f"{config.service_url(name)}{path}", timeout=2).status_code == 200:
                    healthy.add(name)
                    print(f"healthy {name}")
            except httpx.HTTPError:
                pass
        time.sleep(0.5)
    print(f"\nResearch workspace: http://127.0.0.1:{config.PORTS['gateway']}/   "
          f"(corpus status: http://127.0.0.1:{config.PORTS['gateway']}/admin)")
    if not config.model_credentials_present():
        print("Model credential not configured: running in extractive mode (set ANTHROPIC_API_KEY in .env to enable "
              "model-assisted synthesis).")
    if check_only:
        for p in procs.values():
            p.terminate()
        return
    # Supervise: a crashed service is restarted (at most 3 times); the others
    # keep serving and the UI shows that service's failure as an error state.
    supervise = os.environ.get("RA_SUPERVISE", "1") != "0"
    restarts = {n: 0 for n in SERVICES}
    try:
        while True:
            time.sleep(1)
            for name, p in list(procs.items()):
                if p.poll() is None or restarts[name] < 0:
                    continue
                if supervise and restarts[name] < 3:
                    restarts[name] += 1
                    print(f"!! {name} exited (code {p.returncode}); restart {restarts[name]}/3")
                    time.sleep(2 * restarts[name])
                    launch(name)
                else:
                    print(f"!! {name} is down; other services keep running")
                    restarts[name] = -1
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs.values():
            if p.poll() is None:
                p.terminate()
        for p in procs.values():
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
