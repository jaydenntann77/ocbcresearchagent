"""Trade context in the client box: deterministic correlation, idea detectors, research link,
optional Haiku wording (faked) and the "which client?" picker. All offline. NDF cases use fixtures
(the dummy book has no NDFs)."""
from datetime import date

import pytest

from app.clientdata.generate import generate
from app.clientdata.identify import resolve_pick
from app.clientdata.trade_context import pair_key, trade_context, trade_contexts
from app.orchestrator import trade_note

TODAY = date(2026, 11, 13)
BOOK = generate()


def T(ref, trade_date, side, n1, mat, *, ccy1="USD", ccy2="SGD", rate=1.30, label=None, typ="FXD", grp="FXD",
      status="LIVE", strategy="CLIENT_HEDGE", pkg="", strike=None, opt=""):
    return {"trn_internal": ref, "package_ref": pkg, "trn_date": trade_date, "expiry_date": mat, "period_end": mat,
            "buy_sell": side, "ccy1": ccy1, "notional1": n1, "ccy2": ccy2, "notional2": n1 * rate,
            "instrument_label": label or f"{ccy1}/{ccy2} Fwd 3M", "trn_type": typ, "trn_group": grp,
            "status": status, "strategy": strategy, "strike_rate": strike, "dcr_opt_instrument": opt,
            "sibs_cif": "111"}


def SWAP(ref, trade_date, near_side, n, near_mat, far_mat, near_status="DEAD", far_status="LIVE"):
    far_side = "BUY" if near_side == "SELL" else "SELL"
    return [T(f"{ref}-N", trade_date, near_side, n, near_mat, typ="SWLEG", pkg=f"PKG{ref}",
              label="USD/SGD Swap 6M (near)", status=near_status),
            T(f"{ref}-F", trade_date, far_side, n, far_mat, typ="SWLEG", pkg=f"PKG{ref}",
              label="USD/SGD Swap 6M (far)", status=far_status)]


def SPOT(ref, trade_date, side, n):
    return T(ref, trade_date, side, n, trade_date, label="USD/SGD Spot", status="DEAD")


def ctx(trades, pair="USDSGD", interactions=None):
    return trade_context(trades, pair, TODAY, interactions)


def note(c):
    """The visible note as the client box shows it: 'Label: text' per line."""
    return [f"{x['label']}: {x['text']}" if x["label"] else x["text"] for x in c["lines"]]


def idea(c, kind):
    return next((i for i in c["ideas"] if i["kind"] == kind), None)


def pinnacle():
    p = next(c for c in BOOK.clients if c["counterpart_name"].startswith("Pinnacle"))
    return p, [t for t in BOOK.trades if t["sibs_cif"] == p["sibs_cif"]]


# ------------------------------------------------------------------ pairs
def test_pair_normalisation_ignores_case_separator_and_direction():
    keys = {pair_key(p) for p in ("sgd/usd", "SGD/USD", "usdsgd", "USD/SGD", "usd-sgd")}
    assert keys == {("SGD", "USD")}
    assert pair_key("USD/USD") is None and pair_key("ABCXYZ") is None and pair_key("gold") is None


def test_trades_booked_in_either_order_match_and_net_in_one_currency():
    trades = [T("1", "2026-10-01", "BUY", 3_000_000, "2027-01-04"),
              # booked SGD/USD: SELL SGD = BUY USD of notional 2
              T("2", "2026-10-02", "SELL", 3_250_000, "2027-02-04", ccy1="SGD", ccy2="USD", rate=1 / 1.3)]
    for asked in ("sgd/usd", "USD/SGD"):
        c = ctx(trades, asked)
        assert c["pair"] == "USD/SGD" and c["kind"] == "open"
        assert "Net: BUY USD 5.5m" in note(c)


