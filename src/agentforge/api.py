"""Local, single-process REST API. All state is lost on process exit."""

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Generic, Literal, TypeVar
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException

from .demo import TOOL_NAMES, demo_adapter, demo_registry
from .mcp_adapter import MCPClientAdapter
from .models import (
    AgentConfig,
    DeterministicMockAdapter,
    Limits,
    ModelReply,
    RunEvent,
    RunStep,
    StrictModel,
    ToolCall,
)
from .openai_adapter import OpenAIResponsesAdapter
from .runtime import RunState, RuntimeEngine, Status
from .tools import RuntimeFault

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    data: T
    request_id: str


class ErrorInfo(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorInfo


class AgentCreate(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    system_prompt: str = Field(
        default="Use only permitted read-only tools.", max_length=16000
    )
    model_adapter: Literal["mock", "openai"] = "mock"
    allowed_tools: list[str] = Field(
        default_factory=lambda: sorted(TOOL_NAMES), max_length=16
    )
    limits: Limits = Field(default_factory=Limits)


class RunCreate(StrictModel):
    agent_id: str
    input: str = Field(min_length=1, max_length=16000)
    mode: Literal["mock", "live"] = "mock"
    mock_scenario: Literal["two-tools", "procurement", "mcp"] = "two-tools"


class RunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    run_id: str
    agent_id: str
    mode: Literal["mock", "live"]
    status: Status
    stop_reason: str | None
    step_count: int
    model_call_count: int
    tool_call_count: int
    budget_tokens: int
    token_accounting: str
    cost: None
    output: str | None


class ToolView(BaseModel):
    name: str
    description: str
    input_schema: dict
    permission: str
    timeout_seconds: float
    source: str


class HealthView(BaseModel):
    status: str
    storage: str
    live_configured: bool
    mcp_sdk: str
    mcp_protocol: str
    mcp_transport: str


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def create_app() -> FastAPI:
    agents: dict[str, AgentConfig] = {}
    runs: dict[str, RunState] = {}
    tasks: set[asyncio.Task] = set()
    registry = demo_registry()
    mcp = MCPClientAdapter()

    @asynccontextmanager
    async def lifespan(app):
        for tool in await mcp.discover():
            registry.add(tool)
        agents["procurement-demo"] = AgentConfig(allowed_tools=TOOL_NAMES)
        agents["mcp-demo"] = AgentConfig(
            id="mcp-demo",
            name="MCP read-only demo",
            allowed_tools=frozenset(mcp.tool_names),
        )
        yield
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(
        title="AgentForge",
        version="0.2.0",
        lifespan=lifespan,
        responses={
            code: {"model": ErrorEnvelope} for code in (400, 404, 409, 422, 500, 503)
        },
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if request.url.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}:
            response = error(
                request, 400, "INVALID_HOST", "Use the local service hostname."
            )
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def envelope(request, data):
        return {"data": data, "request_id": request.state.request_id}

    def error(request, status, code, message):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": request.state.request_id,
                }
            },
        )

    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        return error(request, exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error(
            request, 422, "INVALID_REQUEST", "Request fields or values are invalid."
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(
            request,
            exc.status_code,
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "Request could not be handled.",
        )

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return error(request, 500, "INTERNAL_ERROR", "An internal error occurred.")

    @app.get("/health", response_model=Envelope[HealthView])
    async def health(request: Request):
        return envelope(
            request,
            {
                "status": "ok",
                "storage": "memory",
                "live_configured": bool(
                    os.environ.get("OPENAI_API_KEY", "").strip()
                    and os.environ.get("OPENAI_MODEL", "").strip()
                ),
                "mcp_sdk": "2.3.0",
                "mcp_protocol": mcp.protocol_version,
                "mcp_transport": "stdio",
            },
        )

    @app.get("/api/agents", response_model=Envelope[list[AgentConfig]])
    async def list_agents(request: Request):
        return envelope(request, list(agents.values()))

    @app.post("/api/agents", status_code=201, response_model=Envelope[AgentConfig])
    async def create_agent(request: Request, body: AgentCreate):
        if not set(body.allowed_tools) <= {t["name"] for t in registry.metadata()}:
            raise ApiError(422, "UNKNOWN_TOOL", "Select only registered tools.")
        if len(agents) >= 100:
            raise ApiError(
                409,
                "CAPACITY_REACHED",
                "Restart the local service to clear demo history.",
            )
        config = AgentConfig(
            id=str(uuid4()),
            name=body.name,
            system_prompt=body.system_prompt,
            allowed_tools=frozenset(body.allowed_tools),
            limits=body.limits,
            model_adapter=body.model_adapter,
            model_name=(os.environ.get("OPENAI_MODEL", "").strip() or "not_configured")
            if body.model_adapter == "openai"
            else "deterministic-mock",
        )
        agents[config.id] = config
        return envelope(request, config)

    @app.get("/api/agents/{agent_id}", response_model=Envelope[AgentConfig])
    async def get_agent(request: Request, agent_id: str):
        if agent_id not in agents:
            raise ApiError(404, "AGENT_NOT_FOUND", "Agent was not found.")
        return envelope(request, agents[agent_id])

    @app.get("/api/tools", response_model=Envelope[list[ToolView]])
    async def tools(request: Request):
        return envelope(request, registry.metadata())

    async def execute(adapter, body, config, state):
        try:
            await RuntimeEngine(registry).run(
                adapter, body.input, config=config, state=state
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            if state.status == Status.RUNNING:
                state.transition(Status.FAILED)
                state.stop_reason = "INTERNAL_ERROR"
                state.emit("run.failed", code="INTERNAL_ERROR")
        finally:
            if isinstance(adapter, OpenAIResponsesAdapter):
                await adapter.aclose()

    @app.post("/api/runs", status_code=202, response_model=Envelope[RunView])
    async def create_run(request: Request, body: RunCreate):
        if body.agent_id not in agents:
            raise ApiError(404, "AGENT_NOT_FOUND", "Agent was not found.")
        if not body.input.strip():
            raise ApiError(422, "INVALID_REQUEST", "Task input must not be blank.")
        if len(tasks) >= 4 or len(runs) >= 200:
            raise ApiError(
                409, "CAPACITY_REACHED", "Local run capacity has been reached."
            )
        config = agents[body.agent_id].model_copy(
            update={
                "model_adapter": "openai" if body.mode == "live" else "mock",
                "model_name": (
                    os.environ.get("OPENAI_MODEL", "").strip() or "not_configured"
                )
                if body.mode == "live"
                else "deterministic-mock",
            }
        )
        if body.mode == "live":
            try:
                adapter = OpenAIResponsesAdapter()
            except RuntimeFault:
                raise ApiError(
                    503,
                    "LIVE_NOT_CONFIGURED",
                    "Set OPENAI_API_KEY and OPENAI_MODEL on the server before using Live.",
                ) from None
        elif body.mock_scenario == "mcp":
            adapter = DeterministicMockAdapter(
                (
                    ModelReply(
                        calls=(
                            ToolCall(
                                call_id="mcp-q",
                                tool_name="mcp_list_supplier_quotes",
                                arguments={},
                            ),
                        )
                    ),
                    ModelReply(
                        calls=(
                            ToolCall(
                                call_id="mcp-d",
                                tool_name="mcp_get_supplier_detail",
                                arguments={"supplier": "A"},
                            ),
                        )
                    ),
                    ModelReply(final_text="[Mock] Two MCP read-only calls completed."),
                )
            )
        else:
            adapter = demo_adapter(body.mock_scenario)
        state = RunState(agent_id=config.id, mode=body.mode)
        runs[state.run_id] = state
        task = asyncio.create_task(execute(adapter, body, config, state))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return envelope(request, state)

    def find_run(run_id):
        if run_id not in runs:
            raise ApiError(404, "RUN_NOT_FOUND", "Run was not found.")
        return runs[run_id]

    @app.get("/api/runs", response_model=Envelope[list[RunView]])
    async def list_runs(
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        return envelope(
            request, list(reversed(list(runs.values())))[offset : offset + limit]
        )

    @app.get("/api/runs/{run_id}", response_model=Envelope[RunView])
    async def get_run(request: Request, run_id: str):
        return envelope(request, find_run(run_id))

    @app.get("/api/runs/{run_id}/steps", response_model=Envelope[list[RunStep]])
    async def steps(request: Request, run_id: str):
        return envelope(request, [asdict(step) for step in find_run(run_id).steps])

    @app.get("/api/runs/{run_id}/events", response_model=Envelope[list[RunEvent]])
    async def events(
        request: Request, run_id: str, after_event_id: int = Query(0, ge=0)
    ):
        return envelope(
            request,
            [
                event
                for event in find_run(run_id).events
                if event["event_id"] > after_event_id
            ],
        )

    return app


app = create_app()
