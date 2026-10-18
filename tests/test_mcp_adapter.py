"""Real official SDK clients and servers; stdio uses a real child process."""

import asyncio
import sys

import pytest
from mcp import Client, StdioServerParameters

from agentforge.mcp_adapter import PROTOCOL, MCPClientAdapter
from agentforge.mcp_server import make_server
from agentforge.models import (
    AgentConfig,
    DeterministicMockAdapter,
    ModelReply,
    ToolCall,
)
from agentforge.runtime import RuntimeEngine, Status
from agentforge.tools import RuntimeFault, ToolRegistry


def test_stdio_discovery_and_real_tool_call():
    async def check():
        adapter = MCPClientAdapter(timeout_seconds=10)
        definitions = await adapter.discover()
        assert adapter.protocol_version == PROTOCOL
        assert {d.name for d in definitions} == {
            "mcp_list_supplier_quotes",
            "mcp_get_supplier_detail",
        }
        registry = ToolRegistry(tuple(definitions))
        result = await registry.dispatch(
            ToolCall(
                call_id="wire-call",
                tool_name="mcp_get_supplier_detail",
                arguments={"supplier": "A"},
            ),
            frozenset(adapter.tool_names),
        )
        assert result.call_id == "wire-call" and result.result["supplier"] == "A"
        assert result.result["delivery_days"] == 7 and result.untrusted is True

    asyncio.run(check())


@pytest.mark.parametrize(
    "arguments",
    [
        {"supplier": "../../etc/passwd"},
        {"supplier": 42},
        {},
        {"supplier": "A", "command": "delete"},
    ],
)
def test_mcp_registry_rejects_malicious_arguments_before_dispatch(arguments):
    async def check():
        adapter = MCPClientAdapter(make_server())
        registry = ToolRegistry(tuple(await adapter.discover()))
        call = ToolCall(
            call_id="bad", tool_name="mcp_get_supplier_detail", arguments=arguments
        )
        with pytest.raises(RuntimeFault, match="INVALID_TOOL_ARGUMENTS"):
            await registry.dispatch(call, frozenset(adapter.tool_names))

    asyncio.run(check())


def test_real_server_rejects_invalid_supplier_without_registry():
    async def check():
        async with Client(make_server()) as client:
            assert client.protocol_version == PROTOCOL
            result = await client.call_tool(
                "get_supplier_detail", {"supplier": "not-allowed"}
            )
            assert result.is_error

    asyncio.run(check())


def test_slow_mcp_tool_becomes_structured_failure_without_retry():
    async def check():
        adapter = MCPClientAdapter(make_server(delay_seconds=1), timeout_seconds=0.05)
        definitions = await adapter.discover()
        registry = ToolRegistry(tuple(definitions))
        script = DeterministicMockAdapter(
            (
                ModelReply(
                    calls=(
                        ToolCall(
                            call_id="slow",
                            tool_name="mcp_list_supplier_quotes",
                            arguments={},
                        ),
                    )
                ),
            )
        )
        run = await RuntimeEngine(registry).run(
            script,
            "slow",
            config=AgentConfig(allowed_tools=frozenset(adapter.tool_names)),
        )
        assert run.status == Status.FAILED and run.stop_reason == "MCP_TIMEOUT"
        assert run.tool_call_count == 1
        assert [
            e["payload"]["code"] for e in run.events if e["type"] == "tool.failed"
        ] == ["MCP_TIMEOUT"]

    asyncio.run(check())


def test_stdio_server_disconnect_is_explicit(tmp_path):
    # Kill the real test server during an actual tool call, not a mock client.
    source = tmp_path / "disconnect.py"
    source.write_text(
        'from mcp.server import MCPServer\nimport os\ns = MCPServer("Disconnect")\n@s.tool()\nasync def get_supplier_detail(supplier: str) -> dict:\n    os._exit(0)\ns.run(transport="stdio")\n',
        encoding="utf-8",
    )

    async def check():
        adapter = MCPClientAdapter(
            StdioServerParameters(command=sys.executable, args=[str(source)]),
            timeout_seconds=10,
        )
        with pytest.raises(RuntimeFault, match="MCP_UNAVAILABLE"):
            await adapter.call("get_supplier_detail", {"supplier": "A"})

    asyncio.run(check())


def test_mcp_remote_name_allowlist():
    async def check():
        with pytest.raises(RuntimeFault, match="TOOL_FORBIDDEN"):
            await MCPClientAdapter(make_server()).call("arbitrary_write", {})

    asyncio.run(check())


def test_mcp_tool_error_preserves_safe_error_code():
    async def check():
        adapter = MCPClientAdapter(make_server())
        with pytest.raises(RuntimeFault, match="MCP_TOOL_ERROR"):
            await adapter.call("get_supplier_detail", {"supplier": "invalid"})

    asyncio.run(check())
