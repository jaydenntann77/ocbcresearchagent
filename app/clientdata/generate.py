"""Seeded generator for the synthetic client book.

    python -m app.clientdata.generate            # writes data/clientdata/clientdata.db + dummy_data/*.csv
    python -m app.clientdata.generate --seed 7   # different but reproducible book

Everything here is FICTIONAL: company names, people, CIFs, trade numbers and
market levels. Spot levels are rough, made-up anchors so that strikes look
plausible; they are not market data and must never be quoted as such.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from app.common import config
from app.clientdata import schema

AS_OF = date(2026, 11, 5)            # matches the research corpus end date
HISTORY_START = date(2026, 5, 4)     # ~6 months of trade history
DB_PATH = config.CLIENT_DIR / "clientdata.db"
CSV_DIR = config.ROOT / "dummy_data"

# pair -> (made-up spot anchor at AS_OF, annualised vol, decimals, pip size)
PAIRS = {
    "USDSGD": (1.3000, 0.05, 4, 0.0001),
    "EURUSD": (1.1600, 0.07, 4, 0.0001),
    "USDJPY": (150.00, 0.10, 2, 0.01),
    "GBPUSD": (1.3300, 0.08, 4, 0.0001),
    "AUDUSD": (0.6600, 0.09, 4, 0.0001),
    "USDCNH": (7.1500, 0.04, 4, 0.0001),
    "USDMYR": (4.2500, 0.05, 4, 0.0001),
    "USDIDR": (16300.0, 0.06, 0, 1.0),
    "USDTHB": (33.000, 0.07, 3, 0.001),
    "USDHKD": (7.7800, 0.01, 4, 0.0001),
    "XAUUSD": (3900.0, 0.16, 2, 0.01),
}

# ---------------------------------------------------------------- reference data
RMS = [
    ("RM001", "Tan Wei Ling", "Global Commercial Banking", "Large Corporates", "SG Corporates 1"),
    ("RM002", "Marcus Lim", "Global Commercial Banking", "Large Corporates", "SG Corporates 2"),
    ("RM003", "Priya Raman", "Global Commercial Banking", "Emerging Business", "SME East"),
    ("RM004", "Daniel Koh", "Global Wealth Management", "Private Banking", "PB Greater China"),
    ("RM005", "Aisha Rahman", "Global Treasury", "Financial Institutions", "FI & NBFI"),
]
DEALERS = [("D101", "KEVIN.ONG"), ("D102", "SARAH.CHUA"), ("D103", "RYAN.TEO"), ("D104", "MEI.HO")]

# name, label, aliases, seg, industry, country, profile, notes, pairs, rm
CLIENTS = [
    ("Harbourline Logistics Pte Ltd", "HARBOURLINE", "Harbourline;Company A", "LC", "Shipping & Logistics", "SG",
     "USD earner", "Earns USD freight revenue, pays SGD costs; sells USD forward 3-6M.", "USDSGD;USDCNH", "RM001"),
    ("Meridian Foods Holdings Ltd", "MERIDIAN FOODS", "Meridian;Meridian Foods", "LC", "Food & Beverage", "SG",
     "importer", "Imports AUD dairy and USD grains; buys AUD and USD forward.", "AUDUSD;USDSGD", "RM001"),
    ("Meridian Food Industries Sdn Bhd", "MERIDIAN FI", "Meridian Food Industries", "SME", "Food Manufacturing",
     "MY", "exporter", "Malaysian exporter; sells USD vs MYR.", "USDMYR", "RM003"),
    ("Kestrel Semiconductor Pte Ltd", "KESTREL SEMI", "Kestrel", "LC", "Electronics", "SG",
     "USD earner", "USD revenue, JPY equipment capex; uses forwards and occasional options.", "USDSGD;USDJPY",
     "RM002"),
    ("Lumina Property Trust", "LUMINA REIT", "Lumina;Lumina REIT", "FI", "Real Estate", "SG",
     "investor", "Holds GBP and AUD properties; hedges distributions with FX swaps.", "GBPUSD;AUDUSD;USDSGD",
     "RM005"),
    ("Nanyang Textile Trading Co", "NANYANG TEXTILE", "Nanyang Textile", "SME", "Wholesale Trade", "SG",
     "importer", "Pays CNH and THB suppliers; mostly spot, some 1-3M forwards.", "USDCNH;USDTHB", "RM003"),
    ("Orchid Bay Hospitality Group", "ORCHID BAY", "Orchid Bay", "LC", "Hospitality", "SG",
     "mixed", "Hotels in SG, ID and TH; converts IDR and THB receipts.", "USDIDR;USDTHB;USDSGD", "RM002"),
    ("Pinnacle Asset Management", "PINNACLE AM", "Pinnacle", "FI", "Asset Management", "SG",
     "investor", "Hedges USD and EUR fund share classes back to SGD; rolls swaps monthly.", "USDSGD;EURUSD",
     "RM005"),
    ("Mr Henry Wong", "WONG HENRY", "Henry Wong", "PB", "Private Individual", "HK",
     "investor", "Private banking client; trades gold and JPY options for views.", "XAUUSD;USDJPY", "RM004"),
    ("Silverleaf Family Office", "SILVERLEAF FO", "Silverleaf", "PB", "Family Office", "SG",
     "investor", "Diversified portfolio; buys gold on dips, holds USD/HKD.", "XAUUSD;USDHKD;EURUSD", "RM004"),
    ("Coastal Energy Resources Pte Ltd", "COASTAL ENERGY", "Coastal Energy", "LC", "Oil & Gas", "SG",
     "USD earner", "USD revenue; large SGD payroll; layered USD/SGD forwards out to 12M.", "USDSGD", "RM001"),
    ("Greenfield Agritech Pte Ltd", "GREENFIELD AGRI", "Greenfield", "SME", "Agriculture", "SG",
     "importer", "Buys EUR machinery; occasional EUR forwards.", "EURUSD;USDSGD", "RM003"),
]

CONTACTS = {  # client index -> [(first, last, title)]; first contact is primary
    0: [("Jimmy", "Tan", "Group Treasurer"), ("Rachel", "Goh", "Finance Manager")],
    1: [("Jimmy", "Lee", "CFO"), ("Siew Ling", "Ng", "Treasury Analyst")],
    2: [("Ahmad", "Ismail", "Finance Director")],
    3: [("Kenji", "Watanabe", "VP Finance"), ("Grace", "Lim", "Treasury Manager"), ("Victor", "Chan", "CFO")],
    4: [("Olivia", "Tan", "Head of Capital Management"), ("Ben", "Yeo", "Treasury Associate")],
    5: [("Ah Kow", "Lim", "Owner"), ("Michelle", "Lim", "Accounts")],
    6: [("Budi", "Santoso", "Group Financial Controller"), ("Natalie", "Ong", "Treasury Manager")],
    7: [("Sean", "Pereira", "Portfolio Manager"), ("Hui Min", "Toh", "Operations")],
    8: [("Henry", "Wong", "Self")],
    9: [("Catherine", "Seah", "CIO"), ("Jimmy", "Seah", "Investment Associate")],
    10: [("Farid", "Hassan", "Treasurer"), ("Lynn", "Chia", "FX Desk Liaison")],
    11: [("Eugene", "Foo", "Founder & CEO")],
}

QUESTION_TEMPLATES = {
    "forecast": ["What is OCBC's {p} forecast for the next 12 months?",
                 "Can you send the latest {p} outlook and key risks?",
                 "Where does OCBC see {p} by end-2026?"],
    "rates": ["What is the house view on the Fed path and what does it mean for {p}?"],
    "commodities": ["What is OCBC's gold forecast and the drivers behind it?"],
}


# ---------------------------------------------------------------- helpers
def business_days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def add_business_days(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    day = min(d.day, [31, 29 if y % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    out = date(y, m, day)
    while out.weekday() >= 5:
        out += timedelta(days=1)
    return out


def spot_paths(rng: random.Random, days: list[date]) -> dict[str, dict[date, float]]:
    """Random walk that ENDS at each pair's anchor on AS_OF (walk backwards)."""
    paths = {}
    for pair, (anchor, vol, dp, _) in PAIRS.items():
        daily = 0.6 * vol / math.sqrt(252)  # damped so history stays near today's anchors
        level, path = anchor, {}
        for d in reversed(days):
            path[d] = round(level, dp)
            level *= math.exp(rng.gauss(0, daily))
        paths[pair] = path
    return paths


