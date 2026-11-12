"""Trade context: how a client's own past FX trades relate to the pair they are asking about.

Deterministic (no model call), so it works without an API key and is fully testable.

Classification
* pair matching ignores case, separators and direction ("sgd/usd" = "USDSGD" = "USD/SGD");
* only the identified client's trades (by SIBS CIF) are passed in;
* open = LIVE; closed = DEAD (matured / settled / expired) or MKT_OP (early termination);
* product spot / forward / swap (SWLEG legs sharing a Package reference = ONE swap) / option / NDF;
  purpose hedge (CLIENT_HEDGE) or investment (CLIENT_INVEST).

Netting (base currency of the pair, BUY +, SELL -)
* LIVE outright forwards and NDFs;
* LIVE swap far legs whose near leg is no longer live: the near leg has settled, so the far leg is
  open exposure exactly like a forward ("swap far leg (roll)");
* NOT netted: options (listed separately) and swaps whose two legs are both live (they net to zero).

Output
* `lines`: a few short labelled lines (position, net, next BUY / SELL maturing);
* `ideas`: up to 3 detector results, each with the evidence that triggered it. A detector says
  nothing unless its evidence rule is met - it never guesses;
* `offsets`, `rolls` and the full `trades` list for the "More details & ideas" dropdown.

Wording is factual and neutral ("may", "looks like"), never what the client should do, and carries
no client name, CIF or contact, so the lines and ideas can be handed to a model for rewording.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.common.instruments import pair_key

OFFSET_NOTIONAL_TOLERANCE = 0.10    # opposite trade within 10% of the earlier trade's notional
OFFSET_MATURITY_DAYS = 30           # ... and maturing within 30 days of it
SOON_DAYS = 30                      # "in 6 days (19 Nov)" rather than "on 5 Apr 2027"
CLOSED_LOOKBACK_MONTHS = 6          # closed trades listed in the trade list
ROLL_WINDOW_DAYS = 3                # a swap traded within 3 days of a maturity ...
ROLL_NOTIONAL_TOLERANCE = 0.10      # ... with notional within 10% looks like a roll
IDEA_MATURITY_DAYS = 14
RHYTHM_MIN_TRADES = 4
RHYTHM_BANDS = (("monthly", 25, 35), ("quarterly", 80, 100))
RHYTHM_MAX_SPREAD = 0.35            # std / median of the gaps between trade dates
NEXT_ASK_WINDOW_DAYS = 7
NEXT_ASK_MIN_COUNT = 3
NEXT_ASK_MIN_SHARE = 0.6
UNUSUAL_SIZE_MULTIPLE = 2.0
UNUSUAL_MIN_RUN = 3
MAX_IDEAS = 3
PURPOSE = {"CLIENT_HEDGE": "hedge", "CLIENT_INVEST": "investment"}
OUTRIGHT = ("spot", "forward", "ndf")


def trade_pair_key(t: dict) -> tuple[str, str] | None:
    return pair_key(f"{t.get('ccy1') or ''}{t.get('ccy2') or ''}")


# ------------------------------------------------------------------ classification
def _d(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def product_of(t: dict) -> str:
    label = (t.get("instrument_label") or "").upper()
    typ, grp = (t.get("trn_type") or "").upper(), (t.get("trn_group") or "").upper()
    if "NDF" in label or "NDF" in typ or "NDF" in grp:
        return "ndf"
    if grp == "OPT" or t.get("dcr_opt_instrument") or re.search(r"\b(CALL|PUT)\b", label):
        return "option"
    if typ == "SWLEG" or "SWAP" in label:
        return "swap"
    if "SPOT" in label or typ == "SPOT":
        return "spot"
    return "forward"


@dataclass
class Item:
    """One deal: a single trade row, or a whole swap package (side/notional/maturity of the far leg)."""
    ref: str
    product: str                 # spot | forward | swap | option | ndf
    side: str                    # BUY / SELL of `ccy`
    ccy: str                     # the pair's base currency (options: as booked)
    notional: float
    pair: str                    # "USD/SGD"
    trade_date: date | None
    maturity: date | None
    status: str                  # LIVE | DEAD | MKT_OP
    purpose: str
    near_side: str | None = None
    near_status: str | None = None   # swaps: LIVE / DEAD / MKT_OP, "UNKNOWN" for a lone far leg
    option: str | None = None        # call / put
    strike: float | None = None

    @property
    def open(self) -> bool:
        return self.status == "LIVE"

    @property
    def far_leg(self) -> bool:
        """A live swap far leg whose near leg has settled: open exposure, like a forward."""
        return self.product == "swap" and self.open and self.near_status not in (None, "LIVE")

    @property
    def both_legs_live(self) -> bool:
        return self.product == "swap" and self.open and self.near_status == "LIVE"

    @property
    def netted(self) -> bool:
        return self.open and (self.product in ("forward", "ndf") or self.far_leg)

    @property
    def signed(self) -> float:
        return self.notional if self.side == "BUY" else -self.notional

    @property
    def word(self) -> str:
        if self.far_leg:
            return "swap far leg"
        return {"spot": "spot", "forward": "forward", "swap": "FX swap", "option": "option", "ndf": "NDF"}[self.product]


def _side_in_base(t: dict, base: str) -> tuple[str, float]:
    """BUY/SELL and notional expressed in the base currency of the pair."""
    side = (t.get("buy_sell") or "").upper()
    if (t.get("ccy1") or "").upper() == base:
        return side, float(t.get("notional1") or 0)
    return ("SELL" if side == "BUY" else "BUY"), float(t.get("notional2") or 0)


def _purpose(t: dict) -> str:
    s = (t.get("strategy") or "").upper()
    return PURPOSE.get(s, s.lower())


def _maturity(t: dict) -> date | None:
    return _d(t.get("expiry_date")) or _d(t.get("period_end"))


def build_items(trades: list[dict], base: str, quote: str) -> list[Item]:
    pair = f"{base}/{quote}"
    packages: dict[str, list[dict]] = {}
    items: list[Item] = []
    for t in trades:
        prod = product_of(t)
        if prod == "swap" and t.get("package_ref"):
            packages.setdefault(t["package_ref"], []).append(t)
            continue
        if prod == "option":   # kept as booked: inverting a pair would turn a call into a put
            label = (t.get("instrument_label") or "") + " " + (t.get("dcr_opt_instrument") or "")
            cp = "call" if re.search(r"\bcall\b", label, re.I) else "put" if re.search(r"\bput\b", label, re.I) else None
            items.append(Item(t.get("trn_internal") or "", prod, (t.get("buy_sell") or "").upper(),
                              (t.get("ccy1") or "").upper(), float(t.get("notional1") or 0),
                              f"{t.get('ccy1')}/{t.get('ccy2')}", _d(t.get("trn_date")), _maturity(t),
                              (t.get("status") or "").upper(), _purpose(t), option=cp,
                              strike=float(t["strike_rate"]) if t.get("strike_rate") not in (None, "") else None))
            continue
        side, amount = _side_in_base(t, base)
        items.append(Item(t.get("trn_internal") or "", prod, side, base, amount, pair, _d(t.get("trn_date")),
                          _maturity(t), (t.get("status") or "").upper(), _purpose(t)))
    for ref, legs in packages.items():
        legs = sorted(legs, key=lambda x: (_maturity(x) or date.min))
        near, far = legs[0], legs[-1]
        side, amount = _side_in_base(far, base)
        if len(legs) > 1:
            near_side, near_status = _side_in_base(near, base)[0], (near.get("status") or "").upper()
        else:   # one leg on file: a far leg is exposure in its own right
            near_side = None
            near_status = "UNKNOWN" if "FAR" in (far.get("instrument_label") or "").upper() else None
        items.append(Item(ref, "swap", side, base, amount, pair,
                          min((d for d in (_d(x.get("trn_date")) for x in legs) if d), default=None),
                          _maturity(far), (far.get("status") or "").upper(), _purpose(far),
                          near_side=near_side, near_status=near_status))
    return items


# ------------------------------------------------------------------ wording helpers
def amt(ccy: str, x: float) -> str:
    x = abs(x)
    return f"{ccy} {x / 1e6:.1f}m" if x >= 1e5 else f"{ccy} {x / 1e3:.0f}k"


def day(d: date | None, year: bool = True) -> str:
    if not d:
        return "n/a"
    return f"{d.day} {d:%b %Y}" if year else f"{d.day} {d:%b}"


def short_day(d: date | None, today: date) -> str:
    """'19 Nov' this year, '5 Apr 2027' otherwise."""
    return day(d, year=bool(d) and d.year != today.year)


def _plural(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def _in_days(n: int) -> str:
    return "today" if n == 0 else f"in {_plural(n, 'day')}"


def _when(d: date, today: date) -> str:
    n = (d - today).days
    return f"{_in_days(n)} ({short_day(d, today)})" if 0 <= n <= SOON_DAYS else f"on {day(d)}"


def describe(i: Item) -> str:
    """Short phrase for one deal, e.g. 'BUY USD 7.7m forward'."""
    if i.product == "option":
        strike = f", strike {i.strike:g}" if i.strike is not None else ""
        return f"{i.side} {amt(i.ccy, i.notional)} {i.pair} {i.option or 'option'}{strike}"
    if i.product == "swap" and not i.far_leg:
        legs = f" (near {i.near_side} / far {i.side})" if i.near_side else f" ({i.side})"
        return f"{amt(i.ccy, i.notional)} FX swap{legs}"
    return f"{i.side} {amt(i.ccy, i.notional)} {i.word}"


def closed_word(i: Item) -> str:
    if i.status == "MKT_OP":
        return "terminated early"
    return {"spot": "settled", "option": "expired"}.get(i.product, "matured")


def status_label(i: Item) -> str:
    return "Live" if i.open else closed_word(i).capitalize()


def _line(label: str | None, text: str) -> dict:
    """One visible note line: a short bold label (None for a plain sentence) and its text."""
    return {"label": label, "text": text}


# ------------------------------------------------------------------ offsets and rolls
def find_offsets(netted: list[Item]) -> list[tuple[Item, Item]]:
    """(later, earlier) pairs: opposite direction, notional within 10% and maturity within 30 days of
    the earlier trade. Closest matches are paired first; each trade is used at most once."""
    order = sorted(netted, key=lambda i: (i.trade_date or date.min, i.ref))
    cands = []
    for k, later in enumerate(order):
        for earlier in order[:k]:
            if earlier.side == later.side or not (earlier.maturity and later.maturity) or not earlier.notional:
                continue
            gap = abs(later.notional - earlier.notional) / earlier.notional
            days = abs((later.maturity - earlier.maturity).days)
            if gap <= OFFSET_NOTIONAL_TOLERANCE and days <= OFFSET_MATURITY_DAYS:
                cands.append((gap, days, later, earlier))
    used: set[str] = set()
    out = []
    for _, _, later, earlier in sorted(cands, key=lambda c: (c[0], c[1], c[2].ref, c[3].ref)):
        if later.ref not in used and earlier.ref not in used:
            used |= {later.ref, earlier.ref}
            out.append((later, earlier))
    return sorted(out, key=lambda p: (p[1].trade_date or date.min))


def is_roll(swap: Item, src: Item) -> bool:
    """`swap` looks like a roll of `src`: traded within 3 days of src's maturity, notional within
    10%, and its far leg continues src's direction."""
    if swap.product != "swap" or swap.ref == src.ref or src.product not in ("forward", "ndf", "swap"):
        return False
    if not (swap.trade_date and src.maturity and src.notional):
        return False
    if src.trade_date and src.trade_date >= swap.trade_date:
        return False
    return (abs((swap.trade_date - src.maturity).days) <= ROLL_WINDOW_DAYS
            and abs(swap.notional - src.notional) / src.notional <= ROLL_NOTIONAL_TOLERANCE
            and swap.side == src.side)


