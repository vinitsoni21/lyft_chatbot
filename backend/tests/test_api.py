import os
import tempfile

# Set config BEFORE importing the app
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["LLM_API_KEYS"] = "fake1,fake2"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"

import pytest
from fastapi.testclient import TestClient

from app import llm_service
from app.main import app


def fake_result(text="Paris.", source="LIVE_INFERENCE", key_id="key_1", fallbacks=0):
    return {
        "reply": text,
        "metadata": {
            "resolution_source": source,
            "model": "test-model",
            "latency_ms": 10,
            "input_tokens": 5,
            "output_tokens": 2,
            "key_id": key_id,
            "fallback_attempts": fallbacks,
        },
    }


@pytest.fixture
def client(monkeypatch):
    async def fake_get_reply(messages, simulate=None):
        simulate = simulate or {}
        if simulate.get("*") or all(simulate.get(f"key_{i}") for i in (1, 2)):
            raise llm_service.AllProvidersUnavailable("all providers unavailable")
        if simulate.get("key_1"):
            return fake_result(key_id="key_2", fallbacks=1)
        return fake_result()

    monkeypatch.setattr(llm_service, "get_reply", fake_get_reply)
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_chat_returns_contract_fields(client):
    r = client.post("/chat", json={"session_id": "t1", "message": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "t1"
    assert body["reply"]
    meta = body["metadata"]
    for field in ["resolution_source", "model", "latency_ms", "input_tokens",
                  "output_tokens", "key_id", "fallback_attempts"]:
        assert field in meta


def test_history_saved_in_order(client):
    client.post("/chat", json={"session_id": "t2", "message": "hello"})
    r = client.get("/sessions/t2/messages")
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert "metadata" not in msgs[0]
    assert msgs[1]["metadata"]["input_tokens"] == 5


def test_sessions_are_separate(client):
    client.post("/chat", json={"session_id": "a", "message": "one"})
    client.post("/chat", json={"session_id": "b", "message": "two"})
    assert len(client.get("/sessions/a/messages").json()["messages"]) == 2
    assert client.get("/sessions/a/messages").json()["messages"][0]["content"] == "one"


def test_unknown_session_404(client):
    r = client.get("/sessions/nope/messages")
    assert r.status_code == 404
    assert r.json() == {"detail": "session not found"}


@pytest.mark.parametrize("payload", [
    {"session_id": "x", "message": "   "},
    {"session_id": "x", "message": ""},
    {"session_id": "", "message": "hi"},
    {"session_id": "x", "message": "a" * 4001},
    {"message": "hi"},
    {"session_id": "x"},
])
def test_validation_422(client, payload):
    r = client.post("/chat", json=payload)
    assert r.status_code == 422
    assert "detail" in r.json()


def test_malformed_json_422(client):
    r = client.post("/chat", content="{bad", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_failover_header(client):
    r = client.post("/chat", json={"session_id": "f1", "message": "hi"},
                    headers={"X-Simulate-Failure": "key_1=429"})
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_2"
    assert r.json()["metadata"]["fallback_attempts"] == 1


def test_all_fail_503_and_not_saved(client):
    r = client.post("/chat", json={"session_id": "f2", "message": "hi"},
                    headers={"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert client.get("/sessions/f2/messages").status_code == 404


def test_parse_simulation():
    assert llm_service.parse_simulation("key_1=429,key_2=500") == {"key_1": 429, "key_2": 500}
    assert llm_service.parse_simulation("*=503") == {"*": 503}
    assert llm_service.parse_simulation("key_1=418") == {}
    assert llm_service.parse_simulation(None) == {}