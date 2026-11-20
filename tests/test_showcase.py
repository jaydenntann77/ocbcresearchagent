"""The showcase client (Brightway Engineering, C013) used in the app walkthrough.

* the committed files in dummy_data/showcase/ hold only relative dates and no status;
* the client is always in the book (demo mode off or on) and is found by company or contact name;
* whatever day the app runs, the story holds: four deals mature within two weeks (three USD/SGD, one
  USD/JPY), two earlier USD/SGD maturities were rolled, the client hedges monthly, usually asks about the
  yen within a week of a USD/SGD question, and the final JPY instalment is not hedged yet;
* asks logged about the client go to the database and join its seeded history; dummy_data/ is never written.
"""
import csv
import hashlib
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.clientdata import insights, patterns, schema, showcase
from app.clientdata.book import ClientBook
from app.clientdata.identify import identify
from app.clientdata.store import Store
from app.clientdata.trade_context import trade_contexts

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "dummy_data" / "showcase"
DAYS = [date(2026, 11, 20), date(2026, 11, 22), date(2026, 12, 5), date(2027, 1, 18), date(2027, 3, 3),
        date(2027, 6, 11)]                                           # incl. a Sunday and a Saturday
CID = showcase.CLIENT_ID


@pytest.fixture
def book(tmp_path):
    clock = {"today": DAYS[0]}
    return ClientBook(Store(tmp_path / "clientdata.db"), today=lambda: clock["today"]), clock


def contexts(cb, today):
    c = cb.client(CID)
    return {ctx["pair"]: ctx for ctx in trade_contexts(cb.trades(c), ["USDSGD", "USDJPY"], today,
                                                       cb.interactions(CID, 1000))}


def idea(ctx, kind):
    return next((i for i in ctx["ideas"] if i["kind"] == kind), None)


def fingerprint():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(FOLDER.iterdir())}


def test_committed_files_hold_only_relative_dates_and_no_status():
    assert sorted(p.name for p in FOLDER.iterdir()) == sorted(showcase.FILES.values())
    for p in FOLDER.iterdir():
        assert not re.search(r"\d{4}-\d{2}-\d{2}", p.read_text(encoding="utf-8")), f"absolute date in {p.name}"
    with (FOLDER / showcase.FILES["trades"]).open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == schema.TRADE_HEADERS
    assert all(r["Status (LIVE/MKT_OP/DEAD)"] == "" and patterns.REL_RE.match(r["Expiry Date"]) for r in rows)


def test_committed_files_match_the_builder():
    """The files are what `python -m app.clientdata.showcase --write` produces (offsets do not drift)."""
    today = DAYS[0]
    built, loaded = showcase.build(today), showcase.load(today)
    key = lambda t: t["trn_internal"]                                                  # noqa: E731
    assert [(t["trn_internal"], t["notional1"], t["instrument_label"]) for t in sorted(built.trades, key=key)] == \
           [(t["trn_internal"], t["notional1"], t["instrument_label"]) for t in sorted(loaded.trades, key=key)]
    assert [i["question"] for i in built.interactions] == [i["question"] for i in loaded.interactions]


def test_always_in_the_book_and_found_by_name(book):
    cb, _ = book
    for demo in (False, True):
        cb.set_demo(demo)
        assert cb.client(CID)["counterpart_name"] == "Brightway Engineering Pte Ltd"
        assert [p["first_name"] for p in cb.contacts(CID)] == ["Amy", "Darren"]          # primary first
        found = identify("Amy from Brightway is asking for OCBC's USD/SGD forecast", cb.clients(), cb.contacts())
        assert found.status == "match" and found.candidates[0].client_id == CID
        assert found.candidates[0].contact_id == "PS01"
    assert cb.store.client(CID) is None                                   # nothing copied into the database


