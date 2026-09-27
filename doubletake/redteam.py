"""Red-team variants for testing the detector (defensive use: they build the eval set and find demo heroes).

gpt-6-sol declines to write scam variants (it returns an empty message), so variants are built from templates:
start from the biller's genuine SMS wording and swap in exactly one scam tell (a lookalike link, a new UPI payee,
an unregistered sender, a "pay again" request...). Each variant is still a scam if checked carefully, and the
construction is reproducible and free.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from .data import Registry, registry as default_registry


@dataclass
class Variant:
    id: str
    sender: str
    text: str
    trick: str
    biller: str
    amount: float


BILLS = {  # genuine wording per biller: (sender, template with {pay})
    "bescom": ("AX-BESCOM", "Dear Consumer, your electricity bill for Acct ID 1234567890 for Sep-2026 is Rs.1,240.00. "
                            "Due date 05-Oct-2026. {pay} Ignore if already paid.", 1240),
    "bwssb": ("AX-BWSSBB", "BWSSB: Water bill for RR No RR-4471-2209 for Sep-2026 is Rs.386. Due 10-Oct-2026. {pay}", 386),
    "airtel": ("AD-AIRTEL", "Your Airtel postpaid bill for 9845012345 of Rs.649 is generated. Due date 04-Oct-2026. {pay}", 649),
    "lic": ("AX-LICIND", "LIC: Premium of Rs.12,480 for Policy 712345678 is due on 08-Oct-2026. {pay} Ignore if paid.", 12480),
    "tataplay": ("VM-TPLAY", "Tata Play: Recharge of Rs.399 due for Sub ID 1087654321 by 03-Oct-2026 to continue watching. {pay}", 399),
    "act": ("VM-ACTBRD", "ACT Fibernet: Your bill for ACT-112233 of Rs.1,178 is due on 06-Oct-2026. {pay}", 1178),
}
LOOKALIKE = {"bescom": ["bescom-bbps.in", "bescom-billpay.in", "bescom.co.in.billpay.site"],
             "bwssb": ["bwssb-payments.in", "bwssb.karnataka.gov.in.paybill.co"],
             "airtel": ["airtel-thanks.in", "airtel.in.bill-pay.co"],
             "lic": ["licindia-paydirect.in", "lic-premium-pay.in"],
             "tataplay": ["tataplay-recharge.co.in", "tataplay.com.renew.site"],
             "act": ["actcorp-billing.in", "act-fibernet-pay.in"]}
FAKE_UPI = {"bescom": "bescom.bbps@okaxis", "bwssb": "bwssb.billdesk@okaxis", "airtel": "airtel.postpaid@ybl",
            "lic": "licpremium.collect@oksbi", "tataplay": "tataplay.recharge@paytm", "act": "actfibernet.bill@okicici"}
FAKE_SENDER = {"bescom": "VK-BESCMS", "bwssb": "VM-BWSSBP", "airtel": "AD-AIRTLE", "lic": "VK-LICPAY",
               "tataplay": "VM-TPLAYY", "act": "VM-ACTFBR"}

TRICKS = {
    "link": ("Lookalike link in a routine bill", lambda b, d, u: f"Pay via BBPS at {d}."),
    "link_soft": ("Lookalike link offered as a shortcut", lambda b, d, u: f"Pay via BBPS in any UPI app. Quick pay: {d}/pay"),
    "upi": ("Routine bill paid to an unknown UPI id", lambda b, d, u: f"Pay via UPI to {u}."),
    "portal": ("New payment portal announcement", lambda b, d, u: f"Payments have moved to the new BBPS portal {d}. Pay there to avoid duplicate charges."),
    "pay_again": ("Asks to pay a bill a second time", lambda b, d, u: f"Your earlier payment could not be updated due to a BBPS issue. Kindly pay again at {d}; any double debit will be auto-refunded."),
    "discount": ("Early-payment discount link", lambda b, d, u: f"Pay by tomorrow at {d} to get Rs.50 cashback."),
}


def variants(reg: Registry | None = None) -> list[Variant]:
    reg = reg or default_registry()
    out: list[Variant] = []
    n = itertools.count(1)
    for bid, (sender, tpl, amount) in BILLS.items():
        for trick, (title, pay) in TRICKS.items():
            for d in LOOKALIKE[bid][:1 if trick != "link" else 2]:
                text = tpl.format(pay=pay(bid, d, FAKE_UPI[bid]))
                out.append(Variant(f"rt-{next(n):03d}", sender, text, f"Red-team rewrite: {title}", bid, amount))
        # the genuine text from a lookalike sender that swaps in its own link (a genuine link would be harmless)
        text = tpl.format(pay=f"Pay via BBPS in any UPI app or at {LOOKALIKE[bid][0]}.")
        out.append(Variant(f"rt-{next(n):03d}", FAKE_SENDER[bid], text, "Red-team rewrite: lookalike sender and link", bid, amount))
    return out