# ------------------------------------------------------------------ swap far-leg netting
def test_live_far_leg_with_settled_near_leg_is_netted_like_a_forward():
    c = ctx([T("1", "2026-10-01", "BUY", 2_000_000, "2027-01-04"),
             *SWAP("9", "2026-10-05", "SELL", 10_000_000, "2026-10-07", "2027-04-07")])
    assert "Net: BUY USD 12.0m" in note(c)                      # 2m forward + 10m far leg
    assert "Open USD/SGD position (internal data): 2 open trades (2 BUY, 0 SELL)" in note(c)
    assert c["trade_count"] == 2                                 # two legs = one swap
    far = next(r for r in c["trades"] if r["product"] == "Swap far leg (roll)")
    assert far["side"] == "BUY" and far["status"] == "Live"


def test_swap_with_both_legs_live_nets_to_zero():
    c = ctx([T("1", "2026-10-01", "BUY", 2_000_000, "2027-01-04"),
             *SWAP("9", "2026-11-10", "SELL", 10_000_000, "2026-11-20", "2027-05-20", near_status="LIVE")])
    assert "Net: BUY USD 2.0m" in note(c)
    assert "Not netted: 1 FX swap with both legs live (nets to zero)" in note(c)
    swap = next(r for r in c["trades"] if r["product"].startswith("FX swap"))
    assert swap["product"] == "FX swap (near SELL / far BUY)" and swap["note"] == "both legs live (nets to zero)"


def test_pinnacle_net_includes_far_legs_and_matches_the_data():
    _, mine = pinnacle()
    usdsgd = [t for t in mine if {t["ccy1"], t["ccy2"]} == {"USD", "SGD"}]
    near_dead = {t["package_ref"] for t in usdsgd if t["package_ref"] and t["status"] != "LIVE"}
    expected = sum((1 if t["buy_sell"] == "BUY" else -1) * t["notional1"] for t in usdsgd
                   if t["status"] == "LIVE" and (t["trn_type"] == "FXD" and "Spot" not in t["instrument_label"]
                                                 or t["trn_type"] == "SWLEG" and t["package_ref"] in near_dead))
    c = ctx(mine)
    assert round(expected / 1e6, 1) == -38.8
    assert c["net"]["side"] == "SELL" and c["net"]["amount"] == pytest.approx(-expected, abs=1)
    assert note(c) == [
        "Open USD/SGD position (internal data): 11 open trades (5 BUY, 6 SELL)",
        "Net: SELL USD 38.8m",
        "Next BUY maturing: in 6 days (19 Nov), USD 7.7m forward (offset)",
        "Next SELL maturing: in 10 days (23 Nov), USD 8.2m forward (offset)",
    ]


def test_note_never_carries_client_identity():
    p, mine = pinnacle()
    c = ctx(mine)
    text = " ".join(note(c) + [i["text"] for i in c["ideas"]]).upper()
    assert p["counterpart_name"].upper() not in text and p["sibs_cif"] not in text and "PINNACLE" not in text


# ------------------------------------------------------------------ visible lines
def test_next_maturing_lines_only_for_sides_that_exist_and_offset_marker_only_when_paired():
    c = ctx([T("1", "2026-08-19", "BUY", 5_300_000, "2026-11-19")])
    assert note(c) == ["Open USD/SGD position (internal data): 1 open trade (1 BUY, 0 SELL)",
                       "Net: BUY USD 5.3m",
                       "Next BUY maturing: in 6 days (19 Nov), USD 5.3m forward"]
    paired = ctx([T("1", "2026-07-03", "BUY", 47_000_000, "2027-04-05"),
                  T("2", "2026-10-16", "SELL", 47_100_000, "2027-04-16")])
    assert "Next BUY maturing: on 5 Apr 2027, USD 47.0m forward (offset)" in note(paired)
    assert not any(line.startswith("Offset") for line in note(paired))     # offsets live in the dropdown


def test_offsets_listed_in_dropdown_and_note_column():
    c = ctx([T("1", "2026-07-03", "BUY", 47_000_000, "2027-04-05"),
             T("2", "2026-10-16", "SELL", 47_100_000, "2027-04-16")])
    assert c["offsets"] == ["SELL USD 47.1m (16 Oct) offsets BUY USD 47.0m (3 Jul)"]
    notes = {r["trade_date"]: r["note"] for r in c["trades"]}
    assert notes == {"16 Oct 2026": "offsets BUY USD 47.0m (3 Jul)", "3 Jul 2026": "offset by SELL USD 47.1m (16 Oct)"}


