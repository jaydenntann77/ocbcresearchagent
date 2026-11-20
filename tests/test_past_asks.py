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
    def past_asks(self, client_id, contact_id, limit=3):
        self.calls.append((client_id, contact_id, limit)); return self.reply

out = {}
service.clientdata = Stub({"count": 9, "items": [{"asked_at": f"2026-11-{13 - k:02d}T14:44:00", "question": "USD/SGD forecast"}
                                                for k in range(5)]})
client = {"candidates": [{"client_id": "C001", "contact_id": "P001"}]}
service.attach_past_asks(client)
out["with"] = client.get("past_asks")
out["calls"] = service.clientdata.calls
out["insights"] = client.get("insights")
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
    # the box lists the 3 most recent; the insights count every ask on record
    assert out["with"]["count"] == 9 and len(out["with"]["items"]) == 3 and out["calls"] == [["C001", "P001", 10]]
    assert out["insights"][0].startswith("9 previous asks on record")
    assert out["without"] is False and out["down"] is False
