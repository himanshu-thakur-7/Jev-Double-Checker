"""Run the evaluation: python eval/run_eval.py [--limit N] [--refresh]

Every message is cross-examined once (all three modes come from the same answers). Writes data/runs/eval-<ts>.json.

Definitions
  money error        paying a scam or a no-action message, or not paying a real bill
  Jev error          Jev's base answer makes a money error (a scam where Jev says hold vs ignore is not an error)
  confident          Jev's base confidence >= 0.8
  shared confident   a confident Jev error where the second opinion makes the same money error
  caught at k%       the message is in the top k% when all messages are ranked for human review
                     (by lowest Jev confidence, or by highest Double Take risk)
"""
import asyncio
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from doubletake import cache, config  # noqa: E402
from doubletake.data import load_jsonl  # noqa: E402
from doubletake.engine import MODES, SCAM_MAX, TAU, Engine, review_risk  # noqa: E402

# A fourth, cheaper variant computed from the same answers: Double Take's 36-answer check and flags, without the LLM.
EVAL_MODES = MODES + ("double_take_jev",)


def dt_without_llm(ex) -> str:
    base = ex["base"]["action"]
    if base != "pay":
        return base
    hard = any(f["severity"] == "hard" for f in ex["flags"])
    return "hold" if ex["brittleness"] > TAU or ex["max_scam"] >= SCAM_MAX or hard else "pay"

EVAL_CACHE = config.DATA / "cache" / "eval"
REVIEW = (0.05, 0.10, 0.20)
CONF = 0.8


def money_error(label: str, action_pays: bool) -> bool:
    return action_pays if label in ("scam", "none") else not action_pays


def row_of(m, ex) -> dict:
    op = ex.get("second_opinion") or {}
    jev_pays = ex["base"]["action"] == "pay"
    llm_pays = bool(op.get("agrees_pay")) if m.label != "none" else op.get("action") == "pay"
    jev_err = money_error(m.label, jev_pays)
    return {
        "id": m.id, "set": m.set, "label": m.label, "note": m.note, "sender": m.sender, "amount": m.amount,
        "base_action": ex["base"]["action"], "confidence": ex["base"]["confidence"],
        "brittleness": ex["brittleness"], "disagree": ex["disagree"], "max_scam": ex["max_scam"], "risk": review_risk(ex),
        "flags": [f["kind"] for f in ex["flags"]], "hard_flag": any(f["severity"] == "hard" for f in ex["flags"]),
        "llm_verdict": op.get("verdict"), "llm_action": op.get("action"),
        "decisions": {k: v["action"] for k, v in ex["decisions"].items()} | {"double_take_jev": dt_without_llm(ex)},
        "jev_error": jev_err, "confident_error": jev_err and ex["base"]["confidence"] >= CONF,
        "shared_confident_error": jev_err and ex["base"]["confidence"] >= CONF and money_error(m.label, llm_pays),
        "cost": {k: ex["cost"][k] for k in ("jev_usd", "jev_only_usd", "llm_usd", "jev_ms", "llm_ms")},
    }


def mode_table(rows) -> dict:
    out = {}
    for mode in EVAL_MODES:
        pays = [r for r in rows if r["decisions"][mode] == "pay"]
        cost = sum((r["cost"]["jev_usd"] if mode.startswith("double_take") else r["cost"]["jev_only_usd"])
                   + (r["cost"]["llm_usd"] if mode in ("jev_llm", "double_take") else 0) for r in rows)
        out[mode] = {
            "scams_paid": sum(r["label"] == "scam" for r in pays),
            "scams": sum(r["label"] == "scam" for r in rows),
            "none_paid": sum(r["label"] == "none" for r in pays),
            "bills_held": sum(r["label"] == "bill" and r["decisions"][mode] != "pay" for r in rows),
            "bills": sum(r["label"] == "bill" for r in rows),
            "money_errors": sum(money_error(r["label"], r["decisions"][mode] == "pay") for r in rows),
            "cost_per_message": cost / max(1, len(rows)),
        }
    return out


def catch_rates(rows, target_key: str) -> dict:
    targets = {r["id"] for r in rows if r[target_key]}
    n = len(rows)
    by_conf = sorted(rows, key=lambda r: r["confidence"])
    by_risk = sorted(rows, key=lambda r: -r["risk"])
    res = {"n_targets": len(targets), "levels": []}
    for k in REVIEW:
        top = math.ceil(n * k)
        res["levels"].append({"review": k, "messages": top,
                              "low_confidence": len(targets & {r["id"] for r in by_conf[:top]}),
                              "double_take": len(targets & {r["id"] for r in by_risk[:top]})})
    rank = {r["id"]: i for i, r in enumerate(by_risk)}
    res["caught_at"] = {t: next((k for k in REVIEW if rank[t] < math.ceil(n * k)), None) for t in targets}
    return res


async def main():
    args = sys.argv[1:]
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    refresh = "--refresh" in args
    msgs = load_jsonl(config.DATA / "messages" / "eval.jsonl")[:limit]
    eng = Engine()
    sem = asyncio.Semaphore(6)
    done = 0
    t0 = time.time()

    async def one(m):
        nonlocal done
        root = cache.CACHE_DIR if m.set in ("gold", "hero") else EVAL_CACHE
        async with sem:
            for attempt in range(3):
                try:
                    ex, _ = await cache.examine_cached(eng, m, refresh=refresh, root=root)
                    break
                except Exception as e:  # keep going; record the failure
                    if attempt == 2:
                        print("FAILED", m.id, e)
                        return None
                    await asyncio.sleep(2)
        done += 1
        if done % 25 == 0:
            print(f"  {done}/{len(msgs)} ({time.time() - t0:.0f}s)")
        return row_of(m, ex)

    rows = [r for r in await asyncio.gather(*(one(m) for m in msgs)) if r]
    await eng.aclose()
    gold = [r for r in rows if r["set"] == "gold"]
    ts = int(time.time())
    run = {
        "run_id": f"eval-{ts}", "created": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "messages": len(rows),
        "failed": len(msgs) - len(rows), "jev_model": config.JEV_MODEL, "llm_model": config.SECOND_OPINION_MODEL,
        "labels": dict(Counter(r["label"] for r in rows)), "sets": dict(Counter(r["set"] for r in rows)),
        "definitions": {"confident": CONF, "review_levels": REVIEW},
        "all": mode_table(rows), "gold": mode_table(gold),
        "by_set": {s: mode_table([r for r in rows if r["set"] == s]) for s in sorted({r["set"] for r in rows})},
        "counts": {"jev_errors": sum(r["jev_error"] for r in rows), "confident_errors": sum(r["confident_error"] for r in rows),
                   "shared_confident_errors": sum(r["shared_confident_error"] for r in rows)},
        "catch": {"shared_confident": catch_rates(rows, "shared_confident_error"),
                  "confident": catch_rates(rows, "confident_error"),
                  "jev_errors": catch_rates(rows, "jev_error")},
        "rows": rows,
    }
    out = config.DATA / "runs" / f"eval-{ts}.json"
    out.write_text(json.dumps(run, indent=1, ensure_ascii=False))
    print(f"saved {out.name} in {time.time() - t0:.0f}s")
    print(json.dumps({k: run[k] for k in ("messages", "failed", "counts")}, indent=1))
    for scope in ("gold", "all"):
        print(scope, json.dumps(run[scope]))
    for k, v in run["catch"].items():
        print(k, v["n_targets"], [(l["review"], l["low_confidence"], l["double_take"]) for l in v["levels"]])


if __name__ == "__main__":
    asyncio.run(main())
