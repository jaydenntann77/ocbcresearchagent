"""Agent mode with a scripted model: the tool loop, and the checks the code enforces on its answer
(research quoted verbatim, figures matched to tool data, labels, budgets). No API key or network."""
import json
from types import SimpleNamespace as NS

import pytest

from app.orchestrator import agent as ag
from app.orchestrator.router import choose

OVERVIEW = {
    "as_of": "16 Nov 2026",
    "client": {"client_id": "C001", "name": "Harbourline Logistics Pte Ltd", "segment": "LC",
               "industry": "Shipping & Logistics", "country": "SG", "profile": "USD earner",
               "hedging_notes": "Sells USD forward 3-6M.", "preferred_pairs": ["USD/SGD"],
               "relationship_manager": "Tan Wei Ling", "team": "Large Corporates"},
    "contacts": [{"contact_id": "P001", "name": "Jimmy Tan", "title": "Group Treasurer", "primary": True}],
    "activity": {"total_deals": 40, "open_deals": 18, "deals_last_90_days": 15, "first_trade": "12 May 2026",
                 "last_trade": {"date": "5 Nov 2026", "pair": "USD/SGD", "deal": "SELL USD 18.9m forward",
                                "status": "Live"},
                 "products": {"Forward": 23, "Spot": 14}, "purpose": {"hedge": 40}},
    "pairs": [{"pair": "USD/SGD", "deals": 17, "open_deals": 5, "net_open_position": "SELL USD 45.7m (net)",
               "next_maturity": "SELL USD 4.7m forward in 17 days (3 Dec)", "last_traded": "5 Nov"}],
    "maturing_next_30_days": [{"ref": "41206189", "pair": "USD/SGD", "deal": "SELL USD 4.7m forward",
                               "maturity": "3 Dec 2026", "purpose": "hedge"}],
    "recent_asks": [{"asked_at": "2026-11-13 14:44", "question": "SGD rates outlook", "topic": None}],
    "pattern_notes": [{"pair": "USD/SGD", "kind": "maturity", "text": "SELL USD 4.7m forward matures in 17 days."}],
}

RESEARCH = {
    "status": "complete", "freshness": {"research_published": "2 Nov 2026"},
    "direct": [{"text": "We expect USD/SGD to ease to 1.2700 by 4Q27.", "citations": [1], "part": "view"}],
    "table": [{"instrument": "USD/SGD", "horizon": "4Q26", "value": "1.2900", "citations": [2], "horizon_kind": "absolute",
               "unit": None, "publication_label": "2 Nov 2026"},
              {"instrument": "USD/SGD", "horizon": "4Q27", "value": "1.2700", "citations": [2], "horizon_kind": "absolute",
               "unit": None, "publication_label": "2 Nov 2026"}],
    "table_notes": [{"text": "Not meant to serve as point forecasts.", "citations": [2], "mode": "verbatim"},
                    {"text": "Our forecasts imply a gradual path.", "citations": [1], "mode": "summary"}],
    "rationale": [{"text": "A softer USD backdrop supports the SGD.", "citations": [1]}],
    "risks": [],
    "limitations": [{"type": "horizon_not_covered", "text": "No verified forecast for the 2028 horizon."},
                    {"type": "note", "text": "3M/6M/12M horizons are relative."}],
    "conflicts": [{"text": "Two reports differ on 4Q26.", "resolution": "unresolved"},
                  {"text": "A newer report revises 1Q27.", "resolution": "latest_publication_applies"}],
    "sources": [{"n": 1, "doc_id": "d1", "pdf_page": 3, "excerpt": "We expect ...", "title": "FX Weekly"},
                {"n": 2, "doc_id": "d2", "pdf_page": 1, "excerpt": "Forecast table", "title": "FX Monthly"}],
}