def roll_source(swap: Item, items: list[Item]) -> Item | None:
    hits = [i for i in items if is_roll(swap, i)]
    return min(hits, key=lambda i: (abs((swap.trade_date - i.maturity).days), abs(swap.notional - i.notional),
                                    i.ref)) if hits else None


def _rolls(items: list[Item], today: date) -> list[str]:
    out = []
    for s in sorted((i for i in items if i.product == "swap" and i.open), key=lambda i: (i.maturity or date.max, i.ref)):
        if s.both_legs_live:
            out.append(f"{describe(s)}: both legs live, nets to zero.")
            continue
        src = roll_source(s, items)
        head = f"Swap far leg {s.side} {amt(s.ccy, s.notional)} (matures {day(s.maturity)})"
        if src:
            out.append(f"{head} looks like a roll of {src.side} {amt(src.ccy, src.notional)} {src.word} that "
                       f"matured {short_day(src.maturity, today)}.")
        else:
            out.append(f"{head}, traded {short_day(s.trade_date, today)}: no matching earlier maturity found.")
    return out


# ------------------------------------------------------------------ visible lines
def _open_lines(items: list[Item], pair: str, base: str, today: date, offset_refs: set[str]) -> list[dict]:
    live = [i for i in items if i.open]
    netted = [i for i in live if i.netted]
    options = [i for i in live if i.product == "option"]
    paired_swaps = [i for i in live if i.product == "swap" and not i.netted]
    spots = [i for i in live if i.product == "spot"]
    not_netted = ([_plural(len(options), "option")] if options else []) \
        + ([f"{_plural(len(paired_swaps), 'FX swap')} with both legs live (nets to zero)"] if paired_swaps else []) \
        + ([_plural(len(spots), "live spot trade")] if spots else [])
    if not netted:
        return [_line(f"Open {pair} trades (internal data)", ", ".join(not_netted))]
    net = sum(i.signed for i in netted)
    buys = sum(1 for i in netted if i.side == "BUY")
    lines = [_line(f"Open {pair} position (internal data)",
                   f"{_plural(len(netted), 'open trade')} ({buys} BUY, {len(netted) - buys} SELL)"),
             _line("Net", f"{'BUY' if net > 0 else 'SELL'} {amt(base, net)}" if abs(net) >= 5e4 else "about flat")]
    for side in ("BUY", "SELL"):
        upcoming = sorted((i for i in netted if i.side == side and i.maturity and i.maturity >= today),
                          key=lambda i: (i.maturity, i.ref))
        if upcoming:
            i = upcoming[0]
            lines.append(_line(f"Next {side} maturing", f"{_when(i.maturity, today)}, {amt(i.ccy, i.notional)} "
                                                       f"{i.word}{' (offset)' if i.ref in offset_refs else ''}"))
    if not_netted:
        lines.append(_line("Not netted", ", ".join(not_netted)))
    ndfs = sorted((i for i in netted if i.product == "ndf" and i.maturity), key=lambda i: i.maturity)
    if ndfs:
        lines.append(_line("NDF", f"next fixing {short_day(ndfs[0].maturity, today)}; cash-settled (no delivery), "
                                  f"so a new ask may be about unwinding/closing or the fixing"))
    return lines


