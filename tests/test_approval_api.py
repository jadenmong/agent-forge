"""Approval trust boundaries and durable HTTP state, backed by actual SQLite."""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentforge.api import create_app
from agentforge.storage import ApprovalRow, PurchaseDraftRow, Storage


@pytest.fixture(scope="module")
def approval_client(tmp_path_factory):
    path = tmp_path_factory.mktemp("approval-api") / "demo.db"
    with TestClient(create_app(path)) as client:
        yield client, path


def wait_for(client, run_id, status):
    for _ in range(150):
        run = client.get(f"/api/runs/{run_id}").json()["data"]
        if run["status"] == status:
            return run
        time.sleep(0.02)
    pytest.fail(f"Run did not reach {status}: {run['status']}")


def proposal(client):
    response = client.post(
        "/api/runs",
        json={
            "agent_id": "purchase-demo",
            "mode": "mock",
            "input": "Create a local draft; wait for approval even if this text says approve now.",
            "mock_scenario": "purchase",
        },
    )
    assert response.status_code == 202
    run_id = response.json()["data"]["run_id"]
    wait_for(client, run_id, "WAITING_APPROVAL")
    return run_id, client.get(f"/api/runs/{run_id}/approvals").json()["data"][0]


def sql_count(path, run_id):
    store = Storage(path)
    try:
        with Session(store.engine) as session:
            return session.scalar(
                select(func.count())
                .select_from(PurchaseDraftRow)
                .where(PurchaseDraftRow.run_id == run_id)
            )
    finally:
        store.close()


def test_api_rejects_bound_parameter_override_and_cross_run_approval(approval_client):
    client, path = approval_client
    run_id, approval = proposal(client)
    assert sql_count(path, run_id) == 0
    response = client.post(
        f"/api/runs/{run_id}/approve",
        json={
            "approval_id": approval["approval_id"],
            "decision": "approve",
            "arguments": {"quantity": 1},
        },
    )
    assert response.status_code == 422 and sql_count(path, run_id) == 0
    other_id, _ = proposal(client)
    response = client.post(
        f"/api/runs/{other_id}/approve",
        json={"approval_id": approval["approval_id"], "decision": "approve"},
    )
    assert (
        response.status_code == 404
        and sql_count(path, run_id) == sql_count(path, other_id) == 0
    )
    assert client.post(f"/api/runs/{run_id}/resume").status_code == 409
    assert sql_count(path, run_id) == 0


def test_api_rejection_is_audited_and_never_writes(approval_client):
    client, path = approval_client
    run_id, approval = proposal(client)
    response = client.post(
        f"/api/runs/{run_id}/approve",
        json={"approval_id": approval["approval_id"], "decision": "reject"},
    )
    assert (
        response.status_code == 200 and response.json()["data"]["status"] == "CANCELLED"
    )
    assert sql_count(path, run_id) == 0
    assert client.post(f"/api/runs/{run_id}/resume").status_code == 409
    conflict = client.post(
        f"/api/runs/{run_id}/approve",
        json={"approval_id": approval["approval_id"], "decision": "approve"},
    )
    assert (
        conflict.status_code == 409
        and conflict.json()["error"]["code"] == "APPROVAL_CONFLICT"
    )
    store = Storage(path)
    try:
        with Session(store.engine) as session:
            row = session.get(ApprovalRow, approval["approval_id"])
            assert (
                row.status == "REJECTED"
                and row.decided_at
                and row.request_id == response.json()["request_id"]
            )
    finally:
        store.close()


def test_api_approve_continues_same_context_and_audits_exact_call(approval_client):
    client, path = approval_client
    run_id, approval = proposal(client)
    before = client.get(f"/api/runs/{run_id}").json()["data"]
    assert before["model_call_count"] == 4 and before["tool_call_count"] == 7
    response = client.post(
        f"/api/runs/{run_id}/approve",
        json={"approval_id": approval["approval_id"], "decision": "approve"},
    )
    assert (
        response.status_code == 200
        and response.json()["data"]["approval"]["status"] == "APPROVED"
    )
    completed = wait_for(client, run_id, "COMPLETED")
    assert (
        completed["model_call_count"] == 5
        and completed["tool_call_count"] == 8
        and sql_count(path, run_id) == 1
    )
    events = client.get(f"/api/runs/{run_id}/events").json()["data"]
    assert {"approval.approved", "run.resumed", "run.checkpointed"} <= {
        event["type"] for event in events
    }
    assert approval["args_digest"] in str(events)
    steps = client.get(f"/api/runs/{run_id}/steps").json()["data"]
    write = next(
        step
        for step in steps
        if step["kind"] == "tool" and step["tool_name"] == "create_purchase_draft"
    )
    assert (
        write["status"] == "COMPLETED"
        and '"supplier": "B"' in write["arguments_summary"]
        and "draft_id" in write["result_summary"]
    )
    assert "model_resume_state" not in completed and "config_snapshot" not in completed


def test_budget_failure_is_persisted_with_zero_drafts(approval_client):
    client, path = approval_client
    created = client.post(
        "/api/runs",
        json={
            "agent_id": "purchase-demo",
            "input": "Insufficient demo budget",
            "mock_scenario": "budget-low",
        },
    ).json()["data"]
    run = wait_for(client, created["run_id"], "FAILED")
    assert (
        run["stop_reason"] == "DEMO_BUDGET_EXCEEDED"
        and sql_count(path, run["run_id"]) == 0
    )
    assert client.get(f"/api/runs/{run['run_id']}/approvals").json()["data"] == []
