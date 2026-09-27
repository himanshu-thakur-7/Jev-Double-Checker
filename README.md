# Double Take: Jev Double-Checker

> Pucho phir se: ask again before any money moves.

An assistant pays household bills from SMS on Appa's phone. Double Take cross-examines TypeSafe's **Jev** decision model
36 ways, adds deterministic red flags and a gpt-6-sol second opinion, and holds brittle payments for a human (Rahul).

Status: **in progress**. See [HANDOFF.md](HANDOFF.md) and [docs/BOARD.md](docs/BOARD.md).

## Quick start
```bash
cp .env.example .env   # add TYPESAFE_API_KEY and OPENAI_API_KEY
uv venv .venv && uv pip install -e ".[dev]"
.venv/bin/pytest -q
```
