#!/usr/bin/env python3
"""Pretend payment rail for the demo. Nothing real moves: it appends to demo/ledger.jsonl.

  python demo/pay_bill.py --bill G01 --payee BESCOM --amount 1240 [--sender S --text T]
"""
import argparse
import json
import time
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--bill", required=True)
p.add_argument("--payee", required=True)
p.add_argument("--amount", type=float, required=True)
p.add_argument("--sender")
p.add_argument("--text")
a = p.parse_args()
entry = {"ts": time.strftime("%H:%M:%S"), "bill_id": a.bill, "payee": a.payee, "amount": a.amount}
with (Path(__file__).parent / "ledger.jsonl").open("a") as f:
    f.write(json.dumps(entry) + "\n")
print(f"PAID {a.payee} Rs.{a.amount:,.0f} for {a.bill}")
