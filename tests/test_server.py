import pytest
from fastapi.testclient import TestClient

from server import app as appmod


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "GATE_LOG", tmp_path / "gate.jsonl")
    appmod.S.gate_log.clear()
    with TestClient(appmod.app) as c:
        yield c


def test_messages_are_cached(client):
    r = client.get("/api/messages").json()
    assert r["count"] == 30 and r["cached"] == 30
    g01 = next(m for m in r["messages"] if m["id"] == "G01")
    assert g01["decisions"]["double_take"] == "pay"


def test_examination_from_cache(client):
    ex = client.get("/api/examine/S01").json()
    assert ex["from_cache"] and len(ex["grid"]) == 4 and ex["reasks"] == 35
    assert client.get("/api/examine/NOPE").status_code == 404


def test_ledger_modes(client):
    led = client.get("/api/ledger").json()
    assert set(led["modes"]) == {"jev_only", "jev_llm", "double_take"}
    dt = led["modes"]["double_take"]
    assert dt["scams_paid"] == 0 and dt["llm_usd"] > 0
    assert led["modes"]["jev_only"]["llm_usd"] == 0


def test_gate_allows_real_bill_and_denies_scam(client):
    ok = client.post("/api/gate", json={"tool_name": "pay_bill", "tool_input": {"bill_id": "G01", "amount": 1240}}).json()
    assert ok["decision"] == "allow"
    no = client.post("/api/gate", json={"tool_input": {"bill_id": "S01", "amount": 1240}}).json()
    assert no["decision"] == "deny" and no["reason"].endswith("Do not retry.")
    wrong_amt = client.post("/api/gate", json={"tool_input": {"bill_id": "G01", "amount": 9999}}).json()
    assert wrong_amt["decision"] == "deny" and "differs" in wrong_amt["reason"]
    log = client.get("/api/gate/log").json()["entries"]
    assert [e["decision"] for e in log] == ["allow", "deny", "deny"]


def test_gate_requires_reference(client):
    assert client.post("/api/gate", json={"tool_input": {}}).status_code == 422


def test_pages(client):
    assert client.get("/").status_code == 200 and client.get("/eval").status_code == 200


def test_latest_run_available(client):
    r = client.get("/api/runs/latest").json()
    assert r["messages"] == 328 and "double_take_jev" in r["all"]


def test_agent_run_needs_key_and_clears_log(client, monkeypatch):
    client.post("/api/gate", json={"tool_input": {"bill_id": "G01", "amount": 1240}})
    monkeypatch.setattr(appmod.config, "OPENAI_API_KEY", "")
    assert client.post("/api/agent/run").status_code == 503

    async def fake_run(url):
        return {"runner": "fake", "final": "done", "calls": []}
    monkeypatch.setattr(appmod.config, "OPENAI_API_KEY", "k")
    import doubletake.agent as agent
    monkeypatch.setattr(agent, "run", fake_run)
    r = client.post("/api/agent/run").json()
    assert r["runner"] == "fake"
    assert client.get("/api/gate/log").json()["entries"] == []
