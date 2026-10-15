"""Fixed, synthetic procurement read-only demo. Never places an order."""

import argparse
import asyncio
import json
from dataclasses import asdict
from typing import Literal

from pydantic import Field

from .models import DeterministicMockAdapter, ModelReply, StrictModel, ToolCall
from .runtime import Limits, RuntimeEngine
from .tools import Tool, ToolRegistry


class EmptyArgs(StrictModel):
    pass


class SupplierArgs(StrictModel):
    supplier: Literal["A", "B", "C"]


class CostArgs(StrictModel):
    unit_price_cents: int = Field(ge=1, le=100000000)
    quantity: int = Field(ge=1, le=10000)


async def list_quotes(args: EmptyArgs):
    return [{"supplier": "A", "unit_price_cents": 95000},
            {"supplier": "B", "unit_price_cents": 98000},
            {"supplier": "C", "unit_price_cents": 105000}]


async def supplier_detail(args: SupplierArgs):
    days, warranty = {"A": (7, 24), "B": (3, 36), "C": (2, 36)}[args.supplier]
    return {"supplier": args.supplier, "delivery_days": days, "warranty_months": warranty}


async def calculate_cost(args: CostArgs):
    return {"total_cents": args.unit_price_cents * args.quantity}


def demo_registry():
    return ToolRegistry((
        Tool("list_supplier_quotes", "List synthetic demo quotations", EmptyArgs, list_quotes),
        Tool("get_supplier_detail", "Get synthetic delivery and warranty", SupplierArgs, supplier_detail),
        Tool("calculate_total_cost", "Multiply integer cents by quantity", CostArgs, calculate_cost),
    ))


def demo_adapter():
    return DeterministicMockAdapter((
        ModelReply(calls=(ToolCall(call_id="quotes", tool_name="list_supplier_quotes", arguments={}),)),
        ModelReply(calls=tuple(ToolCall(call_id=f"detail-{s}", tool_name="get_supplier_detail",
                                       arguments={"supplier": s}) for s in "ABC")),
        ModelReply(calls=tuple(ToolCall(call_id=f"total-{s}", tool_name="calculate_total_cost",
                                       arguments={"unit_price_cents": price, "quantity": 20})
                              for s, price in (("A", 95000), ("B", 98000), ("C", 105000)))),
        ModelReply(final_text="[Mock / synthetic data] A=19000, B=19600, C=21000 CNY. "
                   "B fits 20000 CNY with 3-day delivery and 36-month warranty. "
                   "Read-only comparison complete; no draft or order was created."),
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-steps", type=int, default=8)
    args = parser.parse_args()
    registry = demo_registry()
    allowed = frozenset({"list_supplier_quotes", "get_supplier_detail", "calculate_total_cost"})
    run = asyncio.run(RuntimeEngine(registry).run(
        demo_adapter(), "Compare 20 monitors; budget 20000 CNY. Read-only demo.",
        allowed_tools=allowed, limits=Limits(max_steps=args.max_steps)))
    print(json.dumps(asdict(run), ensure_ascii=False, indent=2))
    return 0 if run.status == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
