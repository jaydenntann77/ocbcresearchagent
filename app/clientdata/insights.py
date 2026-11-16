"""Client-book insights for agent mode: compact, deterministic views of one client or the whole book.

These are the facts the agent's tools return. Every figure comes straight from the client book
(profile, trades, logged asks) and reuses trade_context's wording helpers, so the agent sees the
same numbers the client box shows ("SELL USD 5.0m forward", "19 Nov 2026"). No model call here.

Data minimisation: no SIBS CIF, RM codes or e-mail addresses leave this module - the agent gets
names, titles and trades, which is all it needs to brief a salesperson.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from app.clientdata.trade_context import (Item, _when, amt, build_items, day, describe, orientation, short_day,
                                          status_label, trade_contexts, trade_pair_key)
from app.common.instruments import pair_key

PRODUCT_NAME = {"spot": "Spot", "forward": "Forward", "swap": "FX swap", "option": "Option", "ndf": "NDF"}


def _split(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(";") if x.strip()]


def _fmt_pair(p: str) -> str:
    p = "".join(ch for ch in (p or "").upper() if ch.isalpha())
    return f"{p[:3]}/{p[3:]}" if len(p) == 6 else p


def card(c: dict) -> dict:
    """The profile fields a salesperson needs (no CIF, RM code or e-mail)."""
    return {"client_id": c["client_id"], "name": c.get("counterpart_name"), "segment": c.get("cust_seg"),
            "industry": c.get("industry"), "country": c.get("country"), "profile": c.get("profile"),
            "hedging_notes": c.get("hedging_notes"), "preferred_pairs": [_fmt_pair(p) for p in _split(c.get("preferred_pairs"))],
            "relationship_manager": c.get("cust_rm"), "team": c.get("rm_team_l3") or c.get("rm_team_l2")}


def items_by_pair(trades: list[dict]) -> dict[str, list[Item]]:
    """Every deal grouped by pair, oriented as the client books it (swap legs = one deal)."""
    groups: dict[tuple, list[dict]] = {}
    for t in trades:
        k = trade_pair_key(t)
        if k:
            groups.setdefault(k, []).append(t)
    out: dict[str, list[Item]] = {}
    for k, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        base, quote = orientation(rows, "".join(k))
        out[f"{base}/{quote}"] = build_items(rows, base, quote)
    return out


def _pair_filter(pair: str | None):
    k = pair_key(pair) if pair else None
    return (lambda p: pair_key(p) == k) if k else (lambda p: True)


def _row(i: Item, pair: str, today: date) -> dict:
    row = {"ref": i.ref, "pair": pair, "trade_date": day(i.trade_date), "product": PRODUCT_NAME[i.product],
           "deal": describe(i), "side": i.side, "notional": amt(i.ccy, i.notional),
           "maturity": day(i.maturity), "status": status_label(i), "purpose": i.purpose}
    if i.product == "option":
        row.update(option=i.option, strike=i.strike)
    if i.far_leg:
        row["product"] = "Swap far leg (roll)"
    if i.open and i.maturity:
        row["days_to_maturity"] = (i.maturity - today).days
    return {k: v for k, v in row.items() if v is not None}


def _net(items: list[Item], base: str) -> str | None:
    netted = [i for i in items if i.netted]
    total = sum(i.signed for i in netted)
    if not netted or abs(total) < 5e4:
        return None
    return f"{'BUY' if total > 0 else 'SELL'} {amt(base, total)} (net of open forwards, NDFs and swap far legs)"


def _asks(interactions: list[dict], clean, limit: int) -> list[dict]:
    return [{"asked_at": (r.get("asked_at") or "")[:16].replace("T", " "), "question": clean(r.get("question") or "")[:200],
             "topic": r.get("topic") or None} for r in interactions[:limit]]


def overview(client: dict, contacts: list[dict], trades: list[dict], interactions: list[dict], today: date,
             clean=lambda q: q) -> dict:
    """Meeting-prep view of one client: who they are, what they trade, what is open and maturing,
    what they asked about recently and any patterns the rule-based detectors found."""
    groups = items_by_pair(trades)
    allitems = [(p, i) for p, items in groups.items() for i in items]
    live = [(p, i) for p, i in allitems if i.open]
    dated = [(p, i) for p, i in allitems if i.trade_date]
    last = max(dated, key=lambda x: (x[1].trade_date, x[1].ref)) if dated else None
    first = min(dated, key=lambda x: x[1].trade_date) if dated else None
    pairs = []
    for p, items in groups.items():
        open_items = sorted([i for i in items if i.open and i.maturity and i.maturity >= today], key=lambda i: i.maturity)
        nxt = open_items[0] if open_items else None
        pairs.append({"pair": p, "deals": len(items), "open_deals": sum(1 for i in items if i.open),
                      "net_open_position": _net(items, p.split("/")[0]),
                      "next_maturity": f"{describe(nxt)} {_when(nxt.maturity, today)}" if nxt else None,
                      "last_traded": short_day(max((i.trade_date for i in items if i.trade_date), default=None), today)})
    soon = sorted([(p, i) for p, i in live if i.maturity and 0 <= (i.maturity - today).days <= 30],
                  key=lambda x: x[1].maturity)
    ideas = []
    for ctx in trade_contexts(trades, list(groups), today, interactions, limit=6):
        ideas += [{"pair": ctx["pair"], "kind": x["kind"], "text": x["text"]} for x in ctx.get("ideas") or []]
        ideas += [{"pair": ctx["pair"], "kind": "roll", "text": r} for r in (ctx.get("rolls") or [])[:2]]
    return {
        "as_of": day(today),
        "client": card(client),
        "contacts": [{"contact_id": p["contact_id"], "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                      "title": p.get("title"), "primary": str(p.get("is_primary")) in ("1", "True", "true")}
                     for p in contacts],
        "activity": {
            "total_deals": len(allitems), "open_deals": len(live),
            "deals_last_90_days": sum(1 for _, i in dated if (today - i.trade_date).days <= 90),
            "first_trade": day(first[1].trade_date) if first else None,
            "last_trade": {"date": day(last[1].trade_date), "pair": last[0], "deal": describe(last[1]),
                           "status": status_label(last[1])} if last else None,
            "products": dict(Counter(PRODUCT_NAME[i.product] for _, i in allitems).most_common()),
            "purpose": dict(Counter(i.purpose for _, i in allitems if i.purpose).most_common()),
        },
        "pairs": pairs,
        "maturing_next_30_days": [_row(i, p, today) for p, i in soon],
        "recent_asks": _asks(interactions, clean, 5),
        "pattern_notes": ideas[:6],
    }


def trade_list(trades: list[dict], today: date, pair: str | None = None, status: str = "all",
               product: str | None = None, since_days: int | None = None, limit: int = 25) -> dict:
    """The client's deals, newest first, with optional filters."""
    keep = _pair_filter(pair)
    rows = []
    for p, items in items_by_pair(trades).items():
        if not keep(p):
            continue
        for i in items:
            if status == "open" and not i.open or status == "closed" and i.open:
                continue
            if product and product.lower() not in (i.product, PRODUCT_NAME[i.product].lower()):
                continue
            if since_days is not None and (not i.trade_date or (today - i.trade_date).days > since_days):
                continue
            rows.append((i.trade_date or date.min, i.ref, _row(i, p, today)))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    limit = max(1, min(int(limit or 25), 60))
    return {"as_of": day(today), "matching_deals": len(rows), "shown": min(len(rows), limit),
            "open_in_result": sum(1 for r in rows if r[2]["status"] == "Live"),
            "deals": [r[2] for r in rows[:limit]]}


