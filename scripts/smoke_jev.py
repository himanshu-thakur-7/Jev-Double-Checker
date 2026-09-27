"""Live smoke test: python scripts/smoke_jev.py"""
import asyncio
import json

from doubletake.jev import JevClient, choice, noul

MSG = ("VK-BESCMS: BESCOM: Dear Consumer, Acct ID 1234567890 shows Rs.1,240.00 unpaid for Sep-2026 due to a BBPS "
       "update issue. To avoid disconnection at 9:30 PM tonight, pay at bescom-bbps.in/pay. This is an official BESCOM notice.")


async def main():
    c = JevClient()
    r = await c.ask(MSG, {"act": choice("What should the bill-paying assistant do with this message?",
                                        {"pay": "Pay the bill now", "hold": "Hold and ask the family first",
                                         "ignore": "No payment action needed"}),
                          "scam": noul("Is this message a scam or phishing attempt?")})
    print(json.dumps(r.answers, indent=1), f"\n{r.model} {r.latency_ms:.0f} ms ${r.cost_usd:.7f}")
    await c.aclose()

asyncio.run(main())
