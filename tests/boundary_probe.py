"""Subprocess probe: install a service's access policy (by importing the
service module exactly as uvicorn would) and attempt forbidden operations.
Prints a JSON map of attempt -> outcome. Used by tests/test_boundaries.py."""
from __future__ import annotations

import importlib
import json
import os
import sys


def attempt(fn):
    try:
        fn()
        return "ALLOWED"
    except PermissionError as exc:
        return f"DENIED: {exc}"
    except ImportError as exc:
        return f"DENIED(import): {exc}"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "not permitted" in msg or "not available to this agent" in msg:
            return f"DENIED: {msg}"
        return f"ERROR {type(exc).__name__}: {msg}"


def main(role: str):
    module = {"orchestrator": "app.orchestrator.service", "research": "app.research.service",
              "gateway": "app.gateway.service"}[role]
    importlib.import_module(module)
    from app.common import config
    import socket
    import sqlite3
    import subprocess
    res = {}
    raw = next(config.RAW_DIR.glob("*.pdf"), config.RAW_DIR / "x.pdf")
    res["read_raw_pdf"] = attempt(lambda: open(raw, "rb").read(10))
    res["list_raw_dir"] = attempt(lambda: os.listdir(config.RAW_DIR))
    res["read_corpus_db_file"] = attempt(lambda: open(config.META_DB, "rb").read(10))
    res["sqlite_corpus_db"] = attempt(lambda: sqlite3.connect(f"file:{config.META_DB.as_posix()}?mode=ro", uri=True)
                                      .execute("select count(*) from chunks").fetchone())
    coll = next(config.COLLECTIONS_DIR.glob("fx-*.db"), config.COLLECTIONS_DIR / "fx.db")
    res["sqlite_collection"] = attempt(lambda: sqlite3.connect(f"file:{coll.as_posix()}?mode=ro", uri=True)
                                       .execute("select count(*) from chunks").fetchone())
    res["import_pdf_lib"] = attempt(lambda: importlib.import_module("fitz"))
    res["import_retrieval"] = attempt(lambda: importlib.import_module("app.research.collections"))
    res["import_embeddings"] = attempt(lambda: importlib.import_module("app.common.embedding"))
    res["web_ocbc"] = attempt(lambda: socket.getaddrinfo("www.ocbc.com", 443))
    res["web_search_engine"] = attempt(lambda: socket.getaddrinfo("www.google.com", 443))

    def loop(port):
        s = socket.socket()
        s.settimeout(1)
        try:
            s.connect(("127.0.0.1", port))
        except (ConnectionRefusedError, TimeoutError, OSError) as exc:
            if isinstance(exc, PermissionError):
                raise
            if "not permitted" in str(exc):
                raise
        finally:
            s.close()
    for name in ("research", "validator", "docs", "ingestion", "clientdata", "gateway"):
        res[f"loopback_{name}"] = attempt(lambda p=config.PORTS[name]: loop(p))
    res["subprocess"] = attempt(lambda: subprocess.run(["cmd", "/c", "echo", "x"], capture_output=True))
    if role == "orchestrator":
        from app.orchestrator import conversations
        res["own_conversation_store"] = attempt(lambda: conversations.list_all("probe"))
    print(json.dumps(res))


if __name__ == "__main__":
    main(sys.argv[1])