@pytest.mark.parametrize("n2, mat2", [(53_000_000, "2027-04-16"),     # notional more than 10% apart
                                      (47_100_000, "2027-06-16")])    # maturity more than 30 days apart
def test_no_offset_outside_tolerances(n2, mat2):
    c = ctx([T("1", "2026-07-03", "BUY", 47_000_000, "2027-04-05"), T("2", "2026-10-16", "SELL", n2, mat2)])
    assert c["offsets"] == [] and "(offset)" not in " ".join(note(c))


def test_options_listed_separately_not_netted():
    trades = [T("1", "2026-10-01", "SELL", 4_000_000, "2027-01-04"),
              T("2", "2026-10-02", "BUY", 2_000_000, "2027-02-03", grp="OPT", typ="SMP",
                label="USD/SGD Call 4M K=1.35", strike=1.35, opt="USD/SGD Vanilla Call European")]
    c = ctx(trades)
    assert "Net: SELL USD 4.0m" in note(c) and "Not netted: 1 option" in note(c)
    assert any(r["product"] == "Option: USD/SGD call, strike 1.35" for r in c["trades"])


def test_ndf_fixture_is_netted_and_flagged():
    c = ctx([T("1", "2026-10-20", "BUY", 3_000_000, "2026-11-20", ccy1="USD", ccy2="INR", rate=88.0,
               label="USD/INR NDF 1M")], "inr/usd")
    assert c["pair"] == "USD/INR"
    assert note(c) == ["Open USD/INR position (internal data): 1 open trade (1 BUY, 0 SELL)",
                       "Net: BUY USD 3.0m",
                       "Next BUY maturing: in 7 days (20 Nov), USD 3.0m NDF",
                       "NDF: next fixing 20 Nov; cash-settled (no delivery), so a new ask may be about "
                       "unwinding/closing or the fixing"]
    assert c["trades"][0]["product"] == "NDF (cash-settled)"


def test_no_open_trades_shows_last_transaction():
    trades = [T("1", "2026-05-04", "BUY", 1_000_000, "2026-08-04", status="DEAD"),
              T("2", "2026-10-15", "SELL", 2_000_000, "2026-10-19", label="USD/SGD Spot", status="DEAD"),
              T("3", "2026-06-01", "BUY", 1_500_000, "2026-12-01", status="MKT_OP")]
    c = ctx(trades)
    assert c["kind"] == "closed" and c["net"] is None
    assert note(c) == ["No open USD/SGD trades. Last: SELL USD 2.0m spot, 15 Oct (settled)."]
    assert {r["status"] for r in c["trades"]} == {"Settled", "Matured", "Terminated early"}


def test_never_traded_the_pair():
    c = ctx([T("1", "2026-05-04", "BUY", 1_000_000, "2026-08-04", ccy1="EUR", ccy2="USD")])
    assert c["kind"] == "never" and note(c) == ["No past USD/SGD trades on record."]
    assert c["trades"] == [] and c["count_label"] == "0 trades (0 open)"


# ------------------------------------------------------------------ rolls and the trade list
def test_roll_detected_and_shown():
    c = ctx([T("F", "2026-06-01", "BUY", 10_000_000, "2026-09-01", status="DEAD"),
             *SWAP("9", "2026-09-02", "SELL", 10_200_000, "2026-09-04", "2027-03-04")])
    assert c["rolls"] == ["Swap far leg BUY USD 10.2m (matures 4 Mar 2027) looks like a roll of BUY USD 10.0m "
                          "forward that matured 1 Sep."]
    far = next(r for r in c["trades"] if r["product"] == "Swap far leg (roll)")
    assert far["note"] == "rolled from BUY USD 10.0m forward (1 Sep)"


