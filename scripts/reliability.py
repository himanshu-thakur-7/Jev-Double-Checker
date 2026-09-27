"""Reliability across runs: python scripts/reliability.py [--runs 5] [--repeats 3]

1. Runs the gated bill-paying agent N times through the server (POST /api/agent/run?evaluate=1), so every run is
   judged by Jev and checked against code truth.
2. Re-examines the key messages live, without the cache, K times each, and measures how often each mode's decision
   flips between calls (Jev itself is not deterministic).
Writes data/runs/reliability-<ts>.json, shown on the eval page.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from doubletake.config import DATA  # noqa: E402
from doubletake.data import stage_messages  # noqa: E402
from doubletake.engine import Engine  # noqa: E402

KEY = ["G01", "G02", "G03", "G04", "G05", "G06", "S01", "S07", "H6", "H7"]


async def agent_runs(n: int, url: str) -> list[dict]:
    out = []
    async with httpx.AsyncClient(timeout=900) as c:
        for i in range(n):
            t0 = time.time()
            r = (await c.post(f"{url}/api/agent/run", params={"evaluate": "1"})).json()
            ev = r["evaluation"]
            t = ev["truth"]
            attempted = [a["bill_id"] for a in ev["actions"] if a["tool"] == "pay_bill" and a["truth"]["label"] == "scam"]
            row = {"run_id": r["run_id"], "runner": r["runner"], "seconds": round(time.time() - t0),
                   "passed": ev["passed"], "scams_paid": t["scams_paid"], "genuine_paid": t["genuine_paid"],
                   "attempted_scams": sorted(set(attempted)), "blocked": t["blocked"], "escalated": t["escalated"],
                   "saves": sorted(set(attempted) & set(t["blocked"]) & set(t["escalated"])),
                   "run_agreement": sum(ev["agreement"].values()) / len(ev["agreement"]),
                   "action_agreement": ev["action_agreement"], "jev_run_scores": ev["run"], "jev_cost_usd": ev["jev_cost_usd"]}
            out.append(row)
            print(f"run {i + 1}/{n} {row['run_id']} {'PASS' if row['passed'] else 'FAIL'} scams_paid={row['scams_paid']} "
                  f"saves={row['saves']} genuine={len(row['genuine_paid'])} agree={row['run_agreement']:.0%}/{row['action_agreement']:.0%} {row['seconds']}s")
    return out


async def stability(repeats: int) -> dict:
    msgs = {m.id: m for m in stage_messages()}
    eng = Engine()
    sem = asyncio.Semaphore(6)

    async def one(mid):
        async with sem:
            return mid, (await eng.examine(msgs[mid])).to_dict()
    res = await asyncio.gather(*(one(mid) for mid in KEY for _ in range(repeats)))
    await eng.aclose()
    table = {}
    for mid in KEY:
        exs = [e for m, e in res if m == mid]
        per_mode = {mode: [e["decisions"][mode]["action"] for e in exs] for mode in ("jev_only", "jev_llm", "double_take")}
        table[mid] = {"label": msgs[mid].label, "decisions": per_mode,
                      "stable": {mode: len(set(v)) == 1 for mode, v in per_mode.items()},
                      "correct": {mode: sum((a == "pay") == (msgs[mid].label == "bill") for a in v) / len(v) for mode, v in per_mode.items()},
                      "brittleness": [e["brittleness"] for e in exs], "base_confidence": [e["base"]["confidence"] for e in exs]}
    modes = ("jev_only", "jev_llm", "double_take")
    return {"repeats": repeats, "messages": table,
            "stable_rate": {m: sum(t["stable"][m] for t in table.values()) / len(table) for m in modes},
            "accuracy": {m: sum(t["correct"][m] for t in table.values()) / len(table) for m in modes}}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--url", default="http://localhost:8765")
    a = ap.parse_args()
    t0 = time.time()
    stab_task = asyncio.create_task(stability(a.repeats))
    runs = await agent_runs(a.runs, a.url)
    stab = await stab_task
    attempted = sum(len(r["attempted_scams"]) for r in runs)
    genuine_total = a.runs * 6
    summary = {"runs": len(runs), "passed": sum(r["passed"] for r in runs),
               "scams_paid": sum(len(r["scams_paid"]) for r in runs), "attempted_scams": attempted,
               "saves": sum(len(r["saves"]) for r in runs),
               "genuine_paid_rate": sum(len(r["genuine_paid"]) for r in runs) / genuine_total,
               "jev_agreement": sum((r["run_agreement"] + r["action_agreement"]) / 2 for r in runs) / len(runs),
               "stable_rate": stab["stable_rate"], "accuracy_across_repeats": stab["accuracy"],
               "seconds": round(time.time() - t0)}
    out = DATA / "runs" / f"reliability-{int(time.time())}.json"
    out.write_text(json.dumps({"created": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "summary": summary, "runs": runs,
                               "stability": stab}, indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1))
    for mid, t in stab["messages"].items():
        print(f"  {mid:4} {t['label']:5} jev_only={t['decisions']['jev_only']} jev_llm={t['decisions']['jev_llm']} DT={t['decisions']['double_take']}")
    print("saved", out.name)

asyncio.run(main())
