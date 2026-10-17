"""Regression tests for the explicit Day 1 delivery requirements."""

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentforge import demo
from agentforge.demo import demo_adapter, demo_registry
from agentforge.models import (
    AgentConfig,
    DeterministicMockAdapter,
    Limits,
    ModelReply,
    RunStep,
    ToolCall,
    ToolResult,
)
from agentforge.runtime import RunState, RuntimeEngine, Status
from agentforge.tools import RuntimeFault


def test_model_call_limit_stops_repeated_requests():
    replies = tuple(
        ModelReply(
            calls=(
                ToolCall(
                    call_id=f"repeat-{i}",
                    tool_name="list_supplier_quotes",
                    arguments={},
                ),
            )
        )
        for i in range(5)
    )
    run = asyncio.run(
        RuntimeEngine(demo_registry()).run(
            DeterministicMockAdapter(replies),
            "repeat",
            config=AgentConfig(
                allowed_tools=frozenset({"list_supplier_quotes"}),
                limits=Limits(max_steps=8, max_model_calls=2),
            ),
        )
    )
    assert run.stop_reason == "MAX_MODEL_CALLS"
    assert run.model_call_count == 2 and run.tool_call_count == 2


def test_required_fixture_exists():
    assert (
        Path(__file__).resolve().parents[1] / "examples/procurement/fixtures.json"
    ).is_file()


@pytest.mark.parametrize(
    "scenario,status,reason,model_calls,tool_calls",
    [
        ("direct", Status.COMPLETED, "FINAL_ANSWER", 1, 0),
        ("single-tool", Status.COMPLETED, "FINAL_ANSWER", 2, 1),
        ("two-tools", Status.COMPLETED, "FINAL_ANSWER", 3, 2),
        ("unknown-tool", Status.FAILED, "UNKNOWN_TOOL", 1, 0),
        ("tool-error", Status.FAILED, "TOOL_ERROR", 1, 1),
    ],
)
def test_builtin_mock_scenarios(scenario, status, reason, model_calls, tool_calls):
    run = asyncio.run(
        RuntimeEngine(demo_registry(simulate_tool_error=scenario == "tool-error")).run(
            demo_adapter(scenario),
            "scenario",
            config=AgentConfig(allowed_tools=demo.TOOL_NAMES),
        )
    )
    assert (run.status, run.stop_reason) == (status, reason)
    assert (run.model_call_count, run.tool_call_count) == (model_calls, tool_calls)
    assert len(run.steps) == model_calls + tool_calls
    assert all(step.status != "RUNNING" and step.duration_ms >= 0 for step in run.steps)
    assert [step.seq for step in run.steps] == list(range(1, len(run.steps) + 1))
    if scenario == "tool-error":
        assert run.steps[-1].error_code == "TOOL_ERROR"
        assert any(e["type"] == "tool.failed" for e in run.events)


@pytest.mark.parametrize(
    "limits,reason",
    [
        (Limits(max_steps=2, max_model_calls=8), "MAX_STEPS"),
        (Limits(max_steps=8, max_model_calls=2), "MAX_MODEL_CALLS"),
        (Limits(max_steps=8, max_model_calls=8, max_tool_calls=2), "MAX_TOOL_CALLS"),
    ],
)
def test_endless_mock_is_terminated_at_each_limit(limits, reason):
    async def check():
        return await asyncio.wait_for(
            RuntimeEngine(demo_registry()).run(
                demo_adapter("repeat"),
                "repeat",
                config=AgentConfig(allowed_tools=demo.TOOL_NAMES, limits=limits),
            ),
            timeout=2,
        )

    run = asyncio.run(check())
    assert run.status == Status.FAILED and run.stop_reason == reason
    assert run.tool_call_count == 2
    call_ids = [step.call_id for step in run.steps if step.kind == "tool"]
    assert len(set(call_ids)) == 2
    assert not any(e["payload"].get("code") == "DUPLICATE_CALL_ID" for e in run.events)
    if reason == "MAX_MODEL_CALLS":
        assert run.model_call_count == 2
    assert run.events[-2]["payload"]["code"] == reason


def test_model_call_limit_allows_final_response_at_boundary():
    run = asyncio.run(
        RuntimeEngine(demo_registry()).run(
            demo_adapter("direct"),
            "direct",
            config=AgentConfig(limits=Limits(max_model_calls=1)),
        )
    )
    assert run.status == Status.COMPLETED and run.model_call_count == 1


