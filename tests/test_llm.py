import json

import httpx
import pytest
import respx

from doubletake.llm import LLMClient, LLMError, build_input

URL = "https://api.openai.com/v1/responses"


def resp(payload):
    return {"model": "gpt-6-sol", "usage": {"input_tokens": 300, "output_tokens": 40},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(payload)}]}]}


@respx.mock
async def test_review_parses_structured_output():
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=resp(
        {"verdict": "legitimate", "action": "pay", "scam_probability": 0.05, "reason": "Routine reminder."})))
    op = await LLMClient(api_key="k").review("AX-BESCOM", "bill text", {"billers": ["BESCOM"]})
    assert op.agrees_pay and op.reason == "Routine reminder."
    assert op.cost_usd == pytest.approx((300 * 2 + 40 * 10) / 1e6)
    body = json.loads(route.calls[0].request.content)
    assert body["model"] == "gpt-6-sol"
    assert body["text"]["format"]["strict"] is True
    assert "Sender: AX-BESCOM" in body["input"]


@respx.mock
async def test_scam_verdict_and_clamping():
    respx.post(URL).mock(return_value=httpx.Response(200, json=resp(
        {"verdict": "scam", "action": "hold", "scam_probability": 1.4, "reason": "Lookalike link."})))
    op = await LLMClient(api_key="k").review("VK-BESCMS", "x")
    assert not op.agrees_pay and op.scam_probability == 1.0


@respx.mock
async def test_http_error():
    respx.post(URL).mock(return_value=httpx.Response(400, json={"error": "bad"}))
    with pytest.raises(LLMError, match="400"):
        await LLMClient(api_key="k").review("a", "b")


def test_build_input_marks_untrusted():
    s = build_input("S", "T")
    assert "untrusted" in s and "Household context" not in s
