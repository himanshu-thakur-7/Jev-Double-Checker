"""Precompute examinations for the stage set: python scripts/precompute.py [--refresh]"""
import asyncio
import sys

from doubletake.cache import examine_cached
from doubletake.data import stage_messages
from doubletake.engine import Engine


async def main(refresh: bool):
    eng = Engine()
    sem = asyncio.Semaphore(5)

    async def one(m):
        async with sem:
            return await examine_cached(eng, m, refresh)
    res = await asyncio.gather(*(one(m) for m in stage_messages()))
    hits = sum(h for _, h in res)
    print(f"{len(res)} messages, {hits} from cache, {len(res) - hits} computed")
    for m, (ex, _) in zip(stage_messages(), res):
        d = ex["decisions"]
        print(f"{m.id:4} {m.label:5} jev={d['jev_only']['action']:6} jev+llm={d['jev_llm']['action']:6} DT={d['double_take']['action']}")
    await eng.aclose()

asyncio.run(main("--refresh" in sys.argv))
