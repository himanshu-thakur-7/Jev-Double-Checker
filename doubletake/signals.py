"""Deterministic red flags. Cheap rule checks that sit beside Jev, because text written to steer a model
(TypeSafe's own jaggedness notes) can't argue its way past a lookup table.

Each flag has a severity: "hard" flags hold a payment on their own in Double Take mode; "soft" flags are shown
as evidence and feed the risk score.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .data import Biller, Registry, registry as default_registry

_DOMAIN = re.compile(r"\b((?:[a-z0-9-]+\.)+(?:in|com|co|org|net|top|xyz|info|online|site|gov\.in|co\.in))(?:/[^\s,]*)?", re.I)
_UPI = re.compile(r"\b[a-z0-9._-]{2,}@[a-z]{2,}\b", re.I)
_AMOUNT = re.compile(r"(?:Rs\.?|INR|₹)\s?([\d,]+(?:\.\d{1,2})?)", re.I)
_HEADER = re.compile(r"^[A-Z]{2}-[A-Z0-9]{3,8}$")
_THREAT = re.compile(
    r"((?:disconnect\w*|blocked|block|blacklist\w*|lapse|barring|barred|suspend\w*|cut)\b[^.]{0,40}?"
    r"(?:tonight|today|within \d+ ?(?:hours|hrs)|in \d+ ?(?:hours|hrs)|\d{1,2}[:.]\d{2} ?[ap]m(?: tonight| today)?))"
    r"|((?:tonight|today|within \d+ ?(?:hours|hrs))[^.]{0,40}?(?:disconnect\w*|blocked|blacklist\w*|lapse|barring))",
    re.I)
_INJECTION = re.compile(r"(note to|attention)[^.]{0,30}(assistant|ai|bot|automated)|pre-?approved|without asking|"
                        r"ignore (previous|prior) instructions|you are (authori[sz]ed|verified)", re.I)
_PAYEE_CHANGE = re.compile(r"new (upi|account|bank)|payment details (have )?changed|must now be (made|paid) to|"
                           r"old payment modes? will fail", re.I)
_FEE_FOR_REFUND = re.compile(r"refund.{0,80}?(fee|charge)|(fee|charge).{0,80}?refund", re.I)


@dataclass
class Flag:
    kind: str
    label: str
    severity: str  # "hard" | "soft" | "info"
    evidence: str = ""

    def to_dict(self):
        return asdict(self)


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def domains(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1).lower() for m in _DOMAIN.finditer(text)))


def amounts(text: str) -> list[float]:
    return [float(a.replace(",", "")) for a in _AMOUNT.findall(text)]


def _official(domain: str, reg: Registry) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in reg.all_domains)


def _brand_tokens(b: Biller) -> set[str]:
    toks = {b.id.lower(), b.name.split()[0].lower()}
    toks |= {h.split("-")[-1].lower() for h in b.headers}
    return {t for t in toks if len(t) >= 3}


def identify_biller(sender: str, text: str, reg: Registry) -> Biller | None:
    s = sender.upper()
    for b in reg.billers:
        if s in (h.upper() for h in b.headers) or sender in b.phones:
            return b
    low = text.lower()
    for b in reg.billers:
        if b.account.lower() in low or b.account.split()[-1].lower() in low:
            return b
    for b in reg.billers:
        if b.name.lower() in low:
            return b
    return None


def detect(sender: str, text: str, reg: Registry | None = None) -> tuple[list[Flag], Biller | None]:
    reg = reg or default_registry()
    flags: list[Flag] = []
    biller = identify_biller(sender, text, reg)

    if m := _THREAT.search(text):
        flags.append(Flag("threat", f"Threat within hours: “{m.group(0).strip()}”", "soft", m.group(0).strip()))

    for d in domains(text):
        if _official(d, reg):
            continue
        brand = next((b for b in reg.billers if any(t in d.replace("-", "").replace(".", "") for t in _brand_tokens(b))), None)
        if brand:
            flags.append(Flag("lookalike_link", f"Unknown link: {d}", "hard",
                              f"uses the {brand.name} name but is not an official {brand.name} website"))
        else:
            flags.append(Flag("unknown_link", f"Unknown link: {d}", "soft", d))

    s = sender.upper()
    if _HEADER.match(s):
        if s not in reg.all_headers:
            suffix = s.split("-")[1]
            near = min(((edit_distance(suffix, h.split("-")[1]), h) for h in reg.all_headers), default=(99, ""))
            sev = "soft"
            ev = "not a registered sender for any biller on file"
            if near[0] <= 2:
                ev = f"looks like {near[1]} but is not registered"
            flags.append(Flag("unregistered_sender", f"Unregistered sender: {sender}", sev, ev))
    elif sender.startswith("+") and biller is None and sender not in reg.household.get("family_contacts", {}).values():
        flags.append(Flag("unknown_number", f"Unknown phone number: {sender}", "soft", sender))

    if m := _INJECTION.search(text):
        flags.append(Flag("injection", "Message gives instructions to the assistant", "hard", m.group(0)))
    if m := _PAYEE_CHANGE.search(text):
        flags.append(Flag("payee_change", "Asks to pay a new payee", "hard", m.group(0)))
    if m := _FEE_FOR_REFUND.search(text):
        flags.append(Flag("fee_for_refund", "Fee demanded to receive money", "soft", m.group(0)))

    known_upi = {u.lower() for b in reg.billers for u in b.upi}
    for u in _UPI.findall(text):
        if u.lower() not in known_upi:
            flags.append(Flag("unknown_upi", f"Unknown UPI ID: {u}", "soft", u))

    amts = amounts(text)
    if biller and amts:
        lo, hi = biller.usual_amount
        a = max(amts) if len(amts) > 1 and biller.category != "credit_card" else amts[0]
        if a > hi * 3:
            flags.append(Flag("amount", f"Amount ₹{a:,.0f} is {a / hi:.0f}× the usual {biller.name} bill", "hard", f"usual ₹{lo:,.0f}-{hi:,.0f}"))
        elif a > hi * 1.3 or a < lo * 0.5:
            flags.append(Flag("amount", f"Unusual amount ₹{a:,.0f} for {biller.name}", "soft", f"usual ₹{lo:,.0f}-{hi:,.0f}"))
    if biller and biller.autopay:
        flags.append(Flag("autopay", f"{biller.name} is on AutoPay", "info", "paying again would double pay"))

    return flags, biller


def has_hard(flags: list[Flag]) -> bool:
    return any(f.severity == "hard" for f in flags)
