"""The "Vincent Claude API" switch: one in-memory switch gates every model call; OFF by default and
after every restart; changed from the chat only after Yes; refused in public mode. All offline:
the key is fake and the Anthropic client is mocked."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.orchestrator import client_memory, llm, model_switch, trade_note

ROOT = Path(__file__).resolve().parents[1]
FAKE_KEY = "sk-ant-test-not-a-real-key"


@pytest.fixture(autouse=True)
def fresh_switch(monkeypatch):
    model_switch.reset()
    monkeypatch.setattr(model_switch.config, "PUBLIC_MODE", False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    yield
    model_switch.reset()


# ------------------------------------------------------------------ command matching
@pytest.mark.parametrize("text", [
    "turn on vincent claude api", "activate claude", "enable the api", "switch on AI mode", "Turn ON Claude API!",
    "please turn the claude api on", "can you enable claude", "turn on", "start using the model", "enable",
    "Switch on Vincent's Claude API please", "turn on ai-mode",
])
def test_on_commands(text):
    assert model_switch.parse_command(text) == "on"


@pytest.mark.parametrize("text", [
    "turn off", "deactivate claude", "disable the api", "switch off AI mode", "stop the claude api",
    "please turn the model off", "Turn OFF Vincent Claude API.", "disable",
])
def test_off_commands(text):
    assert model_switch.parse_command(text) == "off"


@pytest.mark.parametrize("text", [
    "What is OCBC's view on AI stocks?",
    "How does the API economy affect SGD?",
    "Will the Fed turn off QE?",
    "Turn off the USD/SGD forecast",
    "Is the Claude API on?",
    "stop", "start",
    "activate hedging for Aurora",
    "turn on and turn off claude",
    "What does OCBC say about AI model risk in markets?",
    "Daniel from Aurora asks for the USD/SGD forecast",
    "enable the claude api and give me the USD/SGD forecast for 2027",
    "",
])
def test_research_questions_are_not_commands(text):
    assert model_switch.parse_command(text) is None


# ------------------------------------------------------------------ the switch
def test_off_by_default_and_on_restart():
    assert model_switch.is_on() is False and model_switch.enabled() is False
    assert llm.status()["available"] is False and llm.status()["key_present"] is True
    # a fresh process (= restarting run.py) starts OFF even with a key in the environment
    code = "from app.orchestrator import model_switch, llm; print(model_switch.is_on(), llm.status()['available'])"
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, ANTHROPIC_API_KEY=FAKE_KEY))
    assert r.stdout.split() == ["False", "False"]


def test_nothing_changes_without_yes():
    p = model_switch.proposal("on")
    assert p["status"] == "pending" and p["ask"] == model_switch.ON_COST and model_switch.is_on() is False
    assert model_switch.confirm(p, False)["status"] == "declined" and model_switch.is_on() is False
    done = model_switch.confirm(p, True)
    assert done["status"] == "done" and done["state"] == "ON" and model_switch.enabled()
    assert model_switch.confirm(done, True) == done                          # an answered box does nothing more
    off = model_switch.proposal("off")
    assert off["ask"] == model_switch.OFF_COST
    model_switch.confirm(off, False)
    assert model_switch.is_on()
    model_switch.confirm(off, True)
    assert not model_switch.is_on()
    assert model_switch.proposal("off")["status"] == "unchanged"


def test_no_key_means_no_change(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = model_switch.proposal("on")
    assert p["status"] == "no_key" and p["message"] == "No API key found in .env" and p["ask"] is None
    pending = {"action": "on", "status": "pending", "state": "OFF"}
    assert model_switch.confirm(pending, True)["status"] == "no_key" and not model_switch.is_on()
    assert llm.status()["available"] is False


def test_public_mode_refuses_the_command_but_uses_the_key_as_before(monkeypatch):
    monkeypatch.setattr(model_switch.config, "PUBLIC_MODE", True)
    assert model_switch.proposal("on")["status"] == "refused"
    assert model_switch.proposal("off")["status"] == "refused"
    assert model_switch.confirm({"action": "off", "status": "pending", "state": "ON"}, True)["status"] == "refused"
    assert not model_switch.is_on()                       # the local switch is untouched ...
    assert model_switch.enabled() and llm.status()["available"]   # ... and does not apply: key present -> on
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert not model_switch.enabled() and not llm.status()["available"]      # no key -> extractive, as before


def test_public_mode_model_calls_work_as_before(monkeypatch):
    import anthropic
    FakeAnthropic.created = 0
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    monkeypatch.setattr(model_switch.config, "PUBLIC_MODE", True)
    assert llm.search_terms("What is the Fed doing?") == ["FOMC"]
    assert FakeAnthropic.created == 1


# ------------------------------------------------------------------ every model call is gated
class FakeAnthropic:
    created = 0

    def __init__(self, *a, **kw):
        FakeAnthropic.created += 1
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        text = json.dumps({"terms": ["FOMC"]}) if "output_config" in kw and "format" in kw["output_config"] \
            else "USD/SGD forecast"
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn")


def test_while_off_no_model_client_is_created(monkeypatch):
    import anthropic
    FakeAnthropic.created = 0
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    assert llm.search_terms("What is the Fed doing?") == []
    with pytest.raises(llm.ModelUnavailable):
        llm.synthesize("q", [], [], [])
    assert client_memory._ai_clean("asked what is the USD/SGD forecast") is None
    assert trade_note.rewrite(["Net: BUY USD 5.3m"]) is None
    assert FakeAnthropic.created == 0                                     # key present, switch OFF: no client

    model_switch.set_on(True)                                             # ON: the same calls do reach the (mock) API
    assert llm.search_terms("What is the Fed doing?") == ["FOMC"]
    assert client_memory._ai_clean("asked what is the USD/SGD forecast") == "USD/SGD forecast"
    assert FakeAnthropic.created == 2


def test_client_memory_haiku_call_has_room_to_answer(monkeypatch):
    import anthropic
    seen = {}

    class Spy(FakeAnthropic):
        def _create(self, **kw):
            seen.update(kw)
            return super()._create(**kw)
    monkeypatch.setattr(anthropic, "Anthropic", Spy)
    model_switch.set_on(True)
    client_memory._ai_clean("asked about USD/SGD")
    assert seen["max_tokens"] >= 1024 and seen["output_config"] == {"effort": "low"}


# ------------------------------------------------------------------ through the orchestrator API
ORCH = r"""
import json, os, sys
os.environ.update({"RA_DATA_DIR": sys.argv[1], "RA_TOKEN_GATEWAY_ORCH": "g", "ANTHROPIC_API_KEY": "sk-ant-fake"})
if sys.argv[2] == "public":
    os.environ["RA_PUBLIC_MODE"] = "1"
