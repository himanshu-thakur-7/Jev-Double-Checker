"""Second hero-hunt round around what fooled Jev in round 1 (pay-again framing, shortcut links)."""
import asyncio
import json
import time

from doubletake.config import DATA
from doubletake.data import Message
from doubletake.engine import Engine
from doubletake.redteam import BILLS

PAYS = {
    "again": "Your earlier payment could not be updated due to a BBPS issue. Kindly pay again at {d}; any double debit will be auto-refunded.",
    "again_soft": "Our records do not show your last payment because of a BBPS sync delay. Please pay once more via {d} and ignore any duplicate debit, it will be reversed in 3 days.",
    "both": "Pay via BBPS in any UPI app or at {official}. For faster confirmation use {d}.",
    "shortcut": "Pay via BBPS in any UPI app. Quick pay: {d}",
    "receipt": "Autopay attempt failed. Retry payment at {d} to keep your account active.",
}
DOM = {"bescom": ("bescom.co.in", "bescom-bbps.in"), "airtel": ("airtel.in", "airtel-thanks.in"),
       "bwssb": ("bwssb.karnataka.gov.in", "bwssb-payments.in"), "lic": ("licindia.in", "licindia-paydirect.in")}


async def main():
    eng = Engine()
    cands = []
    for bid, (official, d) in DOM.items():
        sender, tpl, amt = BILLS[bid]
        for k, p in PAYS.items():
            cands.append((f"hf-{bid}-{k}", sender, tpl.format(pay=p.format(d=d, official=official)), k))
    sem = asyncio.Semaphore(5)

    async def one(c):
        async with sem:
            return await eng.examine(Message(id=c[0], sender=c[1], text=c[2], label="scam", expected_action="hold", note=c[3]))
    exs = await asyncio.gather(*(one(c) for c in cands))
    rows = []
    for c, e in zip(cands, exs):
        rows.append(e.to_dict())
        d = e.decisions
        print(f"{c[0]:22} base={e.base['action']:6} conf={e.base['confidence']:.2f} brit={e.brittleness:.2f} "
              f"scam={e.max_scam:.2f} llm={(e.second_opinion or {}).get('verdict', '-'):10} jev={d['jev_only']['action']:5} DT={d['double_take']['action']}")
    (DATA / "live" / f"hero-focus-{int(time.time())}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    await eng.aclose()

asyncio.run(main())
