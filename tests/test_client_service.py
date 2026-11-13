"""Client-data service API, run in a subprocess so its process guard does not
affect the rest of the test session."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import json, os, sys
os.environ["RA_DATA_DIR"] = sys.argv[1]
os.environ["RA_TOKEN_ORCH_CLIENTS"] = "t"
from fastapi.testclient import TestClient
from app.clientdata.service import app
c = TestClient(app)
h = {"Authorization": "Bearer t"}
out = {}
out["no_token"] = c.post("/v1/identify", json={"question": "Jimmy"}).status_code
out["identify"] = c.post("/v1/identify", json={"question": "Jimmy from company A asks for the USD/SGD forecast"},
                         headers=h).json()
out["wrong_contact"] = c.post("/v1/interactions", json={"client_id": "C001", "contact_id": "P003", "question": "q"},
                              headers=h).status_code
out["unknown_client"] = c.post("/v1/interactions", json={"client_id": "C999", "question": "q"}, headers=h).status_code
out["log"] = c.post("/v1/interactions", json={"client_id": "C001", "contact_id": "P001", "question": "USD/SGD?",
                                              "instruments": ["USDSGD"], "topic": "FX"}, headers=h).json()
out["profile"] = c.get("/v1/clients/C001", headers=h).json()
jimmys = out["identify_jimmy"] = c.post("/v1/identify", json={"question": "Jimmy asks for USD/SGD"}, headers=h).json()
out["pick_b"] = c.post("/v1/resolve-pick", json={"text": "b", "candidates": jimmys["candidates"]}, headers=h).json()
out["pick_q"] = c.post("/v1/resolve-pick", json={"text": "and what about EUR/USD next year?",
                                                 "candidates": jimmys["candidates"]}, headers=h).json()
out["ctx_pinnacle"] = c.post("/v1/clients/C008/trade-context", json={"pairs": ["sgd/usd"]}, headers=h).json()
out["ctx_never"] = c.post("/v1/clients/C003/trade-context", json={"pairs": ["USDSGD"]}, headers=h).json()
out["ctx_unknown"] = c.post("/v1/clients/C999/trade-context", json={"pairs": ["USDSGD"]}, headers=h).status_code
c.post("/v1/interactions", json={"client_id": "C001", "contact_id": "P001",
                                 "question": "Jimmy from Harbourline asked about the SGD rates outlook"}, headers=h)
c.post("/v1/interactions", json={"client_id": "C002", "contact_id": "P003",
                                 "question": "Jimmy from Meridian Foods asked about AUD/USD"}, headers=h)
out["asks_tan"] = c.get("/v1/clients/C001/asks", params={"contact_id": "P001"}, headers=h).json()
out["asks_lee"] = c.get("/v1/clients/C002/asks", params={"contact_id": "P003", "limit": 10}, headers=h).json()
out["asks_unknown"] = c.get("/v1/clients/C999/asks", headers=h).status_code
out["asks_bad_contact"] = c.get("/v1/clients/C001/asks", params={"contact_id": "x;y"}, headers=h).status_code
print(json.dumps(out))
"""


def test_client_service_api(tmp_path):
    r = subprocess.run([sys.executable, "-c", SCRIPT, str(tmp_path)], cwd=ROOT, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["no_token"] == 401
    ident = out["identify"]
    assert ident["status"] == "match" and ident["candidates"][0]["contact_name"] == "Jimmy Tan"
    assert ident["research_question"] == "The USD/SGD forecast"
    assert out["wrong_contact"] == 400 and out["unknown_client"] == 404
    logged = out["log"]["interaction"]
    assert logged["client_id"] == "C001" and logged["instruments"] == "USDSGD"
    assert out["profile"]["client"]["counterpart_name"] == "Harbourline Logistics Pte Ltd"
    assert any(i["interaction_id"] == logged["interaction_id"] for i in out["profile"]["interactions"])
    assert (tmp_path / "clientdata" / "clientdata.db").exists()  # built on first start
    assert out["pick_b"]["pick"] == out["identify_jimmy"]["candidates"][1]
    assert out["pick_q"]["pick"] is None
    pin = out["ctx_pinnacle"]["contexts"][0]
    assert pin["pair"] == "USD/SGD" and pin["kind"] == "open"
    assert {"label": "Net", "text": "SELL USD 38.8m"} in pin["lines"]
    assert any(r["note"] == "offsets BUY USD 47.0m (3 Jul)" for r in pin["trades"])
    assert out["ctx_never"]["contexts"][0]["lines"] == [{"label": None, "text": "No past USD/SGD trades on record."}]
    # Past asks are per contact: Jimmy Tan (Harbourline) and Jimmy Lee (Meridian) never share a history.
    tan, lee = out["asks_tan"], out["asks_lee"]
    rates = [i["question"] for i in tan["items"] if i["question"].lower().endswith("sgd rates outlook")]
    assert rates and all("Harbourline" not in q and "Jimmy" not in q for q in rates)  # names taken out
    assert all("AUD/USD" not in i["question"] for i in tan["items"])
    assert any("AUD/USD" in i["question"] for i in lee["items"])
    assert all("SGD rates outlook" not in i["question"] for i in lee["items"])
    assert out["asks_unknown"] == 404 and out["asks_bad_contact"] == 400
    assert out["ctx_unknown"] == 404
