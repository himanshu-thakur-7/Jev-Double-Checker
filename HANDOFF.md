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
