"""Database invariants for approval, checkpoints and local draft idempotency."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentforge.demo import TOOL_NAMES, demo_adapter, demo_registry
from agentforge.models import AgentConfig
from agentforge.runtime import RuntimeEngine, Status


def waiting_run(tmp_path):
    from agentforge.storage import Storage

    store = Storage(tmp_path / "demo.db")
    store.initialize()
    registry = demo_registry(include_purchase=True)
    state = asyncio.run(
        RuntimeEngine(registry, storage=store).run(
            demo_adapter("purchase"),
            "Compare fixture data and propose a draft, wait for approval.",
            config=AgentConfig(allowed_tools=TOOL_NAMES | {"create_purchase_draft"}),
        )
    )
    return store, registry, state


def draft_count(store):
    from agentforge.storage import PurchaseDraftRow

    with Session(store.engine) as session:
        return session.scalar(select(func.count()).select_from(PurchaseDraftRow))


def test_unapproved_write_is_persisted_pending_with_zero_drafts(tmp_path):
    store, _, run = waiting_run(tmp_path)
    assert run.status == "WAITING_APPROVAL"
    assert draft_count(store) == 0
    approvals = store.approvals(run.run_id)
    assert len(approvals) == 1 and approvals[0]["status"] == "PENDING"
    restored = store.get_run(run.run_id)
    assert (
        restored.model_resume_state["pending_calls"][0]["tool_name"]
        == "create_purchase_draft"
    )
    assert restored.model_resume_state["context"][1]["text"].startswith(
        "Compare fixture"
    )
    assert any(e["type"] == "approval.requested" for e in restored.events)


def test_rejection_never_creates_draft(tmp_path):
    store, registry, run = waiting_run(tmp_path)
    approval_id = store.approvals(run.run_id)[0]["approval_id"]
    result = store.decide(run.run_id, approval_id, "reject", registry)
    assert result.run.status == "CANCELLED" and not result.resume
    assert draft_count(store) == 0
    assert store.approvals(run.run_id)[0]["status"] == "REJECTED"


def test_sequential_and_concurrent_approve_create_only_one_draft(tmp_path):
    store, registry, run = waiting_run(tmp_path)
    approval_id = store.approvals(run.run_id)[0]["approval_id"]

    def approve(_):
        return store.decide(run.run_id, approval_id, "approve", registry)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(approve, range(12)))
    assert sum(not result.replayed for result in results) == 1
    assert sum(result.resume for result in results) == 1
    assert draft_count(store) == 1
    assert store.decide(run.run_id, approval_id, "approve", registry).replayed
    assert draft_count(store) == 1


def test_conflicting_decision_is_rejected(tmp_path):
    from agentforge.tools import RuntimeFault

    store, registry, run = waiting_run(tmp_path)
    approval_id = store.approvals(run.run_id)[0]["approval_id"]
    store.decide(run.run_id, approval_id, "reject", registry)
    with pytest.raises(RuntimeFault, match="APPROVAL_CONFLICT"):
        store.decide(run.run_id, approval_id, "approve", registry)
    assert draft_count(store) == 0


def test_waiting_checkpoint_survives_new_storage_instance_and_completes(tmp_path):
    from agentforge.service import restore_adapter
    from agentforge.storage import Storage

    store, registry, run = waiting_run(tmp_path)
    original = store.get_run(run.run_id)
    approval_id = store.approvals(run.run_id)[0]["approval_id"]
    store.close()
    restored_store = Storage(tmp_path / "demo.db")
    restored_store.initialize()
    restored_store.recover()
    restored = restored_store.get_run(run.run_id)
    assert restored.model_resume_state == original.model_resume_state
    assert restored_store.approvals(run.run_id)[0]["approval_id"] == approval_id
    result = restored_store.decide(run.run_id, approval_id, "approve", registry)
    config = AgentConfig.model_validate_json(json.dumps(result.run.config_snapshot))
    done = asyncio.run(
        RuntimeEngine(registry, storage=restored_store).run(
            restore_adapter(result.run),
            original.model_resume_state["context"][1]["text"],
            config=config,
            state=result.run,
            resume=True,
        )
    )
    assert (
        done.status == "COMPLETED"
        and done.model_call_count == 5
        and done.tool_call_count == 8
    )
    assert draft_count(restored_store) == 1
    assert len([e for e in done.events if e["type"] == "run.resumed"]) == 1
    events = restored_store.get_run(run.run_id).events
    assert [e["event_id"] for e in events] == list(range(1, len(events) + 1))
    write_step = next(
        s
        for s in done.steps
        if s.tool_name == "create_purchase_draft" and s.kind == "tool"
    )
    assert all(
        e["step_id"] == write_step.seq
        for e in events
        if e["type"] in {"tool.started", "tool.completed"}
        and e["payload"]["call_id"] == "purchase-draft"
    )


def test_pending_parameter_tampering_never_writes(tmp_path):
    from agentforge.storage import ApprovalRow
    from agentforge.tools import RuntimeFault

    store, registry, run = waiting_run(tmp_path)
    approval_id = store.approvals(run.run_id)[0]["approval_id"]
    with Session(store.engine) as session:
        row = session.get(ApprovalRow, approval_id)
        row.request_payload = {**row.request_payload, "quantity": 1}
        session.commit()
    with pytest.raises(RuntimeFault, match="CHECKPOINT_INVALID"):
        store.decide(run.run_id, approval_id, "approve", registry)
    assert draft_count(store) == 0


def test_write_and_decision_roll_back_together(tmp_path, monkeypatch):
    store, registry, run = waiting_run(tmp_path)
    approval_id = store.approvals(run.run_id)[0]["approval_id"]
    original = store._insert_draft

    def crash_after_insert(*args):
        original(*args)
        raise RuntimeError("simulated failure before commit")

    monkeypatch.setattr(store, "_insert_draft", crash_after_insert)
    with pytest.raises(RuntimeError, match="before commit"):
        store.decide(run.run_id, approval_id, "approve", registry)
    assert draft_count(store) == 0
    assert store.approvals(run.run_id)[0]["status"] == "PENDING"
    assert store.get_run(run.run_id).status == "WAITING_APPROVAL"
    monkeypatch.setattr(store, "_insert_draft", original)
    store.decide(run.run_id, approval_id, "approve", registry)
    assert draft_count(store) == 1


def test_unknown_write_outcome_requires_reconciliation_without_replay(tmp_path):
    from agentforge.tools import RuntimeFault

    store, registry, run = waiting_run(tmp_path)
    run.transition(Status.RUNNING)
    run.invocations[-1].status = "RUNNING"
    run.model_resume_state["safe_point"] = "IN_FLIGHT"
    store.save(run)
    store.recover()
    recovered = store.get_run(run.run_id)
    assert (
        recovered.status == "RECONCILIATION_REQUIRED"
        and recovered.stop_reason == "WRITE_OUTCOME_UNKNOWN"
    )
    assert draft_count(store) == 0
    with pytest.raises(RuntimeFault, match="UNSAFE_RESUME_POINT"):
        store.claim_resume(run.run_id)
    with pytest.raises(RuntimeFault, match="APPROVAL_CONFLICT"):
        store.decide(
            run.run_id,
            store.approvals(run.run_id)[0]["approval_id"],
            "approve",
            registry,
        )
    assert store.approvals(pending_only=True) == []


def test_confirmed_local_write_checkpoint_can_resume_without_repeating_write(tmp_path):
    from agentforge.service import restore_adapter

    store, registry, run = waiting_run(tmp_path)
    store.decide(
        run.run_id, store.approvals(run.run_id)[0]["approval_id"], "approve", registry
    )
    store.recover()
    assert store.get_run(run.run_id).status == "INTERRUPTED"
    state = store.claim_resume(run.run_id)
    config = AgentConfig.model_validate_json(json.dumps(state.config_snapshot))
    completed = asyncio.run(
        RuntimeEngine(registry, storage=store).run(
            restore_adapter(state), "resume", config=config, state=state, resume=True
        )
    )
    assert completed.status == "COMPLETED" and draft_count(store) == 1


def test_terminal_run_is_never_resumed(tmp_path):
    from agentforge.tools import RuntimeFault

    store, registry, run = waiting_run(tmp_path)
    store.decide(
        run.run_id, store.approvals(run.run_id)[0]["approval_id"], "reject", registry
    )
    with pytest.raises(RuntimeFault, match="UNSAFE_RESUME_POINT"):
        store.claim_resume(run.run_id)
    assert store.get_run(run.run_id).status == "CANCELLED" and draft_count(store) == 0


def test_draft_has_real_database_uniqueness_constraints(tmp_path):
    from sqlalchemy import inspect

    store, registry, run = waiting_run(tmp_path)
    store.decide(
        run.run_id, store.approvals(run.run_id)[0]["approval_id"], "approve", registry
    )
    keys = {
        tuple(c["column_names"])
        for c in inspect(store.engine).get_unique_constraints("purchase_drafts")
    }
    assert {("approval_id",), ("idempotency_key",), ("run_id", "call_id")} <= keys
    assert draft_count(store) == 1


@pytest.mark.parametrize(
    "source,target",
    [
        ("CREATED", "RUNNING"),
        ("RUNNING", "WAITING_APPROVAL"),
        ("WAITING_APPROVAL", "RUNNING"),
        ("WAITING_APPROVAL", "CANCELLED"),
        ("RUNNING", "INTERRUPTED"),
        ("RUNNING", "RECONCILIATION_REQUIRED"),
        ("INTERRUPTED", "RUNNING"),
        ("RECONCILIATION_REQUIRED", "FAILED"),
    ],
)
def test_allowed_state_transitions(source, target):
    from agentforge.runtime import RunState

    state = RunState(status=Status(source))
    state.transition(Status(target))
    assert state.status == target


@pytest.mark.parametrize(
    "source,target",
    [
        ("COMPLETED", "RUNNING"),
        ("FAILED", "RUNNING"),
        ("CANCELLED", "RUNNING"),
        ("CREATED", "COMPLETED"),
        ("WAITING_APPROVAL", "COMPLETED"),
        ("RECONCILIATION_REQUIRED", "RUNNING"),
    ],
)
def test_forbidden_state_transitions(source, target):
    from agentforge.runtime import RunState
    from agentforge.tools import RuntimeFault

    state = RunState(status=Status(source))
    with pytest.raises(RuntimeFault, match="INVALID_STATE_TRANSITION"):
        state.transition(Status(target))
    assert state.status == source


def test_corrupted_waiting_checkpoint_fails_closed_on_startup(tmp_path):
    from agentforge.storage import RunRow

    store, _, run = waiting_run(tmp_path)
    with Session(store.engine) as session:
        row = session.get(RunRow, run.run_id)
        payload = json.loads(json.dumps(row.model_resume_state))
        payload["context"][1]["text"] = "changed task"
        row.model_resume_state = payload
        session.commit()
    store.recover()
    assert store.get_run(run.run_id).status == "FAILED"
    assert store.get_run(run.run_id).stop_reason == "CHECKPOINT_INVALID"
    assert draft_count(store) == 0


def test_trace_redacts_secrets_and_pii_without_mangling_digest():
    from agentforge.redaction import redact, trace_summary

    value = {
        "api_key": "secret",
        "email": "person@example.com",
        "notes": "Bearer secret-token and +8613812345678",
        "args_digest": "abcdef13812345678ff",
    }
    redacted = redact(value)
    assert redacted["api_key"] == redacted["email"] == "[REDACTED]"
    assert (
        "secret-token" not in redacted["notes"]
        and "13812345678" not in redacted["notes"]
    )
    assert redacted["args_digest"] == value["args_digest"]
    assert "secret" not in trace_summary({"supplier": "A", "unknown": "secret"})


def test_trace_tables_store_redacted_summaries_not_private_tool_data(tmp_path):
    from agentforge.models import (
        DeterministicMockAdapter,
        ModelReply,
        StrictModel,
        ToolCall,
    )
    from agentforge.storage import EventRow, StepRow, Storage
    from agentforge.tools import ToolDefinition, ToolRegistry

    class Args(StrictModel):
        value: str

    secret = "sk-proj-" + "x" * 24

    async def echo(args):
        return {
            "api_key": secret,
            "email": "person@example.com",
            "supplier": "A",
            "unknown": args.value,
        }

    registry = ToolRegistry((ToolDefinition("echo", "test-only", Args, echo),))
    store = Storage(tmp_path / "redaction.db")
    store.initialize()
    script = DeterministicMockAdapter(
        (
            ModelReply(
                calls=(
                    ToolCall(
                        call_id="echo-1",
                        tool_name="echo",
                        arguments={"value": "PRIVATE_VALUE"},
                    ),
                )
            ),
            ModelReply(final_text="done"),
        )
    )
    run = asyncio.run(
        RuntimeEngine(registry, storage=store).run(
            script,
            "synthetic task",
            config=AgentConfig(allowed_tools=frozenset({"echo"})),
        )
    )
    assert run.status == "COMPLETED"
    with Session(store.engine) as session:
        raw_trace = json.dumps(
            [row.data for row in session.scalars(select(EventRow))]
            + [row.data for row in session.scalars(select(StepRow))]
        )
        assert (
            secret not in raw_trace
            and "person@example.com" not in raw_trace
            and "PRIVATE_VALUE" not in raw_trace
        )
        assert "[REDACTED]" in raw_trace and "supplier" in raw_trace


def test_resume_cannot_replace_frozen_configuration(tmp_path):
    from agentforge.models import Limits
    from agentforge.service import restore_adapter
    from agentforge.tools import RuntimeFault

    store, registry, run = waiting_run(tmp_path)
    state = store.decide(
        run.run_id, store.approvals(run.run_id)[0]["approval_id"], "approve", registry
    ).run
    wrong = AgentConfig(
        allowed_tools=TOOL_NAMES | {"create_purchase_draft"},
        limits=Limits(max_steps=99),
    )
    with pytest.raises(RuntimeFault, match="CHECKPOINT_INVALID"):
        asyncio.run(
            RuntimeEngine(registry, storage=store).run(
                restore_adapter(state), "resume", state=state, config=wrong, resume=True
            )
        )
    assert draft_count(store) == 1 and store.get_run(run.run_id).model_call_count == 4


def test_newer_schema_is_rejected_without_dropping_data(tmp_path):
    from agentforge.storage import Storage
    from agentforge.tools import RuntimeFault

    store, _, run = waiting_run(tmp_path)
    with store.engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA user_version=99")
    with pytest.raises(RuntimeFault, match="UNSUPPORTED_DB_SCHEMA"):
        Storage(store.path).initialize()
    assert (
        store.get_run(run.run_id).status == "WAITING_APPROVAL"
        and draft_count(store) == 0
    )