@pytest.mark.parametrize("swap_date, size", [("2026-09-10", 10_200_000),   # 9 days after the maturity
                                             ("2026-09-02", 12_000_000)])  # size 20% different
def test_no_roll_without_matching_maturity(swap_date, size):
    c = ctx([T("F", "2026-06-01", "BUY", 10_000_000, "2026-09-01", status="DEAD"),
             *SWAP("9", swap_date, "SELL", size, "2026-09-12", "2027-03-04")])
    assert c["rolls"][0].endswith("no matching earlier maturity found.")


def test_trade_list_is_complete_open_first_then_recent_closed():
    _, mine = pinnacle()
    c = ctx(mine)
    rows = c["trades"]
    assert len(rows) == c["trade_count"] == 20 and c["open_count"] == 11
    assert c["count_label"] == "20 trades (11 open)"
    assert list(rows[0]) == ["trade_date", "side", "notional", "product", "maturity", "status", "note", "open"]
    assert all(r["open"] for r in rows[:11]) and not any(r["open"] for r in rows[11:])
    assert rows[0]["maturity"] == "19 Nov 2026"                # soonest maturity first
    assert {r["note"] for r in rows} >= {"offsets BUY USD 7.7m (19 May)", "offsets BUY USD 47.0m (3 Jul)",
                                         "investment"}
    assert sum(r["product"] == "Swap far leg (roll)" for r in rows) == 2


def test_closed_trades_older_than_six_months_are_left_out():
    trades = [T("old", "2026-01-05", "BUY", 1_000_000, "2026-04-06", status="DEAD"),
              T("recent", "2026-06-01", "SELL", 1_000_000, "2026-09-01", status="DEAD"),
              T("live", "2026-10-01", "SELL", 1_000_000, "2027-01-04")]
    c = ctx(trades)
    assert [r["trade_date"] for r in c["trades"]] == ["1 Oct 2026", "1 Jun 2026"]
    assert c["count_label"] == "2 trades (1 open)"


def test_several_pairs_deduplicated():
    out = trade_contexts([], ["USDSGD", "SGDUSD", "EURUSD", "gold"], TODAY)
    assert [c["pair"] for c in out] == ["USD/SGD", "EUR/USD"]


# ------------------------------------------------------------------ idea detectors
MATURING = [T("open", "2026-08-19", "BUY", 7_700_000, "2026-11-19"),
            T("f1", "2026-06-01", "BUY", 5_000_000, "2026-09-01", status="DEAD"),     # rolled below
            *SWAP("r1", "2026-09-02", "SELL", 5_100_000, "2026-09-04", "2027-03-04"),
            T("f2", "2026-07-01", "SELL", 3_000_000, "2026-10-01", status="DEAD")]    # settled


def test_maturity_idea_fires_with_roll_history():
    i = idea(ctx(MATURING), "maturity")
    assert i["text"] == ("BUY USD 7.7m forward matures in 6 days (19 Nov); of 2 earlier USD/SGD maturities, 1 looked "
                         "rolled (swap within 3 days, size within 10%) and 1 settled.")
    assert i["evidence"] | {} == {"trade": "open", "maturity": "2026-11-19", "days": 6, "also_within_window": 0,
                                  "earlier_maturities": 2, "rolled": 1, "settled": 1}


def test_maturity_idea_silent_beyond_14_days():
    assert idea(ctx([T("open", "2026-08-19", "BUY", 7_700_000, "2026-11-30")]), "maturity") is None


MONTHLY = [SPOT(str(k), d, "SELL", 1_000_000) for k, d in
           enumerate(["2026-06-01", "2026-07-01", "2026-07-31", "2026-08-31", "2026-09-30"])]


