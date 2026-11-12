"""The "Vincent Claude API" switch: ONE in-memory on/off switch for every model call.

* Model use needs BOTH a key in .env (ANTHROPIC_API_KEY; only checked for being non-empty, never
  read out, printed or logged) AND this switch ON.
* The switch lives in the orchestrator's memory, so it is OFF by default and after every restart.
  While OFF nothing calls Anthropic: answer synthesis, the Haiku query rewrite, the client-memory
  summary and the trade-note wording all check `enabled()` before creating a client.
* It is changed from the chat ("turn on vincent claude api", "disable the api", ...) and only after
  the user confirms with Yes.
* Hosted demo (RA_PUBLIC_MODE=1): the switch does not apply. Model use works as before - key present
  means on, with the existing daily cap - and the chat command is refused.
"""
from __future__ import annotations

import re
import threading

from app.common import config

_lock = threading.Lock()
_state = {"on": False}

ON_COST = "Turn ON Claude API? Answers will cost about US$0.05-0.10 per question."
OFF_COST = "Turn OFF Claude API? Answers will quote OCBC research directly, with no API cost."
NO_KEY = "No API key found in .env"
PUBLIC_REFUSED = "Switching the Claude API is not available on the hosted demo."


def key_present() -> bool:
    """A credential is configured (non-empty). The value itself is never touched here."""
    return config.model_credentials_present()


def is_on() -> bool:
    return _state["on"]


def enabled() -> bool:
    """May a model be called right now? Locally: key present AND switch ON. Hosted demo: key present."""
    if config.PUBLIC_MODE:
        return key_present()
    return _state["on"] and key_present()


def set_on(on: bool) -> bool:
    with _lock:
        _state["on"] = bool(on) and key_present()
        return _state["on"]


def reset() -> None:
    with _lock:
        _state["on"] = False


# ------------------------------------------------------------------ chat command matching
ON_WORDS = {"enable", "activate", "start", "resume"}
OFF_WORDS = {"disable", "deactivate", "stop", "pause"}
PHRASAL = {"turn", "switch", "put", "flip"}          # turn/switch ... on|off
TARGETS = {"claude", "api", "apis", "model", "models", "llm", "anthropic", "ai", "haiku", "opus"}
FILLER = {"please", "pls", "plz", "the", "a", "an", "my", "our", "now", "it", "can", "could", "would", "you",
          "kindly", "vincent", "vincents", "mode", "for", "me", "us", "again", "back", "just", "go", "ahead",
          "and", "to", "i", "want", "wanna", "lets", "let", "using", "use", "of", "thanks", "thank", "hey", "hi",
          "ok", "okay", "claudes", "access", "calls", "mode's", "usage"}
NO_TARGET_OK = {"enable", "disable", "activate", "deactivate"}   # "turn off" / "disable" alone also count
MAX_WORDS = 9


def parse_command(text: str) -> str | None:
    """'on' / 'off' for a short command-like message that switches the model; None for anything else
    (research questions that merely mention AI or an API go to research as normal). Deterministic."""
    words = re.sub(r"[^a-z' ]+", " ", (text or "").lower().replace("-", " ")).replace("'", "").split()
    if not words or len(words) > MAX_WORDS:
        return None
    phrasal = any(w in PHRASAL for w in words)
    on = any(w in ON_WORDS for w in words) or (phrasal and "on" in words)
    off = any(w in OFF_WORDS for w in words) or (phrasal and "off" in words)
    if on == off:                               # neither, or both
        return None
    known = ON_WORDS | OFF_WORDS | PHRASAL | TARGETS | FILLER | {"on", "off"}
    if any(w not in known for w in words):      # anything else means it is not a bare command
        return None
    has_target = any(w in TARGETS for w in words)
    bare_ok = (phrasal and ("on" in words or "off" in words)) or any(w in NO_TARGET_OK for w in words)
    if not has_target and not bare_ok:          # "stop" / "start" alone are not enough
        return None
    return "on" if on else "off"


def proposal(action: str) -> dict:
    """What the chat shows for an on/off command. Nothing changes until the user confirms."""
    current = "ON" if is_on() else "OFF"
    want = "ON" if action == "on" else "OFF"
    base = {"action": action, "state": current, "key_present": key_present(), "status": "pending",
            "ask": None, "message": ""}
    if config.PUBLIC_MODE:
        return base | {"status": "refused", "message": PUBLIC_REFUSED}
    if action == "on" and not key_present():
        return base | {"status": "no_key", "message": NO_KEY}
    if current == want:
        return base | {"status": "unchanged", "message": f"Claude API is already {current}."}
    return base | {"ask": ON_COST if action == "on" else OFF_COST}


def confirm(entry: dict, yes: bool) -> dict:
    """Apply a pending proposal: only Yes changes the switch (and only if still allowed)."""
    if entry.get("status") != "pending":
        return entry
    if not yes:
        return entry | {"status": "declined", "ask": None,
                        "message": f"No change: Claude API stays {'ON' if is_on() else 'OFF'}."}
    if config.PUBLIC_MODE:
        return entry | {"status": "refused", "ask": None, "message": PUBLIC_REFUSED}
    if entry["action"] == "on" and not key_present():
        return entry | {"status": "no_key", "ask": None, "message": NO_KEY}
    now = set_on(entry["action"] == "on")
    return entry | {"status": "done", "ask": None, "state": "ON" if now else "OFF",
                    "message": f"Claude API is now {'ON' if now else 'OFF'}."}
