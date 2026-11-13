"""The client box shows the confirmed contact's earlier asks (orchestrator wiring)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import json, os
os.environ["RA_TOKEN_GATEWAY_ORCH"] = "t"
from app.orchestrator import service

class Stub:
    def __init__(self, reply): self.reply, self.calls = reply, []
    def past_asks(self, client_id, contact_id):
        self.calls.append((client_id, contact_id)); return self.reply

out = {}
service.clientdata = Stub({"count": 2, "items": [{"asked_at": "2026-11-13T14:44:00", "question": "USD/SGD forecast"}]})
client = {"candidates": [{"client_id": "C001", "contact_id": "P001"}]}
service.attach_past_asks(client)
out["with"] = client.get("past_asks")
out["calls"] = service.clientdata.calls
service.clientdata = Stub({"count": 0, "items": []})
none = {"candidates": [{"client_id": "C002", "contact_id": None}]}
service.attach_past_asks(none)
out["without"] = "past_asks" in none
service.clientdata = Stub(None)  # service unreachable: never blocks an answer
down = {"candidates": [{"client_id": "C001", "contact_id": "P001"}]}
service.attach_past_asks(down)
out["down"] = "past_asks" in down
print(json.dumps(out))
"""


def test_attach_past_asks():
    import json
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["with"]["count"] == 2 and out["calls"] == [["C001", "P001"]]
    assert out["without"] is False and out["down"] is False