class FakeClientData:
    def __init__(self):
        self.calls = []

    def view(self, name, client_id=None, **params):
        self.calls.append((name, client_id, params))
        if name == "overview":
            if client_id != "C001":
                raise ag.ServiceError("404: client not found")
            return OVERVIEW
        if name == "maturities":
            return {"as_of": "16 Nov 2026", "window": "16 Nov 2026 to 30 Nov 2026", "maturing_deals": 1,
                    "clients": {"Harbourline Logistics Pte Ltd": 1},
                    "deals": [{"maturity": "19 Nov 2026", "client": "Harbourline Logistics Pte Ltd", "pair": "USD/SGD",
                               "deal": "SELL USD 4.7m forward", "has_rolled_this_pair_before": True}]}
        return {"count": 0, "items": []}

    def identify(self, text):
        return {"status": "match", "candidates": [{"client_id": "C001", "client_name": "Harbourline Logistics Pte Ltd",
                                                   "contact_id": None, "contact_name": None}]}


def tool_use(*calls):
    blocks = [NS(type="tool_use", id=f"tu{i}", name=n, input=a) for i, (n, a) in enumerate(calls)]
    return NS(stop_reason="tool_use", content=[NS(type="thinking", thinking="")] + blocks,
              usage=NS(input_tokens=100, output_tokens=20, cache_read_input_tokens=0))


def final(data, stop="end_turn"):
    text = data if isinstance(data, str) else json.dumps(data)
    return NS(stop_reason=stop, content=[NS(type="text", text=text)],
              usage=NS(input_tokens=200, output_tokens=80, cache_read_input_tokens=50))


class FakeModel:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        return self.script.pop(0)


def run_agent(script, question="Brief me on Harbourline before my meeting", research=RESEARCH):
    model = FakeModel(script)
    cd = FakeClientData()
    asked = []

    def research_fn(q):
        asked.append(q)
        return research

    steps = []
    a = ag.Agent(cd, research_fn, steps.append, model_client=model, names={"C001": "Harbourline Logistics Pte Ltd"})
    answer = a.run(question, ag.context_block(None, "16 Nov 2026, 10:00 SGT"), [])
    return answer, model, cd, asked, steps


ANSWER = {
    "headline": "Harbourline is a USD earner with 18 open deals; one forward matures on 3 Dec.",
    "sections": [
        {"title": "Where they stand", "kind": "client_data", "table": None, "points": [
            {"text": "40 deals on record, 18 open; last trade SELL USD 18.9m forward on 5 Nov 2026.", "refs": ["D1"]},
            {"text": "Net open USD/SGD position is SELL USD 99.9m.", "refs": ["D1"]}]},
        {"title": "OCBC's view", "kind": "ocbc_research", "table": None, "points": [
            {"text": "OCBC thinks USD/SGD goes to 1.10", "refs": ["R1"]},
            {"text": "", "refs": ["R2"]},
            {"text": "", "refs": ["R99"]}]},
        {"title": "Ideas", "kind": "ai_suggestion", "points": [
            {"text": "Raise rolling the SELL USD 4.7m forward (3 Dec) with an FX swap; OCBC expects a softer USD.",
             "refs": ["D1", "R1"]},
            {"text": "OCBC expects the SGD to firm, so sell more USD forward.", "refs": ["D1"]}],
         "table": {"columns": ["Deal", "Maturity"], "rows": [["SELL USD 4.7m forward", "3 Dec 2026"],
                                                             ["SELL USD 7.3m forward", "9 Dec 2026"]]}},
        {"title": "Collars in brief", "kind": "general", "table": None, "points": [
            {"text": "A zero-cost collar buys one option and sells another, e.g. strikes 123.45 apart.", "refs": []}]},
    ],
    "follow_ups": ["What is maturing for Harbourline in the next 2 weeks?"],
}


