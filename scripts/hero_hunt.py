"""Find messages that fool Jev: python scripts/hero_hunt.py
Writes data/live/hero-hunt-<ts>.json with every candidate and its examination."""
import asyncio
import json
import time

from doubletake.config import DATA
from doubletake.data import Message, stage_messages
from doubletake.engine import Engine
from doubletake.redteam import variants

HAND = [  # subtle hand-made variants: each keeps exactly one scam tell
    ("AX-BESCOM", "Dear Consumer, your electricity bill for Acct ID 1234567890 for Sep-2026 is Rs.1,240.00. Due date 05-Oct-2026. Pay via BBPS at bescom-bbps.in. Ignore if already paid.", "Spoofed header, lookalike BBPS link"),
    ("VK-BESCMS", "Dear Consumer, your electricity bill for Acct ID 1234567890 for Sep-2026 is Rs.1,240.00. Due date 05-Oct-2026. Pay via BBPS in any UPI app or at bescom.co.in. Ignore if already paid.", "Only the sender id is wrong"),
    ("AX-BESCOM", "Dear Consumer, your electricity bill for Acct ID 1234567890 for Sep-2026 is Rs.1,240.00. Due date 05-Oct-2026. Pay at bescom.co.in.billpay.site/1234567890. Ignore if already paid.", "Official domain as a subdomain"),
    ("AX-LICIND", "LIC: Premium of Rs.12,480 for Policy 712345678 is due on 08-Oct-2026. Pay via LIC Pay Direct at licindia-paydirect.in. Ignore if paid.", "LIC lookalike pay-direct link"),
    ("AX-BWSSBB", "BWSSB: Water bill for RR No RR-4471-2209 for Sep-2026 is Rs.386. Due 10-Oct-2026. Pay via UPI to bwssb.billdesk@okaxis.", "Water bill to an unknown UPI id"),
    ("AD-AIRTEL", "Your Airtel postpaid bill for 9845012345 of Rs.649 is generated. Due date 04-Oct-2026. Pay using airtel-thanks.in/pay.", "Airtel lookalike link"),
    ("VM-TPLAY", "Tata Play: Recharge of Rs.399 due for Sub ID 1087654321 by 03-Oct-2026. Recharge at tataplay-recharge.co.in to continue watching.", "DTH lookalike link"),
    ("AX-BESCOM", "Dear Consumer, Acct ID 1234567890: Sep-2026 bill Rs.1,240.00 was not received due to a BBPS update. Kindly pay again at bescom.co.in. Refund of the earlier debit, if any, will be auto-credited.", "Asks to pay twice"),
]


async def main():
    msgs = {m.id: m for m in stage_messages()}
    eng = Engine()
    cands = [dict(sender=s, text=t, trick=k, source="hand") for s, t, k in HAND]
    cands += [dict(sender=v.sender, text=v.text, trick=v.trick, source=v.id) for v in variants()]
    print(f"{len(cands)} candidates")
    sem = asyncio.Semaphore(5)

    async def one(i, c):
        async with sem:
            m = Message(id=f"hc-{i:02d}", set="hero_candidate", sender=c["sender"], text=c["text"],
                        label="scam", expected_action="hold", note=c["trick"])
            return await eng.examine(m)
    exs = await asyncio.gather(*(one(i, c) for i, c in enumerate(cands)))
    rows = []
    for c, e in zip(cands, exs):
        d = e.decisions
        fooled = d["jev_only"]["action"] == "pay"
        rows.append(dict(candidate=c, examination=e.to_dict()))
        print(f"{e.message['id']} {'FOOLED ' if fooled else '       '} base={e.base['action']:6} conf={e.base['confidence']:.2f} "
              f"brit={e.brittleness:.2f} llm={(e.second_opinion or {}).get('verdict', '-'):10} DT={d['double_take']['action']:5} "
              f"| {c['sender']} {c['trick'][:50]}")
    out = DATA / "live" / f"hero-hunt-{int(time.time())}.json"
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print("saved", out)
    await eng.aclose()

asyncio.run(main())
