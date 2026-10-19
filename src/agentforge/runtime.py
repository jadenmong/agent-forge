"""Self-authored loop with explicit durable approval boundaries."""

import asyncio
import copy
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic_core import PydanticSerializationError

from .models import (
    AgentConfig,
    DeterministicMockAdapter,
    ModelAdapter,
    ModelReply,
    RunEvent,
    RunStep,
    ToolCall,
    ToolInvocation,
)
from .redaction import redact, trace_summary
from .tools import Permission, RuntimeFault, ToolRegistry


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Status(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    INTERRUPTED = "INTERRUPTED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class RunState:
    run_id: str = field(default_factory=lambda: str(uuid4()))
    agent_id: str = "procurement-demo"
    mode: Literal["mock", "live"] = "mock"
    status: Status = Status.CREATED
    stop_reason: str | None = None
    step_count: int = 0
    model_call_count: int = 0
    tool_call_count: int = 0
    budget_tokens: int = 0
    token_accounting: str = "utf8_bytes_estimate"
    cost: None = None
    output: str | None = None
    input_summary: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    active_seconds: float = 0
    approval_wait_seconds: float = 0
    revision: int = 0
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    model_resume_state: dict[str, Any] = field(default_factory=dict)
    steps: list[RunStep] = field(default_factory=list)
    events: list[RunEvent] = field(default_factory=list)
    invocations: list[ToolInvocation] = field(default_factory=list)

    def emit(self, event_type: str, *, step_id=None, **metadata):
        self.events.append(
            {
                "event_id": len(self.events) + 1,
                "run_id": self.run_id,
                "step_id": len(self.steps) if step_id is None else step_id,
                "correlation_id": self.run_id,
                "timestamp": utcnow(),
                "type": event_type,
                "mode": self.mode,
                "payload": redact(metadata),
            }
        )

    def transition(self, target: Status):
        allowed = {
            Status.CREATED: {Status.RUNNING, Status.FAILED, Status.CANCELLED},
            Status.RUNNING: {
                Status.WAITING_APPROVAL,
                Status.COMPLETED,
                Status.FAILED,
                Status.CANCELLED,
                Status.INTERRUPTED,
                Status.RECONCILIATION_REQUIRED,
            },
            Status.WAITING_APPROVAL: {Status.RUNNING, Status.CANCELLED, Status.FAILED},
            Status.INTERRUPTED: {Status.RUNNING, Status.FAILED, Status.CANCELLED},
            Status.RECONCILIATION_REQUIRED: {Status.FAILED},
        }
        if target not in allowed.get(self.status, set()):
            raise RuntimeFault("INVALID_STATE_TRANSITION")
        self.status = target


def estimated_tokens(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


class RuntimeEngine:
    def __init__(self, registry: ToolRegistry, *, storage=None):
        self.registry, self.storage = registry, storage

    async def run(
        self,
        adapter: ModelAdapter,
        task: str,
        *,
        config: AgentConfig | None = None,
        state: RunState | None = None,
        resume: bool = False,
    ) -> RunState:
        if not isinstance(task, str) or not task.strip() or len(task) > 16000:
            raise ValueError("Task must contain 1..16000 characters")
        config = config or AgentConfig()
        run = state if state is not None else RunState()
        if resume:
            if (
                run.status != Status.RUNNING
                or run.model_resume_state.get("safe_point") != "AFTER_APPROVED_TOOL"
            ):
                raise RuntimeFault("UNSAFE_RESUME_POINT")
            if config != AgentConfig.model_validate_json(
                json.dumps(run.config_snapshot)
            ):
                raise RuntimeFault("CHECKPOINT_INVALID")
            run.emit("run.resumed", safe_point="AFTER_APPROVED_TOOL")
        else:
            if run.status != Status.CREATED:
                raise RuntimeFault("INVALID_STATE_TRANSITION")
            run.agent_id = config.id
            run.mode = "live" if config.model_adapter == "openai" else "mock"
            run.config_snapshot = config.model_dump(mode="json")
            snapshot = {"kind": "unsupported"}
            if (
                isinstance(adapter, DeterministicMockAdapter)
                and self.storage is not None
            ):
                try:
                    snapshot = {
                        "kind": "mock",
                        "replies": [r.model_dump(mode="json") for r in adapter.replies],
                        "repeat_last": adapter.repeat_last,
                    }
                except (ValueError, TypeError, PydanticSerializationError):
                    snapshot = {"kind": "unsupported"}
            elif config.model_adapter == "openai":
                snapshot = {"kind": "openai", "model": adapter.model}
            run.model_resume_state = {
                "context": [
                    {"kind": "system", "text": config.system_prompt},
                    {"kind": "input", "text": task},
                ],
                "pending_calls": [],
                "adapter": snapshot,
                "safe_point": "IN_FLIGHT",
            }
            run.input_summary = redact(task)[:160]
            run.started_at = utcnow()
            run.emit("run.created")
            if self.storage is not None:
                self.storage.create_run(run, config, task)
            run.transition(Status.RUNNING)
            run.emit("run.started")
        limits, allowed = config.limits, config.allowed_tools
        context = run.model_resume_state["context"]
        pending = run.model_resume_state["pending_calls"]
        seen = {
            call["call_id"]
            for item in context
            if item["kind"] == "model"
            for call in item["calls"]
        }
        schemas = self.registry.schemas(
            allowed, include_approval=self.storage is not None
        )
        started = time.monotonic()
        base_seconds = run.active_seconds
        active_step = None
        active_invocation = None
        step_started = started

        def persist():
            run.active_seconds = base_seconds + time.monotonic() - started
            if self.storage is not None:
                self.storage.save(run)

        def finish_active(status, code=None):
            nonlocal active_step, active_invocation
            if active_step is not None:
                active_step.status, active_step.error_code = status, code
                active_step.duration_ms = (time.monotonic() - step_started) * 1000
                active_step = None
            if active_invocation is not None:
                active_invocation.status = (
                    "COMPLETED" if status == "COMPLETED" else "FAILED"
                )
                active_invocation = None

        try:
            remaining = limits.wall_seconds - run.active_seconds
            if remaining <= 0:
                raise RuntimeFault("WALL_TIME_LIMIT")
            async with asyncio.timeout(remaining):
                persist()
                while True:
                    if not pending:
                        if run.step_count >= limits.max_steps:
                            raise RuntimeFault("MAX_STEPS")
                        if run.model_call_count >= limits.max_model_calls:
                            raise RuntimeFault("MAX_MODEL_CALLS")
                        request_estimate = estimated_tokens([context, schemas])
                        if run.budget_tokens + request_estimate > limits.max_tokens:
                            raise RuntimeFault("TOKEN_BUDGET")
                        run.step_count += 1
                        run.model_call_count += 1
                        active_step = RunStep(
                            run.run_id, len(run.steps) + 1, "model", utcnow()
                        )
                        run.steps.append(active_step)
                        step_started = time.monotonic()
                        run.model_resume_state["safe_point"] = "IN_FLIGHT"
                        run.emit("model.requested")
                        persist()
                        try:
                            async with asyncio.timeout(limits.model_timeout_seconds):
                                reply = await adapter.respond(
                                    copy.deepcopy(context), copy.deepcopy(schemas)
                                )
                            if not isinstance(reply, ModelReply):
                                raise RuntimeFault("MODEL_PROTOCOL_ERROR")
                            try:
                                reply_size = estimated_tokens(reply.model_dump())
                            except (ValueError, TypeError):
                                raise RuntimeFault("MODEL_PROTOCOL_ERROR") from None
                            if reply_size > 64000:
                                raise RuntimeFault("MODEL_OUTPUT_TOO_LARGE")
                        except TimeoutError:
                            raise RuntimeFault("MODEL_TIMEOUT") from None
                        except RuntimeFault:
                            raise
                        except Exception:
                            raise RuntimeFault("MODEL_ERROR") from None
                        measured = reply.usage_tokens
                        run.budget_tokens += (
                            measured
                            if measured is not None
                            else request_estimate + reply_size
                        )
                        accounting = (
                            "provider_reported"
                            if measured is not None
                            else "utf8_bytes_estimate"
                        )
                        run.token_accounting = (
                            accounting
                            if run.step_count == 1
                            else accounting
                            if run.token_accounting == accounting
                            else "mixed"
                        )
                        run.emit(
                            "model.responded",
                            call_count=len(reply.calls),
                            duration_ms=(time.monotonic() - step_started) * 1000,
                            usage_tokens=measured,
                            token_accounting=accounting,
                        )
                        finish_active("COMPLETED")
                        if run.budget_tokens > limits.max_tokens:
                            raise RuntimeFault("TOKEN_BUDGET")
                        if reply.final_text is not None:
                            run.output = redact(reply.final_text)
                            run.transition(Status.COMPLETED)
                            run.stop_reason = "FINAL_ANSWER"
                            run.finished_at = utcnow()
                            run.emit("run.completed")
                            break
                        if (
                            run.tool_call_count + len(reply.calls)
                            > limits.max_tool_calls
                        ):
                            raise RuntimeFault("MAX_TOOL_CALLS")
                        for call in reply.calls:
                            if call.call_id in seen:
                                raise RuntimeFault("DUPLICATE_CALL_ID")
                            seen.add(call.call_id)
                            self.registry.validate(
                                call, allowed, for_approval=self.storage is not None
                            )
                        context.append(
                            {"kind": "model", **reply.model_dump(mode="json")}
                        )
                        pending.extend(
                            call.model_dump(mode="json") for call in reply.calls
                        )
                        persist()
                    call = ToolCall.model_validate_json(json.dumps(pending[0]))
                    tool, args = self.registry.validate(
                        call, allowed, for_approval=self.storage is not None
                    )
                    validated = (
                        args.model_dump(mode="json")
                        if hasattr(args, "model_dump")
                        else args
                    )
                    active_step = RunStep(
                        run.run_id,
                        len(run.steps) + 1,
                        "tool",
                        utcnow(),
                        tool_name=call.tool_name,
                        call_id=call.call_id,
                        arguments_summary=trace_summary(validated),
                    )
                    run.steps.append(active_step)
                    step_started = time.monotonic()
                    active_invocation = ToolInvocation(
                        call.call_id,
                        call.tool_name,
                        validated,
                        tool.permission.value,
                        active_step.seq,
                    )
                    run.invocations.append(active_invocation)
                    run.emit(
                        "tool.requested",
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        arguments_summary=active_step.arguments_summary,
                    )
                    if tool.permission == Permission.REQUIRES_APPROVAL:
                        if run.model_resume_state["adapter"]["kind"] == "unsupported":
                            raise RuntimeFault("UNSUPPORTED_CHECKPOINT_ADAPTER")
                        run.active_seconds = base_seconds + time.monotonic() - started
                        self.storage.pause(run, active_invocation)
                        active_step = active_invocation = None
                        return run
                    if run.tool_call_count >= limits.max_tool_calls:
                        raise RuntimeFault("MAX_TOOL_CALLS")
                    run.tool_call_count += 1
                    run.model_resume_state["safe_point"] = "IN_FLIGHT"
                    run.emit(
                        "tool.started", call_id=call.call_id, tool_name=call.tool_name
                    )
                    persist()
                    try:
                        result = await self.registry.dispatch(call, allowed)
                    except RuntimeFault as exc:
                        run.emit("tool.failed", call_id=call.call_id, code=exc.code)
                        raise
                    except asyncio.CancelledError:
                        run.emit(
                            "tool.failed",
                            call_id=call.call_id,
                            code="EXECUTION_INTERRUPTED",
                        )
                        raise
                    active_invocation.result = result.result
                    active_step.result_summary = trace_summary(result.result)
                    run.emit(
                        "tool.completed",
                        call_id=call.call_id,
                        duration_ms=(time.monotonic() - step_started) * 1000,
                        result_summary=active_step.result_summary,
                    )
                    finish_active("COMPLETED")
                    context.append(result.model_dump(mode="json"))
                    pending.pop(0)
                    run.model_resume_state["safe_point"] = "AFTER_READ_TOOL"
                    persist()
        except (TimeoutError, RuntimeFault) as exc:
            code = "WALL_TIME_LIMIT" if isinstance(exc, TimeoutError) else exc.code
            finish_active("FAILED", code)
            run.stop_reason, run.finished_at = code, utcnow()
            run.transition(Status.FAILED)
            run.emit("run.failed", code=code)
        except asyncio.CancelledError:
            finish_active("CANCELLED", "CANCELLED")
            run.transition(Status.CANCELLED)
            run.stop_reason, run.finished_at = "CANCELLED", utcnow()
            run.emit("run.cancelled")
            raise
        finally:
            if run.status != Status.WAITING_APPROVAL:
                run.emit(
                    "run.finished", duration_ms=(time.monotonic() - started) * 1000
                )
                persist()
        return run
