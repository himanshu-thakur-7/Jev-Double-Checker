# Architecture

```
message ──► perturb.py (R0..R3) ──► jev.py  (4 calls × 9 questions = 36 answers)
        │                                 │
        ├──► signals.py (deterministic flags: threat, unknown link, unregistered sender, injection, amount)
        ├──► llm.py (gpt-6-sol second opinion, used in "Jev + LLM" and shown in Double Take)
        ▼
     engine.py ──► Decision {mode, action: pay|hold|ignore, brittleness, grid, flags, reasons, cost}
        │
        ├──► cache.py (data/cache: precomputed for instant replay)
        ├──► server/app.py (FastAPI: /api/messages, /api/examine, /api/gate, /api/ledger, /api/runs)
        │       └──► web/stage.html, web/eval.html
        ├──► eval/run_eval.py ──► data/runs/eval-<ts>.json
        └──► failproof/ policy "double-take-gate" (PreToolUse on pay_bill ─► POST /api/gate)
```

## Modes
- **Jev only**: one Jev question (R0, wording 0). Pay if the action is `pay`.
- **Jev + LLM**: Jev base answer. If it says pay, gpt-6-sol must also say legitimate/pay.
- **Double Take**: all 36 answers + flags. Hold if brittleness > τ (0.20), any scam re-ask ≥ 0.70, or a hard flag fires.

## Brittleness
For the 35 re-asks (all but the base): for action questions, the probability mass on actions other than the base
action; for scam/genuine nouls, the probability that contradicts paying. Brittleness is the mean of these.
"k of 35 disagree" counts re-asks whose argmax contradicts the base.

## Review risk (for ranking messages a human should look at)
`engine.review_risk(ex)`: instability of Jev's base action across the 19 action re-asks. When the base is "pay", it is raised by brittleness,
the highest scam re-ask and hard flags (plus 0.02 per soft flag). A message Jev already holds with stable answers scores low, because it goes to Rahul anyway.

## Double Take without the LLM
Computed in the eval from the same answers (`double_take_jev`): hold a Jev "pay" if brittleness > τ, any scam re-ask ≥ 0.70, or a hard flag fires.
On the 328-message run it matched Jev + LLM (0 scams paid, 0 bills held) at $0.00035 per message.

## Gate
`POST /api/gate` ← `failproof/double_take_gate.py` (Codex / Claude Code command hook) or `.failproofai/policies/double-take-gate.mjs`.
Allow only when Double Take would pay and the amount matches the bill. Everything fails closed.
