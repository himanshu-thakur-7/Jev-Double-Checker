import json

import httpx

from doubletake.gatehook import decide, hook_output, parse_pay_bill


def test_parse_bash_command():
    a = parse_pay_bill("Bash", {"command": 'python pay_bill.py --bill S01 --payee "bescom-bbps.in" --amount 1240'})
    assert a == {"bill_id": "S01", "payee": "bescom-bbps.in", "amount": 1240.0}


def test_non_payment_passes_through():
    assert parse_pay_bill("Bash", {"command": "ls -la"}) is None
    assert decide("Bash", {"command": "ls"}) is None
    assert hook_output(None)["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_direct_tool_call_and_deny_shape():
    def handler(req):
        body = json.loads(req.content)
        assert body["tool_input"]["bill_id"] == "S07"
        return httpx.Response(200, json={"decision": "deny", "reason": "Held for Rahul to review. Do not retry."})
    v = decide("pay_bill", {"bill_id": "S07", "amount": 12480}, client=httpx.Client(transport=httpx.MockTransport(handler)))
    out = hook_output(v)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and out["permissionDecisionReason"].endswith("Do not retry.")


def test_fails_closed_when_gate_unreachable():
    def boom(req):
        raise httpx.ConnectError("down")
    v = decide("pay_bill", {"bill_id": "G01"}, client=httpx.Client(transport=httpx.MockTransport(boom)))
    assert v["decision"] == "deny" and "unreachable" in v["reason"]
