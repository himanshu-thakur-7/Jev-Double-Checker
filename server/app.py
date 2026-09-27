"""Double Take API server.

  GET  /api/messages            stage messages with a summary of each cached examination
  GET  /api/examine/{id}        full examination for a stage (or custom) message
  POST /api/examine             cross-examine a new message {sender, text}
  GET  /api/ledger              paid / scams paid / held / costs for every mode over the stage set
  POST /api/gate                Failproof gate: may this pay_bill tool call proceed?
  GET  /api/gate/log            gate decisions so far;  GET /api/gate/stream  as server-sent events
  GET  /api/runs/latest         newest eval run from data/runs
  /  and  /eval                 the stage and the evaluation pages
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from doubletake import cache, config
from doubletake.data import Message, stage_messages
from doubletake.engine import MODES, Engine

WEB = config.ROOT / "web"
GATE_LOG = config.DATA / "gate_log.jsonl"


class State:
    engine: Engine | None = None
    custom: dict[str, Message] = {}
    gate_log: list[dict] = []
    listeners: list[asyncio.Queue] = []
    agent_busy: bool = False


S = State()


def engine() -> Engine:
    if S.engine is None:
        if not (config.TYPESAFE_API_KEY and config.OPENAI_API_KEY):
            raise HTTPException(503, "Live cross-examination needs TYPESAFE_API_KEY and OPENAI_API_KEY; cached replay still works.")
        S.engine = Engine()
    return S.engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    if GATE_LOG.exists():
        S.gate_log = [json.loads(l) for l in GATE_LOG.read_text().splitlines() if l.strip()]
    yield
    if S.engine:
        await S.engine.aclose()


app = FastAPI(title="Double Take", lifespan=lifespan)


def find(msg_id: str) -> Message | None:
    return next((m for m in stage_messages() if m.id == msg_id), None) or S.custom.get(msg_id)


def summary(m: Message, ex: dict | None) -> dict:
    s = m.model_dump()
    if ex:
        s |= {"decisions": {k: v["action"] for k, v in ex["decisions"].items()},
              "base": ex["base"], "brittleness": ex["brittleness"], "risk": ex["risk"],
              "llm_verdict": (ex.get("second_opinion") or {}).get("verdict"), "cached": True}
    else:
        s |= {"cached": False}
    return s


@app.get("/api/messages")
def messages():
    msgs = stage_messages()
    return {"count": len(msgs), "cached": sum(cache.get(m) is not None for m in msgs),
            "messages": [summary(m, cache.get(m)) for m in msgs] + [summary(m, cache.get(m)) for m in S.custom.values()]}


@app.get("/api/examine/{msg_id}")
async def get_examination(msg_id: str, refresh: bool = False):
    m = find(msg_id)
    if not m:
        raise HTTPException(404, f"unknown message {msg_id}")
    if not refresh and (hit := cache.get(m)):
        return hit | {"from_cache": True}
    ex, hit = await cache.examine_cached(engine(), m, refresh=refresh)
    return ex | {"from_cache": hit}


class NewMessage(BaseModel):
    sender: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=2000)
    time: str | None = None


@app.post("/api/examine")
async def examine(body: NewMessage):
    mid = "C-" + hashlib.sha256(f"{body.sender}|{body.text}".encode()).hexdigest()[:8]
    m = Message(id=mid, set="custom", sender=body.sender.strip(), text=body.text.strip(),
                time=body.time or time.strftime("%-I:%M %p"))
    S.custom[mid] = m
    ex, hit = await cache.examine_cached(engine(), m)
    return ex | {"from_cache": hit}


def ledger_for(mode: str, items: list[tuple[Message, dict]]) -> dict:
    paid = scams = 0.0
    n_scams = held = 0
    jev = llm = 0.0
    rows = []
    for m, ex in items:
        action = ex["decisions"][mode]["action"]
        amount = m.amount or 0
        if action == "pay":
            paid += amount
            if m.label == "scam":
                n_scams += 1
                scams += amount
        elif action == "hold":
            held += 1
        c = ex["cost"]
        jev += c["jev_only_usd"] if mode != "double_take" else c["jev_usd"]
        llm += c["llm_usd"] if mode != "jev_only" else 0.0
        rows.append({"id": m.id, "sender": m.sender, "label": m.label, "action": action, "amount": amount})
    return {"paid": paid, "scams_paid": n_scams, "scam_amount": scams, "held": held,
            "jev_usd": jev, "llm_usd": llm, "rows": rows}


@app.get("/api/ledger")
def ledger():
    items = [(m, ex) for m in stage_messages() if (ex := cache.get(m))]
    return {"messages": len(items), "modes": {mode: ledger_for(mode, items) for mode in MODES}}


class GateRequest(BaseModel):
    tool_name: str = "pay_bill"
    tool_input: dict = {}
    agent: str | None = None


def _fmt_rs(x) -> str:
    try:
        return f"₹{float(x):,.0f}"
    except (TypeError, ValueError):
        return ""


@app.post("/api/gate")
async def gate(req: GateRequest):
    ti = req.tool_input
    ref = str(ti.get("bill_id") or ti.get("message_id") or "")
    m = find(ref) if ref else None
    if m is None:
        if not ti.get("message_text"):
            raise HTTPException(422, "tool_input needs bill_id of a known message, or message_sender + message_text")
        m = Message(id=ref or "gate-" + hashlib.sha256(ti["message_text"].encode()).hexdigest()[:8], set="gate",
                    sender=ti.get("message_sender", "unknown"), text=ti["message_text"],
                    amount=ti.get("amount"))
        S.custom[m.id] = m
    ex = cache.get(m)
    if ex is None:
        ex, _ = await cache.examine_cached(engine(), m)
    dt = ex["decisions"]["double_take"]
    amount = ti.get("amount")
    payee = ti.get("payee") or (ex.get("biller") or m.sender)
    if dt["action"] == "pay" and amount is not None and m.amount and abs(float(amount) - m.amount) > 0.5:
        decision, reason = "deny", f"Amount {_fmt_rs(amount)} differs from the bill ({_fmt_rs(m.amount)}). Held for Rahul to review. Do not retry."
    elif dt["action"] == "pay":
        decision, reason = "allow", "Verified bill from a biller on file."
    elif dt["action"] == "ignore":
        decision, reason = "deny", "No payment is needed for this message. Do not retry."
    else:
        why = dt["reason"].removeprefix("Held. ")
        decision, reason = "deny", f"{why} Held for Rahul to review. Do not retry."
    entry = {"ts": time.strftime("%H:%M:%S"), "epoch": time.time(), "tool": req.tool_name, "bill_id": m.id,
             "payee": payee, "amount": amount if amount is not None else m.amount, "decision": decision,
             "reason": reason, "agent": req.agent}
    S.gate_log.append(entry)
    with GATE_LOG.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    for q in list(S.listeners):
        q.put_nowait(entry)
    return {"decision": decision, "reason": reason, "bill_id": m.id}


@app.get("/api/gate/log")
def gate_log():
    return {"entries": S.gate_log}


@app.delete("/api/gate/log")
def clear_gate_log():
    S.gate_log.clear()
    GATE_LOG.unlink(missing_ok=True)
    return {"cleared": True}


@app.get("/api/gate/stream")
async def gate_stream():
    q: asyncio.Queue = asyncio.Queue()
    S.listeners.append(q)

    async def events():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    e = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            S.listeners.remove(q)
    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/api/agent/run")
async def agent_run(request: Request):
    """Run the demo bill-paying agent; its pay_bill calls hit /api/gate through the PreToolUse hook."""
    from doubletake import agent
    if not config.OPENAI_API_KEY:
        raise HTTPException(503, "The demo agent needs OPENAI_API_KEY.")
    if S.agent_busy:
        raise HTTPException(409, "An agent run is already in progress.")
    S.agent_busy = True
    try:
        return await agent.run(str(request.base_url).rstrip("/"))
    finally:
        S.agent_busy = False


@app.get("/api/runs/latest")
def latest_run():
    runs = sorted((config.DATA / "runs").glob("eval-*.json"))
    if not runs:
        raise HTTPException(404, "no eval runs yet; run python eval/run_eval.py")
    return json.loads(runs[-1].read_text()) | {"file": runs[-1].name}


@app.get("/")
def stage_page():
    return FileResponse(WEB / "stage.html")


@app.get("/eval")
def eval_page():
    return FileResponse(WEB / "eval.html")


if WEB.exists():
    app.mount("/web", StaticFiles(directory=WEB), name="web")