from fastapi.testclient import TestClient
from app.orchestrator.service import app
c = TestClient(app)
h = {"Authorization": "Bearer g"}

def chat(msg):
    out = {}
    with c.stream("POST", "/v1/chat", json={"message": msg}, headers=h) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                e = json.loads(line[5:])
                if e["type"] == "answer":
                    out = {"cid": e["conversation_id"], "mid": e["message_id"], "answer": e["answer"]}
    return out

def confirm(r, yes):
    return c.post(f"/v1/conversations/{r['cid']}/messages/{r['mid']}/model-switch", json={"confirm": yes}, headers=h)

out = {}
r = chat("turn on vincent claude api")
out["ask"] = r["answer"]["model_switch"]
out["no_research"] = r["answer"]["status"] == "info" and not r["answer"].get("plan")
if sys.argv[2] == "public":
    out["confirm_status"] = confirm(r, True).status_code
    out["model"] = c.get("/v1/meta", headers=h).json()["model"]
    out["button"] = c.post("/v1/model", json={"enabled": False}, headers=h).status_code
else:
    out["no"] = confirm(r, False).json()
    out["after_no"] = c.get("/v1/meta", headers=h).json()["model"]["available"]
    r2 = chat("activate claude")
    out["yes"] = confirm(r2, True).json()
    out["after_yes"] = c.get("/v1/meta", headers=h).json()["model"]["available"]
    r3 = chat("disable the api")
    out["off"] = confirm(r3, True).json()["model_switch"]["state"]
    # the mode-badge button (sent only after Yes in its confirm box)
    out["button_on"] = c.post("/v1/model", json={"enabled": True}, headers=h).json()["model"]["available"]
    out["button_off"] = c.post("/v1/model", json={"enabled": False}, headers=h).json()["model"]["available"]
    key = os.environ.pop("ANTHROPIC_API_KEY")
    nokey = c.post("/v1/model", json={"enabled": True}, headers=h)
    out["button_no_key"] = [nokey.status_code, nokey.json()["detail"]]
    os.environ["ANTHROPIC_API_KEY"] = key
    out["confirm_texts"] = [c.get("/v1/meta", headers=h).json()["model"][k] for k in ("confirm_on", "confirm_off")]
print(json.dumps(out))
"""


def run_orch(tmp_path, mode):
    r = subprocess.run([sys.executable, "-c", ORCH, str(tmp_path), mode], cwd=ROOT, capture_output=True, text=True,
                       timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_chat_command_flow_through_orchestrator(tmp_path):
    out = run_orch(tmp_path, "local")
    assert out["ask"]["status"] == "pending" and out["ask"]["ask"] == model_switch.ON_COST and out["no_research"]
    assert out["no"]["model_switch"]["status"] == "declined" and out["after_no"] is False
    assert out["yes"]["model_switch"]["state"] == "ON" and out["after_yes"] is True
    assert out["off"] == "OFF"
    assert out["button_on"] is True and out["button_off"] is False
    assert out["button_no_key"] == [400, "No API key found in .env"]
    assert out["confirm_texts"] == [model_switch.ON_COST, model_switch.OFF_COST]


def test_public_mode_refuses_through_orchestrator(tmp_path):
    out = run_orch(tmp_path, "public")
    assert out["ask"]["status"] == "refused" and out["ask"]["ask"] is None
    assert out["confirm_status"] == 403
    assert out["model"]["available"] is True and out["model"]["public_mode"] is True   # key present -> on
    assert out["button"] == 403
