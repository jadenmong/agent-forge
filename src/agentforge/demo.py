"""Fixed, synthetic procurement demo and explicit offline fault scenarios."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .models import (
    AgentConfig,
    DeterministicMockAdapter,
    Limits,
    ModelReply,
    StrictModel,
    ToolCall,
)
from .runtime import RuntimeEngine
from .tools import Permission, RuntimeFault, ToolDefinition, ToolRegistry

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "examples/procurement/fixtures.json"
)
TOOL_NAMES = frozenset(
    {"list_supplier_quotes", "get_supplier_detail", "calculate_total_cost"}
)
SCENARIOS = (
    "procurement",
    "direct",
    "single-tool",
    "two-tools",
    "unknown-tool",
    "repeat",
    "tool-error",
)


class EmptyArgs(StrictModel):
    pass


class SupplierArgs(StrictModel):
    supplier: Literal["A", "B", "C"]


class CostArgs(StrictModel):
    unit_price_cents: int = Field(ge=1, le=100000000)
    quantity: int = Field(ge=1, le=10000)


class SupplierFixture(SupplierArgs):
    unit_price_cents: int = Field(ge=1, le=100000000)
    delivery_days: int = Field(ge=0, le=365)
    warranty_months: int = Field(ge=0, le=120)


class ProcurementFixture(StrictModel):
    quantity: int = Field(ge=1, le=10000)
    budget_cents: int = Field(ge=1)
    suppliers: list[SupplierFixture] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def unique_suppliers(self):
        if {s.supplier for s in self.suppliers} != {"A", "B", "C"}:
            raise ValueError("Fixture must contain each of A/B/C once")
        return self


class PurchaseDraftArgs(CostArgs):
    supplier: Literal["A", "B", "C"]
    budget_cents: int = Field(ge=1)

    @model_validator(mode="after")
    def demo_policy(self):
        fixture = load_fixtures()
        quote = next(s for s in fixture.suppliers if s.supplier == self.supplier)
        if quote.unit_price_cents != self.unit_price_cents:
            raise RuntimeFault("DEMO_QUOTE_CHANGED")
        if (
            self.budget_cents > fixture.budget_cents
            or self.quantity * self.unit_price_cents > self.budget_cents
        ):
            raise RuntimeFault("DEMO_BUDGET_EXCEEDED")
        return self


def load_fixtures() -> ProcurementFixture:
    # Fixed project-owned path; neither the task nor model can choose a file.
    return ProcurementFixture.model_validate_json(
        FIXTURE_PATH.read_text(encoding="utf-8")
    )


async def list_quotes(args: EmptyArgs):
    return [
        {"supplier": s.supplier, "unit_price_cents": s.unit_price_cents}
        for s in load_fixtures().suppliers
    ]


async def supplier_detail(args: SupplierArgs):
    supplier = next(s for s in load_fixtures().suppliers if s.supplier == args.supplier)
    return supplier.model_dump(exclude={"unit_price_cents"})


async def calculate_cost(args: CostArgs):
    return {"total_cents": args.unit_price_cents * args.quantity}


def demo_registry(
    *, simulate_tool_error: bool = False, include_purchase: bool = False
) -> ToolRegistry:
    async def detail(args):
        if simulate_tool_error:
            raise RuntimeError("Synthetic demo tool failure")
        return await supplier_detail(args)

    registry = ToolRegistry(
        (
            ToolDefinition(
                "list_supplier_quotes",
                "List synthetic demo quotations",
                EmptyArgs,
                list_quotes,
            ),
            ToolDefinition(
                "get_supplier_detail",
                "Get synthetic delivery and warranty",
                SupplierArgs,
                detail,
            ),
            ToolDefinition(
                "calculate_total_cost",
                "Multiply integer cents by quantity",
                CostArgs,
                calculate_cost,
            ),
        )
    )
    if include_purchase:
        # The approval transaction is the only executor for this built-in DB operation.
        registry.add(
            ToolDefinition(
                "create_purchase_draft",
                "Create one local demo draft only after explicit approval; never places an order.",
                PurchaseDraftArgs,
                None,
                Permission.REQUIRES_APPROVAL,
            )
        )
    return registry


def demo_adapter(scenario: str = "procurement") -> DeterministicMockAdapter:
    quotes = ToolCall(call_id="quotes", tool_name="list_supplier_quotes", arguments={})
    detail = ToolCall(
        call_id="detail-A", tool_name="get_supplier_detail", arguments={"supplier": "A"}
    )
    final = ModelReply(
        final_text="[Mock] Script complete; no draft or order was created."
    )
    if scenario == "direct":
        return DeterministicMockAdapter((final,))
    if scenario == "single-tool":
        return DeterministicMockAdapter((ModelReply(calls=(quotes,)), final))
    if scenario == "two-tools":
        return DeterministicMockAdapter(
            (ModelReply(calls=(quotes,)), ModelReply(calls=(detail,)), final)
        )
    if scenario == "unknown-tool":
        unknown = ToolCall(
            call_id="unknown", tool_name="unregistered_tool", arguments={}
        )
        return DeterministicMockAdapter((ModelReply(calls=(unknown,)),))
    if scenario == "repeat":
        return DeterministicMockAdapter(
            (ModelReply(calls=(quotes,)),), repeat_last=True
        )
    if scenario == "tool-error":
        return DeterministicMockAdapter((ModelReply(calls=(detail,)),))
    if scenario in {"purchase", "budget-low"}:
        fixture = load_fixtures()
        quote = next(s for s in fixture.suppliers if s.supplier == "B")
        read = demo_adapter("procurement").replies[:3]
        write = ToolCall(
            call_id="purchase-draft",
            tool_name="create_purchase_draft",
            arguments={
                "supplier": "B",
                "unit_price_cents": quote.unit_price_cents,
                "quantity": fixture.quantity,
                "budget_cents": fixture.budget_cents if scenario == "purchase" else 100,
            },
        )
        return DeterministicMockAdapter(
            (
                *read,
                ModelReply(calls=(write,)),
                ModelReply(
                    final_text="[Mock] Approved local draft created; no real order was placed."
                ),
            )
        )
    if scenario != "procurement":
        raise ValueError("Unknown mock scenario")
    fixture = load_fixtures()
    totals = ", ".join(
        f"{s.supplier}={s.unit_price_cents * fixture.quantity / 100:.2f}"
        for s in fixture.suppliers
    )
    return DeterministicMockAdapter(
        (
            ModelReply(calls=(quotes,)),
            ModelReply(
                calls=tuple(
                    ToolCall(
                        call_id=f"detail-{s.supplier}",
                        tool_name="get_supplier_detail",
                        arguments={"supplier": s.supplier},
                    )
                    for s in fixture.suppliers
                )
            ),
            ModelReply(
                calls=tuple(
                    ToolCall(
                        call_id=f"total-{s.supplier}",
                        tool_name="calculate_total_cost",
                        arguments={
                            "unit_price_cents": s.unit_price_cents,
                            "quantity": fixture.quantity,
                        },
                    )
                    for s in fixture.suppliers
                )
            ),
            ModelReply(
                final_text=f"[Mock / synthetic data] {totals} CNY; budget={fixture.budget_cents / 100:.2f} CNY. "
                "Predefined comparison summary from fixtures; no draft or order was created."
            ),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="procurement")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--max-model-calls", type=int, default=8)
    args = parser.parse_args()
    config = AgentConfig(
        allowed_tools=TOOL_NAMES,
        limits=Limits(max_steps=args.max_steps, max_model_calls=args.max_model_calls),
    )
    run = asyncio.run(
        RuntimeEngine(
            demo_registry(simulate_tool_error=args.scenario == "tool-error")
        ).run(
            demo_adapter(args.scenario),
            "Compare synthetic monitor quotations. Read-only demo.",
            config=config,
        )
    )
    public = {
        key: value
        for key, value in asdict(run).items()
        if key not in {"model_resume_state", "config_snapshot", "invocations"}
    }
    print(json.dumps(public, ensure_ascii=False, indent=2))
    return 0 if run.status == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
