"""The cross-examination engine.

For one message it asks Jev 36 questions (4 rewrites × 9 questions, one Jev call per rewrite, in parallel),
asks the second-opinion LLM once, runs the deterministic flags, and decides for all three modes at once:

  jev_only     the base answer (R0, first wording) alone decides
  jev_llm      a payment also needs the LLM to say legitimate + pay
  double_take  a payment also needs the 35 re-asks to hold together (brittleness ≤ τ), no re-ask putting
               scam risk ≥ SCAM_MAX, no hard flag, and the LLM not objecting
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .data import Message, Registry, registry as default_registry
from .jev import JevClient, choice, noul
from .llm import LLMClient, SecondOpinion
from .perturb import NAMES, REWRITES, all_rewrites
from .signals import Flag, detect, has_hard

TAU = 0.20        # hold when brittleness is above this
SCAM_MAX = 0.70   # hold when any re-ask puts scam risk at or above this
MODES = ("jev_only", "jev_llm", "double_take")

ACTION_CRITERIA = {
    "pay": "Pay the bill now: a genuine bill from a biller on file, sent through its official channel",
    "hold": "Hold the payment and ask Rahul first: something is off, unusual or unverifiable",
    "ignore": "No payment needed: not a bill, already paid, on AutoPay, or just information",
}
ACTION_WORDINGS = [
    "What should Appa's bill-paying assistant do with this SMS?",
    "Should the assistant pay this now, hold it for Rahul to check, or take no action?",
    "Decide the payment action for the SMS in `sms`, using the billers in `household`.",
    "If you were managing Appa's household bills, what would you do with this message?",
    "Is it safe to pay the amount requested in this SMS right away?",
]
SCAM_WORDINGS = [
    ("Is this SMS a scam or phishing attempt?", "It is a scam or phishing", "It is a genuine message"),
    ("Is someone trying to trick Appa into sending money to the wrong party?", "Yes, it is a trick", "No trick"),
]
GENUINE_WORDINGS = [
    ("Is this a genuine message from a biller in `household`, sent through its official channel?",
     "Genuine, from a biller on file", "Not genuine or not from a biller on file"),
    ("Did this message really come from the organisation it claims to be from?", "Yes, really from them", "No"),
]
QIDS = [f"a{i}" for i in range(5)] + ["s0", "s1", "g0", "g1"]


def questions() -> dict[str, dict]:
    q = {f"a{i}": choice(w, ACTION_CRITERIA) for i, w in enumerate(ACTION_WORDINGS)}
    for i, (w, t, f) in enumerate(SCAM_WORDINGS):
        q[f"s{i}"] = noul(w, true=t, false=f)
    for i, (w, t, f) in enumerate(GENUINE_WORDINGS):
        q[f"g{i}"] = noul(w, true=t, false=f)
    return q


@dataclass
class Cell:
    rewrite: str
    qid: str
    kind: str          # action | scam | genuine
    value: str         # pay/hold/ignore for action; "legit"/"scam" for nouls
    p: float           # probability of `value` (action) or P(yes) (noul)
    p_pay: float       # action: P(pay); nouls: probability the answer supports paying
    confidence: float | None = None
    base: bool = False

    @property
    def disagrees_with_paying(self) -> bool:
        return self.value != "pay" if self.kind == "action" else self.value == "scam"


@dataclass
class ModeDecision:
    action: str        # pay | hold | ignore
    reason: str


@dataclass
class Examination:
    message: dict
    rewrites: dict[str, str]
    grid: list[list[dict]]
    base: dict
    flags: list[dict]
    biller: str | None
    second_opinion: dict | None
    brittleness: float
    disagree: int
    reasks: int
    max_scam: float
    risk: float
    decisions: dict[str, dict]
    alert: dict | None
    cost: dict
    model: str
    tau: float = TAU
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _cells(rewrite: str, answers: dict[str, dict]) -> list[Cell]:
    out = []
    for qid in QIDS:
        a = answers[qid]
        if qid.startswith("a"):
            probs = a["probabilities"]
            out.append(Cell(rewrite, qid, "action", a["choice"], float(probs[a["choice"]]),
                            float(probs.get("pay", 0.0)), float(a.get("confidence", 0.0))))
        else:
            p = float(a["noul"])
            if qid.startswith("s"):
                out.append(Cell(rewrite, qid, "scam", "scam" if p >= 0.5 else "legit", p, 1 - p))
            else:
                out.append(Cell(rewrite, qid, "genuine", "legit" if p >= 0.5 else "scam", p, p))
    return out


def score(cells: list[Cell]) -> tuple[float, int, int, float]:
    """Brittleness against paying over the re-asks (every cell but the base)."""
    reasks = [c for c in cells if not c.base]
    brittleness = sum(1 - c.p_pay for c in reasks) / len(reasks)
    disagree = sum(c.disagrees_with_paying for c in reasks)
    max_scam = max((c.p for c in cells if c.kind == "scam"), default=0.0)
    return round(brittleness, 3), disagree, len(reasks), round(max_scam, 3)


def _rs(x: float | None) -> str:
    return f"₹{x:,.0f}" if x else ""


def decide(msg: Message, cells: list[Cell], flags: list[Flag], op: SecondOpinion | None,
           amount: float | None) -> tuple[dict[str, ModeDecision], float, int, int, float]:
    base = next(c for c in cells if c.base)
    brit, disagree, n, max_scam = score(cells)
    hard = [f for f in flags if f.severity == "hard"]
    amt = _rs(amount)
    pay_txt = f"Paid {amt}." if amt else "Paid."

    d: dict[str, ModeDecision] = {}
    if base.value == "pay":
        d["jev_only"] = ModeDecision("pay", f"{pay_txt} Jev said pay with confidence {base.confidence:.2f}, so the assistant paid.")
    else:
        d["jev_only"] = ModeDecision(base.value, f"Jev said {base.value} with confidence {base.confidence:.2f}.")

    if base.value != "pay":
        d["jev_llm"] = ModeDecision(base.value, d["jev_only"].reason)
    elif op is None:
        d["jev_llm"] = ModeDecision("hold", "Held. The second opinion was unavailable, so the payment waits for Rahul.")
    elif op.agrees_pay:
        d["jev_llm"] = ModeDecision("pay", f"{pay_txt} Jev said pay ({base.confidence:.2f}) and the second opinion agreed: “{op.reason}”")
    else:
        d["jev_llm"] = ModeDecision("hold", f"Held. Jev said pay but the second opinion said {op.verdict}: “{op.reason}”")

    if base.value != "pay":
        why = f"Jev's base answer was {base.value} ({base.confidence:.2f})."
        if base.value == "hold":
            why += f" {disagree} of {n} re-asks disagreed with paying."
        d["double_take"] = ModeDecision(base.value, ("Held. " if base.value == "hold" else "No action. ") + why)
    else:
        reasons = []
        if brit > TAU:
            reasons.append(f"{disagree} of {n} re-asks disagreed with paying (brittleness {brit:.2f}).")
        if max_scam >= SCAM_MAX:
            reasons.append(f"At least one re-ask put scam risk at {max_scam:.0%}.")
        for f in hard:
            reasons.append(f"{f.label} ({f.evidence}).")
        if op is not None and not op.agrees_pay:
            reasons.append(f"The second opinion said {op.verdict}.")
        if reasons:
            tail = ""
            if op is not None and op.agrees_pay:
                tail = " Jev and the second opinion both said pay, so confidence alone would have paid this."
            elif op is not None:
                tail = ""
            d["double_take"] = ModeDecision("hold", "Held. " + " ".join(reasons) + tail)
        else:
            d["double_take"] = ModeDecision("pay", f"{pay_txt} All {n + 1} answers held together (brittleness {brit:.2f}, "
                                                   f"hold above {TAU:.2f}) and no red flags fired.")
    return d, brit, disagree, n, max_scam


def risk_score(brittleness: float, max_scam: float, flags: list[Flag]) -> float:
    """Ranking score used to pick which messages a human reviews first."""
    hard = 1.0 if has_hard(flags) else 0.0
    soft = sum(f.severity == "soft" for f in flags)
    return round(max(brittleness, max_scam, hard) + 0.02 * soft, 4)


def alert_card(msg: Message, flags: list[Flag], biller_name: str | None, disagree: int, n: int) -> dict:
    kinds = {f.kind for f in flags}
    bits = []
    if "unregistered_sender" in kinds or "unknown_number" in kinds:
        bits.append("an unregistered sender")
    if kinds & {"lookalike_link", "unknown_link"}:
        bits.append("a different website")
    if "payee_change" in kinds:
        bits.append("a request to pay a new account")
    if "injection" in kinds:
        bits.append("text telling the assistant it is pre-approved")
    if "amount" in kinds:
        bits.append("an unusual amount")
    who = f"This looks like {biller_name}" if biller_name else "This payment request"
    why = f"{who} but came from {' and '.join(bits)}." if bits else f"{who} could not be confirmed."
    why += f" The answers disagreed on {disagree} of {n} re-asks."
    return {"title": "Held for Rahul", "who": f"Appa’s Assistant paused a payment{', ' + msg.time if msg.time else ''}",
            "why": why, "actions": ["Block and report", "It’s genuine, pay"]}


class Engine:
    def __init__(self, jev: JevClient | None = None, llm: LLMClient | None = None, reg: Registry | None = None,
                 use_llm: bool = True):
        self.jev = jev or JevClient()
        self.llm = llm or (LLMClient() if use_llm else None)
        self.reg = reg or default_registry()

    async def aclose(self):
        await self.jev.aclose()
        if self.llm:
            await self.llm.aclose()

    async def examine(self, msg: Message) -> Examination:
        rewrites = all_rewrites(msg.text)
        ctx = self.reg.context()
        qs = questions()
        flags, biller = detect(msg.sender, msg.text, self.reg)
        errors: list[str] = []

        async def jev_call(r: str):
            return await self.jev.ask({"sms": {"sender": msg.sender, "text": rewrites[r]}, "household": ctx}, qs)

        async def llm_call():
            if not self.llm:
                return None
            try:
                return await self.llm.review(msg.sender, msg.text, ctx)
            except Exception as e:  # the LLM is optional evidence; never block on it
                errors.append(f"second opinion failed: {e}")
                return None

        t0 = time.perf_counter()
        jev_task = asyncio.gather(*(jev_call(r) for r in REWRITES))
        results, op = await asyncio.gather(jev_task, llm_call())
        jev_ms = max(r.latency_ms for r in results)

        cells: list[Cell] = []
        for r, res in zip(REWRITES, results):
            cells.extend(_cells(r, res.answers))
        cells[0].base = True  # R0, first action wording

        amount = msg.amount
        if amount is None:
            from .signals import amounts
            a = amounts(msg.text)
            amount = a[0] if a else None
        decisions, brit, disagree, n, max_scam = decide(msg, cells, flags, op, amount)
        base = cells[0]
        grid = [[{**asdict(c), "name": NAMES[r]} for c in cells if c.rewrite == r] for r in REWRITES]
        alert = alert_card(msg, flags, biller.name if biller else None, disagree, n) \
            if decisions["double_take"].action == "hold" else None
        jev_cost = sum(r.cost_usd for r in results)
        return Examination(
            message=msg.model_dump(), rewrites=rewrites, grid=grid,
            base={"action": base.value, "confidence": base.confidence, "p": base.p},
            flags=[f.to_dict() for f in flags], biller=biller.id if biller else None,
            second_opinion=None if op is None else {
                "verdict": op.verdict, "action": op.action, "scam_probability": op.scam_probability,
                "reason": op.reason, "agrees_pay": op.agrees_pay, "model": op.model},
            brittleness=brit, disagree=disagree, reasks=n, max_scam=max_scam,
            risk=risk_score(brit, max_scam, flags),
            decisions={k: asdict(v) for k, v in decisions.items()}, alert=alert,
            cost={"jev_usd": jev_cost, "jev_calls": len(results), "jev_ms": round(jev_ms),
                  "jev_only_usd": jev_cost / len(results),  # one call carries the state; that dominates tokens
                  "jev_tokens": sum(r.input_tokens for r in results),
                  "llm_usd": op.cost_usd if op else 0.0, "llm_ms": round(op.latency_ms) if op else 0,
                  "wall_ms": round((time.perf_counter() - t0) * 1000)},
            model=results[0].model, errors=errors)