def test_serial_tools_return_results_before_next_model_call():
    class InspectAdapter:
        async def respond(self, context, tools):
            results = [item for item in context if item["kind"] == "tool_result"]
            if not results:
                return ModelReply(
                    calls=(
                        ToolCall(
                            call_id="quotes",
                            tool_name="list_supplier_quotes",
                            arguments={},
                        ),
                    )
                )
            if len(results) == 1:
                assert (
                    results[0]["call_id"] == "quotes" and len(results[0]["result"]) == 3
                )
                return ModelReply(
                    calls=(
                        ToolCall(
                            call_id="cost",
                            tool_name="calculate_total_cost",
                            arguments={
                                "unit_price_cents": results[0]["result"][0][
                                    "unit_price_cents"
                                ],
                                "quantity": 20,
                            },
                        ),
                    )
                )
            assert results[1]["call_id"] == "cost"
            return ModelReply(final_text=str(results[1]["result"]["total_cents"]))

    run = asyncio.run(
        RuntimeEngine(demo_registry()).run(
            InspectAdapter(),
            "calculate",
            config=AgentConfig(allowed_tools=demo.TOOL_NAMES),
        )
    )
    assert run.output == "1900000"
    assert [s.kind for s in run.steps] == ["model", "tool", "model", "tool", "model"]


def test_tools_load_actual_fixture_values(tmp_path, monkeypatch):
    fixture = json.loads(demo.FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture["suppliers"][0].update(unit_price_cents=12345, delivery_days=9)
    custom = tmp_path / "fixtures.json"
    custom.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setattr(demo, "FIXTURE_PATH", custom)

    async def check():
        registry = demo_registry()
        quotes = await registry.dispatch(
            ToolCall(call_id="q", tool_name="list_supplier_quotes", arguments={}),
            demo.TOOL_NAMES,
        )
        detail = await registry.dispatch(
            ToolCall(
                call_id="d",
                tool_name="get_supplier_detail",
                arguments={"supplier": "A"},
            ),
            demo.TOOL_NAMES,
        )
        cost = await registry.dispatch(
            ToolCall(
                call_id="c",
                tool_name="calculate_total_cost",
                arguments={
                    "unit_price_cents": quotes.result[0]["unit_price_cents"],
                    "quantity": fixture["quantity"],
                },
            ),
            demo.TOOL_NAMES,
        )
        assert isinstance(quotes, ToolResult)
        assert detail.result["delivery_days"] == 9
        assert cost.result == {"total_cents": 246900}

    asyncio.run(check())


@pytest.mark.parametrize(
    "fault", ["malformed-json", "negative-price", "duplicate-supplier"]
)
def test_invalid_fixture_is_rejected(tmp_path, monkeypatch, fault):
    fixture = json.loads(demo.FIXTURE_PATH.read_text(encoding="utf-8"))
    if fault == "negative-price":
        fixture["suppliers"][0]["unit_price_cents"] = -1
    if fault == "duplicate-supplier":
        fixture["suppliers"][1]["supplier"] = "A"
    custom = tmp_path / "fixtures.json"
    custom.write_text(
        "{" if fault == "malformed-json" else json.dumps(fixture), encoding="utf-8"
    )
    monkeypatch.setattr(demo, "FIXTURE_PATH", custom)
    with pytest.raises(ValidationError):
        demo.load_fixtures()


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_model_calls", 0),
        ("max_model_calls", 101),
        ("max_model_calls", "2"),
        ("model_adapter", "live"),
    ],
)
def test_configuration_rejects_unsupported_values(field, value):
    with pytest.raises(ValidationError):
        if field == "max_model_calls":
            AgentConfig(limits=Limits(**{field: value}))
        else:
            AgentConfig(**{field: value})


def test_cancellation_preserves_observable_state_and_steps():
    started = asyncio.Event()
    state = RunState()

    class SlowAdapter:
        async def respond(self, context, tools):
            started.set()
            await asyncio.sleep(10)

    async def check():
        task = asyncio.create_task(
            RuntimeEngine(demo_registry()).run(SlowAdapter(), "cancel", state=state)
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(check())
    assert (state.status, state.stop_reason, state.model_call_count) == (
        Status.CANCELLED,
        "CANCELLED",
        1,
    )
    assert isinstance(state.steps[0], RunStep)
    assert state.steps[0].status == "CANCELLED" and state.steps[0].duration_ms >= 0
    assert state.events[-2]["type"] == "run.cancelled"
    json.dumps(asdict(state), allow_nan=False)


def test_failed_model_attempt_is_counted_and_step_finalized():
    class ErrorAdapter:
        async def respond(self, context, tools):
            raise RuntimeError("private error")

    run = asyncio.run(RuntimeEngine(demo_registry()).run(ErrorAdapter(), "error"))
    assert run.model_call_count == 1 and run.stop_reason == "MODEL_ERROR"
    assert run.steps[0].status == "FAILED" and run.steps[0].error_code == "MODEL_ERROR"


def test_runtime_cannot_reuse_completed_state():
    state = RunState()
    engine = RuntimeEngine(demo_registry())
    asyncio.run(engine.run(demo_adapter("direct"), "direct", state=state))
    event_count = len(state.events)
    with pytest.raises(RuntimeFault, match="INVALID_STATE_TRANSITION"):
        asyncio.run(engine.run(demo_adapter("direct"), "direct", state=state))
    assert state.status == Status.COMPLETED and len(state.events) == event_count
