"""Typed local tools and the policy boundary shared by schema and dispatch."""

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from .models import StrictModel, ToolCall


class RuntimeFault(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Permission(StrEnum):
    READ_ONLY = "READ_ONLY"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    DENIED = "DENIED"


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    arguments_type: type[StrictModel]
    handler: Callable[[Any], Awaitable[Any]]
    permission: Permission = Permission.READ_ONLY
    timeout_seconds: float = 2.0

    def __post_init__(self):
        if (not self.name or not math.isfinite(self.timeout_seconds)
                or not 0 < self.timeout_seconds <= 300):
            raise ValueError("Invalid tool name or timeout")
        if not isinstance(self.permission, Permission):
            raise ValueError("Permission must be explicitly classified")
        if not asyncio.iscoroutinefunction(self.handler):
            raise ValueError("Tools must use async handlers")


class ToolRegistry:
    def __init__(self, tools: tuple[Tool, ...]):
        self._tools = {tool.name: tool for tool in tools}
        if len(self._tools) != len(tools):
            raise ValueError("Duplicate tool name")

    def schemas(self, allowed: frozenset[str]) -> list[dict[str, Any]]:
        return [
            {"name": tool.name, "description": tool.description,
             "parameters": tool.arguments_type.model_json_schema()}
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
            arguments = tool.arguments_type.model_validate(call.arguments)
        except ValidationError:
            raise RuntimeFault("INVALID_TOOL_ARGUMENTS") from None
        return tool, arguments

    async def dispatch(self, call: ToolCall, allowed: frozenset[str]):
        tool, arguments = self.validate(call, allowed)
        try:
            async with asyncio.timeout(tool.timeout_seconds):
                result = await tool.handler(arguments)
            # Bound context growth and reject non-JSON results, including NaN.
            encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
            if len(encoded.encode("utf-8")) > 32000:
                raise RuntimeFault("TOOL_OUTPUT_TOO_LARGE")
            return json.loads(encoded)
        except TimeoutError:
            raise RuntimeFault("TOOL_TIMEOUT") from None
        except RuntimeFault:
            raise
        except Exception:
            raise RuntimeFault("TOOL_ERROR") from None
