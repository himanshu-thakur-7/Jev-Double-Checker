"""Typed loaders for the message sets and the household biller registry."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .config import DATA

Label = Literal["bill", "scam", "none"]
Action = Literal["pay", "hold", "ignore"]


class Message(BaseModel):
    id: str
    sender: str
    text: str
    set: str = "custom"
    time: str | None = None
    label: Label | None = None
    expected_action: Action | None = None
    biller: str | None = None
    amount: float | None = None
    note: str = ""


class Biller(BaseModel):
    id: str
    name: str
    category: str
    account: str
    headers: list[str] = []
    domains: list[str] = []
    phones: list[str] = []
    upi: list[str] = []
    usual_amount: tuple[float, float]
    pay_via: str
    autopay: bool = False


class Registry(BaseModel):
    household: dict
    billers: list[Biller]

    def by_id(self, biller_id: str) -> Biller | None:
        return next((b for b in self.billers if b.id == biller_id), None)

    @property
    def all_headers(self) -> set[str]:
        return {h.upper() for b in self.billers for h in b.headers}

    @property
    def all_domains(self) -> set[str]:
        return {d.lower() for b in self.billers for d in b.domains}

    def context(self) -> dict:
        """Compact, trusted household context shared with Jev and the LLM."""
        return {
            "billers_on_file": [
                {"name": b.name, "account": b.account, "official_senders": b.headers or b.phones,
                 "official_websites": b.domains, "upi": b.upi, "usual_amount_rs": list(b.usual_amount),
                 "autopay": b.autopay}
                for b in self.billers
            ],
            "family": self.household.get("family_contacts", {}),
        }


def load_jsonl(path: Path) -> list[Message]:
    return [Message(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


@lru_cache
def stage_messages() -> list[Message]:
    return load_jsonl(DATA / "messages" / "stage.jsonl")


def gold_messages() -> list[Message]:
    return [m for m in stage_messages() if m.set == "gold"]


@lru_cache
def registry() -> Registry:
    return Registry(**json.loads((DATA / "billers.json").read_text()))