def test_rhythm_idea_monthly_and_quarterly():
    i = idea(ctx(MONTHLY), "rhythm")
    assert i["text"] == "Trades USD/SGD roughly monthly (5 trades, median gap 30 days); last 30 Sep (44 days ago)."
    assert i["evidence"]["median_gap_days"] == 30 and i["evidence"]["gap_spread"] <= 0.35
    quarterly = [SPOT(str(k), d, "SELL", 1_000_000) for k, d in
                 enumerate(["2025-11-03", "2026-02-02", "2026-05-04", "2026-08-03"])]
    assert "roughly quarterly" in idea(ctx(quarterly), "rhythm")["text"]


@pytest.mark.parametrize("dates", [
    ["2026-06-01", "2026-07-01", "2026-07-31"],                              # only 3 trades
    ["2026-06-01", "2026-06-11", "2026-08-10", "2026-09-04", "2026-10-04"],  # gaps 10/60/25/30: too uneven
    ["2026-06-01", "2026-06-15", "2026-06-29", "2026-07-13"],                # fortnightly: no band
])
def test_rhythm_idea_silent_without_a_regular_pattern(dates):
    assert idea(ctx([SPOT(str(k), d, "SELL", 1_000_000) for k, d in enumerate(dates)]), "rhythm") is None


def ASK(when, inst):
    return {"asked_at": f"{when}T10:00:00", "instruments": inst}


def test_next_ask_idea_fires():
    asks = [ASK("2026-09-01", "USDSGD"), ASK("2026-09-03", "JPYSGD"), ASK("2026-09-15", "USDSGD"),
            ASK("2026-09-18", "JPYSGD"), ASK("2026-10-01", "USDSGD"), ASK("2026-10-04", "JPYSGD;EURUSD"),
            ASK("2026-10-20", "USDSGD")]
    i = idea(ctx([], interactions=asks), "next_ask")
    assert i["text"] == "After USD/SGD asks, asked JPY/SGD within a week 3 of 4 times."
    assert i["evidence"]["times_followed"] == 3 and i["evidence"]["asks"] == 4


@pytest.mark.parametrize("asks", [
    # only twice
    [ASK("2026-09-01", "USDSGD"), ASK("2026-09-03", "JPYSGD"), ASK("2026-09-15", "USDSGD"),
     ASK("2026-09-18", "JPYSGD"), ASK("2026-10-01", "USDSGD")],
    # 3 of 6 = 50%
    [ASK(d, "USDSGD") for d in ("2026-07-01", "2026-07-20", "2026-08-10", "2026-09-01", "2026-09-15", "2026-10-01")]
    + [ASK(d, "JPYSGD") for d in ("2026-09-03", "2026-09-18", "2026-10-04")],
    # B more than 7 days later
    [ASK(d, "USDSGD") for d in ("2026-08-01", "2026-09-01", "2026-10-01")]
    + [ASK(d, "JPYSGD") for d in ("2026-08-12", "2026-09-12", "2026-10-12")],
])
def test_next_ask_idea_silent_without_enough_evidence(asks):
    assert idea(ctx([], interactions=asks), "next_ask") is None


def test_unusual_idea_size_and_direction():
    trades = [SPOT("1", "2026-06-01", "SELL", 1_000_000), SPOT("2", "2026-06-20", "SELL", 1_000_000),
              SPOT("3", "2026-08-15", "SELL", 1_200_000), SPOT("4", "2026-10-30", "BUY", 2_500_000)]
    i = idea(ctx(trades), "unusual")
    assert i["text"] == ("Newest USD/SGD trade (BUY USD 2.5m spot, 30 Oct) is 2.5x the median size of earlier USD/SGD "
                         "trades (USD 1.0m) and a BUY after 3 SELL trades in a row.")
    assert i["evidence"]["size_ratio"] == 2.5 and i["evidence"]["opposite_run"] == 3


def test_unusual_idea_silent_for_ordinary_trade():
    trades = [SPOT("1", "2026-06-01", "SELL", 1_000_000), SPOT("2", "2026-06-20", "BUY", 1_000_000),
              SPOT("3", "2026-08-15", "SELL", 1_200_000), SPOT("4", "2026-10-30", "SELL", 1_500_000)]
    assert idea(ctx(trades), "unusual") is None


