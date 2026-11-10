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
