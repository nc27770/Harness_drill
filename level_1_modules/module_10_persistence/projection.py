"""Projection — the neutral faculty-transcript ↔ vendor wire format (SCHEMA.md invariant 3).

The stored state is provider-agnostic (faculty-tagged). This is the ONLY place
that knows Anthropic's message shape. Swap the provider later → rewrite this file
only; the Mind's stored identity is untouched. That's what "outlasts the vendor"
buys, and the price is this one translation layer.

  perception (no ref) → user text          perception (with ref) → tool_result
  action               → assistant tool_use  reasoning / expression → assistant text

Consecutive same-role entries are grouped into one message (Anthropic carries a
list of content blocks per turn — e.g. reasoning text + a tool_use in one
assistant turn).
"""

from __future__ import annotations


def to_anthropic_messages(transcript: list[dict]) -> list[dict]:
    msgs: list[dict] = []
    for e in transcript:
        f = e["faculty"]
        if f == "perception":
            role = "user"
            if e.get("ref"):  # tool_result: an engine's output OR a human's answer to an ask
                block = {"type": "tool_result", "tool_use_id": e["ref"],
                         "content": str(e.get("content", ""))}
            else:
                block = {"type": "text", "text": str(e.get("content", ""))}
        elif f == "action":
            role = "assistant"
            block = {"type": "tool_use", "id": e["ref"], "name": e["engine"],
                     "input": e.get("input", {})}
        else:  # reasoning, expression
            txt = str(e.get("content", "")).strip()
            if not txt:
                continue  # Anthropic rejects empty text blocks
            role, block = "assistant", {"type": "text", "text": txt}

        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"].append(block)
        else:
            msgs.append({"role": role, "content": [block]})
    return msgs
