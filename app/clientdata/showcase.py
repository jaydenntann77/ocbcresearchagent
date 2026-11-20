"""The showcase client for the app walkthrough: Brightway Engineering Pte Ltd (C013).

One hand-built client whose book tells a single, coherent story, so the walkthrough shows what the
assistant does with client data:

* a USD earner with a board hedging policy: layered USD/SGD forwards booked about monthly (3M and 6M),
  rolled with FX swaps when a US customer pays late (two past rolls on record);
* three USD/SGD deals maturing within two weeks (two forwards and one swap far leg from a roll), so the
  client stands out in a book-wide maturity check;
* JPY instalments for a new machining line from a Japanese supplier: two paid, the third hedged and due
  within two weeks, the final one not hedged yet;
* a year of logged asks from the Group Treasurer (Amy Lim) and the Finance Manager (Darren Ng):
  USD/SGD questions before most monthly hedges, usually followed by a yen question within a week.

Unlike the pattern test clients (T01-T04, demo mode only) this client is ALWAYS in the book, also on the
hosted site. Like them, it is loaded read-only from committed files (dummy_data/showcase/) whose dates are
all relative to today ("T-87", "T+4"), so the maturities are always upcoming whenever the app runs.
LIVE/DEAD status is computed at load. The app never writes to dummy_data/; asks a salesperson logs
about this client go to the database like any other client's.

This module is also the TOOL that (re)creates those files:

    python -m app.clientdata.showcase --write

Everything is FICTIONAL: the company, people, CIF, trade numbers and rates (made-up levels, not market
data); e-mail addresses use example.com.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from pathlib import Path

from app.clientdata import generate, patterns
from app.clientdata.generate import Book
from app.common import config
from app.common.timeutil import today_sgt

SHOWCASE_DIR = config.ROOT / "dummy_data" / "showcase"
FILES = {t: f"showcase_{t}.csv" for t in ("clients", "contacts", "trades", "interactions")}
CLIENT_ID = "C013"
CLIENT_IDS = (CLIENT_ID,)
INTERACTION_PREFIX = "IS-"
CONTRACT_BASE = 47_300_000

CLIENT = {
    "client_id": CLIENT_ID, "sibs_cif": "731846209", "counterpart_name": "Brightway Engineering Pte Ltd",
    "counterpart_label": "BRIGHTWAY ENG", "aliases": "Brightway;Brightway Engineering", "cust_seg": "LC",
    "industry": "Precision Engineering", "country": "SG", "profile": "USD earner",
    "hedging_notes": ("Makes precision parts for US semiconductor-equipment makers: about USD 8m of customer "
                      "receipts a month, costs mostly in SGD. Board policy: hedge 50-75% of forecast USD receipts, "
                      "layered monthly with 3M and 6M USD/SGD forwards; a forward is rolled with an FX swap when a "
                      "customer pays late. Also buying a new machining line from a Japanese supplier, paid in four "
                      "JPY instalments of about JPY 750m; each instalment is hedged with a USD/JPY forward once "
                      "its invoice is confirmed."),
    "preferred_pairs": "USDSGD;USDJPY",
}
RM = "RM001"
CONTACTS = [("PS01", "Amy", "Lim", "Group Treasurer", 1), ("PS02", "Darren", "Ng", "Finance Manager", 0)]
DEALER = ("D102", "SARAH.CHUA")

# Made-up mid levels by days before today (not market data), interpolated in between.
SPOT_PATH = {
    "USDSGD": {-300: 1.3420, -240: 1.3330, -180: 1.3160, -120: 1.3010, -90: 1.2960, -60: 1.2925, -30: 1.2980,
               0: 1.3010},
    "USDJPY": {-300: 146.20, -200: 144.80, -130: 147.50, -90: 149.60, -30: 151.80, 0: 153.40},
}
CARRY = {"USDSGD": 0.020, "USDJPY": 0.034}   # made-up annual forward discount of USD vs SGD / JPY
MARGIN_PIPS = 5
JPY_INSTALMENT = 750_000_000

# USD/SGD hedging programme: SELL USD forwards, one about every 30 days.
# (booked, matures, tenor label, USD m, remark), in days relative to today
USDSGD_FORWARDS = [
    (-297, -206, "3M", 5.0, "Monthly layered hedge"),
    (-267, -176, "3M", 4.5, "Monthly layered hedge"),      # rolled (swap A)
    (-237, -55, "6M", 5.0, "Monthly layered hedge"),
    (-207, -116, "3M", 5.5, "Monthly layered hedge"),
    (-177, -86, "3M", 6.0, "Monthly layered hedge"),       # rolled (swap B), far leg matures T+12
    (-147, 35, "6M", 5.0, "Monthly layered hedge"),
    (-117, 65, "6M", 5.0, "Monthly layered hedge"),
    (-87, 4, "3M", 5.0, "Monthly layered hedge"),
    (-57, 8, "2M", 5.5, "Invoice hedge"),
    (-27, 155, "6M", 4.5, "Monthly layered hedge"),
]
# Rolls of a maturing forward when a customer paid late: (index of the forward above, far-leg maturity, label)
USDSGD_ROLLS = [(1, -115, "2M"), (4, 12, "3M")]
# JPY machine instalments: SELL USD / BUY JPY 750m forwards. The fourth instalment is not hedged yet.
USDJPY_FORWARDS = [
    (-175, -114, "2M", "Machine instalment 1 (JPY)"),
    (-131, -10, "4M", "Machine instalment 2 (JPY)"),
    (-86, 10, "3M", "Machine instalment 3 (JPY)"),
]
# Logged asks: (days relative to today, HH:MM, contact, instrument, topic, question, what was sent)
ASKS = [
    (-241, "09:42", "PS01", "USDSGD", "forecast",
     "Where does OCBC see USD/SGD over the next six months? We are setting the budget rate for second-half receipts.",
     "Sent OCBC's USD/SGD forecast table and the main drivers."),
    (-238, "15:10", "PS01", "USDJPY", "forecast",
     "We sign the machining-line contract with our Japanese supplier next month. What is OCBC's USD/JPY outlook?",
     "Sent OCBC's USD/JPY forecast and risks."),
    (-180, "10:05", "PS01", "USDSGD", "rates",
     "Has OCBC changed its view on the Fed path, and what would it mean for USD/SGD?",
     "Sent OCBC's Fed view and the USD/SGD forecast."),
    (-178, "11:30", "PS01", "USDJPY", "forecast",
     "The first instalment invoice is in. Where does OCBC see USD/JPY over the next two months?",
     "Sent OCBC's USD/JPY forecast; client booked the instalment hedge."),
    (-150, "14:20", "PS01", "USDSGD", "macro",
     "Could you send OCBC's latest view on SGD and MAS policy for our board pack?",
     "Sent OCBC's SGD and MAS policy outlook."),
    (-133, "16:45", "PS02", "USDJPY", "forecast",
     "The second instalment invoice is confirmed. Could you send the latest USD/JPY view before we book the hedge?",
     "Sent OCBC's USD/JPY forecast."),
    (-90, "09:15", "PS01", "USDSGD", "hedging",
     "A US customer is paying about three months late. Can we roll the USD 6m forward due next week, and has the "
     "USD/SGD forecast changed?",
     "Explained an FX swap roll and sent the USD/SGD forecast; client rolled the forward."),
    (-88, "10:50", "PS01", "USDJPY", "forecast",
     "Third instalment invoice confirmed. What is OCBC's latest yen view?",
     "Sent OCBC's USD/JPY forecast; client booked the instalment hedge."),
    (-31, "08:55", "PS01", "USDSGD", "rates",
     "US yields are climbing again. Is OCBC still expecting USD/SGD to move lower next year?",
     "Sent OCBC's USD/SGD forecast and the note on US yields."),
    (-28, "17:05", "PS01", "USDJPY", "forecast",
     "Any update on the yen? We are starting to plan the final instalment.",
     "Sent OCBC's USD/JPY forecast."),
]


def _spot(pair: str, offset: int) -> float:
    pts = sorted(SPOT_PATH[pair].items())
    if offset <= pts[0][0]:
        return pts[0][1]
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        if d0 <= offset <= d1:
            return v0 + (v1 - v0) * (offset - d0) / (d1 - d0)
    return pts[-1][1]


def _client() -> dict:
    code, rm_name, l1, l2, l3 = next(r for r in generate.RMS if r[0] == RM)
    return CLIENT | {"cust_rm": rm_name, "customer_rm_code": code, "rm_team_l1": "OCBC Singapore",
                     "rm_team_l2": l1, "rm_team_l3": l2, "rm_team_l4": l3, "rm_team_l5": rm_name}


def build(today: date | None = None) -> Book:
    """The showcase book with absolute dates for `today` (used to write the files). Deterministic."""
    today = today or today_sgt()
    c = _client()
    spots = {p: v[0] for p, v in generate.PAIRS.items()}
    contract = CONTRACT_BASE
    trades: list[dict] = []
    at = lambda n: today + timedelta(days=n)   # noqa: E731

    def deal(pair, booked, matures, side, notional, label, remark, *, suffix="", trn_type="FXD", package="",
             ref=None, carry=True, hhmm="10:00", quote_amount=None):
        _, dp, pip = patterns._anchor(pair)
        spot = round(_spot(pair, booked), dp)
        tenor_y = max(matures - booked, 0) / 365 if carry else 0.0
        margin = MARGIN_PIPS * pip
        fwd = spot * (1 - CARRY[pair] * tenor_y)
        strike = round(fwd + (margin if side == "BUY" else -margin), dp + 1)
        if quote_amount:                      # the quote-currency amount is the fixed one (JPY instalments)
            notional = round(quote_amount / strike, 2)
        row = patterns.trade_row(c, contract=ref, suffix=suffix, tdate=at(booked), maturity=at(matures), pair=pair,
                                 side=side, notional=notional, label=label, spot=spot, strike=strike, margin=margin,
                                 live=matures >= 0, spots=spots, trn_type=trn_type, remark=remark, package=package,
                                 comment="", sys_time=f"{hhmm}:00", dealer=DEALER)
        trades.append(row)
        return row

    fwd_rows = []
    for k, (booked, matures, tenor, usd_m, remark) in enumerate(USDSGD_FORWARDS):
        contract += 7 + k % 3
        fwd_rows.append(deal("USDSGD", booked, matures, "SELL", usd_m * 1e6, f"USD/SGD Fwd {tenor}", remark,
                             ref=contract, hhmm=f"{10 + k % 5:02d}:{(17 * k) % 60:02d}"))
    for idx, far, tenor in USDSGD_ROLLS:
        src = fwd_rows[idx]
        rolled_on = USDSGD_FORWARDS[idx][1]
        contract += 5
        remark = f"Roll of {src['trn_internal']} (customer paid late)"
        deal("USDSGD", rolled_on, rolled_on + 2, "BUY", src["notional1"], f"USD/SGD Swap {tenor} (near)", remark,
             suffix="-N", trn_type="SWLEG", package=f"PKG{contract}", ref=contract, carry=False, hhmm="11:20")
        deal("USDSGD", rolled_on, far, "SELL", src["notional1"], f"USD/SGD Swap {tenor} (far)", remark,
             suffix="-F", trn_type="SWLEG", package=f"PKG{contract}", ref=contract, hhmm="11:20")
    for k, (booked, matures, tenor, remark) in enumerate(USDJPY_FORWARDS):
        contract += 11
        deal("USDJPY", booked, matures, "SELL", 0.0, f"USD/JPY Fwd {tenor}", remark, ref=contract,
             hhmm=f"{14 + k:02d}:{(23 * k) % 60:02d}", quote_amount=JPY_INSTALMENT)
    trades.sort(key=lambda r: (r["trn_date"], r["trn_internal"]))

    contacts = [{"contact_id": pid, "client_id": CLIENT_ID, "first_name": first, "last_name": last, "title": title,
                 "email": f"{first.lower()}.{last.lower()}@brightway.example.com", "is_primary": primary}
                for pid, first, last, title, primary in CONTACTS]
    interactions = []
    for k, (offset, hhmm, pid, inst, topic, question, sent) in enumerate(ASKS, start=1):
        d = patterns._weekday(at(offset))
        hh, mm = (int(x) for x in hhmm.split(":"))
        interactions.append({
            "interaction_id": f"{INTERACTION_PREFIX}{CLIENT_ID}-{k:02d}", "client_id": CLIENT_ID, "contact_id": pid,
            "asked_at": datetime.combine(d, time(hh, mm)).isoformat(), "logged_by": c["cust_rm"],
            "question": question, "instruments": inst, "topic": topic, "answer_summary": sent,
            "conversation_id": None})
    return Book([c], contacts, trades, interactions)


def load(today: date | None = None, folder: Path = SHOWCASE_DIR) -> Book:
    """The showcase book with every T± date resolved against `today` (SGT). Read-only."""
    return patterns.load(today, folder, FILES)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Regenerate the showcase client files (dummy_data/showcase/).")
    ap.add_argument("--write", action="store_true", help="overwrite dummy_data/showcase/*.csv")
    ap.add_argument("--folder", type=Path, default=SHOWCASE_DIR)
    args = ap.parse_args(argv)
    today = today_sgt()
    book = build(today)
    if args.write:
        for p in patterns.write_files(book, today, args.folder, FILES):
            print(f"wrote {p}")
    live = sum(t["expiry_date"] >= today.isoformat() for t in book.trades)
    print(f"{book.clients[0]['counterpart_name']}: {len(book.trades)} trade rows ({live} live), "
          f"{len(book.interactions)} logged asks" + ("" if args.write else " (dry run; add --write to write the files)"))


if __name__ == "__main__":
    main()
