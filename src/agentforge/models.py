"""Provider-neutral day-one protocol. Not an OpenAI Responses wire format."""

from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Limits(StrictModel):
    max_steps: int = Field(default=8, ge=1, le=100)
    max_model_calls: int = Field(default=8, ge=1, le=100)
    max_tool_calls: int = Field(default=16, ge=0, le=200)
    wall_seconds: float = Field(default=30.0, gt=0, le=300)
    model_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    max_tokens: int = Field(default=64000, ge=1, le=1000000)


class AgentConfig(StrictModel):
    id: str = Field(default="procurement-demo", min_length=1, max_length=128)
    name: str = Field(
        default="Read-only procurement demo", min_length=1, max_length=128
    )
    system_prompt: str = Field(default="Use only permitted tools.", max_length=16000)
    model_adapter: Literal["mock"] = "mock"
    model_name: str = Field(default="deterministic-mock", min_length=1, max_length=128)
    allowed_tools: frozenset[str] = frozenset()
    limits: Limits = Field(default_factory=Limits)
    version: int = Field(default=1, ge=1)


class ToolResult(StrictModel):
    kind: Literal["tool_result"] = "tool_result"
    call_id: str
    untrusted: Literal[True] = True
    result: Any


@dataclass
class RunStep:
    run_id: str
    seq: int
    kind: Literal["model", "tool"]
    started_at: str
    status: Literal["RUNNING", "COMPLETED", "FAILED", "CANCELLED"] = "RUNNING"
    duration_ms: float | None = None
    error_code: str | None = None
    tool_name: str | None = None
    call_id: str | None = None


class RunEvent(TypedDict):
    event_id: int
    run_id: str
    step_id: int
    correlation_id: str
    timestamp: str
    type: str
    mode: Literal["mock"]
    payload: dict[str, Any]


class ToolCall(StrictModel):
    call_id: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any]


class ModelReply(StrictModel):
    calls: tuple[ToolCall, ...] = ()
    final_text: str | None = Field(default=None, max_length=16000)
    usage_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def one_action(self):
        if bool(self.calls) == (self.final_text is not None):
            raise ValueError("Expected tool calls or final text")
        return self


class ModelAdapter(Protocol):
    async def respond(
        self, context: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelReply: ...


class DeterministicMockAdapter:
    """Explicit script; no network, random decisions, keys or provider claims."""

    def __init__(self, replies: tuple[ModelReply, ...], *, repeat_last: bool = False):
        if not replies:
            raise ValueError("Mock script must not be empty")
        self.replies = replies
        self.repeat_last = repeat_last

    async def respond(self, context, tools):
        turn = sum(item["kind"] == "model" for item in context)
        if turn >= len(self.replies) and not self.repeat_last:
            raise ValueError("Mock script exhausted")
        reply = self.replies[min(turn, len(self.replies) - 1)]
        if self.repeat_last:
            # Repeat the action with fresh protocol IDs; the runtime must stop it.
            reply = reply.model_copy(
                update={
                    "calls": tuple(
                        call.model_copy(update={"call_id": f"{call.call_id}-{turn}"})
                        for call in reply.calls
                    )
                }
            )
        return reply