def test_ideas_ranked_and_capped_at_three():
    trades = MATURING + MONTHLY[:4] + [SPOT("big", "2026-10-30", "BUY", 9_000_000)]
    asks = [ASK("2026-09-01", "USDSGD"), ASK("2026-09-03", "JPYSGD"), ASK("2026-09-15", "USDSGD"),
            ASK("2026-09-18", "JPYSGD"), ASK("2026-10-01", "USDSGD"), ASK("2026-10-04", "JPYSGD")]
    c = ctx(trades, interactions=asks)
    assert [i["kind"] for i in c["ideas"]] == ["next_ask", "maturity", "unusual"]


def test_no_ideas_in_the_dummy_book_without_evidence():
    # Pinnacle has a maturity within 14 days, but no regular rhythm and no repeated follow-up asks.
    _, mine = pinnacle()
    asks = [i for i in BOOK.interactions if i["client_id"] == "C008"]
    assert [i["kind"] for i in ctx(mine, interactions=asks)["ideas"]] == ["maturity"]


# ------------------------------------------------------------------ research link
def ROW(value, horizon, key="USDSGD", pub="2026-11-03", **kw):
    return {"instrument": "USD/SGD" if key == "USDSGD" else key, "instrument_key": key, "horizon": horizon,
            "horizon_kind": "absolute", "value": value, "scenario": "Baseline", "publication_date": pub,
            "horizon_passed": False} | kw


TABLE = [ROW("1.2800", "Dec-26"), ROW("1.27", "Mar-27"), ROW("1.25", "Dec-27"),
         ROW("1.31", "Dec-26", pub="2026-10-01"),                       # older publication
         ROW("1.30", "Sep-26", horizon_passed=True),                    # horizon passed
         ROW("1.20", "Dec-27", scenario="Bear"),                        # not the baseline
         ROW("1.17", "Dec-26", key="EURUSD")]                           # another pair


def test_research_link_combines_validated_forecast_with_net_position():
    _, mine = pinnacle()
    link = trade_note.research_link({"table": TABLE}, ctx(mine))
    assert link == {"label": "OCBC research + internal data",
                    "text": "OCBC forecast path USD/SGD: 1.2800 (Dec-26) -> 1.25 (Dec-27); client is net SELL USD 38.8m."}
    assert not trade_note.ADVICE_RE.search(link["text"])


def test_research_link_conditions():
    _, mine = pinnacle()
    open_ctx = ctx(mine)
    assert trade_note.research_link({"table": []}, open_ctx) is None                         # no forecast table
    assert trade_note.research_link({"table": [ROW("1.17", "Dec-26", key="EURUSD")]}, open_ctx) is None  # other pair
    closed = ctx([T("1", "2026-05-04", "BUY", 1_000_000, "2026-08-04", status="DEAD")])
    assert trade_note.research_link({"table": TABLE}, closed) is None                        # no open net position
    flat = ctx([T("1", "2026-07-03", "BUY", 5_000_000, "2027-04-05"), T("2", "2026-08-03", "SELL", 5_000_000, "2027-04-05")])
    assert trade_note.research_link({"table": TABLE}, flat) is None                          # nets to flat
    single = trade_note.research_link({"table": [ROW("1.28", "Dec-26")]}, open_ctx)
    assert single["text"] == "OCBC forecast USD/SGD: 1.28 (Dec-26); client is net SELL USD 38.8m."


# ------------------------------------------------------------------ Haiku, line by line (faked)
def simple():
    return ctx([T("1", "2026-08-19", "BUY", 5_300_000, "2026-11-19")])