def test_tool_loop_and_enforced_checks():
    script = [tool_use(("client_overview", {"client_id": "C001"}), ("ocbc_research", {"question": "OCBC USD/SGD view"})),
              final(ANSWER)]
    answer, model, cd, asked, steps = run_agent(script)

    # The loop: two model calls, tools run, results returned with matching ids.
    assert len(model.calls) == 2
    first, second = model.calls
    assert "tool_choice" not in first
    assert first["output_config"]["format"]["type"] == "json_schema"
    assert first["extra_body"] == {"fallbacks": "default"}
    assert {t["name"] for t in first["tools"]} >= {"client_overview", "ocbc_research", "upcoming_maturities"}
    results = second["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["tu0", "tu1"]
    assert json.loads(results[0]["content"])["result_id"] == "D1"
    assert "R1" in results[1]["content"] and "1.2700" in results[1]["content"]
    assert asked == ["OCBC USD/SGD view"]
    assert cd.calls[0][:2] == ("overview", "C001")
    assert [t["id"] for t in answer["trace"]] == ["D1", "Q1"]
    assert any("Harbourline" in s for s in steps)   # progress names the client once it is known

    secs = {s["kind"]: s for s in answer["sections"]}
    # client_data: real figures pass, an invented one is flagged.
    pts = secs["client_data"]["points"]
    assert "unverified" not in pts[0]
    assert pts[1]["unverified"] == ["99.9"]
    # ocbc_research: the model's own words are discarded; the research sentence is shown verbatim,
    # citations renumbered to this answer's sources; forecast items become the table; bad ids dropped.
    rpts = secs["ocbc_research"]["points"]
    assert [p["text"] for p in rpts] == ["We expect USD/SGD to ease to 1.2700 by 4Q27."]
    assert rpts[0]["quote"] and rpts[0]["citations"] == [1]
    assert [r["value"] for r in secs["ocbc_research"]["research_tables"]] == ["1.2900", "1.2700"]
    assert secs["ocbc_research"]["research_tables"][0]["citations"] == [2]
    # The forecast's published qualification travels with its table; gaps and conflicts are attached by
    # code whatever the model chose to show (minor notes are not).
    assert secs["ocbc_research"]["research_notes"] == [
        {"text": "Not meant to serve as point forecasts.", "citations": [2], "mode": "verbatim"}]
    assert answer["research_caveats"] == ["No verified forecast for the 2028 horizon.", "Two reports differ on 4Q26."]
    assert answer["verification"]["research_dropped"] == 1
    # ai_suggestion: figures from the client book pass; a view attributed to OCBC is flagged unless the
    # idea cites the research item it comes from; the table cell with an invented deal is flagged.
    sug = secs["ai_suggestion"]
    assert "unverified" not in sug["points"][0] and "view_flag" not in sug["points"][0]
    assert sug["points"][0]["citations"] == [1]
    assert sug["points"][1]["view_flag"] is True and "citations" not in sug["points"][1]
    assert sug["table"]["unverified"] == ["7.3"]
    # general: not checked against client data.
    assert "unverified" not in secs["general"]["points"][0]
    v = answer["verification"]
    assert v["unverified"] == 2 and v["research_quoted"] == 2 and v["view_flags"] == 1
    assert answer["cited_sources"] == [1, 2] and len(answer["sources"]) == 2
    assert answer["follow_ups"] == ANSWER["follow_ups"]
    assert answer["agent"]["turns"] == 2 and answer["agent"]["input_tokens"] == 300
    assert answer["kind"] == "agent" and answer["status"] == "complete"


def test_last_turn_cannot_call_tools():
    script = [tool_use(("past_asks", {"client_id": "C001"}))] * (ag.MAX_TURNS - 1) + [final(ANSWER)]
    answer, model, *_ = run_agent(script)
    assert len(model.calls) == ag.MAX_TURNS
    assert model.calls[-1]["tool_choice"] == {"type": "none"}
    assert all("tool_choice" not in c for c in model.calls[:-1])
    assert answer["sections"]


def test_research_budget_and_tool_errors():
    script = [tool_use(("ocbc_research", {"question": "a"}), ("ocbc_research", {"question": "b"}),
                       ("ocbc_research", {"question": "c"}), ("client_overview", {"client_id": "C999"})),
              final(ANSWER)]
    answer, model, cd, asked, _ = run_agent(script)
    results = model.calls[1]["messages"][-1]["content"]
    assert len(asked) == ag.MAX_RESEARCH_CALLS
    assert sum(1 for r in results if r.get("is_error")) == 2   # third research call + unknown client
    assert any("research budget" in r["content"] for r in results if r.get("is_error"))
    assert [t["ok"] for t in answer["trace"]].count(False) == 2


def test_refusal_and_cut_off_raise():
    with pytest.raises(ag.AgentUnavailable):
        run_agent([final("", stop="refusal")])
    with pytest.raises(ag.AgentUnavailable):
        run_agent([final("{", stop="max_tokens")])


def test_non_json_reply_is_labelled_as_ai():
    answer, *_ = run_agent([final("Just some prose.")])
    assert answer["sections"][0]["kind"] == "ai_suggestion"
    assert answer["sections"][0]["points"][0]["text"] == "Just some prose."


def test_unknown_kind_becomes_ai_suggestion():
    data = {"headline": "h", "follow_ups": [], "sections": [
        {"title": "x", "kind": "house_view", "table": None, "points": [{"text": "hello", "refs": []}]}]}
    answer, *_ = run_agent([final(data)])
    assert answer["sections"][0]["kind"] == "ai_suggestion"


def test_snapshot_without_a_model():
    client = {"status": "match", "candidates": [{"client_id": "C001", "client_name": "Harbourline"}]}
    snap = ag.snapshot(FakeClientData(), client, "brief me")
    assert snap["agent"]["deterministic"] is True and snap["kind"] == "agent"
    assert {s["kind"] for s in snap["sections"]} == {"client_data"}
    assert snap["verification"]["unverified"] == 0
    titles = [s["title"] for s in snap["sections"]]
    assert "Maturing in the next 30 days" in titles and "Positions by pair" in titles
    book = ag.snapshot(FakeClientData(), None, "Which clients have deals maturing in the next 2 weeks?")
    assert book["sections"][0]["table"]["rows"][0][-1] == "yes"
    assert ag.snapshot(FakeClientData(), None, "what is a collar?") is None


def test_quoted_client_question_is_not_an_ocbc_view():
    data = {"headline": "h", "follow_ups": [], "sections": [{"title": "Asks", "kind": "ai_suggestion", "table": None,
            "points": [{"text": 'On 9 Oct he asked "Where does OCBC see USD/CNH by end-2026?"', "refs": []},
                       {"text": "OCBC expects the SGD to firm.", "refs": []},
                       {"text": "16 Sep: asked for OCBC's 12-month USD/SGD forecast.", "refs": []},
                       {"text": "Jimmy asked about rates. OCBC sees the Fed cutting.", "refs": []}]}]}
    answer, *_ = run_agent([final(data)])
    pts = answer["sections"][0]["points"]
    assert "view_flag" not in pts[0] and pts[1]["view_flag"] is True
    assert "view_flag" not in pts[2]          # reports what the client asked for
    assert pts[3]["view_flag"] is True        # the ask is in another sentence; the claim still counts
    data["headline"] = "Brightway has four deals maturing. OCBC research has forecasts for both USD/SGD and USD/JPY."
    answer, *_ = run_agent([final(data)])
    assert answer["headline_view_flag"] is False     # saying research HAS a forecast is not a view
    data["sections"][0]["kind"] = "client_data"   # logged client data is never flagged
    answer, *_ = run_agent([final(data)])
    assert not any("view_flag" in p for p in answer["sections"][0]["points"])


def test_book_views_send_the_client_as_a_filter():
    from app.orchestrator.clients import ClientDataClient
    seen = []

    class Http:
        def get(self, url, params=None, headers=None):
            seen.append((url, params))
            return NS(status_code=200, json=lambda: {"ok": True})

    cd = ClientDataClient(base="http://x", token="t")
    cd.client = Http()
    cd.view("maturities", client_id="C001", days=30, pair=None)
    cd.view("overview", "C002")
    assert seen[0] == ("http://x/v1/book/maturities", {"days": 30, "client_id": "C001"})
    assert seen[1] == ("http://x/v1/clients/C002/overview", {})


def test_figure_rules():
    assert ag.days_asked("next 2 weeks") == 14 and ag.days_asked("in the next 10 days") == 10
    assert ag.days_asked("anything soon?") == 30
    assert [r for r, _ in ag.numbers("SELL USD 1,250.5k on 19 Nov 2026 at 1.2992")] == ["1,250.5", "19", "2026", "1.2992"]
    assert ag.needs_check("1.2992", 1.2992) and ag.needs_check("150", 150)
    assert not ag.needs_check("19", 19) and not ag.needs_check("2027", 2027)


@pytest.mark.parametrize("q,kw,want", [
    ("What does the latest available research say about USD/SGD through 2027?", {}, "research"),
    ("Summarize OCBC's published view on SGD interest rates.", {}, "research"),
    ("Jimmy from Harbourline asked about the SGD rates outlook", {"client_matched": True}, "research"),
    ("Brief me on Harbourline Logistics before my meeting", {}, "agent"),
    ("Which clients have deals maturing in the next 2 weeks?", {}, "agent"),
    ("Any hedging ideas for Lumina Property Trust?", {}, "agent"),
    ("What's a zero-cost collar?", {}, "agent"),
    ("Harbourline Logistics", {"client_matched": True}, "agent"),
    ("what about USD/JPY?", {"last_mode": "agent"}, "agent"),
    ("what about USD/JPY?", {}, "research"),
    ("hi", {}, "auto"),
    ("Brief me on Harbourline", {"forced": "research"}, "research"),
])
def test_router(q, kw, want):
    assert choose(q, **kw) == want


def test_executive_summary_opens_with_picked_research_verbatim():
    script = [tool_use(("client_overview", {"client_id": "C001"}), ("ocbc_research", {"question": "OCBC USD/SGD view"})),
              final(ANSWER | {"summary_refs": ["R2", "R99"]})]
    answer, *_ = run_agent(script)
    picked = answer["summary_research"]
    assert [p["item"] for p in picked] == ["R2"]                       # unknown ids are dropped
    assert picked[0]["citations"] and set(picked[0]["citations"]) <= set(answer["cited_sources"])


def test_executive_summary_falls_back_to_quoted_research_and_sections_are_ordered():
    script = [tool_use(("client_overview", {"client_id": "C001"}), ("ocbc_research", {"question": "OCBC USD/SGD view"})),
              final(ANSWER)]                                            # no summary_refs from the model
    answer, *_ = run_agent(script)
    quoted = [p["item"] for s in answer["sections"] for p in s["points"] if p.get("type") == "summary"]
    assert [p["item"] for p in answer["summary_research"]] == quoted[:ag.MAX_SUMMARY_REFS]
    kinds = [s["kind"] for s in answer["sections"]]
    assert kinds == sorted(kinds, key=ag.SECTION_ORDER.index)           # client book, ideas, research, general


def test_missing_talking_points_or_research_are_asked_for_once():
    """A client's records were read and research returned items, but the answer left out the talking points
    and the quoted research: the model is asked once (no tools) to add them."""
    thin = {"headline": "Harbourline has one forward maturing on 3 Dec.", "follow_ups": [],
            "sections": [{"title": "Where they stand", "kind": "client_data", "table": None,
                          "points": [{"text": "SELL USD 4.7m forward matures on 3 Dec 2026.", "refs": ["D1"]}]}]}
    script = [tool_use(("client_overview", {"client_id": "C001"}), ("ocbc_research", {"question": "USD/SGD view"})),
              final(thin), final(ANSWER)]
    answer, model, *_ = run_agent(script)
    assert len(model.calls) == 3
    repair = model.calls[2]
    assert repair["tool_choice"] == {"type": "none"}
    ask = repair["messages"][-1]["content"]
    assert "Talking points & trade ideas" in ask and "ocbc_research section" in ask
    assert {s["kind"] for s in answer["sections"]} >= {"ai_suggestion", "ocbc_research"}
    assert answer["agent"]["turns"] == 3

    # a complete answer is not sent back, and a book-wide maturity check needs no client talking points
    _, model, *_ = run_agent([tool_use(("client_overview", {"client_id": "C001"})), final(ANSWER)])
    assert len(model.calls) == 2
    book = {"headline": "1 deal matures.", "follow_ups": [], "sections": [
        {"title": "Maturing", "kind": "client_data", "table": None,
         "points": [{"text": "Harbourline: SELL USD 4.7m forward on 19 Nov 2026.", "refs": ["D1"]}]}]}
    _, model, *_ = run_agent([tool_use(("upcoming_maturities", {"days": 14})), final(book)],
                             question="What is maturing in the next 2 weeks?")
    assert len(model.calls) == 2