def to_sgd(amount: float, ccy: str, spots: dict[str, float]) -> float:
    if ccy == "SGD":
        return amount
    usd = amount if ccy == "USD" else None
    if usd is None:
        if f"{ccy}USD" in spots:
            usd = amount * spots[f"{ccy}USD"]
        elif f"USD{ccy}" in spots:
            usd = amount / spots[f"USD{ccy}"]
        else:
            raise KeyError(ccy)
    return usd * spots["USDSGD"]


@dataclass
class Book:
    clients: list[dict]
    contacts: list[dict]
    trades: list[dict]
    interactions: list[dict]


# ---------------------------------------------------------------- generator
def generate(seed: int = 42, n_trades: int = 360) -> Book:
    rng = random.Random(seed)
    days = business_days(HISTORY_START, AS_OF)
    paths = spot_paths(rng, days)
    spot_on = lambda d: {p: paths[p][d] for p in PAIRS}  # noqa: E731
    rm_by_code = {r[0]: r for r in RMS}

    clients, contacts = [], []
    for i, (name, label, aliases, seg, ind, ctry, prof, notes, pairs, rm) in enumerate(CLIENTS):
        code, rm_name, l1, l2, l3 = rm_by_code[rm]
        clients.append({
            "client_id": f"C{i + 1:03d}", "sibs_cif": f"{rng.randint(10**8, 10**9 - 1)}",
            "counterpart_name": name, "counterpart_label": label, "aliases": aliases, "cust_seg": seg,
            "industry": ind, "country": ctry, "profile": prof, "hedging_notes": notes, "preferred_pairs": pairs,
            "cust_rm": rm_name, "customer_rm_code": code, "rm_team_l1": "OCBC Singapore", "rm_team_l2": l1,
            "rm_team_l3": l2, "rm_team_l4": l3, "rm_team_l5": rm_name,
        })
        domain = label.split()[0].lower() + ".example.com"
        for j, (first, last, title) in enumerate(CONTACTS[i]):
            contacts.append({
                "contact_id": f"P{len(contacts) + 1:03d}", "client_id": f"C{i + 1:03d}", "first_name": first,
                "last_name": last, "title": title,
                "email": f"{first.lower().replace(' ', '')}.{last.lower()}@{domain}", "is_primary": int(j == 0),
            })

    trades: list[dict] = []
    weights = [3, 2, 1, 2, 2, 2, 1.5, 3, 1, 1.5, 2.5, 1]  # trading activity per client
    contract_no = 41_200_000
    while len(trades) < n_trades:
        ci = rng.choices(range(len(clients)), weights=weights)[0]
        c = clients[ci]
        pair = rng.choice(c["preferred_pairs"].split(";"))
        kind = rng.choices(["SPOT", "FWD", "SWAP", "OPT"],
                           weights=[3, 4, 2 if c["cust_seg"] == "FI" else 0.5,
                                    2 if c["cust_seg"] == "PB" else 0.4])[0]
        contract_no += rng.randint(1, 40)
        trades.extend(_make_trade(rng, c, pair, kind, contract_no, days, spot_on))
    trades.sort(key=lambda t: (t["trn_date"], t["trn_internal"]))

    interactions = _make_interactions(rng, clients, contacts)
    return Book(clients, contacts, trades, interactions)


