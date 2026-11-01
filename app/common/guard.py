"""Process-level access guards built on CPython audit hooks (PEP 578).

Each service process calls `install(...)` at startup with its own policy.
Audit hooks cannot be removed once installed, so code running later in the
process (including model-driven code paths) cannot lift the restriction.

This is defence in depth on top of the primary boundaries:
  * every agent role runs in its own OS process;
  * the orchestrator process is never given corpus paths, index handles or
    retrieval credentials - it can only call narrow HTTP endpoints;
  * services authenticate each other with per-launch scoped tokens.
For production, also run each service under its own OS account with
filesystem ACLs and an egress firewall (documented in README).
"""
from __future__ import annotations

import ipaddress
import os
import socket
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path


class AccessDenied(PermissionError):
    pass


@dataclass
class Policy:
    role: str
    # Filesystem: any path under a denied root is refused unless it is also
    # under an allowed root (more specific allow wins).
    denied_roots: list[Path] = field(default_factory=list)
    allowed_roots: list[Path] = field(default_factory=list)
    read_only_roots: list[Path] = field(default_factory=list)
    # Network: hostnames that may be resolved. Loopback is always allowed.
    allowed_hosts: set[str] = field(default_factory=set)
    # If set, loopback connections to any other *service* port (config.PORTS)
    # are refused - e.g. the orchestrator may reach only the research and
    # validator services. Ephemeral loopback ports (asyncio self-pipes) are
    # unaffected because no service listens there.
    allowed_loopback_ports: set[int] | None = None
    # Module prefixes that must never be imported in this process.
    blocked_modules: tuple[str, ...] = ()
    block_subprocess: bool = True


_state = threading.local()
_installed: Policy | None = None
_resolved_ips: set[str] = set()
_violations: list[str] = []


def violations() -> list[str]:
    return list(_violations)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _norm(p) -> Path | None:
    if isinstance(p, int):
        return None
    try:
        p = os.fsdecode(p)
    except TypeError:
        return None
    try:
        return Path(os.path.abspath(p))
    except (OSError, ValueError):
        return None


def _deny(msg: str):
    _violations.append(msg)
    raise AccessDenied(f"[{_installed.role}] {msg}")


def _check_path(raw, write: bool):
    pol = _installed
    path = _norm(raw)
    if path is None:
        return
    for root in pol.denied_roots:
        if _is_under(path, root):
            if any(_is_under(path, a) for a in pol.allowed_roots):
                break
            _deny(f"filesystem access to {path} is not permitted for this agent")
    if write:
        for root in pol.read_only_roots:
            if _is_under(path, root):
                _deny(f"write access to {path} is not permitted (read-only)")


def _service_ports() -> set[int]:
    from app.common import config
    return set(config.PORTS.values())


def _is_loopback(host: str) -> bool:
    if host in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _hook(event: str, args):
    pol = _installed
    if pol is None or getattr(_state, "busy", False):
        return
    _state.busy = True
    try:
        if event == "open":
            path, mode, flags = args
            write = False
            if isinstance(mode, str):
                write = any(c in mode for c in "wax+")
            elif isinstance(flags, int):
                write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND))
            _check_path(path, write)
        elif event == "sqlite3.connect":
            # SQLite opens files through its own C VFS (no 'open' event), so
            # check the database path here. URIs: file:<path>?mode=...
            db = args[0] if args else None
            if isinstance(db, (str, bytes, os.PathLike)):
                db = os.fsdecode(db)
                read_only = db.startswith("file:") and "mode=ro" in db
                if db.startswith("file:"):
                    db = db[5:].split("?", 1)[0]
                if db and db != ":memory:":
                    _check_path(db, not read_only)
        elif event in ("os.listdir", "os.scandir"):
            _check_path(args[0] if args else ".", False)
        elif event in ("os.remove", "os.rename", "os.mkdir", "os.rmdir"):
            _check_path(args[0], True)
        elif event == "socket.getaddrinfo":
            host = args[0]
            if isinstance(host, bytes):
                host = host.decode()
            if host and not _is_loopback(str(host)) and str(host).lower() not in pol.allowed_hosts:
                _deny(f"network access to {host} is not permitted for this agent")
        elif event == "socket.connect":
            addr = args[1]
            if isinstance(addr, tuple) and addr:
                host = str(addr[0])
                if _is_loopback(host) and pol.allowed_loopback_ports is not None and len(addr) > 1                         and int(addr[1]) in _service_ports() and int(addr[1]) not in pol.allowed_loopback_ports:
                    _deny(f"loopback connection to port {addr[1]} is not permitted for this agent")
                if not _is_loopback(host) and host not in _resolved_ips:
                    # Allow IPs that resolved from an allow-listed hostname.
                    allowed_ips = set()
                    for h in pol.allowed_hosts:
                        try:
                            allowed_ips.update(i[4][0] for i in socket.getaddrinfo(h, None))
                        except OSError:
                            pass
                    _resolved_ips.update(allowed_ips)
                    if host not in allowed_ips:
                        _deny(f"network connection to {host} is not permitted for this agent")
        elif event == "import":
            name = args[0]
            if pol.blocked_modules and any(name == m or name.startswith(m + ".") for m in pol.blocked_modules):
                _deny(f"module {name} is not available to this agent")
        elif pol.block_subprocess and event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn",
                                               "os.spawn", "os.startfile"):
            _deny(f"process execution ({event}) is not permitted for this agent")
    finally:
        _state.busy = False


class _ImportBlocker:
    """sys.meta_path finder that refuses blocked modules (the 'import' audit
    event alone does not cover every submodule import path)."""

    @staticmethod
    def find_spec(name, path=None, target=None):
        pol = _installed
        if pol and pol.blocked_modules and any(name == m or name.startswith(m + ".") for m in pol.blocked_modules):
            _violations.append(f"import {name}")
            raise ImportError(f"[{pol.role}] module {name} is not available to this agent")
        return None


def install(policy: Policy) -> None:
    global _installed
    if _installed is not None:
        raise RuntimeError("guard already installed")
    policy.allowed_hosts = {h.lower() for h in policy.allowed_hosts}
    _installed = policy
    # Unload any already-imported blocked modules so they cannot be reached
    # through sys.modules either.
    for name in list(sys.modules):
        if policy.blocked_modules and any(name == m or name.startswith(m + ".") for m in policy.blocked_modules):
            del sys.modules[name]
    sys.meta_path.insert(0, _ImportBlocker)
    sys.addaudithook(_hook)


def current_policy() -> Policy | None:
    return _installed