def maturities(book_rows: list[tuple[dict, list[dict]]], today: date, days: int = 30,
               pair: str | None = None) -> dict:
    """Open deals maturing in the next `days` days, across the given clients, soonest first."""
    days = max(1, min(int(days or 30), 366))
    keep = _pair_filter(pair)
    rows = []
    for client, trades in book_rows:
        groups = items_by_pair(trades)
        rolled_pairs = {p for p, items in groups.items() if any(i.far_leg for i in items)}
        for p, items in groups.items():
            if not keep(p):
                continue
            for i in items:
                if i.open and i.maturity and 0 <= (i.maturity - today).days <= days:
                    r = _row(i, p, today) | {"client_id": client["client_id"], "client": client.get("counterpart_name"),
                                             "has_rolled_this_pair_before": p in rolled_pairs}
                    rows.append((i.maturity, client["client_id"], r))
    rows.sort(key=lambda r: (r[0], r[1]))
    by_client = Counter(r[2]["client"] for r in rows)
    return {"as_of": day(today), "window": f"{day(today)} to {day(today + timedelta(days=days))}",
            "maturing_deals": len(rows), "clients": dict(by_client.most_common()),
            "deals": [r[2] for r in rows[:60]]}


def positions(trades: list[dict], interactions: list[dict], today: date, pair: str | None = None) -> dict:
    """Per pair: open position lines, net exposure, offsets, rolls and rule-based pattern notes."""
    pairs = [p for p in items_by_pair(trades) if _pair_filter(pair)(p)]
    if pair and not pairs:
        pairs = [pair]   # never traded: trade_context says so
    out = []
    for ctx in trade_contexts(trades, pairs, today, interactions, limit=6):
        out.append({"pair": ctx["pair"], "summary": ctx["count_label"],
                    "position_lines": [(f"{x['label']}: " if x.get("label") else "") + x["text"] for x in ctx["lines"]],
                    "net_open": ctx["net"]["text"] if ctx.get("net") else None,
                    "offsets": ctx.get("offsets") or [], "rolls": ctx.get("rolls") or [],
                    "pattern_notes": [x["text"] for x in ctx.get("ideas") or []]})
    return {"as_of": day(today), "pairs": out}


def client_list(rows: list[tuple[dict, list[dict]]], today: date, rm: str | None = None, segment: str | None = None,
                pair: str | None = None, query: str | None = None) -> dict:
    """Clients in the book with a one-line activity summary, optionally filtered."""
    keep = _pair_filter(pair)
    out = []
    for c, trades in rows:
        if rm and rm.lower() not in (c.get("cust_rm") or "").lower():
            continue
        if segment and segment.lower() not in ((c.get("cust_seg") or "") + " " + (c.get("profile") or "")).lower():
            continue
        q = (query or "").lower()
        if q and q not in " ".join(str(c.get(k) or "") for k in ("counterpart_name", "aliases", "industry", "country",
                                                                  "profile", "hedging_notes")).lower():
            continue
        groups = items_by_pair(trades)
        if pair and not any(keep(p) for p in groups):
            continue
        live = sorted([i for items in groups.values() for i in items if i.open and i.maturity and i.maturity >= today],
                      key=lambda i: i.maturity)
        out.append(card(c) | {"pairs_traded": list(groups), "open_deals": sum(1 for items in groups.values()
                                                                            for i in items if i.open),
                              "next_maturity": day(live[0].maturity) if live else None})
    return {"as_of": day(today), "count": len(out), "clients": out}
