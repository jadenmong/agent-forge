"""Provider-neutral day-one protocol. Not an OpenAI Responses wire format."""

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


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

    def __init__(self, replies: tuple[ModelReply, ...]):
        self.replies = replies

    async def respond(self, context, tools):
        turn = sum(item["kind"] == "model" for item in context)
        if turn >= len(self.replies):
            raise ValueError("Mock script exhausted")
        return self.replies[turn]
