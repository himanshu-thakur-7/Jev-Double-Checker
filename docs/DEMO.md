# Double Take: 3-minute buildathon demo

**One line:** an agent that pays an elderly parent's bills from SMS, where a Jev verdict on every `pay_bill` call, enforced by Failproof,
catches the scams Jev alone would pay and steers the agent to ask the son instead.

## Before you go on (5 min)

```bash
cd <repo> && .venv/bin/uvicorn server.app:app --port 8765     # leave running
curl -s -X DELETE localhost:8765/api/gate/log                   # clean Failproof log
open http://localhost:8765  &&  open http://localhost:8765/eval
```
- Stage in **Double Take** mode, playback reset (Replay then Pause). Browser zoom so the whole stage fits.
- If Failproof is wired into Codex (`failproofai config`, then `failproofai policies -i -c ./failproof/pack/double-take-pack.mjs`), start the server with
  `DEMO_CODEX=failproof` so the button runs **real Codex under Failproof**. Otherwise the button runs the built-in agent through the same hook (it says which).
- Offline fallback: everything on the stage and eval page replays from the committed cache with no network. Only "Send", the agent button and live evals need keys.

## Script

**0:00 Stakes (20 s).** "Appa is 72. His phone gets 30 texts a day; some are bills, some are scams that copy the real bill down to his account number.
An agent that pays bills can empty a pension. That's the agent you'd be nervous to ship."

**0:20 Why confidence isn't enough (40 s).** Press **1** (Jev only), then **H**. The hero is H6: a real Airtel bill with a lookalike "faster" link.
"Jev says *pay* with confidence 0.75, and a threshold on confidence would pay it." Press **3** (Double Take). "We ask Jev the same decision
**36 ways**: 4 rewrites × 9 wordings. 4 of 35 re-asks disagree, brittleness 0.33, over our 0.20 bar. Plus a deterministic flag: the domain uses Airtel's name
but isn't Airtel's. Held; Rahul gets this alert." Point at the alert card. "36 Jev answers cost $0.00035."

**1:00 The save, live (60 s).** Click **Run Codex under Failproof**, then the **Failproof log** tab. The agent works through Appa's inbox; every `pay_bill`
hits the Failproof policy `double-take-gate` on PreToolUse, which asks Double Take.
- ALLOW lines: BESCOM, BWSSB, Airtel, LIC, Tata Play, ACT (genuine bills on file).
- **DENY → STEERED**: S01, H6, H7, S07. The deny tells the agent what to do instead: `ask_rahul.py --bill H6 --reason …`. The next line is the agent doing exactly that.
- Read the agent's final message: paid 6, blocked 4, escalated 4, no retries.
"H6 and H7 are the save: Jev alone pays both, every time. The verdict changed what the agent did."

**2:00 Reliability (40 s).** Open **/eval**. Scroll to "The agent, judged by Jev".
- **5 of 5 full runs passed: 0 scams paid, 20 of 20 scam attempts caught and steered, 100% of genuine bills paid.**
- Jev also judges the agent: every action (wrong payee? followed the verdict? money at risk?) and every run (paid a scam? retried? escalated all?),
  checked against code ground truth: **96% agreement**.
- Re-asked live 3× with no cache: every mode's decision identical each time; Jev-only pays H6/H7 each time, Double Take holds them each time.
- Up top: on 328 messages, Jev alone pays 15 of 152 scams; Double Take pays 0 and holds 0 of 96 real bills, **without the LLM, at 1/8 the cost** of Jev + gpt-6-sol.

**2:40 Close (20 s).** "Jev is cheap enough to ask 36 times. Disagreement is the signal confidence can't see. Failproof turns it into a deny that steers.
Everything you saw is from real API runs, and the repo shows the misses too."

## Numbers (all real runs)

| | |
|---|---|
| Eval set | 328 messages: 96 bills, 152 scams, 80 no-action (`data/runs/eval-1790492806.json`) |
| Jev only | 15/152 scams paid, $0.00009/msg |
| Double Take, no LLM | 0/152 scams paid, 0/96 bills held, $0.00035/msg |
| Jev + gpt-6-sol | 0/152, 0/96, $0.0027/msg |
| Review ranking | DT risk catches 12/14/15 of Jev's 15 errors at 5/10/20% review vs 8/12/12 for low confidence |
| Agent reliability | 5/5 runs passed, 20/20 saves, 0 scams paid (`data/runs/reliability-1790495782.json`) |
| Jev evals of the agent | 96% agreement with code ground truth, $0.0012 per run (15 Jev calls) |

## Honest limits (say them if asked)
- No shared *confident* errors: gpt-6-sol catches every scam Jev pays on this set. Double Take's edge is safety without the LLM, at 1/8 the cost, plus better review ranking.
- Jev is non-deterministic across calls; the gate replays cached examinations for known bills; live re-asks showed the same decisions 3/3.
- The payment rail is fake (`demo/pay_bill.py`). No real money moves.
