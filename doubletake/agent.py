"""Runs the demo bill-paying agent with every pay_bill call gated by the PreToolUse hook.

If the Codex CLI is installed it is used (`codex exec` in demo/). Otherwise a built-in agent loop runs on the OpenAI
Responses API with a `pay_bill` function tool. Before each pay_bill call executes, the same hook the Codex config
uses (`failproof/double_take_gate.py`) is run as a subprocess with the PreToolUse event on stdin, and a deny is honoured.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

from . import config

DEMO = config.ROOT / "demo"
HOOK = config.ROOT / "failproof" / "double_take_gate.py"
AGENT_MODEL = os.getenv("DEMO_AGENT_MODEL", "gpt-6-luna")

PAY_TOOL = {
    "type": "function", "name": "pay_bill", "strict": True,
    "description": "Pay one bill from the inbox. A safety gate may block the call.",
    "parameters": {"type": "object", "additionalProperties": False,
                   "required": ["bill_id", "payee", "amount", "message_sender", "message_text"],
                   "properties": {"bill_id": {"type": "string"}, "payee": {"type": "string"}, "amount": {"type": "number"},
                                  "message_sender": {"type": ["string", "null"]}, "message_text": {"type": ["string", "null"]}}},
}


def run_hook(tool_input: dict, server_url: str) -> dict:
    ev = {"hook_event_name": "PreToolUse", "tool_name": "pay_bill", "tool_input": tool_input, "agent": "codex-demo"}
    out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev), capture_output=True, text=True, timeout=90,
                         env={**os.environ, "DOUBLE_TAKE_URL": server_url})
    return json.loads(out.stdout)["hookSpecificOutput"]


def pay(args: dict) -> str:
    cmd = [sys.executable, str(DEMO / "pay_bill.py"), "--bill", args["bill_id"], "--payee", args["payee"],
           "--amount", str(args["amount"])]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()


async def run_builtin(server_url: str) -> dict:
    instructions = (DEMO / "AGENTS.md").read_text()
    inbox = (DEMO / "inbox.json").read_text()
    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
    url = config.OPENAI_API_BASE.rstrip("/") + "/responses"
    body = {"model": AGENT_MODEL, "instructions": instructions + "\nUse the pay_bill tool instead of the shell command.",
            "input": [{"role": "user", "content": f"inbox.json:\n{inbox}\n\nStart now."}], "tools": [PAY_TOOL]}
    calls = []
    async with httpx.AsyncClient(timeout=120) as c:
        for _ in range(20):
            r = await c.post(url, json=body, headers=headers)
            r.raise_for_status()
            data = r.json()
            fcs = [o for o in data["output"] if o["type"] == "function_call"]
            if not fcs:
                text = "".join(ct.get("text", "") for o in data["output"] if o["type"] == "message" for ct in o.get("content", []))
                return {"runner": f"built-in agent loop ({AGENT_MODEL}); Codex CLI not installed", "agent": "Agent", "final": text, "calls": calls}
            body["input"] = body["input"] + data["output"]
            for fc in fcs:
                args = json.loads(fc["arguments"])
                args = {k: v for k, v in args.items() if v is not None}
                verdict = await asyncio.to_thread(run_hook, args, server_url)
                if verdict["permissionDecision"] == "allow":
                    result = await asyncio.to_thread(pay, args)
                else:
                    result = f"BLOCKED by PreToolUse hook: {verdict['permissionDecisionReason']}"
                calls.append({"args": args, "decision": verdict["permissionDecision"], "result": result})
                body["input"].append({"type": "function_call_output", "call_id": fc["call_id"], "output": result})
    return {"runner": f"built-in agent loop ({AGENT_MODEL})", "agent": "Agent", "final": "Stopped after 20 turns.", "calls": calls}


async def run_codex(server_url: str) -> dict:
    proc = await asyncio.create_subprocess_exec("codex", "exec", "Follow AGENTS.md.", cwd=str(DEMO),
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                                env={**os.environ, "DOUBLE_TAKE_URL": server_url})
    out, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
    text = out.decode(errors="replace").strip()
    return {"runner": "codex exec", "agent": "Codex agent", "final": text[-2000:], "calls": []}


async def run(server_url: str = "http://localhost:8765") -> dict:
    (DEMO / "ledger.jsonl").unlink(missing_ok=True)
    if shutil.which("codex") and os.getenv("DEMO_USE_CODEX", "1") == "1":
        return await run_codex(server_url)
    return await run_builtin(server_url)