@pytest.mark.parametrize("today", DAYS)
def test_the_story_holds_whatever_the_day(book, today):
    cb, clock = book
    clock["today"] = today
    c = cb.client(CID)
    trades = cb.trades(c)
    for t in trades:
        assert t["trn_date"] <= today.isoformat() <= t["expiry_date"] or t["status"] == "DEAD"
        assert date.fromisoformat(t["expiry_date"]).weekday() < 5

    # four deals mature within two weeks, nothing else within a month
    m = insights.maturities([(c, trades)], today, 14)
    assert m["maturing_deals"] == 4
    assert sorted((r["pair"], r["deal"]) for r in m["deals"]) == [
        ("USD/JPY", "SELL USD 5.1m forward"), ("USD/SGD", "SELL USD 5.0m forward"),
        ("USD/SGD", "SELL USD 5.5m forward"), ("USD/SGD", "SELL USD 6.0m swap far leg")]
    assert all(r["has_rolled_this_pair_before"] == (r["pair"] == "USD/SGD") for r in m["deals"])
    assert insights.maturities([(c, trades)], today, 30)["maturing_deals"] == 4

    ctx = contexts(cb, today)
    sgd, jpy = ctx["USD/SGD"], ctx["USD/JPY"]
    assert sgd["net"]["text"] == "SELL USD 31.0m"
    assert idea(sgd, "next_ask")["text"] == "After USD/SGD asks, asked USD/JPY within a week 4 of 5 times."
    mat = idea(sgd, "maturity")["evidence"]
    assert (mat["days"] <= 6, mat["also_within_window"], mat["rolled"], mat["settled"]) == (True, 2, 2, 4)
    assert "roughly monthly" in idea(sgd, "rhythm")["text"]
    assert sum("looks like a roll of SELL USD 6.0m forward" in r for r in sgd["rolls"]) == 1
    # the third JPY instalment is hedged and due soon; nothing is hedged for the fourth
    live_jpy = [r for r in jpy["trades"] if r["open"]]
    assert len(live_jpy) == 1 and idea(jpy, "maturity")["evidence"]["days"] <= 12
    assert len([r for r in jpy["trades"] if not r["open"]]) == 2


def test_overview_for_the_brief(book):
    cb, clock = book
    ov = insights.overview(cb.client(CID), cb.contacts(CID), cb.trades(cb.client(CID)), cb.interactions(CID, 1000),
                           clock["today"])
    assert ov["client"]["relationship_manager"] == "Tan Wei Ling" and "JPY instalments" in ov["client"]["hedging_notes"]
    assert len(ov["maturing_next_30_days"]) == 4 and ov["activity"]["open_deals"] == 7
    assert ov["recent_asks"][0]["question"].startswith("Any update on the yen?")
    assert "sibs_cif" not in str(ov) and "731846209" not in str(ov)          # no CIF leaves the service


def test_logged_asks_go_to_the_database_and_join_the_history(book):
    cb, clock = book
    before = fingerprint()
    n = len(cb.interactions(CID, 1000))
    cb.add_interaction({"client_id": CID, "contact_id": "PS01", "question": "OCBC's USD/SGD forecast into 2027",
                        "instruments": "USDSGD", "topic": "forecast"})
    assert len(cb.store.interactions(CID)) == 1
    rows = cb.interactions(CID, 1000)
    assert len(rows) == n + 1 and rows[0]["question"] == "OCBC's USD/SGD forecast into 2027"   # newest first
    # one more USD/SGD ask without a yen follow-up still leaves the pattern in place (4 of 6)
    sgd = contexts(cb, clock["today"])["USD/SGD"]
    assert idea(sgd, "next_ask")["text"] == "After USD/SGD asks, asked USD/JPY within a week 4 of 6 times."
    assert fingerprint() == before


def test_bookings_and_asks_never_in_the_future():
    for today in DAYS:
        b = showcase.load(today)
        assert all(t["trn_date"] <= today.isoformat() for t in b.trades)
        assert all(i["asked_at"] < (today + timedelta(days=0)).isoformat() for i in b.interactions)
