"""Synthetic HTTP fixtures parsed by the real OpenAI SDK; no live provider test."""

import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from agentforge.demo import TOOL_NAMES, demo_registry
from agentforge.models import AgentConfig
from agentforge.openai_adapter import OpenAIResponsesAdapter
from agentforge.runtime import RuntimeEngine, Status
from agentforge.tools import RuntimeFault


def response(output, *, status="completed"):
    return {
        "id": "resp_offline",
        "object": "response",
        "created_at": 0,
        "model": "offline-model",
        "status": status,
        "output": output,
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }


def message(text="done"):
    return {
        "type": "message",
        "id": "msg_offline",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def client_for(handler):
    return AsyncOpenAI(
        api_key="offline-test",
        base_url="https://offline.invalid/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_responses_tool_continuation_keeps_call_ids_and_encrypted_reasoning():
    requests = []
    reasoning = {
        "type": "reasoning",
        "id": "rs_offline",
        "summary": [],
        "encrypted_content": "opaque-offline-state",
    }
    calls = [
        {
            "type": "function_call",
            "id": f"fc_{i}",
            "call_id": f"call_{i}",
            "status": "completed",
            "name": "calculate_total_cost",
            "arguments": json.dumps({"unit_price_cents": price, "quantity": 20}),
        }
        for i, price in enumerate((95000, 98000))
    ]

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == "offline-model" and body["store"] is False
        assert "previous_response_id" not in body
        assert all(t["type"] == "function" for t in body["tools"])
        if len(requests) == 1:
            return httpx.Response(200, json=response([reasoning, *calls]))
        assert body["input"][1:4] == [reasoning, *calls]
        outputs = body["input"][4:]
        assert [item["call_id"] for item in outputs] == ["call_0", "call_1"]
        assert all(item["type"] == "function_call_output" for item in outputs)
        assert [json.loads(item["output"])["total_cents"] for item in outputs] == [
            1900000,
            1960000,
        ]
        return httpx.Response(200, json=response([message("computed")]))

    async def check():
        adapter = OpenAIResponsesAdapter(client_for(handler), model="offline-model")
        try:
            return await RuntimeEngine(demo_registry()).run(
                adapter,
                "compute",
                config=AgentConfig(model_adapter="openai", allowed_tools=TOOL_NAMES),
            )
        finally:
            await adapter.aclose()

    run = asyncio.run(check())
    assert (
        run.status,
        run.output,
        run.mode,
        run.model_call_count,
        run.tool_call_count,
    ) == (Status.COMPLETED, "computed", "live", 2, 2)
    assert run.budget_tokens == 30 and run.token_accounting == "provider_reported"
    assert "opaque-offline-state" not in json.dumps(run.events)
    assert run.cost is None


@pytest.mark.parametrize(
    "http_status,code",
    [
        (401, "PROVIDER_AUTH"),
        (403, "PROVIDER_AUTH"),
        (429, "PROVIDER_RATE_LIMIT"),
        (500, "PROVIDER_UNAVAILABLE"),
        (400, "PROVIDER_REQUEST_REJECTED"),
    ],
)
def test_provider_errors_are_sanitized_and_not_retried(http_status, code):
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(
            http_status,
            json={"error": {"message": "PRIVATE_PROVIDER_DETAIL", "type": "test"}},
        )

    async def check():
        adapter = OpenAIResponsesAdapter(client_for(handler), model="offline-model")
        try:
            return await RuntimeEngine(demo_registry()).run(
                adapter, "task", config=AgentConfig(model_adapter="openai")
            )
        finally:
            await adapter.aclose()

    run = asyncio.run(check())
    assert run.status == Status.FAILED and run.stop_reason == code
    assert len(attempts) == 1 and run.tool_call_count == 0
    assert "PRIVATE_PROVIDER_DETAIL" not in json.dumps(run.events)


@pytest.mark.parametrize(
    "status,output,reason",
    [
        ("incomplete", [message()], "MODEL_INCOMPLETE"),
        ("failed", [], "MODEL_NOT_COMPLETED"),
        ("completed", [], "MODEL_EMPTY_OUTPUT"),
        (
            "completed",
            [
                {
                    "type": "function_call",
                    "id": "fc",
                    "call_id": "c",
                    "name": "calculate_total_cost",
                    "arguments": "not-json",
                }
            ],
            "MODEL_PROTOCOL_ERROR",
        ),
        (
            "completed",
            [
                {"type": "reasoning", "id": "rs", "summary": []},
                {
                    "type": "function_call",
                    "id": "fc",
                    "call_id": "c",
                    "name": "list_supplier_quotes",
                    "arguments": "{}",
                },
            ],
            "MODEL_CONTINUATION_UNAVAILABLE",
        ),
        (
            "completed",
            [
                {
                    "type": "message",
                    "id": "msg",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "refusal", "refusal": "No"}],
                }
            ],
            "MODEL_REFUSAL",
        ),
    ],
)
def test_model_termination_and_invalid_continuation_do_not_execute_tools(
    status, output, reason
):
    async def check():
        adapter = OpenAIResponsesAdapter(
            client_for(
                lambda request: httpx.Response(
                    200, json=response(output, status=status)
                )
            ),
            model="offline-model",
        )
        try:
            return await RuntimeEngine(demo_registry()).run(
                adapter,
                "task",
                config=AgentConfig(model_adapter="openai", allowed_tools=TOOL_NAMES),
            )
        finally:
            await adapter.aclose()

    run = asyncio.run(check())
    assert (
        run.status == Status.FAILED
        and run.stop_reason == reason
        and run.tool_call_count == 0
    )


