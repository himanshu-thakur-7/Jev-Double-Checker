# Double Take: Jev Double-Checker

> *Pucho phir se* (ask again) before any money moves.

An assistant pays household bills from the SMS on Appa's phone. **Double Take** asks TypeSafe's **Jev** decision model the
same question **36 ways** (4 rewrites of the message × 9 differently worded questions), runs deterministic red-flag checks,
and asks **gpt-6-sol** for a second opinion. When the answers don't hold together, the payment is **held for Rahul** (the son)
instead of paid. The same check is exposed as a **Failproof** PreToolUse gate, so any agent (for example Codex) must ask before it calls `pay_bill`.

Spec mockups: [`docs/mockups/stage.html`](docs/mockups/stage.html), [`docs/mockups/eval.html`](docs/mockups/eval.html)

## For the Jev buildathon judges

- **Stakes:** an agent that pays an elderly parent's bills from SMS. A wrong `pay_bill` sends his pension to a scammer.
- **The save:** every `pay_bill` passes the Failproof policy `double-take-gate` (PreToolUse), which asks Jev 36 ways. H6 and H7 are scams **Jev alone pays**.
  The verdict denies them and the deny message steers the agent to `ask_rahul` instead, which it does.
- **Reliability:** 5/5 full agent runs passed: 0 scams paid, 20/20 scam attempts caught and steered, 100% of genuine bills paid. Live re-asks gave identical decisions 3/3.
- **Jev evals:** Jev scores every agent action and run (wrong payee, followed verdict, money at risk, paid a scam, retried, escalated), with 96% agreement with ground truth.
- Demo script: [docs/DEMO.md](docs/DEMO.md) · Failproof pack with native Jev checks: [failproof/pack](failproof/pack/README.md)

## Results (real run `eval-1790492806`, 328 messages)

| Mode | Scams paid | Real bills held | Cost / message |
|---|---|---|---|
| Jev only | **15 of 152** | 0 of 96 | $0.00009 |
| Jev + LLM (gpt-6-sol) | 0 of 152 | 0 of 96 | $0.0027 |
| Double Take | 0 of 152 | 0 of 96 | $0.0030 |
| **Double Take, no LLM** | **0 of 152** | **0 of 96** | **$0.00035** |

- Double Take's Jev-only cross-examination matches Jev + LLM safety at **about 1/8 the cost**.
- Ranking messages for human review by Double Take risk catches **12 / 14 / 15** of Jev's 15 errors at 5 / 10 / 20% review.
  Ranking by low confidence catches 8 / 12 / 12. The one *confident* Jev error (conf 0.86) is in DT's top 5% and outside low-confidence's top 20%.
- Honest caveats: there were **no shared confident errors** (gpt-6-sol caught every scam Jev paid). Jev's errors come from red-team variants
  and heroes; on the gold 24 and 250 synthetic messages every mode was perfect. Jev is not deterministic between calls.
  See [HANDOFF.md](HANDOFF.md) for the full story.

## Quick start

```bash
cp .env.example .env          # add TYPESAFE_API_KEY and OPENAI_API_KEY (optional for cached replay)
uv venv .venv && uv pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/uvicorn server.app:app --port 8765
```

Open http://localhost:8765 (the stage) and http://localhost:8765/eval (the evaluation). Without API keys, everything replays
from the committed cache. Only "Send and cross-examine", the demo agent and a fresh eval need the keys.

**Stage keys:** Space play/pause · 1, 2, 3 switch mode (Jev only, Jev + LLM, Double Take) · H opens the hero scam (the most confident
scam that Jev alone paid and Double Take held, chosen from the real cached run).

## How it works

```
SMS ─► perturb.py  R0 Original · R1 Noisy text · R2 Reshuffled · R3 Plain text   (deterministic; amounts, links, ids protected)
    ─► jev.py      4 parallel calls × 9 questions: 5 × "what should it do?" (pay/hold/ignore), 2 × scam?, 2 × genuine?
    ─► signals.py  lookalike links, unregistered senders, payee change, prompt injection, unusual amount, pay-again …
    ─► llm.py      gpt-6-sol verdict (strict JSON)
    ─► engine.py   decisions for all 3 modes + brittleness, grid, reasons, alert, cost, review risk
```

- **Brittleness** is the mean, over the 35 re-asks, of how much each one leans against paying. Double Take holds a Jev "pay" when brittleness > **0.20**,
  any re-ask puts scam risk ≥ 0.70, a hard flag fires, or the second opinion objects.
- Jev sees the SMS plus trusted household context (billers on file, official senders and websites, usual amounts): `data/billers.json`.

## Repository map

| Path | What |
|---|---|
| `doubletake/` | `jev.py` TypeSafe client · `llm.py` second opinion · `perturb.py` rewrites · `signals.py` red flags · `engine.py` cross-examination · `cache.py` · `data.py` · `redteam.py` · `gatehook.py` · `agent.py` |
| `server/app.py` | FastAPI: `/api/messages`, `/api/examine`, `/api/ledger`, `/api/gate` (+ log, SSE), `/api/agent/run`, `/api/runs/latest` |
| `web/` | `stage.html/.css/.js` live demo stage · `eval.html` evaluation page |
| `eval/` | `build_dataset.py` (328 messages) · `run_eval.py` → `data/runs/eval-<ts>.json` |
| `.failproofai/policies/double-take-gate.mjs` | Failproof AI policy |
| `failproof/double_take_gate.py` | the same gate as a Codex / Claude Code PreToolUse command hook (fails closed) |
| `demo/` | the bill-paying agent demo (inbox, fake `pay_bill.py`, Codex setup in `demo/README.md`) |
| `data/` | messages, biller registry, cached examinations, eval runs, live hunt logs |
| `scripts/` | `precompute.py`, `live_engine.py`, `hero_hunt.py`, smoke tests, `board.py` (kanban mirror) |

## Re-running things

```bash
.venv/bin/python scripts/precompute.py --refresh    # re-examine the 30 stage messages (≈ $0.10)
.venv/bin/python eval/build_dataset.py              # rebuild data/messages/eval.jsonl (seeded)
.venv/bin/python eval/run_eval.py --refresh         # full eval (≈ $1, ~3.5 min)
```

## Live enforcement (Failproof / Codex)

Press **Run Codex under Failproof** on the stage. If the `codex` CLI is installed, the server runs `codex exec` in `demo/`. Otherwise it runs a
built-in gpt-6-luna agent loop. Every `pay_bill` call goes through `failproof/double_take_gate.py` → `POST /api/gate`. In the last live run the agent
paid the 6 genuine bills, and the gate denied S01 and S07 ("… Held for Rahul to review. Do not retry."). Wiring for Codex and Failproof AI: [`demo/README.md`](demo/README.md).

## Working on this repo

Agents: read [HANDOFF.md](HANDOFF.md) first. The board is mirrored in [`docs/BOARD.md`](docs/BOARD.md); restore it with `python scripts/board.py import`.
Never commit `.env`.
