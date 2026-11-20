"""Agent-mode plumbing: the client-data views the agent's tools read, and the orchestrator's choice
between research mode and agent mode. Each runs in a subprocess so its process guard stays there."""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VIEWS = r"""
import json, os, sys
os.environ["RA_DATA_DIR"] = sys.argv[1]
os.environ["RA_TOKEN_ORCH_CLIENTS"] = "t"
from fastapi.testclient import TestClient
from app.clientdata.service import app
c = TestClient(app)
h = {"Authorization": "Bearer t"}
g = lambda path, **p: c.get(path, params=p, headers=h)
out = {
    "no_token": c.get("/v1/clients/C001/overview").status_code,
    "overview": g("/v1/clients/C001/overview").json(),
    "unknown": g("/v1/clients/C999/overview").status_code,
    "bad_id": g("/v1/clients/C0;1/trades").status_code,
    "bad_status": g("/v1/clients/C001/trades", status="sometimes").status_code,
    "trades": g("/v1/clients/C001/trades", pair="sgd/usd", status="open", limit=3).json(),
    "all_trades": g("/v1/clients/C001/trades", limit=500).json(),
    "maturities": g("/v1/book/maturities", days=14).json(),
    "maturities_one": g("/v1/book/maturities", days=400, client_id="C001").json(),
    "positions": g("/v1/clients/C005/positions", pair="AUDUSD").json(),
    "clients_sgd": g("/v1/book/clients", pair="USD/SGD").json(),
    "clients_rm": g("/v1/book/clients", rm="priya").json(),
}
print(json.dumps(out))
"""