def _make_trade(rng, c, pair, kind, contract_no, days, spot_on) -> list[dict]:
    anchor, vol, dp, pip = PAIRS[pair]
    ccy1, ccy2 = pair[:3], pair[3:]
    tdate = rng.choice(days)
    spots_t = spot_on(tdate)
    spot = spots_t[pair]
    dealer_id, dealer = rng.choice(DEALERS)

    # client direction from their profile
    if c["profile"] == "USD earner" and ccy1 == "USD":
        side = "SELL"
    elif c["profile"] == "importer":
        side = "BUY" if ccy1 != "USD" or ccy2 in ("CNH", "THB", "SGD") else "SELL"
    elif c["profile"] == "exporter":
        side = "SELL"
    else:
        side = rng.choice(["BUY", "SELL"])

    if ccy1 == "XAU":
        notional1 = float(rng.choice([100, 200, 500, 1000, 2000]))
    else:
        size = {"LC": (1, 20), "FI": (5, 50), "SME": (0.1, 2), "PB": (0.5, 5)}[c["cust_seg"]]
        notional1 = round(rng.uniform(*size), 1) * 1_000_000

    margin_pips = rng.choice([2, 3, 5, 8, 10, 15, 20, 25]) * (0.5 if c["cust_seg"] == "FI" else 1)
    margin = margin_pips * pip
    carry = rng.uniform(-0.02, 0.02)  # annual fwd points as % of spot, made up

    def leg(months: int | None, leg_side: str, suffix: str, trn_type: str, label: str, strike_override=None,
            option: str | None = None):
        if months is None:
            expiry = add_business_days(tdate, 2)
            tenor_y = 2 / 365
        else:
            expiry = add_months(tdate, months)
            tenor_y = (expiry - tdate).days / 365
        outright = spot * (1 + carry * tenor_y)
        client_rate = outright + (margin if leg_side == "BUY" else -margin)
        strike = strike_override if strike_override is not None else round(client_rate, dp + 1)
        notional2 = round(notional1 * strike, 2)
        credit_fcy = round(notional1 * margin, 2)       # in ccy2
        credit_sgd = round(to_sgd(credit_fcy, ccy2, spots_t), 2)
        status, last_op = _status(rng, expiry)
        mtm = _mtm(notional1, strike, leg_side, ccy2, pair, expiry, status, carry, spot_on, option)
        npv0, s0, npv1, s1, npv2, s2 = mtm
        return {
            "contract_ref": f"{contract_no}", "package_ref": "", "trn_internal": f"{contract_no}{suffix}",
            "portfolio": {"FI": "SG_FX_SALES_FI", "PB": "SG_FX_SALES_PB"}.get(c["cust_seg"], "SG_FX_SALES_CORP"),
            "trade_category": "Sales", "dealer": dealer, "remark": "", "counterpart_label": c["counterpart_label"],
            "counterpart_name": c["counterpart_name"], "cust_seg": c["cust_seg"], "cust_rm": c["cust_rm"],
            "trn_date": tdate.isoformat(), "period_start": tdate.isoformat(), "period_end": expiry.isoformat(),
            "instrument_label": label, "dcr_opt_instrument": "", "ccy1": ccy1, "notional1": notional1,
            "ccy2": ccy2, "notional2": notional2, "initial_price": spot, "strike_rate": strike,
            "sale_credit_ccy": ccy2, "sales_fx_margin_fcy": round(margin, dp + 2),
            "amt_sales_credit_udf_fcy": credit_fcy, "total_sale_credit_fcy": credit_fcy, "nominal_ccy": ccy1,
            "nominal_amt_adj": notional1, "notional_sgd": round(to_sgd(notional1, ccy1, spots_t), 2),
            "sales_fx_margin_sgd": round(to_sgd(margin, ccy2, spots_t), 6),
            "amt_sales_credit_udf_sgd": credit_sgd, "total_sales_credit_sgd": credit_sgd,
            "cost_centre": "SGTM" + {"LC": "101", "SME": "102", "FI": "201", "PB": "301"}[c["cust_seg"]],
            "strategy": "CLIENT_HEDGE" if c["profile"] != "investor" else "CLIENT_INVEST",
            "trn_family": "CURR", "trn_group": "FXD", "trn_type": trn_type, "status": status,
            "ta_rm_id": c["customer_rm_code"], "expiry_date": expiry.isoformat(),
            "trn_external": f"EXT{contract_no}{suffix}", "buy_sell": leg_side,
            "spot_margin": round(margin, dp + 2), "comment_1": "", "sibs_cif": c["sibs_cif"],
            "rm_team_l1": c["rm_team_l1"], "rm_team_l2": c["rm_team_l2"], "rm_team_l3": c["rm_team_l3"],
            "rm_team_l4": c["rm_team_l4"], "rm_team_l5": c["rm_team_l5"], "customer_rm_code": c["customer_rm_code"],
            "amendment_status": "Amended" if rng.random() < 0.05 else "Not amended",
            "contract_na_event_action": "", "security_isin": "", "contract_source_module": "FX",
            "last_market_operation": last_op,
            "contract_last_event": "Amendment" if rng.random() < 0.05 else "Insertion",
            "contract_last_impact_event": last_op, "sys_date": tdate.isoformat(),
            "sys_time": f"{rng.randint(8, 17):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}",
            "nfin_npv0": npv0, "nfin_npv0s": round(npv0 * s0, 2) if ccy2 != "SGD" else npv0, "fxspot0s": s0,
            "nfin_npv1": npv1, "fxspot1s": s1, "nfin_npv1s": round(npv1 * s1, 2) if ccy2 != "SGD" else npv1,
            "nfin_npv2": npv2, "fxspot2s": s2, "nfin_npv2s": round(npv2 * s2, 2) if ccy2 != "SGD" else npv2,
            "pl_ccy": ccy2, "entity": "OCBC SG", "entity_accounting_ccy": "SGD", "external_inter_intra": "External",
            "internal": "N", "dealer_id": dealer_id, "contract_origin_ref": "", "replacement_origin_nb": "",
            "trader_credit_udf_fcy": round(credit_fcy * 0.2, 2), "trader_credit_udf_sgd": round(credit_sgd * 0.2, 2),
            "total_client_markup_fcy": credit_fcy, "total_client_markup_sgd": credit_sgd, "replacement_date": "",
        }

    slash = f"{ccy1}/{ccy2}"
    if kind == "SPOT":
        return [leg(None, side, "", "FXD", f"{slash} Spot")]
    if kind == "FWD":
        m = rng.choice([1, 2, 3, 3, 6, 6, 9, 12])
        t = leg(m, side, "", "FXD", f"{slash} Fwd {m}M")
        t["remark"] = rng.choice(["", "Layered hedge", "Invoice hedge", "Rolled from prior fwd"])
        return [t]
    if kind == "SWAP":
        m = rng.choice([1, 1, 3, 6])
        near = leg(None, side, "-N", "SWLEG", f"{slash} Swap {m}M (near)")
        far = leg(m, "SELL" if side == "BUY" else "BUY", "-F", "SWLEG", f"{slash} Swap {m}M (far)")
        for t in (near, far):
            t["package_ref"] = f"PKG{contract_no}"
        return [near, far]
    # vanilla option
    m = rng.choice([1, 2, 3, 6])
    cp = rng.choice(["Call", "Put"])
    k = round(spot * (1 + rng.choice([-0.03, -0.02, 0.0, 0.02, 0.03])), dp)
    t = leg(m, side, "", "SMP", f"{slash} {cp} {m}M K={k}", strike_override=k, option=cp)
    t["trn_group"] = "OPT"
    t["dcr_opt_instrument"] = f"{slash} Vanilla {cp} {'European' if rng.random() < 0.8 else 'American'}"
    t["comment_1"] = f"Premium {round(rng.uniform(0.4, 2.5), 2)}% of notional"
    return [t]


