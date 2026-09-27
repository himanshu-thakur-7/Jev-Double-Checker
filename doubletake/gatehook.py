"""PreToolUse hook logic shared by the command hook (Codex / Claude Code) and the built-in agent runner.

A pay_bill call reaches us either as a Bash command (`python demo/pay_bill.py --bill S01 --amount 1240 ...`)
or as a direct tool call named pay_bill with JSON input. Either way it is sent to POST /api/gate, and the
decision comes back in the hook output shape both harnesses accept.
"""
from __future__ import annotations

import json
import os
import shlex

import httpx

GATE_URL = os.getenv("DOUBLE_TAKE_URL", "http://localhost:8765").rstrip("/") + "/api/gate"


def parse_pay_bill(tool_name: str, tool_input: dict) -> dict | None:
    """Return pay_bill arguments, or None when the call is not a payment."""
    if "pay_bill" in (tool_name or "").lower():
        return dict(tool_input)
    cmd = (tool_input or {}).get("command")
    if isinstance(cmd, list):
        cmd = " ".join(cmd)
    if not cmd or "pay_bill" not in cmd:
        return None
    try:
        toks = shlex.split(cmd)
    except ValueError:
        return {"unparseable": cmd}
    args: dict = {}
    keys = {"--bill": "bill_id", "--payee": "payee", "--amount": "amount", "--sender": "message_sender", "--text": "message_text"}
    for i, t in enumerate(toks):
        k, _, v = t.partition("=")
        if k in keys:
            val = v or (toks[i + 1] if i + 1 < len(toks) else "")
            args[keys[k]] = float(val) if keys[k] == "amount" and val else val
    return args


def decide(tool_name: str, tool_input: dict, agent: str = "codex", client: httpx.Client | None = None) -> dict | None:
    """None = not our business (let it through). Otherwise {'decision': 'allow'|'deny', 'reason': ...}."""
    args = parse_pay_bill(tool_name, tool_input)
    if args is None:
        return None
    if "unparseable" in args:
        return {"decision": "deny", "reason": "Could not read the pay_bill arguments. Do not retry."}
    try:
        c = client or httpx.Client(timeout=60)
        r = c.post(GATE_URL, json={"tool_name": "pay_bill", "tool_input": args, "agent": agent})
        r.raise_for_status()
        return r.json()
    except Exception as e:  # fail closed: no verdict, no payment
        return {"decision": "deny", "reason": f"Double Take gate unreachable ({type(e).__name__}); payment blocked. Do not retry."}


def hook_output(verdict: dict | None) -> dict:
    if verdict is None or verdict["decision"] == "allow":
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                       "permissionDecisionReason": (verdict or {}).get("reason", "Not a payment.")}}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": verdict["reason"]}}


def run_hook(stdin_text: str) -> str:
    ev = json.loads(stdin_text or "{}")
    return json.dumps(hook_output(decide(ev.get("tool_name", ""), ev.get("tool_input") or {}, agent=ev.get("agent", "codex"))))
