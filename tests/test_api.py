"""HTTP contracts and actual Runtime executions, without a model API key."""

import time

import pytest
from fastapi.testclient import TestClient

from agentforge.api import create_app


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as client:
        yield client


def completed_run(client, **overrides):
    response = client.post(
        "/api/runs",
        json={"agent_id": "procurement-demo", "input": "synthetic demo", **overrides},
    )
    assert response.status_code == 202, response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    run_id = response.json()["data"]["run_id"]
    for _ in range(150):
        run = client.get(f"/api/runs/{run_id}").json()["data"]
        if run["status"] not in {"CREATED", "RUNNING"}:
            return run
        time.sleep(0.05)
    pytest.fail("Run did not terminate in time")


def test_api_mock_run_executes_two_tools_and_exposes_steps_and_events(client):
    run = completed_run(client)
    assert run["mode"] == "mock" and run["status"] == "COMPLETED"
    assert (run["model_call_count"], run["tool_call_count"], run["stop_reason"]) == (
        3,
        2,
        "FINAL_ANSWER",
    )
    assert run["cost"] is None
    steps = client.get(f"/api/runs/{run['run_id']}/steps").json()["data"]
    assert [s["tool_name"] for s in steps if s["kind"] == "tool"] == [
        "list_supplier_quotes",
        "get_supplier_detail",
    ]
    events = client.get(f"/api/runs/{run['run_id']}/events").json()["data"]
    assert all(e["mode"] == "mock" for e in events)
    cursor = events[2]["event_id"]
    after = client.get(
        f"/api/runs/{run['run_id']}/events?after_event_id={cursor}"
    ).json()["data"]
    assert after == [e for e in events if e["event_id"] > cursor]


def test_api_can_run_real_mcp_tools(client):
    run = completed_run(client, agent_id="mcp-demo", mock_scenario="mcp")
    assert run["status"] == "COMPLETED" and run["tool_call_count"] == 2
    steps = client.get(f"/api/runs/{run['run_id']}/steps").json()["data"]
    assert all(s["tool_name"].startswith("mcp_") for s in steps if s["kind"] == "tool")


def test_api_missing_live_configuration_is_readable(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    response = client.post(
        "/api/runs",
        json={"agent_id": "procurement-demo", "input": "task", "mode": "live"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LIVE_NOT_CONFIGURED"
    assert "Traceback" not in response.text


def test_create_agent_and_enforce_its_allowlist(client):
    created = client.post("/api/agents", json={"name": "No tools", "allowed_tools": []})
    assert created.status_code == 201
    agent = created.json()["data"]
    assert (
        client.get(f"/api/agents/{agent['id']}").json()["data"]["allowed_tools"] == []
    )
    run = completed_run(client, agent_id=agent["id"])
    assert (
        run["status"] == "FAILED"
        and run["stop_reason"] == "TOOL_FORBIDDEN"
        and run["tool_call_count"] == 0
    )


@pytest.mark.parametrize(
    "body",
    [
        {"name": "bad", "allowed_tools": ["shell"]},
        {"name": "bad", "limits": {"max_steps": 0}},
        {"name": "bad", "api_key": "PRIVATE_INPUT"},
    ],
)
def test_invalid_agent_requests_are_sanitized(client, body):
    response = client.post("/api/agents", json=body)
    assert response.status_code == 422
    assert set(response.json()) == {"error"}
    assert (
        "PRIVATE_INPUT" not in response.text and "ValidationError" not in response.text
    )


def test_openapi_metadata_and_schema(client):
    spec = client.get("/openapi.json").json()
    for route in (
        "/health",
        "/api/agents",
        "/api/tools",
        "/api/runs",
        "/api/runs/{run_id}",
        "/api/runs/{run_id}/steps",
        "/api/runs/{run_id}/events",
    ):
        assert route in spec["paths"]
    assert "202" in spec["paths"]["/api/runs"]["post"]["responses"]
    assert "503" in spec["paths"]["/api/runs"]["post"]["responses"]
    metadata = client.get("/api/tools").json()["data"]
    assert len(metadata) == 5 and {t["source"] for t in metadata} == {"local", "mcp"}
    assert all(t["permission"] == "READ_ONLY" for t in metadata)
    health = client.get("/health").json()["data"]
    assert health["mcp_protocol"] == "2026-07-28" and health["storage"] == "memory"


def test_not_found_and_invalid_cursor_use_error_envelope(client):
    response = client.get("/api/runs/missing")
    assert (
        response.status_code == 404
        and response.json()["error"]["code"] == "RUN_NOT_FOUND"
    )
    response = client.get("/api/runs/missing/events?after_event_id=-1")
    assert response.status_code == 422 and response.json()["error"]["request_id"]


def test_empty_live_environment_does_not_break_agent_creation(client, monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    response = client.post(
        "/api/agents", json={"name": "Live unconfigured", "model_adapter": "openai"}
    )
    assert (
        response.status_code == 201
        and response.json()["data"]["model_name"] == "not_configured"
    )
    assert client.get("/health").json()["data"]["live_configured"] is False


def test_invalid_host_is_structured(client):
    response = client.get("/health", headers={"Host": "untrusted.invalid"})
    assert (
        response.status_code == 400
        and response.json()["error"]["code"] == "INVALID_HOST"
    )
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