def _status(rng, expiry: date) -> tuple[str, str]:
    if expiry < AS_OF:
        return "DEAD", "Maturity"
    if rng.random() < 0.04:
        return "MKT_OP", "Early termination"
    return "LIVE", "New"


def _mtm(notional1, strike, side, ccy2, pair, expiry, status, carry, spot_on, option=None):
    """Very rough MTM in ccy2 for today and the two previous business days.
    Options use intrinsic value against the forward (no time value) - dummy data only."""
    d0 = AS_OF
    d1 = d0 - timedelta(days=1 if d0.weekday() != 0 else 3)
    d2 = d1 - timedelta(days=1 if d1.weekday() != 0 else 3)
    out = []
    for d in (d0, d1, d2):
        spots = spot_on(d)
        to_sgd_rate = round(to_sgd(1.0, ccy2, spots), 6)
        if status != "LIVE":
            out += [0.0, to_sgd_rate]
            continue
        remaining = max((expiry - d).days, 0) / 365
        fwd = spots[pair] * (1 + carry * remaining)
        sign = 1 if side == "BUY" else -1
        if option == "Call":
            payoff = max(fwd - strike, 0.0)
        elif option == "Put":
            payoff = max(strike - fwd, 0.0)
        else:
            payoff = fwd - strike
        out += [round(sign * notional1 * payoff, 2), to_sgd_rate]
    return tuple(out)