@pytest.mark.parametrize(
    "kind,reason",
    [
        (httpx.ConnectError, "PROVIDER_UNAVAILABLE"),
        (httpx.ReadTimeout, "MODEL_TIMEOUT"),
    ],
)
def test_transport_errors(kind, reason):
    def handler(request):
        raise kind("private network detail", request=request)

    async def check():
        adapter = OpenAIResponsesAdapter(client_for(handler), model="offline-model")
        try:
            with pytest.raises(RuntimeFault, match=reason):
                await adapter.respond([{"kind": "input", "text": "task"}], [])
        finally:
            await adapter.aclose()

    asyncio.run(check())


def test_live_requires_environment_configuration(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(RuntimeFault, match="LIVE_NOT_CONFIGURED"):
        OpenAIResponsesAdapter()


def test_encrypted_continuation_survives_sqlite_approval_checkpoint(tmp_path):
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from agentforge.storage import PurchaseDraftRow, Storage

    requests = []
    reasoning = {
        "type": "reasoning",
        "id": "rs_saved",
        "summary": [],
        "encrypted_content": "opaque-fixture-state",
    }
    call = {
        "type": "function_call",
        "id": "fc_write",
        "call_id": "call_write",
        "status": "completed",
        "name": "create_purchase_draft",
        "arguments": json.dumps(
            {
                "supplier": "B",
                "unit_price_cents": 98000,
                "quantity": 20,
                "budget_cents": 2000000,
            }
        ),
    }

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(200, json=response([reasoning, call]))
        assert body["input"][1:3] == [reasoning, call]
        assert (
            body["input"][3]["type"] == "function_call_output"
            and body["input"][3]["call_id"] == "call_write"
        )
        assert json.loads(body["input"][3]["output"])["draft_id"]
        return httpx.Response(
            200, json=response([message("fixture continuation completed")])
        )

    async def check():
        path = tmp_path / "provider-checkpoint.db"
        store = Storage(path)
        store.initialize()
        registry = demo_registry(include_purchase=True)
        config = AgentConfig(
            model_adapter="openai",
            model_name="offline-model",
            allowed_tools=frozenset({"create_purchase_draft"}),
        )
        adapter = OpenAIResponsesAdapter(client_for(handler), model="offline-model")
        try:
            waiting = await RuntimeEngine(registry, storage=store).run(
                adapter, "synthetic draft", config=config
            )
        finally:
            await adapter.aclose()
        assert (
            waiting.status == Status.WAITING_APPROVAL and waiting.tool_call_count == 0
        )
        with Session(store.engine) as session:
            assert (
                session.scalar(select(func.count()).select_from(PurchaseDraftRow)) == 0
            )
        store.close()
        restored = Storage(path)
        restored.initialize()
        restored.recover()
        approval = restored.approvals(waiting.run_id)[0]
        resumed = restored.decide(
            waiting.run_id, approval["approval_id"], "approve", registry
        ).run
        adapter = OpenAIResponsesAdapter(client_for(handler), model="offline-model")
        try:
            done = await RuntimeEngine(registry, storage=restored).run(
                adapter, "synthetic draft", config=config, state=resumed, resume=True
            )
        finally:
            await adapter.aclose()
        assert (
            done.status == Status.COMPLETED
            and done.output == "fixture continuation completed"
        )
        assert "opaque-fixture-state" not in json.dumps(done.events)
        with Session(restored.engine) as session:
            assert (
                session.scalar(select(func.count()).select_from(PurchaseDraftRow)) == 1
            )
        restored.close()

    asyncio.run(check())


def test_incomplete_function_call_is_not_dispatched():
    async def check():
        output = [
            {
                "type": "function_call",
                "id": "fc",
                "call_id": "c",
                "name": "list_supplier_quotes",
                "arguments": "{}",
                "status": "incomplete",
            }
        ]
        adapter = OpenAIResponsesAdapter(
            client_for(lambda request: httpx.Response(200, json=response(output))),
            model="offline-model",
        )
        try:
            run = await RuntimeEngine(demo_registry()).run(
                adapter,
                "task",
                config=AgentConfig(model_adapter="openai", allowed_tools=TOOL_NAMES),
            )
            assert (
                run.stop_reason == "MODEL_PROTOCOL_ERROR" and run.tool_call_count == 0
            )
        finally:
            await adapter.aclose()

    asyncio.run(check())
