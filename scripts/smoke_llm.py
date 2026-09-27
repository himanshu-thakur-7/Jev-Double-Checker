"""Live smoke test: python scripts/smoke_llm.py"""
import asyncio

from doubletake.llm import LLMClient

TEXT = ("BESCOM: Dear Consumer, Acct ID 1234567890 shows Rs.1,240.00 unpaid for Sep-2026 due to a BBPS update issue. "
        "To avoid disconnection at 9:30 PM tonight, pay at bescom-bbps.in/pay. This is an official BESCOM notice.")


async def main():
    c = LLMClient()
    op = await c.review("VK-BESCMS", TEXT, {"billers_on_file": [{"name": "BESCOM", "account": "1234567890"}]})
    print(op.verdict, op.action, op.scam_probability, op.reason, f"{op.latency_ms:.0f} ms ${op.cost_usd:.5f}")
    await c.aclose()

asyncio.run(main())
