"""Self-authored sequential loop; no framework runner or persistent recovery."""

import asyncio
import copy
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from .models import AgentConfig, ModelAdapter, ModelReply, RunEvent, RunStep
from .tools import RuntimeFault, ToolRegistry


class Status(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class RunState:
    run_id: str = field(default_factory=lambda: str(uuid4()))
    agent_id: str = "procurement-demo"
    mode: Literal["mock"] = "mock"
    status: Status = Status.CREATED
    stop_reason: str | None = None
    step_count: int = 0
    model_call_count: int = 0
    tool_call_count: int = 0
    budget_tokens: int = 0
    token_accounting: str = "utf8_bytes_estimate"
    cost: None = None
    output: str | None = None
    steps: list[RunStep] = field(default_factory=list)
    events: list[RunEvent] = field(default_factory=list)

    def emit(self, event_type: str, **metadata):
        self.events.append(
            {
                "event_id": len(self.events) + 1,
                "run_id": self.run_id,
                "step_id": len(self.steps),
                "correlation_id": self.run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": event_type,
                "mode": self.mode,
                "payload": metadata,
            }
        )

    def transition(self, target: Status):
        allowed = {
            Status.CREATED: {Status.RUNNING},
            Status.RUNNING: {Status.COMPLETED, Status.FAILED, Status.CANCELLED},
        }
        if target not in allowed.get(self.status, set()):
            raise RuntimeFault("INVALID_STATE_TRANSITION")
        self.status = target


def estimated_tokens(value: Any) -> int:
    # Deliberately conservative proxy, not a tokenizer or measured usage.
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


class RuntimeEngine:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def run(
        self,
        adapter: ModelAdapter,
        task: str,
        *,
        config: AgentConfig | None = None,
        state: RunState | None = None,
    ) -> RunState:
        if not isinstance(task, str) or not task.strip() or len(task) > 16000:
            raise ValueError("Task must contain 1..16000 characters")
        config = config or AgentConfig()
        limits = config.limits
        allowed_tools = config.allowed_tools
        run = state if state is not None else RunState()
        if run.status != Status.CREATED:
            raise RuntimeFault("INVALID_STATE_TRANSITION")
        run.agent_id = config.id
        run.emit("run.created")
        run.transition(Status.RUNNING)
        run.emit("run.started")
        context = [
            {"kind": "system", "text": config.system_prompt},
            {"kind": "input", "text": task},
        ]
        schemas = self.registry.schemas(allowed_tools)
        seen_calls: set[str] = set()
        started = time.monotonic()
        active_step: RunStep | None = None
        step_started = started

        def finish_active(status, code=None):
            nonlocal active_step
            if active_step is not None:
                active_step.status = status
                active_step.error_code = code
                active_step.duration_ms = (time.monotonic() - step_started) * 1000
                active_step = None

        try:
            async with asyncio.timeout(limits.wall_seconds):
                while True:
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
                        run.run_id,
                        len(run.steps) + 1,
                        "model",
                        datetime.now(timezone.utc).isoformat(),
                    )
                    run.steps.append(active_step)
                    step_started = time.monotonic()
                    run.emit("model.requested")
                    model_started = time.monotonic()
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
                        else (request_estimate + reply_size)
                    )
                    accounting = (
                        "provider_reported"
                        if measured is not None
                        else "utf8_bytes_estimate"
                    )
                    if run.step_count == 1:
                        run.token_accounting = accounting
                    elif run.token_accounting != accounting:
                        run.token_accounting = "mixed"
                    run.emit(
                        "model.responded",
                        call_count=len(reply.calls),
                        duration_ms=(time.monotonic() - model_started) * 1000,
                        usage_tokens=measured,
                        token_accounting=accounting,
                    )
                    finish_active("COMPLETED")
                    if run.budget_tokens > limits.max_tokens:
                        raise RuntimeFault("TOKEN_BUDGET")
                    if reply.final_text is not None:
                        run.output = reply.final_text
                        run.transition(Status.COMPLETED)
                        run.stop_reason = "FINAL_ANSWER"
                        run.emit("run.completed")
                        break
                    if run.tool_call_count + len(reply.calls) > limits.max_tool_calls:
                        raise RuntimeFault("MAX_TOOL_CALLS")
                    # Validate the whole batch before executing any member.
                    for call in reply.calls:
                        if call.call_id in seen_calls:
                            raise RuntimeFault("DUPLICATE_CALL_ID")
                        seen_calls.add(call.call_id)
                        self.registry.validate(call, allowed_tools)
                    context.append({"kind": "model", **reply.model_dump(mode="json")})
                    for call in reply.calls:
                        active_step = RunStep(
                            run.run_id,
                            len(run.steps) + 1,
                            "tool",
                            datetime.now(timezone.utc).isoformat(),
                            tool_name=call.tool_name,
                            call_id=call.call_id,
                        )
                        run.steps.append(active_step)
                        step_started = time.monotonic()
                        run.emit(
                            "tool.requested",
                            call_id=call.call_id,
                            tool_name=call.tool_name,
                        )
                        run.tool_call_count += 1
                        run.emit(
                            "tool.started",
                            call_id=call.call_id,
                            tool_name=call.tool_name,
                        )
                        tool_started = time.monotonic()
                        try:
                            result = await self.registry.dispatch(call, allowed_tools)
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
                        run.emit(
                            "tool.completed",
                            call_id=call.call_id,
                            duration_ms=(time.monotonic() - tool_started) * 1000,
                        )
                        finish_active("COMPLETED")
                        context.append(result.model_dump(mode="json"))
        except TimeoutError:
            finish_active("FAILED", "WALL_TIME_LIMIT")
            run.stop_reason = "WALL_TIME_LIMIT"
            run.transition(Status.FAILED)
            run.emit("run.failed", code=run.stop_reason)
        except RuntimeFault as exc:
            finish_active("FAILED", exc.code)
            run.stop_reason = exc.code
            run.transition(Status.FAILED)
            run.emit("run.failed", code=exc.code)
        except asyncio.CancelledError:
            finish_active("CANCELLED", "CANCELLED")
            run.transition(Status.CANCELLED)
            run.stop_reason = "CANCELLED"
            run.emit("run.cancelled")
            # Let the caller's cancellation scope work; no recovery claim.
            raise
        finally:
            run.emit("run.finished", duration_ms=(time.monotonic() - started) * 1000)
        return run