def test_client_views(tmp_path):
    r = subprocess.run([sys.executable, "-c", VIEWS, str(tmp_path)], cwd=ROOT, capture_output=True, text=True,
                       timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["no_token"] == 401 and out["unknown"] == 404 and out["bad_id"] == 404 and out["bad_status"] == 400

    ov = out["overview"]
    assert ov["client"]["name"] == "Harbourline Logistics Pte Ltd"
    assert {"USD/SGD", "USD/CNH"} <= {p["pair"] for p in ov["pairs"]}
    assert ov["contacts"][0]["name"] == "Jimmy Tan" and ov["contacts"][0]["primary"] is True
    assert ov["activity"]["total_deals"] >= ov["activity"]["open_deals"] > 0
    # Data minimisation: no CIF, RM code or e-mail reaches the agent.
    text = json.dumps(ov)
    assert "sibs_cif" not in text and "@" not in text and "customer_rm_code" not in text

    t = out["trades"]
    assert t["shown"] <= 3 and all(d["pair"] == "USD/SGD" and d["status"] == "Live" for d in t["deals"])
    assert out["all_trades"]["shown"] <= 60          # limit is capped
    dates = [datetime.strptime(d["trade_date"], "%d %b %Y") for d in out["all_trades"]["deals"]]
    assert dates and dates == sorted(dates, reverse=True)   # newest first

    m = out["maturities"]
    days = [d["days_to_maturity"] for d in m["deals"]]
    assert days == sorted(days) and all(0 <= x <= 14 for x in days)
    assert sum(m["clients"].values()) == m["maturing_deals"]
    assert all(d["client_id"] == "C001" for d in out["maturities_one"]["deals"])

    pos = out["positions"]["pairs"]
    assert [p["pair"] for p in pos] == ["AUD/USD"] and pos[0]["position_lines"]

    assert {c["client_id"] for c in out["clients_sgd"]["clients"]} >= {"C001", "C002", "C004", "C008"}
    assert all("USD/SGD" in c["pairs_traded"] for c in out["clients_sgd"]["clients"])
    assert out["clients_rm"]["count"] >= 1
    assert all(c["relationship_manager"] == "Priya Raman" for c in out["clients_rm"]["clients"])


ROUTING = r"""
import json, os
os.environ["RA_TOKEN_GATEWAY_ORCH"] = "t"
from app.orchestrator import service

OVERVIEW = {"as_of": "16 Nov 2026",
            "client": {"client_id": "C001", "name": "Harbourline Logistics Pte Ltd", "segment": "LC",
                       "industry": "Shipping", "country": "SG", "profile": "USD earner", "hedging_notes": "",
                       "relationship_manager": "Tan Wei Ling"},
            "contacts": [], "pairs": [], "maturing_next_30_days": [], "recent_asks": [], "pattern_notes": [],
            "activity": {"total_deals": 3, "open_deals": 1, "deals_last_90_days": 1, "last_trade": None,
                         "products": {}}}
MATCH = {"status": "match", "research_question": "", "mention": "Harbourline",
         "candidates": [{"client_id": "C001", "client_name": "Harbourline Logistics Pte Ltd",
                         "contact_id": None, "contact_name": None}]}

AMBIG = {"status": "ambiguous", "research_question": "asked about USD/CNH", "mention": "Jimmy",
         "candidates": [{"client_id": "C001", "client_name": "Harbourline Logistics Pte Ltd", "contact_id": "P001",
                         "contact_name": "Jimmy Tan"},
                        {"client_id": "C002", "client_name": "Meridian Foods Holdings Ltd", "contact_id": "P003",
                         "contact_name": "Jimmy Lee"}]}

class CD:
    def identify(self, q):
        if "Jimmy" in q: return AMBIG
        return MATCH if "Harbourline" in q else {"status": "none", "candidates": []}
    def exists(self, cid): return True
    def view(self, name, client_id=None, **p): return OVERVIEW
    def past_asks(self, *a, **kw): return None
    def trade_context(self, *a): return []

research_calls = []
def fake_research(q, state, emit):
    research_calls.append(q)
    a = service._simple(q, "complete", "research answer")
    a["direct"] = [{"text": "We expect USD/SGD to ease.", "citations": []}]
    return a, {**state, "last_plan": {"q": q}}

service.clientdata = CD()
service.answer_question = fake_research
service.llm.status = lambda: {"available": False, "key_present": True}
quiet = lambda _t: None
out = {}
a, s = service.routed_answer("Brief me on Harbourline before my meeting", {}, "auto", quiet)
out["brief"] = {"kind": a.get("kind"), "deterministic": a["agent"]["deterministic"], "client": s.get("client", {}).get("client_id"),
                "notice": a["notices"][0]["text"], "log_box": a["client"]["status"]}
a, s = service.routed_answer("What is OCBC's USD/SGD forecast?", {}, "auto", quiet)
out["research"] = {"kind": a.get("kind"), "direct": a["direct"][0]["text"]}
a, s = service.routed_answer("Brief me on Harbourline", {}, "research", quiet)
out["forced_research"] = a.get("kind")
a, s = service.routed_answer("What's a zero-cost collar?", {}, "auto", quiet)
out["collar_no_model"] = {"kind": a.get("kind"), "notice": (a["notices"] or [{}])[0].get("text", "")}
# "Jimmy" right after Meridian's Jimmy Lee: still not assumed, and not asked - a generic research answer.
prior = {"client": AMBIG["candidates"][1], "last_mode": "agent"}
a, s = service.routed_answer("Jimmy asked about USD/CNH", prior, "auto", quiet)
out["ambiguous"] = {"kind": a.get("kind"), "client": a["client"]["status"], "picks": len(a["client"]["candidates"]),
                    "notice": a["notices"][0]["text"], "kept": s.get("client", {}).get("client_id")}
# Typed in lower case at the start, a first name still counts: "jimmy asked ..." is the three Jimmys.
a, s = service.routed_answer("jimmy asked for usd/sgd", prior, "auto", quiet)
out["lower"] = {"status": a["client"]["status"], "unknown": bool(a["client"].get("unknown")),
                "picks": len(a["client"]["candidates"])}
# A name not in the book: research first, then "which company is Jeremy from?" - never the earlier client.
a, s = service.routed_answer("jeremy asked for usd/sgd", prior, "auto", quiet)
out["unknown"] = {"kind": a.get("kind"), "client": a["client"], "notice": a["notices"][0]["text"]}
out["memory"] = service.memory_entry(a["client"], "SuperHeroes Bank")
out["company_reply"] = [service.looks_like_company(t) for t in ("SuperHeroes Bank", "what about usd/jpy?",
                                                                  "Jimmy asked about gold")]
out["research_calls"] = research_calls
print(json.dumps(out))
"""


def test_routing_between_modes():
    r = subprocess.run([sys.executable, "-c", ROUTING], cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    # Agent question, model off: a deterministic client-book snapshot with the reason, and the log box.
    assert out["brief"]["kind"] == "agent" and out["brief"]["deterministic"] is True
    assert "Claude API" in out["brief"]["notice"] and out["brief"]["client"] == "C001"
    assert out["brief"]["log_box"] == "match"
    # Research question: the research pipeline, unchanged.
    assert out["research"]["kind"] is None and out["research"]["direct"] == "We expect USD/SGD to ease."
    # Pinned to research mode: research even for an agent-style ask.
    assert out["forced_research"] is None
    # Agent-only ask with no model and no client: research is shown, with the reason.
    assert out["collar_no_model"]["kind"] is None and "Agent mode needs" in out["collar_no_model"]["notice"]
    # A name matching several clients: OCBC research on the question with the name removed, no client box.
    amb = out["ambiguous"]
    assert amb["kind"] is None and amb["client"] == "ambiguous" and amb["picks"] == 2 and amb["kept"] == "C002"
    assert "matches several clients" in amb["notice"] and "Jimmy Tan (Harbourline" in amb["notice"]
    assert out["research_calls"][-2] == "asked about USD/CNH"
    unk = out["unknown"]
    assert unk["kind"] is None and unk["client"]["unknown"] and unk["client"]["candidates"] == []
    assert unk["client"]["mention"] == "Jeremy" and "which company Jeremy is from" in unk["notice"]
    assert out["research_calls"][-1] == "for usd/sgd"
    mem = out["memory"]
    assert mem["name"] == "Jeremy" and mem["company"] == "SuperHeroes Bank" and "insights" in mem
    assert out["company_reply"] == [True, False, False]
    assert out["lower"] == {"status": "ambiguous", "unknown": False, "picks": 2}
    assert len(out["research_calls"]) == 6
