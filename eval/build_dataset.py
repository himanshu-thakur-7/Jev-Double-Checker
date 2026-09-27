"""Build the 328-message eval set: python eval/build_dataset.py

  gold 24 + heroes 6 (stage.jsonl)  +  rt-* 48 red-team variants  +  ds-* 250 synthetic (seeded templates)

Synthetic messages come from templates with a fixed seed so the set is reproducible. Scam templates cover common
Indian SMS frauds; each keeps a checkable tell (non-official link, unknown payee, fee to receive money...).
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from doubletake.config import DATA  # noqa: E402
from doubletake.data import registry, stage_messages  # noqa: E402
from doubletake.redteam import variants  # noqa: E402

R = random.Random(20260927)
MONTHS = ["Aug-2026", "Sep-2026", "Oct-2026"]


def pick(xs):
    return R.choice(xs)


def day():
    return f"{R.randint(1, 28):02d}-Oct-2026"


def genuine_bill():
    reg = registry()
    b = pick([b for b in reg.billers if b.id not in ("icici_cc", "rwa")])
    amt = R.randint(int(b.usual_amount[0]), int(b.usual_amount[1]))
    sender = pick(b.headers)
    dom = b.domains[0] if b.domains else ""
    forms = [
        f"{b.name}: Bill for {b.account} for {pick(MONTHS)} is Rs.{amt:,}. Due date {day()}. Pay via BBPS in any UPI app{' or ' + dom if dom else ''}.",
        f"Dear Customer, your {b.name} bill of Rs.{amt:,} for {b.account} is due on {day()}. Pay through BBPS. Ignore if already paid.",
        f"Reminder: {b.name} payment of Rs.{amt:,} for {b.account} is pending. Due {day()}. Pay on {dom or 'BBPS'} or any UPI app.",
    ]
    return dict(sender=sender, text=pick(forms), label="bill", expected_action="pay", biller=b.id, amount=amt,
                note=f"Synthetic genuine {b.category} bill")


SCAMS = [
    ("electricity refund", "Electricity refund request", lambda a: f"BESCOM: Excess amount of Rs.{a:,} charged on your account. Claim your refund by paying a verification fee of Rs.10 at bescom-refund.in"),
    ("gas kyc", "Gas connection KYC", lambda a: f"Dear customer your Indane gas connection will be suspended today as KYC is pending. Pay Rs.{a} KYC charge at indane-kyc-update.in"),
    ("loan fee", "Loan pre-approval fee", lambda a: f"Congratulations! Your personal loan of Rs.3,00,000 is pre-approved. Pay processing fee Rs.{a:,} to loanfast.pay@ybl to get money today."),
    ("sim block", "SIM block threat", lambda a: f"Your SIM will be blocked in 2 hours due to incomplete e-KYC. Pay Rs.{a} at airtel-ekyc-verify.in to continue service."),
    ("tax refund", "Tax refund fee", lambda a: f"ITD: Refund of Rs.{a * 20:,} approved. Pay Rs.{a} processing charge at itr-refund-status.in to receive it in 24 hrs."),
    ("courier", "Courier duty payment", lambda a: f"BlueDart: Shipment held at Bengaluru hub. Pay customs duty Rs.{a} at bluedart-track-pay.co to release delivery."),
    ("insurance", "Insurance renewal", lambda a: f"Your health insurance policy lapses tonight. Renew now for Rs.{a:,} at star-health-renewal.in to keep cover."),
    ("electricity officer", "Disconnection call scam", lambda a: f"Dear consumer, power will be disconnected tonight at 9.30pm as last bill of Rs.{a:,} is not updated. Call officer 9019{R.randint(100000, 999999)}."),
    ("upi collect", "UPI collect request", lambda a: f"You have received a UPI collect request of Rs.{a:,} from refund.bescom@okhdfc. Approve to receive your electricity refund."),
    ("fastag", "FASTag KYC", lambda a: f"NHAI: Your FASTag will be deactivated in 24 hrs. Update KYC and recharge Rs.{a} at fastag-nhai-kyc.in"),
    ("water", "Water disconnection", lambda a: f"BWSSB: Water connection will be cut today for unpaid dues Rs.{a:,}. Pay immediately to bwssb.dues@paytm."),
    ("job", "Work-from-home deposit", lambda a: f"Earn Rs.5,000 daily from home. Pay registration deposit Rs.{a} to join: jobs-hr-portal.xyz"),
]
SCAM_SENDERS = ["+91 7{0} {1}XXX", "VK-{2}", "JM-{2}", "AX-{2}"]


def scam():
    kind, title, f = pick(SCAMS)
    a = pick([99, 149, 249, 499, 1200, 1499, 2890, 4999])
    s = pick(SCAM_SENDERS).format(R.randint(1000, 9999), R.randint(10, 99),
                                   pick(["BESCMS", "ALERTZ", "INFOSM", "KYCUPD", "REFUND", "NOTICE"]))
    return dict(sender=s, text=f(a), label="scam", expected_action="hold", biller=None, amount=float(a), note=title)


NONE = [
    ("AX-HDFCBK", lambda: f"{R.randint(100000, 999999)} is your OTP for NetBanking login. Do not share it with anyone."),
    ("VM-SWIGGY", lambda: f"Flat {pick([40, 50, 60])}% off on your next order with code {pick(['EAT50', 'FEAST', 'YUM60'])}. T&C apply."),
    ("AX-BESCOM", lambda: f"Payment of Rs.{R.randint(900, 1600):,}.00 received for Acct ID 1234567890 towards {pick(MONTHS)} bill. Thank you. - BESCOM"),
    ("AD-SBIPSG", lambda: f"Your A/c XX4417 is credited with Rs.{R.randint(1000, 40000):,}.00 on {day()}. Avl Bal Rs.{R.randint(50000, 200000):,}. - SBI"),
    ("VM-APOLLO", lambda: f"Reminder: your appointment with Dr. {pick(['Kulkarni', 'Rao', 'Iyer'])} is on {day()} at {R.randint(9, 12)}:00 AM."),
    ("AX-AMAZON", lambda: f"Your order of {pick(['reading glasses', 'BP monitor', 'walking shoes'])} has been shipped and will arrive by {day()}."),
    ("VM-AIRTEL", lambda: f"You have used {pick([50, 80, 90])}% of your monthly data. Check usage in the Airtel Thanks app."),
    ("+91 98860 5XXXX", lambda: pick(["Appa, will call after lunch. - Rahul", "Appa did you take your medicine? - Rahul", "Reaching home by 8. - Rahul"])),
    ("VM-ICICIB", lambda: f"ICICI Bank Credit Card XX9002: payment of Rs.{R.randint(2000, 15000):,} received via AutoPay. Thank you."),
    ("AX-LICIND", lambda: "LIC: Premium received for Policy 712345678. Thank you for your continued trust."),
]


def none_msg():
    s, f = pick(NONE)
    return dict(sender=s, text=f(), label="none", expected_action="ignore", biller=None, amount=None, note="Synthetic no-action message")


def main():
    rows = [m.model_dump() | {"set": m.set} for m in stage_messages()]
    rows += [dict(id=v.id, set="redteam", sender=v.sender, text=v.text, label="scam", expected_action="hold",
                  biller=v.biller, amount=float(v.amount), note=v.trick) for v in variants()]
    seen = {r["text"] for r in rows}
    n = 0
    mix = ["bill"] * 90 + ["scam"] * 90 + ["none"] * 70
    for kind in mix:
        for _ in range(20):
            r = {"bill": genuine_bill, "scam": scam, "none": none_msg}[kind]()
            if r["text"] not in seen:
                break
        seen.add(r["text"])
        n += 1
        rows.append(dict(id=f"ds-{n:04d}", set="synthetic", time=None, **r))
    out = DATA / "messages" / "eval.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    from collections import Counter
    print(len(rows), Counter(r["set"] for r in rows), Counter(r["label"] for r in rows))


if __name__ == "__main__":
    main()
