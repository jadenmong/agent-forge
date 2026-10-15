"""Self-authored sequential loop; no framework runner or persistent recovery."""

import asyncio
import copy
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import Field

from .models import ModelAdapter, ModelReply, StrictModel
from .tools import RuntimeFault, ToolRegistry


class Status(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Limits(StrictModel):
    max_steps: int = Field(default=8, ge=1, le=100)
    max_tool_calls: int = Field(default=16, ge=0, le=200)
    wall_seconds: float = Field(default=30.0, gt=0, le=300)
    model_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    max_tokens: int = Field(default=64000, ge=1, le=1000000)


@dataclass
class Run:
    run_id: str = field(default_factory=lambda: str(uuid4()))
    mode: str = "mock"
    status: Status = Status.CREATED
    stop_reason: str | None = None
    step_count: int = 0
    tool_call_count: int = 0
    budget_tokens: int = 0
    token_accounting: str = "utf8_bytes_estimate"
    cost: None = None
    output: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def emit(self, event_type: str, **metadata):
        self.events.append({
            "event_id": len(self.events) + 1, "run_id": self.run_id,
            "step_id": self.step_count, "correlation_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type, "mode": self.mode, "payload": metadata,
        })

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
        self, adapter: ModelAdapter, task: str, *,
        allowed_tools: frozenset[str] = frozenset(),
        limits: Limits | None = None, system_prompt: str = "Use only permitted tools.",
    ) -> Run:
        if not isinstance(task, str) or not task.strip() or len(task) > 16000:
            raise ValueError("Task must contain 1..16000 characters")
        if not isinstance(system_prompt, str) or len(system_prompt) > 16000:
            raise ValueError("System prompt must contain at most 16000 characters")
        limits = limits or Limits()
        run = Run()
        run.emit("run.created")
        run.transition(Status.RUNNING)
        run.emit("run.started")
        context = [{"kind": "system", "text": system_prompt},
                   {"kind": "input", "text": task}]
        schemas = self.registry.schemas(allowed_tools)
        seen_calls: set[str] = set()
        started = time.monotonic()
        try:
            async with asyncio.timeout(limits.wall_seconds):
                while True:
                    if run.step_count >= limits.max_steps:
                        raise RuntimeFault("MAX_STEPS")
                    request_estimate = estimated_tokens([context, schemas])
                    if run.budget_tokens + request_estimate > limits.max_tokens:
                        raise RuntimeFault("TOKEN_BUDGET")
                    run.step_count += 1
                    run.emit("model.requested")
                    model_started = time.monotonic()
                    try:
                        async with asyncio.timeout(limits.model_timeout_seconds):
                            reply = await adapter.respond(copy.deepcopy(context), copy.deepcopy(schemas))
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
                    run.budget_tokens += measured if measured is not None else (
                        request_estimate + reply_size)
                    accounting = "provider_reported" if measured is not None else "utf8_bytes_estimate"
                    if run.step_count == 1:
                        run.token_accounting = accounting
                    elif run.token_accounting != accounting:
                        run.token_accounting = "mixed"
                    run.emit("model.responded", call_count=len(reply.calls),
                             duration_ms=(time.monotonic() - model_started) * 1000,
                             usage_tokens=measured, token_accounting=accounting)
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
                        run.emit("tool.requested", call_id=call.call_id, tool_name=call.tool_name)
                        run.tool_call_count += 1
                        run.emit("tool.started", call_id=call.call_id, tool_name=call.tool_name)
                        tool_started = time.monotonic()
                        try:
                            result = await self.registry.dispatch(call, allowed_tools)
                        except RuntimeFault as exc:
                            run.emit("tool.failed", call_id=call.call_id, code=exc.code)
                            raise
                        except asyncio.CancelledError:
                            run.emit("tool.failed", call_id=call.call_id, code="EXECUTION_INTERRUPTED")
                            raise
                        run.emit("tool.completed", call_id=call.call_id,
                                 duration_ms=(time.monotonic() - tool_started) * 1000)
                        context.append({"kind": "tool_result", "call_id": call.call_id,
                                        "untrusted": True, "result": result})
        except TimeoutError:
            run.stop_reason = "WALL_TIME_LIMIT"
            run.transition(Status.FAILED)
            run.emit("run.failed", code=run.stop_reason)
        except RuntimeFault as exc:
            run.stop_reason = exc.code
            run.transition(Status.FAILED)
            run.emit("run.failed", code=exc.code)
        except asyncio.CancelledError:
            run.transition(Status.CANCELLED)
            run.stop_reason = "CANCELLED"
            run.emit("run.cancelled")
            # Let the caller's cancellation scope work; no recovery claim.
            raise
        run.emit("run.finished", duration_ms=(time.monotonic() - started) * 1000)
        return run
