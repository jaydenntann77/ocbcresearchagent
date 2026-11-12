"""Pattern test clients T01-T04 and demo mode.

* the committed files in dummy_data/patterns/ hold only relative dates (T-45, T+6) and no status;
* loading resolves them against "today" and computes LIVE/DEAD;
* demo OFF hides T01-T04 completely; demo ON makes them identifiable with their intended ideas;
* saves always go to the database, survive toggling, and nothing in dummy_data/ is ever written;
* demo mode starts OFF on every restart and is refused in public mode.
"""
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.clientdata import generate, patterns, schema
from app.clientdata.book import ClientBook
from app.clientdata.identify import identify
from app.clientdata.store import Store
from app.clientdata.trade_context import trade_contexts

ROOT = Path(__file__).resolve().parents[1]
DUMMY = ROOT / "dummy_data"
DAYS = [date(2026, 11, 13), date(2026, 12, 31), date(2027, 2, 28), date(2027, 3, 6), date(2027, 6, 7),
        date(2028, 1, 3)]                                            # incl. a Sunday and a Saturday
QUESTIONS = {"T01": ("Daniel from Aurora asks for OCBC's USD/SGD forecast", ["USDSGD"]),
             "T02": ("Priya from Bluewater wants OCBC's view on USD/JPY and USD/SGD", ["USDJPY", "USDSGD"]),
             "T03": ("Ahmad from Cendana asks about the USD/INR and USD/KRW outlook", ["USDINR", "USDKRW"]),
             "T04": ("Mei Ling from Dovetail asks for the USD/SGD forecast", ["USDSGD"])}


