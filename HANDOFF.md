# HANDOFF — read this first

This file is how agents hand work to each other. **Every loop run appends a timestamped entry to the
Run log below** (newest at the bottom): what was done, what was verified, and what comes next.

## How to resume (for any agent)

1. `git pull` on `main`.
2. `cp .env.example .env` and fill in `TYPESAFE_API_KEY` and `OPENAI_API_KEY` (ask the owner; never commit `.env`).
3. `uv venv .venv && uv pip install -e ".[dev]"` then `.venv/bin/pytest -q`.
4. Restore the kanban board: `python scripts/board.py import` (creates `~/.claude/kanban-dbs/jev-double-checker.db`).
   The human-readable board is `docs/BOARD.md`.
5. Pick the lowest-rank card that isn't `done` (see `docs/BOARD.md`), build it, test it, then:
   `python scripts/board.py move <id> done "<notes>"`, add a Run log entry here, commit, and push.

## What we are building

**Double Take** ("Pucho phir se", which means "ask again"). An assistant pays bills from messages on Appa's phone.
Before any money moves, Double Take cross-examines **Jev** (TypeSafe's typed decision model). It asks the same
decision 36 ways: 4 rewrites of the message (Original, Noisy text, Reshuffled, Plain text) × 9 questions
(5 wordings of "what should it do?", 2 "is it a scam?", 2 "is it genuine?"). When the answers are *brittle*
(re-asks disagree with the base answer) or deterministic red flags fire, it holds the payment and asks Rahul (the son).
It is compared against **Jev only** and **Jev + LLM** (gpt-6-sol second opinion). A **Failproof** PreToolUse policy lets
any agent (for example Codex) call `POST /api/gate` before `pay_bill`.

Spec mockups: `docs/mockups/stage.html` (live demo stage; `?view=fail|dt|failproof`) and `docs/mockups/eval.html`.
Architecture: `docs/ARCHITECTURE.md`.

## Key facts learned

- TypeSafe API: `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer $TYPESAFE_API_KEY`,
  body `{model, state, questions:{id:{type: choice|noul|score, instructions, criteria}}}`. Many questions fit in one call
  (answered in parallel). Choice answers carry `probabilities` + `confidence`; noul answers carry the P(yes) value `noul`.
  Pin `jev-1.13.0`. Retry on 429/529. Docs: https://docs.typesafe.ai/api
- Jev's known weakness (TypeSafe's jaggedness page): adversarial text can steer it. This is why deterministic checks sit beside it.
- OpenAI model `gpt-6-sol` is available on the provided key (it's the spec's second opinion).
- Failproof AI: `npm i -g failproofai`, supports custom policies and Codex hooks. Docs: https://docs.befailproof.ai/
- Smoke test 2026-09-27: Jev on the hero scam said `hold` 0.79 (conf 0.68), scam noul 0.85, which took ~1 s.

## Run log

### 2026-09-27 11:42 IST: Run 0 (planning + card #1)
- Read spec mockups (stage/eval), researched the TypeSafe Jev API and Failproof, and smoke-tested both API keys (both work).
- Created kanban board (15 cards, see docs/BOARD.md) and a mirror/restore script `scripts/board.py`.
- Card #1 done: repo scaffold, pyproject, .gitignore (.env excluded), HANDOFF/ARCHITECTURE/README, mockups in docs/mockups.
- **Next:** card #2, the Jev client (`doubletake/jev.py`).

