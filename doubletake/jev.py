"""Async client for TypeSafe's System One API (Jev).

One request carries many typed questions about one state; Jev answers them in parallel.
Every call reports usage, latency and cost so the stage can show what each check cost.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import config

RETRY_STATUSES = {429, 500, 502, 503, 529}


class JevError(RuntimeError):
    pass


@dataclass
class JevResult:
    model: str
    answers: dict[str, dict[str, Any]]
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float
    raw: dict[str, Any] = field(repr=False, default_factory=dict)


def choice(instructions: Any, criteria: dict[str, Any]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def noul(instructions: Any, true: str | None = None, false: str | None = None) -> dict:
    q: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if true or false:
        q["criteria"] = {k: v for k, v in (("true", true), ("false", false)) if v}
    return q


def cost_of(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * config.JEV_PRICE_IN_PER_M + output_tokens * config.JEV_PRICE_OUT_PER_M) / 1e6


class JevClient:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 base_url: str | None = None, max_retries: int = 3, timeout: float = 20.0,
                 client: httpx.AsyncClient | None = None):
        self.api_key = api_key or config.TYPESAFE_API_KEY
        self.model = model or config.JEV_MODEL
        self.url = (base_url or config.TYPESAFE_API_BASE).rstrip("/") + "/v1/systemone"
        self.max_retries = max_retries
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def aclose(self):
        await self._client.aclose()

    async def ask(self, state: Any, questions: dict[str, dict]) -> JevResult:
        if not self.api_key:
            raise JevError("TYPESAFE_API_KEY is not set")
        body = {"model": self.model, "state": state, "questions": questions}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        delay = 0.5
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = await self._client.post(self.url, json=body, headers=headers)
            except httpx.TransportError as e:
                if attempt == self.max_retries:
                    raise JevError(f"Jev transport error: {e}") from e
            else:
                latency = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    usage = data.get("usage", {})
                    it, ot = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
                    return JevResult(model=data.get("model", self.model), answers=data["answers"],
                                     input_tokens=it, output_tokens=ot, latency_ms=latency,
                                     cost_usd=cost_of(it, ot), raw=data)
                if resp.status_code not in RETRY_STATUSES or attempt == self.max_retries:
                    raise JevError(f"Jev HTTP {resp.status_code}: {resp.text[:300]}")
            await asyncio.sleep(delay)
            delay *= 2
        raise JevError("unreachable")


def top_prob(answer: dict) -> float:
    """Probability of the chosen option (choice) or P(yes) (noul)."""
    if answer["type"] == "noul":
        return float(answer["noul"])
    return float(answer["probabilities"][answer["choice"]])