# ------------------------------------------------------------------ idea detectors
def _idea(kind: str, rank: int, text: str, evidence: dict) -> dict:
    return {"kind": kind, "rank": rank, "text": text, "evidence": evidence}


def idea_next_ask(interactions: list[dict], pair: str) -> dict | None:
    """Pair B asked within 7 days after an ask about this pair, at least 3 times and in >= 60% of them."""
    key = pair_key(pair)
    asks, names = [], {}
    for r in interactions or []:
        try:
            t = datetime.fromisoformat(str(r.get("asked_at"))[:19])
        except ValueError:
            continue
        keys = set()
        for raw in (r.get("instruments") or "").split(";"):
            k = pair_key(raw)
            if k:
                keys.add(k)
                letters = re.sub(r"[^A-Za-z]", "", raw).upper()
                names.setdefault(k, f"{letters[:3]}/{letters[3:]}")
        asks.append((t, keys))
    a_times = sorted(t for t, ks in asks if key in ks)
    if len(a_times) < NEXT_ASK_MIN_COUNT:
        return None
    follow: Counter = Counter()
    for t in a_times:
        after = set()
        for t2, ks in asks:
            if t < t2 <= t + timedelta(days=NEXT_ASK_WINDOW_DAYS):
                after |= ks - {key}
        follow.update(after)
    if not follow:
        return None
    b, n = sorted(follow.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    if n < NEXT_ASK_MIN_COUNT or n / len(a_times) < NEXT_ASK_MIN_SHARE:
        return None
    return _idea("next_ask", 0, f"After {pair} asks, asked {names[b]} within a week {n} of {len(a_times)} times.",
                 {"pair_asked": pair, "next_pair": names[b], "times_followed": n, "asks": len(a_times),
                  "window_days": NEXT_ASK_WINDOW_DAYS})


def idea_maturity(items: list[Item], pair: str, today: date) -> dict | None:
    """An open trade maturing within 14 days, with how earlier maturities in the pair were handled."""
    soon = sorted((i for i in items if i.open and i.product != "spot" and i.maturity
                   and 0 <= (i.maturity - today).days <= IDEA_MATURITY_DAYS), key=lambda i: (i.maturity, i.ref))
    if not soon:
        return None
    i = soon[0]
    n = (i.maturity - today).days
    swaps = [s for s in items if s.product == "swap"]
    past = [x for x in items if x.status == "DEAD" and x.product in ("forward", "ndf", "swap") and x.maturity
            and x.maturity < today]
    rolled = [x for x in past if any(is_roll(s, x) for s in swaps)]
    history = (f"of {_plural(len(past), f'earlier {pair} maturity', f'earlier {pair} maturities')}, "
               f"{len(rolled)} looked rolled (swap within {ROLL_WINDOW_DAYS} days, size within 10%) and "
               f"{len(past) - len(rolled)} settled" if past else f"no earlier {pair} maturities on record")
    more = f" (+{len(soon) - 1} more within {IDEA_MATURITY_DAYS} days)" if len(soon) > 1 else ""
    verb = "expires" if i.product == "option" else "matures"
    return _idea("maturity", 1, f"{describe(i)} {verb} {_in_days(n)} ({short_day(i.maturity, today)}){more}; "
                                f"{history}.",
                 {"trade": i.ref, "maturity": i.maturity.isoformat(), "days": n, "also_within_window": len(soon) - 1,
                  "earlier_maturities": len(past), "rolled": len(rolled), "settled": len(past) - len(rolled)})


def idea_unusual(items: list[Item], pair: str, today: date) -> dict | None:
    """Newest outright trade at least 2x the median size of earlier ones, or a direction change after 3+."""
    outright = sorted((i for i in items if i.product in OUTRIGHT and i.trade_date), key=lambda i: (i.trade_date, i.ref))
    if len(outright) < 1 + UNUSUAL_MIN_RUN:
        return None
    newest, earlier = outright[-1], outright[:-1]
    med = statistics.median(x.notional for x in earlier)
    parts, ev = [], {"trade": newest.ref, "trade_date": newest.trade_date.isoformat(), "earlier_trades": len(earlier)}
    if med and newest.notional >= UNUSUAL_SIZE_MULTIPLE * med:
        ratio = newest.notional / med
        parts.append(f"{ratio:.1f}x the median size of earlier {pair} trades ({amt(newest.ccy, med)})")
        ev |= {"size_ratio": round(ratio, 2), "median_notional": med}
    run = 0
    for x in reversed(earlier):
        if x.side == newest.side:
            break
        run += 1
    if run >= UNUSUAL_MIN_RUN:
        parts.append(f"a {newest.side} after {run} {'SELL' if newest.side == 'BUY' else 'BUY'} trades in a row")
        ev |= {"opposite_run": run}
    if not parts:
        return None
    return _idea("unusual", 2, f"Newest {pair} trade ({describe(newest)}, {short_day(newest.trade_date, today)}) is "
                               + " and ".join(parts) + ".", ev)


def idea_rhythm(items: list[Item], pair: str, today: date) -> dict | None:
    """>= 4 outright trades whose gaps cluster around a month (25-35 days) or a quarter (80-100)."""
    outright = [i for i in items if i.product in OUTRIGHT and i.trade_date]
    dates = sorted({i.trade_date for i in outright})
    if len(outright) < RHYTHM_MIN_TRADES or len(dates) < RHYTHM_MIN_TRADES:
        return None
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    med = statistics.median(gaps)
    spread = statistics.pstdev(gaps) / med if med else float("inf")
    band = next((name for name, lo, hi in RHYTHM_BANDS if lo <= med <= hi), None)
    if not band or spread > RHYTHM_MAX_SPREAD:
        return None
    last, ago = dates[-1], (today - dates[-1]).days
    return _idea("rhythm", 3, f"Trades {pair} roughly {band} ({len(outright)} trades, median gap {med:g} days); "
                              f"last {short_day(last, today)} ({_plural(ago, 'day')} ago).",
                 {"trades": len(outright), "median_gap_days": med, "gap_spread": round(spread, 3),
                  "last_trade": last.isoformat()})


def ideas_for(items: list[Item], pair: str, today: date, interactions: list[dict]) -> list[dict]:
    """Ranked: the pair asked about (next likely ask) > maturity soon > the rest. At most 3."""
    found = [idea_next_ask(interactions, pair), idea_maturity(items, pair, today),
             idea_unusual(items, pair, today), idea_rhythm(items, pair, today)]
    return sorted((i for i in found if i), key=lambda i: i["rank"])[:MAX_IDEAS]


# ------------------------------------------------------------------ trade list
def _months_back(today: date, months: int) -> date:
    y, m = divmod(today.year * 12 + today.month - 1 - months, 12)
    return date(y, m + 1, min(today.day, 28))


def _trade_rows(items: list[Item], today: date, offsets: list[tuple[Item, Item]]) -> list[dict]:
    """Open trades (soonest maturity first), then trades closed in the last 6 months (most recent first)."""
    cutoff = _months_back(today, CLOSED_LOOKBACK_MONTHS)

    def closed_on(i: Item) -> date:
        return min(i.maturity or i.trade_date or date.min, today)

    live = sorted([i for i in items if i.open], key=lambda i: (i.maturity or date.max, i.ref))
    closed = sorted([i for i in items if not i.open and closed_on(i) >= cutoff],
                    key=lambda i: (closed_on(i), i.trade_date or date.min, i.ref), reverse=True)
    notes: dict[str, str] = {}
    for later, earlier in offsets:
        notes[later.ref] = f"offsets {earlier.side} {amt(earlier.ccy, earlier.notional)} " \
                           f"({short_day(earlier.trade_date, today)})"
        notes[earlier.ref] = f"offset by {later.side} {amt(later.ccy, later.notional)} " \
                             f"({short_day(later.trade_date, today)})"
    rows = []
    for i in live + closed:
        note = notes.get(i.ref)
        if i.product == "option":
            prod = f"Option: {i.pair} {i.option or ''}{f', strike {i.strike:g}' if i.strike is not None else ''}"
        elif i.far_leg:
            prod = "Swap far leg (roll)"
            src = roll_source(i, items)
            if not note and src:
                note = f"rolled from {src.side} {amt(src.ccy, src.notional)} {src.word} " \
                       f"({short_day(src.maturity, today)})"
        elif i.product == "swap":
            prod = f"FX swap (near {i.near_side} / far {i.side})" if i.near_side else "FX swap"
            if i.both_legs_live:
                note = "both legs live (nets to zero)"
        else:
            prod = {"spot": "Spot", "forward": "Forward", "ndf": "NDF (cash-settled)"}[i.product]
        rows.append({"trade_date": day(i.trade_date), "side": i.side, "notional": amt(i.ccy, i.notional),
                     "product": prod, "maturity": day(i.maturity), "status": status_label(i),
                     "note": note or i.purpose, "open": i.open})
    return rows


# ------------------------------------------------------------------ the context for one pair
def orientation(trades: list[dict], requested: str) -> tuple[str, str]:
    """Base/quote as the client's trades are booked (most common CCY 1); else as asked."""
    key = pair_key(requested)
    c = Counter((t.get("ccy1") or "").upper() for t in trades if (t.get("ccy1") or "").upper() in (key or ()))
    t = re.sub(r"[^A-Za-z]", "", requested).upper()
    base = c.most_common(1)[0][0] if c else t[:3]
    return base, (key[0] if key[1] == base else key[1])


def trade_context(trades: list[dict], requested_pair: str, today: date,
                  interactions: list[dict] | None = None) -> dict | None:
    """The note for ONE pair. `trades` and `interactions` must already be limited to the identified client."""
    key = pair_key(requested_pair)
    if not key:
        return None
    mine = [t for t in trades if trade_pair_key(t) == key]
    base, quote = orientation(mine, requested_pair)
    pair = f"{base}/{quote}"
    items = build_items(mine, base, quote)
    netted = [i for i in items if i.netted]
    offsets = find_offsets(netted)
    net_amount = sum(i.signed for i in netted)
    net = ({"side": "BUY" if net_amount > 0 else "SELL", "amount": round(abs(net_amount), 2),
            "text": f"{'BUY' if net_amount > 0 else 'SELL'} {amt(base, net_amount)}"}
           if netted and abs(net_amount) >= 5e4 else None)
    if not items:
        kind, lines = "never", [_line(None, f"No past {pair} trades on record.")]
    elif any(i.open for i in items):
        kind = "open"
        lines = _open_lines(items, pair, base, today, {x.ref for p in offsets for x in p})
    else:
        last = max(items, key=lambda i: (i.trade_date or date.min, i.ref))
        kind = "closed"
        lines = [_line(None, f"No open {pair} trades. Last: {describe(last)}, {short_day(last.trade_date, today)} "
                             f"({closed_word(last)}).")]
    rows = _trade_rows(items, today, offsets)
    n_open = sum(1 for r in rows if r["open"])
    return {"pair": pair, "kind": kind, "lines": lines, "net": net,
            "ideas": ideas_for(items, pair, today, interactions or []),
            "research_link": None,
            "offsets": [f"{a.side} {amt(a.ccy, a.notional)} ({short_day(a.trade_date, today)}) offsets "
                        f"{b.side} {amt(b.ccy, b.notional)} ({short_day(b.trade_date, today)})" for a, b in offsets],
            "rolls": _rolls(items, today),
            "trades": rows, "trade_count": len(rows), "open_count": n_open,
            "count_label": f"{_plural(len(rows), 'trade')} ({n_open} open)",
            "as_of": day(today), "text_source": "rules"}


def trade_contexts(trades: list[dict], pairs: list[str], today: date, interactions: list[dict] | None = None,
                   limit: int = 3) -> list[dict]:
    out, seen = [], set()
    for p in pairs:
        k = pair_key(p)
        if k and k not in seen:
            seen.add(k)
            ctx = trade_context(trades, p, today, interactions)
            if ctx:
                out.append(ctx)
        if len(out) >= limit:
            break
    return out
