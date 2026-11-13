"""Pattern test clients T01-T04 for DEMO MODE: small, hand-shaped books that exercise the
trade-context detectors (rhythm, maturity + roll history, unusual size / direction, next likely
ask, NDFs, offsets) plus one control client that must trigger none of them.

The app loads them from the committed, READ-ONLY files in dummy_data/patterns/ (patterns_clients.csv,
patterns_contacts.csv, patterns_trades.csv, patterns_interactions.csv). Every date there is written relative to today -
"T-45", "T+6", "T+0" (interactions: "T-45 14:32") - and resolved against today (SGT) when demo mode
is switched on, so maturities stay upcoming whenever the app runs. LIVE/DEAD status is not stored:
it is computed at load from the resolved maturity. The app never writes to dummy_data/.

This module is also the TOOL that (re)creates those files:

    python -m app.clientdata.patterns --write     # regenerate dummy_data/patterns/*.csv from build()

Everything is FICTIONAL (names, CIFs, trade numbers, levels; emails @example.com). Weiyang's 12 seeded
clients (C001-C012, dummy_data/*.csv, generate.py) are separate and never date-shifted.
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from app.clientdata import generate, schema
from app.clientdata.generate import Book, add_months, to_sgd
from app.common import config
from app.common.timeutil import today_sgt

SEED = 7
PATTERN_DIR = config.ROOT / "dummy_data" / "patterns"
FILES = {t: f"patterns_{t}.csv" for t in ("clients", "contacts", "trades", "interactions")}
CLIENT_IDS = ("T01", "T02", "T03", "T04")
INTERACTION_PREFIX = "IT-"
# Made-up anchors (not market data) for the pairs generate.PAIRS does not have.
EXTRA_PAIRS = {"USDINR": (88.00, 2, 0.01), "USDKRW": (1400.0, 1, 0.1)}
TRADE_DATE_FIELDS = ("trn_date", "period_start", "period_end", "expiry_date", "sys_date", "replacement_date")
BOOKING_DATE_FIELDS = ("trn_date", "period_start", "sys_date")       # never later than today
MATURITY_DATE_FIELDS = ("period_end", "expiry_date")
STATUS_FIELDS = ("status", "last_market_operation", "contract_last_impact_event")   # computed at load
NPV_FIELDS = ("nfin_npv0", "nfin_npv0s", "nfin_npv1", "nfin_npv1s", "nfin_npv2", "nfin_npv2s")
REAL_FIELDS = {f for _, f, t in schema.TRADE_COLUMNS if t == "REAL"}

CLIENTS = [  # id, cif, name, label, aliases, seg, industry, country, profile, notes, pairs, rm
    ("T01", "900000101", "Aurora Shipping Pte Ltd", "AURORA SHIPPING", "Aurora", "LC", "Shipping", "SG",
     "USD earner", "PATTERN TEST CLIENT. Sells USD/SGD 3M forwards monthly; rolls some maturities with swaps.",
     "USDSGD", "RM001"),
    ("T02", "900000102", "Bluewater Electronics Pte Ltd", "BLUEWATER ELEC", "Bluewater", "LC", "Electronics", "SG",
     "importer", "PATTERN TEST CLIENT. Buys JPY for equipment with quarterly USD/JPY 6M forwards.",
     "USDJPY;USDSGD", "RM002"),
    ("T03", "900000103", "Cendana Resources Sdn Bhd", "CENDANA RES", "Cendana", "SME", "Mining Services", "MY",
     "mixed", "PATTERN TEST CLIENT. Hedges INR and KRW exposure with cash-settled NDFs.", "USDINR;USDKRW",
     "RM003"),
    ("T04", "900000104", "Dovetail Foods Pte Ltd", "DOVETAIL FOODS", "Dovetail", "SME", "Food Distribution", "SG",
     "importer", "PATTERN TEST CLIENT (control). Irregular USD/SGD trades; should trigger no ideas.", "USDSGD",
     "RM003"),
]
CONTACTS = {"T01": ("Daniel", "Koh", "Treasury Manager"), "T02": ("Priya", "Nair", "CFO"),
            "T03": ("Ahmad", "Faiz", "Finance Director"), "T04": ("Mei Ling", "Chua", "Treasury Analyst")}


# ================================================================ relative dates ("T-45")
REL_RE = re.compile(r"^T(?:([+-])(\d+))?(?:\s+(\d{1,2}):(\d{2}))?$")


def to_rel(d: date, today: date) -> str:
    n = (d - today).days
    return f"T{'+' if n >= 0 else '-'}{abs(n)}"


def to_rel_dt(dt: datetime, today: date) -> str:
    return f"{to_rel(dt.date(), today)} {dt:%H:%M}"


def resolve(value: str, today: date) -> date:
    """'T-45' -> today - 45 days; 'T+6' -> today + 6; 'T' / 'T+0' -> today."""
    m = REL_RE.match((value or "").strip())
    if not m:
        raise ValueError(f"not a relative date: {value!r}")
    n = int(m.group(2) or 0) * (-1 if m.group(1) == "-" else 1)
    return today + timedelta(days=n)


def resolve_dt(value: str, today: date) -> datetime:
    """'T-45 14:32' -> that day at 14:32 (no time -> 09:00)."""
    m = REL_RE.match((value or "").strip())
    if not m:
        raise ValueError(f"not a relative date-time: {value!r}")
    d = resolve(value.split()[0], today)
    return datetime(d.year, d.month, d.day, int(m.group(3) or 9), int(m.group(4) or 0))


# ================================================================ loading (what the app uses)
def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def business_day(d: date, today: date | None = None) -> date:
    """A Saturday or Sunday moves to the next Monday. With `today` (booking dates), a Monday that
    would lie after today falls back to the Friday before instead, so no trade is booked in the future."""
    if d.weekday() < 5:
        return d
    monday = d + timedelta(days=7 - d.weekday())
    if today is not None and monday > today:
        return d - timedelta(days=d.weekday() - 4)
    return monday


def _trade_from_file(row: dict, today: date) -> dict:
    t = {field: row.get(header, "") for header, field, _ in schema.TRADE_COLUMNS}
    for f in TRADE_DATE_FIELDS:
        if t[f]:
            d = resolve(t[f], today)
            if f in BOOKING_DATE_FIELDS:
                d = business_day(d, today)
            elif f in MATURITY_DATE_FIELDS:
                d = business_day(d)
            t[f] = d.isoformat()
    for f in REAL_FIELDS:
        t[f] = float(t[f]) if t[f] not in ("", None) else None
    live = bool(t["expiry_date"]) and t["expiry_date"] >= today.isoformat()
    t["status"] = "LIVE" if live else "DEAD"
    t["last_market_operation"] = t["contract_last_impact_event"] = "New" if live else "Maturity"
    if not live:
        for f in NPV_FIELDS:
            t[f] = 0.0
    return t


def load(today: date | None = None, folder: Path = PATTERN_DIR) -> Book:
    """The pattern book with every T± date resolved against `today` (SGT) and status computed.
    Read-only: nothing is written anywhere."""
    today = today or today_sgt()
    clients = _read(folder / FILES["clients"])
    contacts = [r | {"is_primary": int(r["is_primary"] or 0)} for r in _read(folder / FILES["contacts"])]
    trades = [_trade_from_file(r, today) for r in _read(folder / FILES["trades"])]
    interactions = [r | {"asked_at": resolve_dt(r["asked_at"], today).isoformat(),
                         "conversation_id": r.get("conversation_id") or None}
                    for r in _read(folder / FILES["interactions"])]
    trades.sort(key=lambda r: (r["trn_date"], r["trn_internal"]))
    return Book(clients, contacts, trades, interactions)


# ================================================================ generator (tool only)
def _weekday(d: date) -> date:
    """Saturday -> Friday, Sunday -> Monday."""
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


def _anchor(pair: str) -> tuple[float, int, float]:
    if pair in generate.PAIRS:
        anchor, _, dp, pip = generate.PAIRS[pair]
        return anchor, dp, pip
    return EXTRA_PAIRS[pair]


class _Builder:
    def __init__(self, today: date, seed: int):
        self.today, self.rng = today, random.Random(seed)
        self.spots = {p: _anchor(p)[0] for p in [*generate.PAIRS, *EXTRA_PAIRS]}
        rms = {r[0]: r for r in generate.RMS}
        self.clients, self.contacts, self.trades, self.interactions = [], [], [], []
        for cid, cif, name, label, aliases, seg, ind, ctry, prof, notes, pairs, rm in CLIENTS:
            code, rm_name, l1, l2, l3 = rms[rm]
            self.clients.append({
                "client_id": cid, "sibs_cif": cif, "counterpart_name": name, "counterpart_label": label,
                "aliases": aliases, "cust_seg": seg, "industry": ind, "country": ctry, "profile": prof,
                "hedging_notes": notes, "preferred_pairs": pairs, "cust_rm": rm_name, "customer_rm_code": code,
                "rm_team_l1": "OCBC Singapore", "rm_team_l2": l1, "rm_team_l3": l2, "rm_team_l4": l3,
                "rm_team_l5": rm_name})
            first, last, title = CONTACTS[cid]
            self.contacts.append({
                "contact_id": f"P{cid}", "client_id": cid, "first_name": first, "last_name": last, "title": title,
                "email": f"{first.lower().replace(' ', '')}.{last.lower()}@{label.split()[0].lower()}.example.com",
                "is_primary": 1})
        self.by_id = {c["client_id"]: c for c in self.clients}
        self.contract = {cid: 49_100_000 + 1000 * (k + 1) for k, cid in enumerate(CLIENT_IDS)}

    # dates and sizes: "slightly random"
    def ago(self, days: int, jitter: int = 2) -> date:
        d = _weekday(self.today - timedelta(days=days + self.rng.randint(-jitter, jitter)))
        return min(d, self.today - timedelta(days=1))

    def size(self, base_m: float, spread: float = 0.10) -> float:
        return round(base_m * self.rng.uniform(1 - spread, 1 + spread), 1) * 1_000_000

    def trade(self, cid: str, tdate: date, maturity: date, pair: str, side: str, notional: float, label: str, *,
              trn_type: str = "FXD", strategy: str = "CLIENT_HEDGE", remark: str = "", package: str = "",
              suffix: str = "", contract: int | None = None) -> dict:
        c = self.by_id[cid]
        if contract is None:
            self.contract[cid] += self.rng.randint(1, 9)
            contract = self.contract[cid]
        anchor, dp, pip = _anchor(pair)
        ccy1, ccy2 = pair[:3], pair[3:]
        spot = round(anchor * self.rng.uniform(0.99, 1.01), dp)
        tenor_y = max((maturity - tdate).days, 0) / 365
        margin = self.rng.choice([2, 3, 5, 8]) * pip
        strike = round(spot * (1 + 0.01 * tenor_y) + (margin if side == "BUY" else -margin), dp + 1)
        status = "LIVE" if maturity >= self.today else "DEAD"
        credit_fcy = round(notional * margin, 2)
        credit_sgd = round(to_sgd(credit_fcy, ccy2, self.spots), 2)
        npv0 = round((1 if side == "BUY" else -1) * notional * (spot - strike), 2)
        s0 = round(to_sgd(1.0, ccy2, self.spots), 6)
        last_op = "New" if status == "LIVE" else "Maturity"
        row = {
            "contract_ref": f"{contract}", "package_ref": package, "trn_internal": f"{contract}{suffix}",
            "portfolio": "SG_FX_SALES_CORP", "trade_category": "Sales", "dealer": "KEVIN.ONG", "remark": remark,
            "counterpart_label": c["counterpart_label"], "counterpart_name": c["counterpart_name"],
            "cust_seg": c["cust_seg"], "cust_rm": c["cust_rm"], "trn_date": tdate.isoformat(),
            "period_start": tdate.isoformat(), "period_end": maturity.isoformat(), "instrument_label": label,
            "dcr_opt_instrument": "", "ccy1": ccy1, "notional1": notional, "ccy2": ccy2,
            "notional2": round(notional * strike, 2), "initial_price": spot, "strike_rate": strike,
            "sale_credit_ccy": ccy2, "sales_fx_margin_fcy": round(margin, dp + 2),
            "amt_sales_credit_udf_fcy": credit_fcy, "total_sale_credit_fcy": credit_fcy, "nominal_ccy": ccy1,
            "nominal_amt_adj": notional, "notional_sgd": round(to_sgd(notional, ccy1, self.spots), 2),
            "sales_fx_margin_sgd": round(to_sgd(margin, ccy2, self.spots), 6), "amt_sales_credit_udf_sgd": credit_sgd,
            "total_sales_credit_sgd": credit_sgd,
            "cost_centre": "SGTM" + {"LC": "101", "SME": "102", "FI": "201", "PB": "301"}[c["cust_seg"]],
            "strategy": strategy, "trn_family": "CURR", "trn_group": "FXD", "trn_type": trn_type, "status": status,
            "ta_rm_id": c["customer_rm_code"], "expiry_date": maturity.isoformat(),
            "trn_external": f"EXT{contract}{suffix}", "buy_sell": side, "spot_margin": round(margin, dp + 2),
            "comment_1": "PATTERN TEST CLIENT", "sibs_cif": c["sibs_cif"], "rm_team_l1": c["rm_team_l1"],
            "rm_team_l2": c["rm_team_l2"], "rm_team_l3": c["rm_team_l3"], "rm_team_l4": c["rm_team_l4"],
            "rm_team_l5": c["rm_team_l5"], "customer_rm_code": c["customer_rm_code"], "amendment_status": "Not amended",
            "contract_na_event_action": "", "security_isin": "", "contract_source_module": "FX",
            "last_market_operation": last_op, "contract_last_event": "Insertion", "contract_last_impact_event": last_op,
            "sys_date": tdate.isoformat(), "sys_time": "10:00:00", "nfin_npv0": npv0,
            "nfin_npv0s": round(npv0 * s0, 2), "fxspot0s": s0, "nfin_npv1": npv0, "fxspot1s": s0,
            "nfin_npv1s": round(npv0 * s0, 2), "nfin_npv2": npv0, "fxspot2s": s0, "nfin_npv2s": round(npv0 * s0, 2),
            "pl_ccy": ccy2, "entity": "OCBC SG", "entity_accounting_ccy": "SGD", "external_inter_intra": "External",
            "internal": "N", "dealer_id": "D101", "contract_origin_ref": "", "replacement_origin_nb": "",
            "trader_credit_udf_fcy": round(credit_fcy * 0.2, 2), "trader_credit_udf_sgd": round(credit_sgd * 0.2, 2),
            "total_client_markup_fcy": credit_fcy, "total_client_markup_sgd": credit_sgd, "replacement_date": "",
        }
        self.trades.append(row)
        return row

    def forward(self, cid, tdate, months, pair, side, notional, *, ndf=False, **kw) -> dict:
        maturity = add_months(tdate, months)
        p = f"{pair[:3]}/{pair[3:]}"
        label = f"{p} NDF {months}M" if ndf else f"{p} Fwd {months}M"
        if ndf:
            kw.setdefault("remark", "Cash-settled NDF")
        return self.trade(cid, tdate, maturity, pair, side, notional, label, **kw)

    def swap(self, cid, tdate, months, pair, near_side, notional, remark="") -> list[dict]:
        self.contract[cid] += self.rng.randint(1, 9)
        n = self.contract[cid]
        p = f"{pair[:3]}/{pair[3:]}"
        far_side = "SELL" if near_side == "BUY" else "BUY"
        return [self.trade(cid, tdate, generate.add_business_days(tdate, 2), pair, near_side, notional,
                           f"{p} Swap {months}M (near)", trn_type="SWLEG", package=f"PKG{n}", suffix="-N",
                           contract=n, remark=remark),
                self.trade(cid, tdate, add_months(tdate, months), pair, far_side, notional,
                           f"{p} Swap {months}M (far)", trn_type="SWLEG", package=f"PKG{n}", suffix="-F",
                           contract=n, remark=remark)]

    def ask(self, cid: str, when: date, pair: str, question: str):
        k = sum(i["client_id"] == cid for i in self.interactions) + 1
        self.interactions.append({
            "interaction_id": f"{INTERACTION_PREFIX}{cid}-{k:02d}", "client_id": cid, "contact_id": f"P{cid}",
            "asked_at": datetime(when.year, when.month, when.day, self.rng.randint(9, 17),
                                 self.rng.randint(0, 59)).isoformat(),
            "logged_by": self.by_id[cid]["cust_rm"], "question": question, "instruments": pair, "topic": "forecast",
            "answer_summary": "(pattern test client - no answer stored)", "conversation_id": None})


def _aurora(b: _Builder):
    """Monthly SELL USD/SGD 3M forwards on ~the 25th; one forward maturing in 5-8 days; two past
    maturities rolled with same-size swaps traded on the maturity date (far leg 3M later)."""
    cid, t = "T01", b.today
    anchors, k = [], 0
    while len(anchors) < 7:
        y, m = divmod(t.year * 12 + t.month - 1 - k, 12)
        d = date(y, m + 1, 25)
        if d < t:
            anchors.append(d)
        k += 1
    monthly = []
    for d in sorted(anchors):
        tdate = min(_weekday(d + timedelta(days=b.rng.randint(-2, 2))), t - timedelta(days=1))
        monthly.append(b.forward(cid, tdate, 3, "USDSGD", "SELL", b.size(5.0), remark="Monthly layered hedge"))
    # one forward maturing in 5-8 days, booked on one of the monthly dates (keeps the monthly rhythm)
    # stored as T+5 or T+6: after a weekend roll at load time it is still 5-8 days away
    maturity = t + timedelta(days=b.rng.randint(5, 6))
    base = min((date.fromisoformat(r["trn_date"]) for r in monthly), key=lambda d: abs((maturity - d).days - 91))
    months = max(1, round((maturity - base).days / 30.4))
    b.trade(cid, base, maturity, "USDSGD", "SELL", b.size(5.0), f"USD/SGD Fwd {months}M", remark="Invoice hedge")
    # two settled maturities rolled: swap on the maturity date, near leg settles it, far leg 3M later
    matured = [r for r in monthly if date.fromisoformat(r["expiry_date"]) <= t - timedelta(days=6)]
    for r in matured[-2:]:
        b.swap(cid, date.fromisoformat(r["expiry_date"]), 3, "USDSGD", "BUY", r["notional1"],
               remark=f"Roll of {r['trn_internal']}")
    # a USD/SGD ask 2-4 days before most monthly trades
    for r in b.rng.sample(monthly, 5):
        when = date.fromisoformat(r["trn_date"]) - timedelta(days=b.rng.randint(2, 4))
        b.ask(cid, when, "USDSGD", "What is OCBC's USD/SGD forecast for the next 3 months?")


def _bluewater(b: _Builder):
    """Quarterly SELL USD/JPY 6M forwards (~USD 12m); the newest (last 2 weeks) ~3x the usual size.
    5 USD/SGD asks, 4 of them followed by a JPY/SGD ask 2-6 days later."""
    cid = "T02"
    newest = b.ago(b.rng.randint(3, 12), jitter=0)
    for q in (3, 2, 1):
        b.forward(cid, _weekday(newest - timedelta(days=90 * q + b.rng.randint(-2, 2))), 6, "USDJPY", "SELL",
                  b.size(12.0), remark="Equipment payment hedge")
    b.forward(cid, newest, 6, "USDJPY", "SELL", b.size(36.0), remark="Equipment payment hedge")
    skip = b.rng.randrange(5)
    for k, back in enumerate((80, 62, 44, 26, 8)):
        when = b.ago(back, jitter=1)
        b.ask(cid, when, "USDSGD", "Where does OCBC see USD/SGD in the next quarter?")
        if k != skip:
            b.ask(cid, when + timedelta(days=b.rng.randint(2, 6)), "JPYSGD", "And what about JPY/SGD?")


def _cendana(b: _Builder):
    """USD/INR NDF 3M: four BUYs, newest a SELL. USD/KRW NDFs: one fixing within 7 days, plus an
    offsetting BUY/SELL pair (size within 10%, maturities within 30 days)."""
    cid = "T03"
    for back in (160, 150, 95, 40):
        b.forward(cid, b.ago(back), 3, "USDINR", "BUY", b.size(3.0), ndf=True)
    b.forward(cid, b.ago(6), 3, "USDINR", "SELL", b.size(5.0), ndf=True)
    fixing = _weekday(b.today + timedelta(days=b.rng.randint(2, 6)))
    b.trade(cid, _weekday(fixing - timedelta(days=91)), fixing, "USDKRW", "BUY", b.size(2.0), "USD/KRW NDF 3M",
            remark="Cash-settled NDF")
    buy = b.size(4.0)
    b.forward(cid, b.ago(60), 6, "USDKRW", "BUY", buy, ndf=True)
    b.forward(cid, b.ago(20), 4, "USDKRW", "SELL", round(buy * b.rng.uniform(0.95, 1.05) / 1e5) * 1e5, ndf=True)
    b.ask(cid, b.ago(30), "USDINR", "What is OCBC's view on the rupee?")
    b.ask(cid, b.ago(12), "USDKRW", "Any update on USD/KRW?")


def _dovetail(b: _Builder):
    """Control: 8 USD/SGD trades at irregular gaps and sizes, no swaps, two asks."""
    cid = "T04"
    plan = [(175, "spot", "BUY", 1.2), (160, 1, "SELL", 3.5), (118, "spot", "BUY", 0.8), (110, 3, "BUY", 2.6),
            (64, 1, "SELL", 1.9), (51, 3, "BUY", 4.1), (22, 2, "BUY", 1.5), (15, "spot", "BUY", 2.2)]
    for back, tenor, side, size in plan:
        tdate = b.ago(back)
        if tenor == "spot":
            b.trade(cid, tdate, generate.add_business_days(tdate, 2), "USDSGD", side, b.size(size), "USD/SGD Spot")
        else:
            b.forward(cid, tdate, tenor, "USDSGD", side, b.size(size))
    b.ask(cid, b.ago(90), "USDSGD", "What is OCBC's USD/SGD outlook?")
    b.ask(cid, b.ago(30), "USDSGD", "Any change to the USD/SGD forecast?")


def build(today: date | None = None, seed: int = SEED) -> Book:
    """Generate the pattern book with absolute dates for `today` (used to write the files)."""
    b = _Builder(today or today_sgt(), seed)
    for make in (_aurora, _bluewater, _cendana, _dovetail):
        make(b)
    b.trades.sort(key=lambda r: (r["trn_date"], r["trn_internal"]))
    b.interactions.sort(key=lambda r: (r["client_id"], r["asked_at"]))
    return Book(b.clients, b.contacts, b.trades, b.interactions)


def write_files(book: Book, today: date, folder: Path = PATTERN_DIR) -> list[Path]:
    """Write the book with every date as T± relative to `today` and no stored status."""
    folder.mkdir(parents=True, exist_ok=True)
    out = []

    def dump(name, header, rows):
        p = folder / name
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        out.append(p)

    dump(FILES["clients"], list(book.clients[0]), [list(r.values()) for r in book.clients])
    dump(FILES["contacts"], list(book.contacts[0]), [list(r.values()) for r in book.contacts])
    trades = []
    for t in book.trades:
        t = dict(t)
        for f in TRADE_DATE_FIELDS:
            t[f] = to_rel(date.fromisoformat(t[f]), today) if t[f] else ""
        for f in STATUS_FIELDS:
            t[f] = ""
        trades.append([t[f] for f in schema.TRADE_FIELDS])
    dump(FILES["trades"], schema.TRADE_HEADERS, trades)   # export-style headers, like dummy_data/trades.csv
    inter = [r | {"asked_at": to_rel_dt(datetime.fromisoformat(r["asked_at"]), today),
                  "conversation_id": r["conversation_id"] or ""} for r in book.interactions]
    dump(FILES["interactions"], list(inter[0]), [list(r.values()) for r in inter])
    return out


# ================================================================ legacy cleanup
def purge_legacy(conn: sqlite3.Connection) -> bool:
    """An earlier version copied T01-T04 into clientdata.db (marked by a pattern_meta table). Remove
    exactly those generated rows; asks a user logged about T01-T04 (I-... ids) are kept."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pattern_meta'").fetchone():
        return False
    cifs = [c[1] for c in CLIENTS]
    conn.execute(f"DELETE FROM clients WHERE client_id IN ({','.join('?' * len(CLIENT_IDS))})", CLIENT_IDS)
    conn.execute(f"DELETE FROM contacts WHERE contact_id IN ({','.join('?' * len(CLIENT_IDS))})",
                 [f"P{c}" for c in CLIENT_IDS])
    conn.execute(f"DELETE FROM trades WHERE sibs_cif IN ({','.join('?' * len(cifs))})", cifs)
    conn.execute("DELETE FROM interactions WHERE interaction_id LIKE ?", (INTERACTION_PREFIX + "%",))
    conn.execute("DROP TABLE pattern_meta")
    conn.commit()
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Regenerate the pattern test client files (dummy_data/patterns/).")
    ap.add_argument("--write", action="store_true", help="overwrite dummy_data/patterns/*.csv")
    ap.add_argument("--folder", type=Path, default=PATTERN_DIR)
    args = ap.parse_args(argv)
    today = today_sgt()
    book = build(today)
    if args.write:
        for p in write_files(book, today, args.folder):
            print(f"wrote {p}")
    print(f"{len(book.clients)} pattern clients, {len(book.trades)} trade rows, {len(book.interactions)} asks"
          + ("" if args.write else " (dry run; add --write to overwrite the files)"))


if __name__ == "__main__":
    main()
