#!/usr/bin/env python3
"""Hold a payment and ask Rahul to review it (demo: posts to Double Take, which shows it on the stage).

  python ask_rahul.py --bill S01 --reason "Lookalike BESCOM link"
"""
import argparse
import json
import os
import urllib.request

p = argparse.ArgumentParser()
p.add_argument("--bill", required=True)
p.add_argument("--reason", required=True)
a = p.parse_args()
url = os.getenv("DOUBLE_TAKE_URL", "http://localhost:8765").rstrip("/") + "/api/escalate"
req = urllib.request.Request(url, data=json.dumps({"bill_id": a.bill, "reason": a.reason}).encode(),
                             headers={"content-type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        json.load(r)
    print(f"ASKED RAHUL to review {a.bill}: {a.reason}")
except Exception as e:  # the demo still records the intent
    print(f"ASKED RAHUL to review {a.bill} (could not reach Double Take: {e})")