def test_haiku_lines_are_checked_one_by_one():
    c = simple() | {"research_link": {"label": "OCBC research + internal data", "text": "LINK"}}
    sent = []

    def fake(texts):
        sent.extend(texts)
        return ("1. Open USD/SGD position (internal data): 1 open trade, 1 BUY and 0 SELL\n"
                "2. Net: a BUY of USD 5.4m\n"                                               # invented number
                "3. Next BUY maturing: a USD 5.3m forward, in 6 days (19 Nov)\n"
                "4. BUY USD 5.3m forward matures in 6 days (19 Nov); the client should roll it, "
                "no earlier USD/SGD maturities on record.")                                 # advice
    out = trade_note.polish(c, writer=fake)
    assert len(sent) == 4 and not any("LINK" in s for s in sent)          # research link never sent
    assert out["lines"][0]["text"] == "1 open trade, 1 BUY and 0 SELL" and out["lines"][0]["model"]
    assert out["lines"][0]["rule_text"] == "1 open trade (1 BUY, 0 SELL)"
    assert out["lines"][1] == c["lines"][1]                               # rejected line keeps code text
    assert out["lines"][2]["text"] == "a USD 5.3m forward, in 6 days (19 Nov)"
    assert out["ideas"][0] == c["ideas"][0]
    assert out["research_link"] == c["research_link"] and out["text_source"] == "mixed"


@pytest.mark.parametrize("new", [
    "a BUY of USD 5.3m and 2 more",               # adds a number
    "a BUY",                                      # drops a number
    "a BUY of USD 5.3m; we recommend a hedge",    # advice
    "a BUY of USD 5.3m. It is open.",             # two sentences
    "**a BUY of USD 5.3m**",                      # markdown
])
def test_haiku_line_rejections(new):
    assert not trade_note.acceptable(new, "BUY USD 5.3m")


def test_haiku_all_lines_accepted_and_label_must_stay():
    c = simple()
    good = ("1. Open USD/SGD position (internal data): 1 open trade, 1 BUY and 0 SELL\n"
            "2. Net: a BUY of USD 5.3m\n"
            "3. Next BUY maturing: USD 5.3m forward, in 6 days (19 Nov)\n"
            "4. A BUY USD 5.3m forward matures in 6 days (19 Nov), with no earlier USD/SGD maturities on record.")
    assert trade_note.polish(c, writer=lambda t: good)["text_source"] == "model"
    relabelled = good.replace("2. Net:", "2. Net position:")
    assert trade_note.polish(c, writer=lambda t: relabelled)["lines"][1] == c["lines"][1]


def test_no_api_key_or_switch_off_means_no_model_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert trade_note.rewrite(["Net: BUY USD 5.3m"]) is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(trade_note.config, "CLIENT_NOTE_MODEL", False)
    assert trade_note.rewrite(["Net: BUY USD 5.3m"]) is None
    assert trade_note.polish(simple())["text_source"] == "rules"


# ------------------------------------------------------------------ picker
JIMMYS = [
    {"client_id": "C001", "client_name": "Harbourline Logistics Pte Ltd", "contact_id": "P001", "contact_name": "Jimmy Tan"},
    {"client_id": "C002", "client_name": "Meridian Foods Holdings Ltd", "contact_id": "P003", "contact_name": "Jimmy Lee"},
    {"client_id": "C010", "client_name": "Silverleaf Family Office", "contact_id": "P019", "contact_name": "Jimmy Seah"},
]


def pick(text, cands=JIMMYS):
    return resolve_pick(text, cands, BOOK.clients, BOOK.contacts)


@pytest.mark.parametrize("text, contact", [("b", "P003"), ("B)", "P003"), ("option c", "P019"), ("a.", "P001"),
                                           ("Meridian Foods", "P003"), ("Meridian", "P003"),
                                           ("it's Harbourline", "P001"), ("Jimmy Lee", "P003")])
def test_reply_picks_a_listed_match(text, contact):
    assert pick(text)["contact_id"] == contact


@pytest.mark.parametrize("text", ["d", "What about EUR/USD for Meridian Foods next year?", "thanks", ""])
def test_reply_that_is_not_a_pick(text):
    assert pick(text) is None


def test_typed_company_outside_the_list_is_picked_without_a_contact():
    p = pick("Kestrel Semiconductor")
    assert p["client_name"] == "Kestrel Semiconductor Pte Ltd" and p["contact_id"] is None
