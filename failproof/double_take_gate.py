#!/usr/bin/env python3
"""PreToolUse command hook: ask Double Take before any pay_bill call runs.

Works as a Codex or Claude Code hook (reads the hook event JSON on stdin, prints the decision JSON).
Set DOUBLE_TAKE_URL if the server is not on http://localhost:8765. Fails closed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from doubletake.gatehook import run_hook  # noqa: E402

print(run_hook(sys.stdin.read()))
