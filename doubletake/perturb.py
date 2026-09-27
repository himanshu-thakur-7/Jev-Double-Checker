"""Deterministic rewrites of a message. Each keeps the facts and changes only the surface.

R0 Original   the message as received
R1 Noisy text typos, odd casing and spacing, the way SMS often arrives
R2 Reshuffled the same sentences in a different order
R3 Plain text urgency formatting and salutations removed, one sentence per line

Facts are protected: any token with a digit, a URL/domain, an @ (UPI id) or a sender id is never altered,
so a rewrite can't change what is being paid or to whom. No LLM is involved, so the rewrites are free and reproducible.
"""
from __future__ import annotations

import hashlib
import random
import re

REWRITES = ("R0", "R1", "R2", "R3")
NAMES = {"R0": "Original", "R1": "Noisy text", "R2": "Reshuffled", "R3": "Plain text"}

_PROTECTED = re.compile(r"\d|@|https?://|www\.|\.[a-z]{2,4}(/|$)|^[A-Z]{2}-[A-Z0-9]+$", re.I)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _rng(text: str, salt: str) -> random.Random:
    return random.Random(int(hashlib.sha256((salt + text).encode()).hexdigest()[:12], 16))


def protected(token: str) -> bool:
    return bool(_PROTECTED.search(token))


def noisy(text: str) -> str:
    rng = _rng(text, "R1")
    out = []
    for tok in text.split(" "):
        core = tok.strip(".,:;!?")
        if len(core) >= 4 and core.isalpha() and not protected(tok):
            r = rng.random()
            if r < 0.18:  # swap two inner letters
                i = rng.randrange(1, len(core) - 2)
                core2 = core[:i] + core[i + 1] + core[i] + core[i + 2:]
                tok = tok.replace(core, core2, 1)
            elif r < 0.28:
                tok = tok.lower()
            elif r < 0.34:
                tok = tok.upper()
            elif r < 0.40:  # drop a vowel, SMS style
                m = re.search(r"(?<=\w)[aeiou](?=\w)", core)
                if m:
                    tok = tok.replace(core, core[:m.start()] + core[m.end():], 1)
        out.append(tok)
    s = ""
    for i, tok in enumerate(out):
        sep = "" if i == 0 else ("  " if rng.random() < 0.08 else " ")
        s += sep + tok
    return s


def sentences(text: str) -> list[str]:
    return [p for p in _SENT_SPLIT.split(text.strip()) if p]


def reshuffle(text: str) -> str:
    parts = sentences(text)
    if len(parts) < 2:
        # a single sentence: move the trailing clause to the front
        m = re.search(r",\s+", text)
        return f"{text[m.end():].rstrip('.')} {text[:m.start()]}." if m else text
    rng = _rng(text, "R2")
    order = list(range(len(parts)))
    while order == sorted(order):
        rng.shuffle(order)
    return " ".join(parts[i] if parts[i][-1] in ".!?" else parts[i] + "." for i in order)


# Acronyms and brand names are not shouting; everything else in capitals is.
ACRONYMS = {"BESCOM", "BWSSB", "BWSSBB", "BBPS", "LIC", "ACT", "ICICI", "SBI", "HDFC", "UPI", "KYC", "PAN", "OTP",
            "RWA", "YONO", "NPCI", "FASTAG", "DTH", "PM", "AM", "RR", "ID", "CPAO", "TPLAY", "BP"}


def plain(text: str) -> str:
    def calm(m: re.Match) -> str:
        w = m.group(0)
        return w if protected(w) or w in ACRONYMS else w.capitalize()
    s = re.sub(r"\b[A-Z][A-Z]{2,}\b", calm, text)
    s = re.sub(r"!+", ".", s)
    s = re.sub(r"\.{2,}|…", ".", s)
    s = re.sub(r"\b(immediately|urgently|now|today itself|asap)\b", "", s, flags=re.I)
    s = re.sub(r"\b(Dear|Hello|Hi|Namaskara)\s+[A-Za-z]+(\s+(sir|madam|customer|consumer))?\s*,\s*", "", s, flags=re.I)
    s = re.sub(r"\s+([.,])", r"\1", s)
    s = re.sub(r"[ \t]{2,}", " ", s).strip()
    return "\n".join(sentences(s))  # one fact per line, no flourish


def rewrite(text: str, which: str) -> str:
    return {"R0": lambda t: t, "R1": noisy, "R2": reshuffle, "R3": plain}[which](text)


def all_rewrites(text: str) -> dict[str, str]:
    return {r: rewrite(text, r) for r in REWRITES}


def facts(text: str) -> set[str]:
    """Tokens that must survive every rewrite: amounts, ids, links, UPI ids."""
    return {c for c in (t.strip(".,:;!?()") for t in text.split()) if protected(c)}
