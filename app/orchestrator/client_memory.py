"""Client memory: stores who asked what. Saved only after the user confirms."""
from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from app.common import config

SGT = timezone(timedelta(hours=8))
DB_PATH = os.path.join(str(config.ORCH_DIR), "client_memory.db")

# "Jeremy from Company A asked what is the USD rates forecast till 2028"
CLIENT_RE = re.compile(
    r"^\s*(?P<name>[A-Z][\w'-]+(?: [A-Z][\w'-]+)?) from (?P<company>[A-Z][\w&.' -]*?)"
    r"\s+(?:asked|wants|wanted|is asking|needs)\s*(?:for|what is|about)?\s*(?P<desc>.+)$",
    re.I,
)
SAME_RE = re.compile(r"\bsame (person|client)\b", re.I)
LEADING_WORDS_RE = re.compile(r"^(the|a|an)\s+", re.I)


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS client_asks (
        id INTEGER PRIMARY KEY, client_name TEXT, company TEXT,
        ask_description TEXT, asked_at TEXT)""")
    return con


def _clean(desc: str) -> str:
    return LEADING_WORDS_RE.sub("", desc.strip(" ,.?"))


def propose(question: str, last_client: dict | None) -> dict | None:
    """Work out what WOULD be saved. Nothing is written here."""
    now = datetime.now(SGT).strftime("%d %b %Y, %H:%M")
    m = CLIENT_RE.match(question)
    if m:
        name, company, desc = m["name"], m["company"].strip(), _clean(m["desc"])
        ask = "Please confirm the below is accurate."
    elif last_client:
        name, company = last_client["name"], last_client["company"]
        desc = _clean(SAME_RE.sub("", question))
        ask = ("Is the below accurate?" if SAME_RE.search(question)
               else f"Is this for {name} ({company})? Is the below accurate?")
    else:
        return None
    return {"name": name, "company": company, "description": desc, "time": now, "ask": ask}


def save(entry: dict) -> None:
    with closing(_conn()) as con, con:  # "with con" commits; closing() releases the file (matters on Windows)
        con.execute("INSERT INTO client_asks (client_name, company, ask_description, asked_at) VALUES (?,?,?,?)",
                    (entry["name"], entry["company"], entry["description"], entry["time"]))


def history(name: str, limit: int = 10) -> list[tuple]:
    with closing(_conn()) as con:
        return con.execute("SELECT ask_description, asked_at FROM client_asks WHERE client_name=? "
                           "ORDER BY id DESC LIMIT ?", (name, limit)).fetchall()