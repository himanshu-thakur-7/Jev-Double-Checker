# Live enforcement demo

Start the Double Take server first: `.venv/bin/uvicorn server.app:app --port 8765` (from the repo root).

## Option A: the stage button
Press **Run Codex under Failproof** on the stage. If the `codex` CLI is installed and logged in, the server runs
`codex exec` in this folder with the hook below. Otherwise it runs a built-in agent loop (gpt-6-luna with a `pay_bill`
tool). Either way, every pay_bill call goes through the same PreToolUse hook, `failproof/double_take_gate.py`.

## Option B: Codex CLI by hand
Add the hook to `~/.codex/config.toml` (or your project's Codex config):

```toml
[[hooks.PreToolUse]]
matcher = "^Bash$"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "python3 /ABSOLUTE/PATH/TO/repo/failproof/double_take_gate.py"
timeout = 60
statusMessage = "Double Take is checking this payment"
```

Then from this folder: `codex exec "Follow AGENTS.md."`

## Option C: Failproof AI
`npm install -g failproofai && failproofai config` wires Codex/Claude Code hooks. The policy
`.failproofai/policies/double-take-gate.mjs` at the repo root loads automatically when you run the agent from the repo.

The payment rail is fake: `pay_bill.py` only appends to `demo/ledger.jsonl`.