def _make_interactions(rng, clients, contacts) -> list[dict]:
    rows = []
    for c in clients:
        people = [p for p in contacts if p["client_id"] == c["client_id"]]
        for _ in range(rng.randint(1, 4)):
            p = rng.choice(people)
            pair = rng.choice(c["preferred_pairs"].split(";"))
            topic = "commodities" if pair.startswith("XAU") else rng.choice(["forecast", "forecast", "rates"])
            q = rng.choice(QUESTION_TEMPLATES[topic]).format(p=f"{pair[:3]}/{pair[3:]}")
            day = rng.choice(business_days(date(2026, 9, 1), AS_OF))
            rows.append({
                "interaction_id": f"I{len(rows) + 1:04d}", "client_id": c["client_id"],
                "contact_id": p["contact_id"],
                "asked_at": datetime(day.year, day.month, day.day, rng.randint(9, 17), rng.randint(0, 59)).isoformat(),
                "logged_by": c["cust_rm"], "question": q, "instruments": pair, "topic": topic,
                "answer_summary": "(seeded example - no answer stored)", "conversation_id": None,
            })
    rows.sort(key=lambda r: r["asked_at"])
    for i, r in enumerate(rows):
        r["interaction_id"] = f"I{i + 1:04d}"
    return rows


# ---------------------------------------------------------------- output
def write_sqlite(book: Book, path: Path = DB_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript(schema.ddl())
    for table, rows in (("clients", book.clients), ("contacts", book.contacts), ("trades", book.trades),
                        ("interactions", book.interactions)):
        cols = list(rows[0])
        conn.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                         [tuple(r[c] for c in cols) for r in rows])
    conn.commit()
    conn.close()
    return path


def write_csvs(book: Book, out_dir: Path = CSV_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, rows in (("clients", book.clients), ("contacts", book.contacts),
                       ("interactions", book.interactions)):
        p = out_dir / f"{name}.csv"
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        paths.append(p)
    p = out_dir / "trades.csv"  # export-style headers, exactly as in the sales report
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(schema.TRADE_HEADERS)
        w.writerows([[t[k] for k in schema.TRADE_FIELDS] for t in book.trades])
    paths.append(p)
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate the synthetic client book.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--trades", type=int, default=360)
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--csv-dir", type=Path, default=CSV_DIR)
    args = ap.parse_args(argv)
    book = generate(args.seed, args.trades)
    db = write_sqlite(book, args.db)
    csvs = write_csvs(book, args.csv_dir)
    live = sum(t["status"] == "LIVE" for t in book.trades)
    print(f"{len(book.clients)} clients, {len(book.contacts)} contacts, {len(book.trades)} trade rows "
          f"({live} live), {len(book.interactions)} interactions")
    print(f"SQLite: {db}")
    for p in csvs:
        print(f"CSV:    {p}")


if __name__ == "__main__":
    main()
