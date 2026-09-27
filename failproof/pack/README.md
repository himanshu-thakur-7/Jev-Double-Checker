# Double Take pack for Failproof AI

`double-take-pack.mjs` holds:

- **double-take-gate** (custom, hard, on by default): asks the Double Take server (`POST /api/gate`, 36 Jev answers + red flags)
  before any `pay_bill` call. A deny tells the agent to escalate instead: `python3 ask_rahul.py --bill <id> --reason "..."`.
- **payment-to-unverified-payee** (Jev semantic check, deny): *is this a payment?* and *is the payee or channel not the official biller's?*
- **payment-under-time-pressure** (Jev semantic check, instruct): *is this a payment?* and *does the bill threaten a same-day consequence?*

Jev semantic checks take effect only from a published pack, with Jev configured (`failproofai jev setup`).

```bash
# build and validate, publish nothing
failproofai publish failproof/pack/double-take-pack.mjs --dry-run --version 0.1.0 --id himanshu-thakur-7/double-take --out failproof/pack/dist

# enforce the gate on this machine only, no publishing (needs `failproofai config` done)
failproofai policies -i -c ./failproof/pack/double-take-pack.mjs

# publish a GitHub release anyone can install (owner decision: makes a public release)
failproofai publish failproof/pack/double-take-pack.mjs --repo himanshu-thakur-7/Jev-Double-Checker --id himanshu-thakur-7/double-take
failproofai policies add himanshu-thakur-7/Jev-Double-Checker
```
