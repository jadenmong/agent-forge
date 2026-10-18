"""Trusted local demo server using the official SDK v2 high-level API."""

import asyncio
from typing import Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .demo import EmptyArgs, SupplierArgs, list_quotes, supplier_detail
from .models import StrictModel


class QuotesOutput(StrictModel):
    quotes: list[dict]


class DetailOutput(SupplierArgs):
    delivery_days: int
    warranty_months: int


def make_server(*, delay_seconds: float = 0) -> MCPServer:
    server = MCPServer("AgentForge Demo", instructions="Synthetic read-only data only.")
    annotations = ToolAnnotations(
        read_only_hint=True, destructive_hint=False, open_world_hint=False
    )

    @server.tool(annotations=annotations)
    async def list_supplier_quotes() -> QuotesOutput:
        """List three synthetic supplier quotations. No business writes."""
        await asyncio.sleep(delay_seconds)
        return QuotesOutput(quotes=await list_quotes(EmptyArgs()))

    @server.tool(annotations=annotations)
    async def get_supplier_detail(supplier: Literal["A", "B", "C"]) -> DetailOutput:
        """Read delivery and warranty from the local synthetic fixture."""
        await asyncio.sleep(delay_seconds)
        return DetailOutput(**await supplier_detail(SupplierArgs(supplier=supplier)))

    return server


if __name__ == "__main__":
    make_server().run(transport="stdio")