### 2026-09-27 11:46 IST: Run 1 (card #2, Jev client)
- **Done:** `doubletake/config.py` (env/.env settings, pinned `jev-1.13.0`, price $0.042/M input with output free per TypeSafe's rate card)
  and `doubletake/jev.py` (`JevClient.ask(state, questions)`, `choice()`/`noul()` builders, retry with backoff on 429/5xx/529,
  and returns answers + tokens + latency_ms + cost_usd).
- **Verified:** `pytest` 4/4 (respx mocks). Live `scripts/smoke_jev.py` on the hero scam returned hold 0.55, scam 0.93, 1.8 s, $0.000018.
- **Note:** Jev's answers on the same text vary between calls/wordings (hold 0.79 earlier vs 0.55 now). That variance is exactly the brittleness signal.
- **Next:** card #3, the second-opinion LLM client (`doubletake/llm.py`, gpt-6-sol).

### 2026-09-27 11:52 IST: Run 2 (card #3, second-opinion LLM)
- **Done:** `doubletake/llm.py`. `LLMClient.review(sender, text, context)` calls the OpenAI **Responses API** with a strict json_schema
  → `SecondOpinion{verdict: legitimate|scam|not_a_bill, action: pay|hold|ignore, scam_probability, reason, cost_usd, latency_ms}`.
  `agrees_pay` is used by "Jev + LLM" mode. The message is marked untrusted in the prompt. Prices are $2/M in and $10/M out (gpt-6-sol standard), set in config.
- **Verified:** pytest 8/8. Live `scripts/smoke_llm.py`: hero S01 gave **scam, 0.98**, 3.4 s, $0.0016.
- **Important finding:** the mockup's story says the second opinion *agrees to pay* on S01. The real gpt-6-sol catches it. The UI must
  render real results, not the mockup copy. The eval (card #11) is where "shared confident errors" get measured honestly, and the
  red-team rewrites (rt-*) are designed to fool both models.
- **Next:** card #4, the message dataset (`data/messages/*.jsonl`, `data/billers.json`, loader).

### 2026-09-27 11:57 IST: Run 3 (card #4, dataset)
- **Done:** `data/messages/stage.jsonl` has 28 messages: gold 24 (6 real bills G01-G06, 8 scams S01-S08, 10 no-action N01-N10)
  and heroes H2-H5 (spoofed registered header, subdomain trick at 7x the usual amount, payee-change request, and a prompt injection saying "you are verified").
  Texts match the mockup thread (AX-BESCOM, RWA via UPI, ICICI AutoPay, Rahul, VK-BESCMS). Each message has label, expected_action, biller, amount and note.
  `data/billers.json` has 8 billers with registered DLT headers, official domains, account, usual amount range, UPI and autopay.
  `doubletake/data.py` has Pydantic `Message`/`Biller`/`Registry`, `stage_messages()`, `gold_messages()`, `registry()`, and `Registry.context()` (trusted household context for the models).
- **Verified:** pytest 13/13 (counts, unique ids, label↔action consistency, biller refs, S01 header/domain not registered).
- **Design note:** G06 (RWA from a personal number) is a genuine bill a cautious system may hold. That's the expected "1 of 6 real bills held".
- **Next:** card #5, the perturbation rewrites R0-R3 (`doubletake/perturb.py`).

### 2026-09-27 12:00 IST: Run 4 (card #5, perturbations)
- **Done:** `doubletake/perturb.py`: `all_rewrites(text)` returns R0 Original, R1 Noisy text (seeded typos/case/spacing),
  R2 Reshuffled (sentence order permuted, never identity), and R3 Plain text (no shouting, "!", urgency adverbs or salutations; one sentence per line;
  brand acronyms kept via `ACRONYMS`). Any token with a digit, URL/domain, @ (UPI) or sender id is *protected*, so rewrites can't change the payee or amount.
- **Verified:** pytest 46/46. The key test checks that `facts()` of every rewrite ⊇ facts of the original, for all 28 stage messages.
- **Next:** card #6, deterministic risk signals (`doubletake/signals.py`).

### 2026-09-27 12:02 IST: Run 5 (card #6, deterministic signals)
- **Done:** `doubletake/signals.py`: `detect(sender, text) -> (flags, biller)`. Flags: threat within hours, lookalike link (**hard**: brand name
  in a non-official domain), unknown link, unregistered DLT sender (notes the nearest registered header), unknown phone number,
  instructions to the assistant (**hard**), payee change (**hard**), fee-for-refund, unknown UPI ID, amount vs usual (**hard** if >3×), and AutoPay (info).
  The biller is identified by header/phone → account number in text → name.
- **Verified:** pytest 63/63. S01 yields exactly the mockup's 3 flags (threat "disconnection at 9:30 PM tonight", unknown link bescom-bbps.in,
  unregistered sender VK-BESCMS). No real bill G01-G06 has a hard flag, and every scam has ≥1 flag.
- **Honest limitation:** flags alone would over-hold. Non-biller promos (N03-N09) carry a soft "unregistered sender". The engine must only gate
  *payment* decisions, and soft flags should add to risk, not decide it. H2 (spoofed registered header) is caught only by its link.
- **Next:** card #7, the cross-examination engine and 3 modes (`doubletake/engine.py`). This is the core; it needs live Jev runs to tune τ.

### 2026-09-27 12:07 IST: Run 6 (card #7, cross-examination engine)
- **Done:** `doubletake/engine.py`. `Engine().examine(msg) -> Examination`: 4 parallel Jev calls (R0-R3, each with 9 questions: 5 action
  wordings pay/hold/ignore, 2 scam nouls, 2 genuine nouls) plus the gpt-6-sol review in parallel, deterministic flags, and decisions for **all 3 modes**
  in one pass. Brittleness = mean over the 35 re-asks of (1 − support for paying); "k of 35 disagree" = argmax contradictions.
  Double Take holds a Jev "pay" if brittleness > τ=0.20, any scam re-ask ≥ 0.70, a hard flag fires, or the LLM objects. Output includes the
  36-cell grid, reasons text (mockup phrasing), alert card, cost (Jev USD/ms/tokens, LLM USD/ms), and risk score for eval ranking.
  Jev's state is `{"sms": {sender, text}, "household": Registry.context()}`.
- **Verified:** pytest 70/70 (fake Jev/LLM: consistent pay, brittle pay held only by DT, hard flag, LLM objection, ignore). **Live run on
  all 28** (`scripts/live_engine.py`, saved as `data/live/engine-run-1.json`): ~0.4-1.2 s for Jev (4 calls), 2.6-3 s for the LLM, $0.00035 Jev + $0.0027 LLM per message.
- **Big finding:** with the biller registry in context, **real Jev is right on all 24 gold and all 4 heroes**. All 3 modes score 100%, so the mockup's
  story (Jev confidently pays S01) does not happen on these texts. Real bills brittleness 0.08-0.15 (< τ, good); scams 0.78-0.98.
  → Added **card #16 "Hero hunt"** (rank right after #7): generate adversarial candidates, keep the ones where Jev pays with conf ≥ 0.8 and DT holds. No faking.
- **Next:** card #16, the hero hunt.

### 2026-09-27 12:14 IST: Run 7 (card #16, hero hunt)
- **Done:** tried to generate adversarial candidates with gpt-6-sol. **It declines** (it reasons, then returns an empty message) even when framed as a detector eval.
  Replaced it with `doubletake/redteam.py`: a reproducible template red-team with 48 variants (6 billers × tricks: lookalike link, shortcut link, unknown UPI,
  new portal, pay again, cashback, lookalike sender+link). Each keeps one checkable scam tell. Scripts: `scripts/hero_hunt.py` and `scripts/hero_focus.py`.
- **Verified (real APIs, 76 candidates, saved in data/live/):** 17/56 fooled "Jev only" in round 1 (mostly Airtel/BWSSB/ACT lookalike links, conf 0.27-0.71),
  and **Double Take held every one**. Shared errors (Jev pay + LLM legitimate): the "pay again" BESCOM text (hc-07) and a lookalike-sender Tata Play.
  **No scam reached Jev pay with conf ≥ 0.8** while the biller registry is in context (max 0.78, H6). A 0.97 hit (genuine airtel.in link + typo sender) was
  excluded because paying via the official link isn't a scam.
- **Promoted heroes:** H6 (Airtel bill with real link plus lookalike "faster" link) and H7 (official BESCOM header asking to pay again; Jev and
  gpt-6-sol both said pay, DT held on brittleness 0.35). Stage set is now **30** messages. Added soft flag `pay_again`.
- **Jev is non-deterministic:** the same H7 text was paid in round 1 and held in round 2. The UI should pick "the hero" dynamically from cached
  results (jev_only=pay and DT=hold, highest confidence) rather than hard-coding S01.
- pytest 73/73. **Next:** card #8, precompute the cache and replay (`doubletake/cache.py`, `scripts/precompute.py`).

### 2026-09-27 12:16 IST: Run 8 (card #8, cache + replay)
- **Done:** `doubletake/cache.py`: content-addressed key (sender, text, Jev model, LLM model, question set, household context),
  one file per message `data/cache/<id>-<key>.json`, and `examine_cached(engine, msg, refresh)`. `scripts/precompute.py [--refresh]`.
- **Verified:** pytest 75/75. Live precompute of all 30 stage messages is committed in `data/cache/`, so the server can replay offline.
  Cached outcome: every mode is right on the gold 24 and H2-H5. **H6 and H7 are paid by "Jev only" and held by "Jev + LLM" and Double Take.**
  So on the stage, Jev only pays 2 scams (₹1,889), and the other two modes pay 0.
- **Next:** card #9, the FastAPI server (`server/app.py`).

### 2026-09-27 12:18 IST: Run 9 (card #9, FastAPI server)
- **Done:** `server/app.py` (run: `.venv/bin/uvicorn server.app:app --port 8765`). Endpoints: `GET /api/messages`, `GET /api/examine/{id}[?refresh=1]`,
  `POST /api/examine {sender,text}` (live, cached by content, id `C-xxxx`), `GET /api/ledger` (paid, scams paid, held, Jev and LLM USD per mode;
  Jev+LLM = 1 Jev call + LLM, DT = 4 Jev calls + LLM), `POST /api/gate` (Failproof: `{tool_name, tool_input:{bill_id|message_text, amount, payee}}` →
  allow/deny with a "... Held for Rahul to review. Do not retry." reason; denies an amount mismatch), `GET/DELETE /api/gate/log`, `GET /api/gate/stream` (SSE),
  `GET /api/runs/latest`, and pages `/` and `/eval` (placeholders until cards #10 and #12). Without API keys, cached replay still works (live endpoints return 503).
- **Verified:** pytest 81/81 (TestClient on the committed cache). Live server: ledger Jev-only paid ₹19,543 incl. **2 scams**; Jev+LLM and DT paid ₹17,654 with 0 scams.
  Stage cost: Jev-only $0.0026, Jev+LLM $0.080, DT $0.088. A POST examine of a new lookalike message took 2.9 s and was held.
- **Next:** card #10, the stage UI (`web/stage.html`), matching `docs/mockups/stage.html` but driven by the API.

### 2026-09-27 12:29 IST: Run 10 (card #10, stage UI)
- **Done:** `web/stage.html`, `web/stage.css` (mockup tokens and layout, fluid height, min-width 1280) and `web/stage.js` (vanilla JS, no build).
  Loads `/api/messages` + every cached examination, then plays messages in time order at 0.5/1/2×. Phone badges and top counters are computed per mode.
  Cross-examination tab: base answer card, second-opinion card (dimmed in Jev-only), the 4×9 grid (base cell ringed, muted outside DT, tooltips with probabilities
  and the rewritten text), brittleness meter with a τ marker, flags (hard = filled), reasons, per-message cost, and the "Held for Rahul" alert with working buttons.
  Outside DT, a paid scam says "Double Take would have held it (brittleness x)". Failproof log tab subscribes to `/api/gate/stream` (SSE).
  Ledger tab shows totals for all modes plus rows for the current one. The send form POSTs `/api/examine` live. Keys: Space, 1/2/3, and **H = the most confident
  scam that Jev-only paid and DT held, chosen from real data** (currently H6). "Run Codex under Failproof" calls `POST /api/agent/run` (card #13).
- **Verified in the browser (preview config at the session root, `.claude/launch.json` in repo too):** counters after full playback match `/api/ledger` exactly
  (Jev only ₹19,543 / 2 scams; Jev+LLM and DT ₹17,654 / 0 scams / 14 held). H opens H6 (Jev "Pay now" 0.75, 4/35 disagree, brittleness 0.33, alert shown).
  A live custom lookalike-link message: Jev base pay 0.62, 18/35 disagree, held in 4.6 s. No console errors. Fixed a blank-thread flash (smooth scroll removed).
- **Next:** card #11, the eval dataset and harness (`eval/`, writes `data/runs/eval-<ts>.json`).