def dummy_fingerprint():
    return {str(p.relative_to(DUMMY)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(DUMMY.rglob("*")) if p.is_file()}


@pytest.fixture
def book(tmp_path):
    """A client book on a fresh temp database, with a controllable 'today'."""
    clock = {"today": DAYS[0]}
    return ClientBook(Store(tmp_path / "clientdata.db"), today=lambda: clock["today"]), clock


def ideas_for(cb, cid, today):
    c = cb.client(cid)
    pairs = QUESTIONS[cid][1]
    return {ctx["pair"]: ctx for ctx in trade_contexts(cb.trades(c), pairs, today, cb.interactions(cid, 1000))}


def idea(ctx, kind):
    return next((i for i in ctx["ideas"] if i["kind"] == kind), None)


# ------------------------------------------------------------------ relative dates
def test_relative_date_parsing():
    today = date(2026, 11, 13)
    assert patterns.resolve("T-45", today) == date(2026, 9, 29)
    assert patterns.resolve("T+6", today) == date(2026, 11, 19)
    assert patterns.resolve("T+0", today) == patterns.resolve("T", today) == today
    assert patterns.resolve_dt("T-3 14:32", today) == datetime(2026, 11, 10, 14, 32)
    assert patterns.to_rel(date(2026, 9, 29), today) == "T-45" and patterns.to_rel(today, today) == "T+0"
    for bad in ("2026-11-13", "T-", "T+x", "-45", ""):
        with pytest.raises(ValueError):
            patterns.resolve(bad, today)


def test_committed_files_hold_only_relative_dates_and_no_status():
    folder = DUMMY / "patterns"
    assert sorted(p.name for p in folder.iterdir()) == ["patterns_clients.csv", "patterns_contacts.csv",
                                                        "patterns_interactions.csv", "patterns_trades.csv"]
    for p in folder.iterdir():
        assert not re.search(r"\d{4}-\d{2}-\d{2}", p.read_text(encoding="utf-8")), f"absolute date in {p.name}"
    import csv
    with (folder / "patterns_trades.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == schema.TRADE_HEADERS
    for r in rows:
        assert r["Status (LIVE/MKT_OP/DEAD)"] == ""
        for h in ("Trn.Date", "Date: Period calc. start", "Date: Period calc. end", "Expiry Date", "Sys.Date"):
            assert patterns.REL_RE.match(r[h]), (h, r[h])
    assert not list(DUMMY.glob("patterns_*.csv"))                 # old top-level snapshot files removed


def test_weekend_dates_roll_to_monday_and_bookings_never_in_future():
    fri, sat, sun, mon = date(2026, 11, 13), date(2026, 11, 14), date(2026, 11, 15), date(2026, 11, 16)
    assert patterns.business_day(sat) == patterns.business_day(sun) == mon
    assert patterns.business_day(fri) == fri and patterns.business_day(mon) == mon
    # a booking on a weekend that would roll past "today" falls back to Friday instead
    assert patterns.business_day(sat, today=sun) == fri
    assert patterns.business_day(sat, today=mon) == mon
    # in the loaded book: a maturity stored on a Saturday lands on the Monday after
    sat_rows = [t for t in patterns.load(sat).trades]          # "today" = Saturday 14 Nov 2026
    assert all(date.fromisoformat(t["expiry_date"]).weekday() < 5 for t in sat_rows)


@pytest.mark.parametrize("today", DAYS)
def test_load_resolves_dates_and_computes_status(today):
    b = patterns.load(today)
    assert {c["client_id"] for c in b.clients} == set(patterns.CLIENT_IDS)
    for t in b.trades:
        assert set(t) == set(schema.TRADE_FIELDS)
        assert t["status"] == ("LIVE" if t["expiry_date"] >= today.isoformat() else "DEAD")
        assert t["trn_date"] <= today.isoformat() and t["expiry_date"] >= t["trn_date"]
        for f in ("trn_date", "period_start", "period_end", "expiry_date", "sys_date"):
            assert date.fromisoformat(t[f]).weekday() < 5, (f, t[f])          # no weekend dates
        assert isinstance(t["notional1"], float)
        if t["status"] == "DEAD":
            assert t["nfin_npv0"] == 0.0
    assert all(i["asked_at"] < today.isoformat() for i in b.interactions)
    # offsets do not move: on the same weekday (so the same weekend rolls) the book has the same shape
    later = patterns.load(today + timedelta(weeks=52))
    assert [t["status"] for t in later.trades] == [t["status"] for t in b.trades]


# ------------------------------------------------------------------ demo off / on
def test_demo_off_hides_pattern_clients(book):
    cb, _ = book
    assert cb.demo is False                                       # starts OFF
    for cid, (q, _) in QUESTIONS.items():
        found = identify(q, cb.clients(), cb.contacts())
        assert all(c.client_id != cid for c in found.candidates)
        assert cb.client(cid) is None and cb.contacts(cid) == [] and cb.interactions(cid) == []
    assert len(cb.clients()) == 12


def test_demo_on_identifies_pattern_clients(book):
    cb, _ = book
    cb.set_demo(True)
    assert len(cb.clients()) == 16
    for cid, (q, _) in QUESTIONS.items():
        found = identify(q, cb.clients(), cb.contacts())
        assert found.status == "match" and found.candidates[0].client_id == cid


@pytest.mark.parametrize("today", DAYS)
def test_intended_ideas_fire_in_demo_mode(book, today):
    cb, clock = book
    clock["today"] = today
    cb.set_demo(True)

    aurora = ideas_for(cb, "T01", today)["USD/SGD"]
    assert "roughly monthly" in idea(aurora, "rhythm")["text"]
    m = idea(aurora, "maturity")
    assert m["evidence"]["days"] <= 8 and m["evidence"]["rolled"] == 2
    assert sum("looks like a roll of SELL" in r for r in aurora["rolls"]) == 2

    blue = ideas_for(cb, "T02", today)
    assert "roughly quarterly" in idea(blue["USD/JPY"], "rhythm")["text"]
    assert idea(blue["USD/JPY"], "unusual")["evidence"]["size_ratio"] >= 2.4
    assert idea(blue["USD/SGD"], "next_ask")["text"] == "After USD/SGD asks, asked JPY/SGD within a week 4 of 5 times."

    cendana = ideas_for(cb, "T03", today)
    krw, inr = cendana["USD/KRW"], cendana["USD/INR"]
    assert any(line["label"] == "NDF" for line in krw["lines"])
    assert idea(krw, "maturity")["evidence"]["days"] <= 7 and len(krw["offsets"]) == 1
    assert "a SELL after 4 BUY trades in a row" in idea(inr, "unusual")["text"]

    dovetail = ideas_for(cb, "T04", today)["USD/SGD"]
    assert dovetail["kind"] == "open" and dovetail["ideas"] == [] and dovetail["rolls"] == []


# ------------------------------------------------------------------ saving
def test_saved_asks_survive_toggling_and_count_again(book):
    cb, clock = book
    before = dummy_fingerprint()
    cb.set_demo(True)
    today = clock["today"]
    # one more USD/SGD ask followed by a JPY/SGD ask, saved like the app does (to the database)
    cb.add_interaction({"client_id": "T02", "contact_id": "PT02", "question": "USD/SGD?", "instruments": "USDSGD",
                        "asked_at": "2026-11-01T10:00:00"})
    cb.add_interaction({"client_id": "T02", "contact_id": "PT02", "question": "JPY/SGD?", "instruments": "JPYSGD",
                        "asked_at": "2026-11-03T10:00:00"})
    assert idea(ideas_for(cb, "T02", today)["USD/SGD"], "next_ask")["evidence"]["times_followed"] == 5
    cb.set_demo(False)
    assert cb.interactions("T02") == []                                   # hidden ...
    assert len(cb.store.interactions("T02")) == 2                         # ... but still in the database
    cb.set_demo(True)
    nxt = idea(ideas_for(cb, "T02", today)["USD/SGD"], "next_ask")
    assert nxt["text"] == "After USD/SGD asks, asked JPY/SGD within a week 5 of 6 times."
    assert dummy_fingerprint() == before                                  # nothing in dummy_data/ written


def test_seeded_clients_unchanged_by_demo_mode(book):
    cb, _ = book
    seeded = generate.generate()
    off = cb.clients()
    cb.set_demo(True)
    on = [c for c in cb.clients() if c["client_id"].startswith("C")]
    assert off == on == sorted(seeded.clients, key=lambda c: c["client_id"])
    assert cb.trades(cb.client("C008")) == cb.store.trades(cb.client("C008")["sibs_cif"])


def test_legacy_pattern_rows_removed_and_user_asks_kept(tmp_path):
    db = generate.write_sqlite(generate.generate(), tmp_path / "old.db")
    old = patterns.build(DAYS[0])          # what the earlier version copied into the database
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE pattern_meta (key TEXT PRIMARY KEY, value TEXT)")
        for table, rows in (("clients", old.clients), ("contacts", old.contacts), ("trades", old.trades),
                            ("interactions", old.interactions)):
            cols = list(rows[0])
            conn.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                             [tuple(r[c] for c in cols) for r in rows])
        conn.execute("INSERT INTO interactions (interaction_id, client_id, question) VALUES ('I-mine', 'T01', 'q')")
    store = Store(db)
    assert [c for c in store.clients() if c["client_id"].startswith("T")] == []
    assert store.trades("900000101") == []
    assert [i["interaction_id"] for i in store.interactions("T01")] == ["I-mine"]
    assert len(store.clients()) == 12


# ------------------------------------------------------------------ the service: restart, guard, public mode
SERVICE = r"""
import json, os, sys
os.environ["RA_DATA_DIR"] = sys.argv[1]
os.environ["RA_TOKEN_ORCH_CLIENTS"] = "t"
from fastapi.testclient import TestClient
from app.clientdata.service import app
from app.common import config
c = TestClient(app)
h = {"Authorization": "Bearer t"}
q = {"question": "Daniel from Aurora asks for OCBC's USD/SGD forecast"}
out = {"start": c.get("/v1/demo", headers=h).json()}
if sys.argv[2] == "first":
    out["off_identify"] = c.post("/v1/identify", json=q, headers=h).json()["status"]
    out["on"] = c.post("/v1/demo", json={"enabled": True}, headers=h).json()
    out["on_identify"] = c.post("/v1/identify", json=q, headers=h).json()["candidates"][0]["client_id"]
    out["ctx"] = c.post("/v1/clients/T01/trade-context", json={"pairs": ["USDSGD"]}, headers=h).json()["contexts"][0]["kind"]
    out["log"] = c.post("/v1/interactions", json={"client_id": "T01", "contact_id": "PT01", "question": "USD/SGD?",
                                                  "instruments": ["USDSGD"]}, headers=h).status_code
    out["off"] = c.post("/v1/demo", json={"enabled": False}, headers=h).json()
    out["off_profile"] = c.get("/v1/clients/T01", headers=h).status_code
    out["off_log"] = c.post("/v1/interactions", json={"client_id": "T01", "question": "x"}, headers=h).status_code
    try:
        open(config.ROOT / "dummy_data" / "patterns" / "patterns_clients.csv", "a").close()
        out["write_dummy"] = "allowed"
    except Exception as exc:
        out["write_dummy"] = type(exc).__name__
else:
    c.post("/v1/demo", json={"enabled": True}, headers=h)
    out["kept"] = [i["question"] for i in c.get("/v1/clients/T01", headers=h).json()["interactions"]
                   if i["interaction_id"].startswith("I-")]
    out["public"] = None
print(json.dumps(out))
"""

PUBLIC = r"""
import json, os, sys
os.environ["RA_DATA_DIR"] = sys.argv[1]
os.environ["RA_TOKEN_ORCH_CLIENTS"] = "t"
os.environ["RA_PUBLIC_MODE"] = "1"
from fastapi.testclient import TestClient
from app.clientdata.service import app
c = TestClient(app)
h = {"Authorization": "Bearer t"}
print(json.dumps({"get": c.get("/v1/demo", headers=h).json(),
                  "post": c.post("/v1/demo", json={"enabled": True}, headers=h).status_code}))
"""


def run(script, *args):
    r = subprocess.run([sys.executable, "-c", script, *args], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_service_demo_mode_restart_saving_and_read_only_dummy_data(tmp_path):
    before = dummy_fingerprint()
    first = run(SERVICE, str(tmp_path), "first")
    assert first["start"] == {"enabled": False, "available": True}
    assert first["off_identify"] == "none"
    assert first["on"]["enabled"] and first["on_identify"] == "T01" and first["ctx"] == "open"
    assert first["log"] == 200
    assert first["off"]["enabled"] is False and first["off_profile"] == 404 and first["off_log"] == 404
    assert first["write_dummy"] == "AccessDenied"                   # the process cannot write dummy_data/
    second = run(SERVICE, str(tmp_path), "second")                  # "restart run.py"
    assert second["start"] == {"enabled": False, "available": True}  # starts OFF again
    assert second["kept"] == ["USD/SGD?"]                           # the saved ask is still there
    assert dummy_fingerprint() == before


def test_public_mode_refuses_demo(tmp_path):
    out = run(PUBLIC, str(tmp_path))
    assert out == {"get": {"enabled": False, "available": False}, "post": 403}
