import httpx
import pytest
import respx

from doubletake.jev import JevClient, JevError, choice, cost_of, noul

URL = "https://api.typesafe.ai/v1/systemone"
OK = {"model": "jev-1.13.0",
      "answers": {"act": {"type": "choice", "choice": "hold", "confidence": 0.68,
                          "probabilities": {"hold": 0.79, "ignore": 0.09, "pay": 0.12}},
                  "scam": {"type": "noul", "noul": 0.85}},
      "usage": {"input_tokens": 392, "output_tokens": 56}}


def client():
    return JevClient(api_key="k", model="jev-1.13.0")


@respx.mock
async def test_ask_parses_answers_and_cost():
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=OK))
    r = await client().ask("msg", {"act": choice("q", {"pay": "p", "hold": "h", "ignore": None}),
                                   "scam": noul("scam?")})
    assert r.answers["act"]["choice"] == "hold"
    assert r.answers["scam"]["noul"] == 0.85
    assert r.cost_usd == pytest.approx(392 * 0.042 / 1e6)
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer k"
    assert b'"model":"jev-1.13.0"' in sent.content.replace(b" ", b"")


@respx.mock
async def test_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", lambda s: _noop())
    respx.post(URL).mock(side_effect=[httpx.Response(429), httpx.Response(529), httpx.Response(200, json=OK)])
    r = await client().ask("msg", {"scam": noul("scam?")})
    assert r.input_tokens == 392


@respx.mock
async def test_422_raises_without_retry():
    route = respx.post(URL).mock(return_value=httpx.Response(422, json={"detail": "bad"}))
    with pytest.raises(JevError, match="422"):
        await client().ask("msg", {"scam": noul("scam?")})
    assert route.call_count == 1


def test_noul_criteria_and_cost():
    assert noul("q", true="yes")["criteria"] == {"true": "yes"}
    assert "criteria" not in noul("q")
    assert cost_of(1_000_000, 500) == pytest.approx(0.042)


async def _noop():
    return None
