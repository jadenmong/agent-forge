"""Allowlisted official MCP v2 client; default target is our fixed stdio module."""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import Client, StdioServerParameters

from .tools import Permission, RuntimeFault, ToolDefinition

PROTOCOL = "2026-07-28"
REMOTE_NAMES = frozenset({"list_supplier_quotes", "get_supplier_detail"})


class MCPClientAdapter:
    def __init__(self, target=None, *, timeout_seconds: float = 5.0):
        # target is only injectable by trusted source/tests, never by HTTP or model input.
        self.target = (
            target
            if target is not None
            else StdioServerParameters(
                command=sys.executable,
                args=["-m", "agentforge.mcp_server"],
                cwd=str(Path(__file__).resolve().parents[2]),
                env={
                    k: v
                    for k, v in os.environ.items()
                    if not k.upper().endswith("API_KEY")
                },
            )
        )
        self.timeout_seconds = timeout_seconds
        self.protocol_version = None
        self.tool_names: list[str] = []

    @asynccontextmanager
    async def connect(self):
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with Client(self.target) as client:
                    if client.protocol_version != PROTOCOL:
                        raise RuntimeFault("MCP_PROTOCOL_MISMATCH")
                    yield client
        except TimeoutError:
            raise RuntimeFault("MCP_TIMEOUT") from None
        except RuntimeFault:
            raise
        except ExceptionGroup as exc:
            pending = list(exc.exceptions)
            while pending:
                cause = pending.pop()
                if isinstance(cause, RuntimeFault):
                    raise cause from None
                if isinstance(cause, ExceptionGroup):
                    pending.extend(cause.exceptions)
            raise RuntimeFault("MCP_UNAVAILABLE") from None
        except Exception:
            raise RuntimeFault("MCP_UNAVAILABLE") from None

    async def call(self, name: str, arguments: dict):
        if name not in REMOTE_NAMES:
            raise RuntimeFault("TOOL_FORBIDDEN")
        async with self.connect() as client:
            result = await client.call_tool(name, arguments)
        if result.is_error:
            raise RuntimeFault("MCP_TOOL_ERROR")
        data = result.structured_content
        if not isinstance(data, dict):
            raise RuntimeFault("MCP_INVALID_RESULT")
        if len(json.dumps(data, ensure_ascii=False, allow_nan=False).encode()) > 32000:
            raise RuntimeFault("TOOL_OUTPUT_TOO_LARGE")
        return data

    async def discover(self) -> list[ToolDefinition]:
        async with self.connect() as client:
            self.protocol_version = client.protocol_version
            listing = await client.list_tools()
        definitions = []
        for tool in listing.tools:
            if tool.name not in REMOTE_NAMES:
                continue
            remote_name = tool.name

            async def handler(args, name=remote_name):
                return await self.call(name, args)

            # Narrow the trusted demo's object schema: extra parameters are never allowed.
            schema = {**tool.input_schema, "additionalProperties": False}
            definitions.append(
                ToolDefinition(
                    name=f"mcp_{remote_name}",
                    description=tool.description or remote_name,
                    arguments_type=None,
                    handler=handler,
                    permission=Permission.READ_ONLY,
                    timeout_seconds=self.timeout_seconds + 1,
                    input_schema=schema,
                    source="mcp",
                )
            )
        if {t.name for t in definitions} != {f"mcp_{name}" for name in REMOTE_NAMES}:
            raise RuntimeFault("MCP_CAPABILITY_MISSING")
        self.tool_names = [t.name for t in definitions]
        return definitions
