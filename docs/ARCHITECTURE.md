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
