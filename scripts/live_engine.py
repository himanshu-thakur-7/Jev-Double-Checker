"""Run the engine live on stage messages: python scripts/live_engine.py [ID ...] [--json out.json]"""
import asyncio
import json
import sys

from doubletake.data import stage_messages
from doubletake.engine import Engine


async def main(ids, out):
    msgs = [m for m in stage_messages() if not ids or m.id in ids]
    eng = Engine()
    sem = asyncio.Semaphore(4)

    async def one(m):
        async with sem:
            return await eng.examine(m)
    exs = await asyncio.gather(*(one(m) for m in msgs))
    print(f"{'id':4} {'lab':5} {'base':6} {'conf':4} {'brit':5} {'dis':3} {'scam':4} {'llm':10} | jev  jev+llm  DT")
    for m, e in zip(msgs, exs):
        d = e.decisions
        print(f"{m.id:4} {m.label:5} {e.base['action']:6} {e.base['confidence']:.2f} {e.brittleness:.2f}  {e.disagree:3} "
              f"{e.max_scam:.2f} {(e.second_opinion or {}).get('verdict', '-'):10} | {d['jev_only']['action']:5} "
              f"{d['jev_llm']['action']:6} {d['double_take']['action']:5}  {e.cost['jev_ms']}ms")
    if out:
        json.dump([e.to_dict() for e in exs], open(out, "w"), indent=1, ensure_ascii=False)
    await eng.aclose()

args = sys.argv[1:]
out = args[args.index("--json") + 1] if "--json" in args else None
ids = [a for a in args if a != "--json" and a != out]
asyncio.run(main(ids, out))
