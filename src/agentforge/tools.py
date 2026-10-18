"""Typed local tools and the policy boundary shared by schema and dispatch."""

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from .models import StrictModel, ToolCall, ToolResult


class RuntimeFault(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Permission(StrEnum):
    READ_ONLY = "READ_ONLY"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    DENIED = "DENIED"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    arguments_type: type[StrictModel] | None
    handler: Callable[[Any], Awaitable[Any]]
    permission: Permission = Permission.READ_ONLY
    timeout_seconds: float = 2.0
    input_schema: dict[str, Any] | None = None
    source: str = "local"

    def __post_init__(self):
        if (
            not self.name
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 300
        ):
            raise ValueError("Invalid tool name or timeout")
        if not isinstance(self.permission, Permission):
            raise ValueError("Permission must be explicitly classified")
        if not asyncio.iscoroutinefunction(self.handler):
            raise ValueError("Tools must use async handlers")
        Draft202012Validator.check_schema(self.schema)

    @property
    def schema(self):
        return (
            self.input_schema
            if self.input_schema is not None
            else self.arguments_type.model_json_schema()
        )


class ToolRegistry:
    def __init__(self, tools: tuple[ToolDefinition, ...]):
        self._tools = {tool.name: tool for tool in tools}
        if len(self._tools) != len(tools):
            raise ValueError("Duplicate tool name")

    def schemas(self, allowed: frozenset[str]) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.schema,
            }
            for tool in self._tools.values()
            if tool.name in allowed and tool.permission == Permission.READ_ONLY
        ]

    def validate(self, call: ToolCall, allowed: frozenset[str]):
        tool = self._tools.get(call.tool_name)
        if tool is None:
            raise RuntimeFault("UNKNOWN_TOOL")
        if tool.name not in allowed or tool.permission == Permission.DENIED:
            raise RuntimeFault("TOOL_FORBIDDEN")
        # No approval bypass parameter exists. Writes stay disabled until day three.
        if tool.permission == Permission.REQUIRES_APPROVAL:
            raise RuntimeFault("APPROVAL_REQUIRED")
        try:
            errors = Draft202012Validator(tool.schema).iter_errors(call.arguments)
            if next(errors, None) is not None:
                raise RuntimeFault("INVALID_TOOL_ARGUMENTS")
            arguments = (
                tool.arguments_type.model_validate(call.arguments)
                if tool.arguments_type is not None
                else call.arguments
            )
        except ValidationError:
            raise RuntimeFault("INVALID_TOOL_ARGUMENTS") from None
        return tool, arguments

    def metadata(self):
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.schema,
                "permission": tool.permission.value,
                "timeout_seconds": tool.timeout_seconds,
                "source": tool.source,
            }
            for tool in self._tools.values()
        ]

    def add(self, tool: ToolDefinition):
        if tool.name in self._tools:
            raise ValueError("Duplicate tool name")
        self._tools[tool.name] = tool

    async def dispatch(self, call: ToolCall, allowed: frozenset[str]) -> ToolResult:
        tool, arguments = self.validate(call, allowed)
        try:
            async with asyncio.timeout(tool.timeout_seconds):
                result = await tool.handler(arguments)
            # Bound context growth and reject non-JSON results, including NaN.
            encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
            if len(encoded.encode("utf-8")) > 32000:
                raise RuntimeFault("TOOL_OUTPUT_TOO_LARGE")
            return ToolResult(call_id=call.call_id, result=json.loads(encoded))
        except TimeoutError:
            raise RuntimeFault("TOOL_TIMEOUT") from None
        except RuntimeFault:
            raise
        except Exception:
            raise RuntimeFault("TOOL_ERROR") from None
