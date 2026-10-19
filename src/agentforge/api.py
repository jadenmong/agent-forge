"""Local REST API backed by one SQLite demo database and one task owner."""

import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Generic, Literal, TypeVar
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException

from .demo import TOOL_NAMES, demo_registry
from .eval_service import EvalJobs, EvalView
from .mcp_adapter import MCPClientAdapter
from .metrics import RunMetrics
from .models import AgentConfig, Limits, RunEvent, RunStep, StrictModel
from .runtime import Status
from .service import RunService
from .storage import Storage
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
        default="Use only permitted tools. Writes require explicit human approval.",
        max_length=16000,
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
    mock_scenario: Literal[
        "two-tools", "procurement", "mcp", "purchase", "budget-low"
    ] = "two-tools"


class ApprovalDecision(StrictModel):
    approval_id: str
    decision: Literal["approve", "reject"]


class EvalCreate(StrictModel):
    mode: Literal["mock"] = "mock"


class ApprovalView(BaseModel):
    approval_id: str
    run_id: str
    call_id: str
    tool_name: str
    request_payload: dict
    args_digest: str
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    created_at: str
    decided_at: str | None
    effect: str


class DecisionView(BaseModel):
    run_id: str
    status: Status
    approval: ApprovalView
    replayed: bool


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
    input_summary: str | None
    started_at: str | None
    finished_at: str | None
    active_seconds: float
    approval_wait_seconds: float
    metrics: RunMetrics


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
    schema_version: int


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def create_app(database_path=None) -> FastAPI:
    path = (
        database_path
        or os.environ.get("AGENTFORGE_DB_PATH")
        or Path(__file__).resolve().parents[2] / "data/demo.db"
    )
    storage = Storage(path)
    registry = demo_registry(include_purchase=True)
    service = RunService(storage, registry)
    evals = EvalJobs(storage.path.parent / "evals")
    mcp = MCPClientAdapter()

    @asynccontextmanager
    async def lifespan(app):
        storage.initialize()
        storage.recover()
        evals.recover()
        for tool in await mcp.discover():
            registry.add(tool)
        for config in (
            AgentConfig(allowed_tools=TOOL_NAMES),
            AgentConfig(
                id="mcp-demo",
                name="MCP read-only demo",
                allowed_tools=frozenset(mcp.tool_names),
            ),
            AgentConfig(
                id="purchase-demo",
                name="Purchase approval demo",
                allowed_tools=TOOL_NAMES | {"create_purchase_draft"},
            ),
        ):
            storage.save_agent(config)
        try:
            yield
        finally:
            await evals.close()
            await service.close()
            storage.close()

    app = FastAPI(
        title="AgentForge",
        version="0.4.0",
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

    @app.exception_handler(RuntimeFault)
    async def runtime_error(request, exc):
        if exc.code in {
            "RUN_NOT_FOUND",
            "AGENT_NOT_FOUND",
            "APPROVAL_NOT_FOUND",
            "EVAL_NOT_FOUND",
        }:
            return error(
                request, 404, exc.code, "The requested resource was not found."
            )
        if exc.code == "LIVE_NOT_CONFIGURED":
            return error(
                request,
                503,
                exc.code,
                "Set OPENAI_API_KEY and OPENAI_MODEL on the server before using Live.",
            )
        if exc.code == "STORAGE_BUSY":
            return error(
                request,
                503,
                exc.code,
                "Local storage is busy; query the current decision before retrying.",
            )
        return error(
            request,
            409,
            exc.code,
            "The operation conflicts with the current state or policy; refresh the Run and approval.",
        )

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
                "storage": "sqlite",
                "schema_version": 1,
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
        return envelope(request, storage.agents())

    @app.post("/api/agents", status_code=201, response_model=Envelope[AgentConfig])
    async def create_agent(request: Request, body: AgentCreate):
        if not set(body.allowed_tools) <= {
            tool["name"] for tool in registry.metadata()
        }:
            raise ApiError(422, "UNKNOWN_TOOL", "Select only registered tools.")
        if len(storage.agents()) >= 100:
            raise ApiError(
                409,
                "CAPACITY_REACHED",
                "The local demo agent capacity has been reached.",
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
        storage.save_agent(config)
        return envelope(request, config)

    @app.get("/api/agents/{agent_id}", response_model=Envelope[AgentConfig])
    async def get_agent(request: Request, agent_id: str):
        config = next(
            (agent for agent in storage.agents() if agent.id == agent_id), None
        )
        if config is None:
            raise RuntimeFault("AGENT_NOT_FOUND")
        return envelope(request, config)

    @app.get("/api/tools", response_model=Envelope[list[ToolView]])
    async def tools(request: Request):
        return envelope(request, registry.metadata())

    @app.post("/api/evals/run", status_code=202, response_model=Envelope[EvalView])
    async def create_eval(request: Request, body: EvalCreate):
        return envelope(request, evals.start())

    @app.get("/api/evals", response_model=Envelope[list[EvalView]])
    async def list_evals(request: Request):
        # Summaries avoid returning all traces for every historic batch.
        return envelope(request, [{**report, "results": []} for report in evals.list()])

    @app.get("/api/evals/compare", response_model=Envelope[dict])
    async def compare_evals(request: Request, baseline_id: str, candidate_id: str):
        return envelope(request, evals.compare(baseline_id, candidate_id))

    @app.get("/api/evals/{eval_id}", response_model=Envelope[EvalView])
    async def get_eval(request: Request, eval_id: str):
        return envelope(request, evals.get(eval_id))

    @app.post("/api/runs", status_code=202, response_model=Envelope[RunView])
    async def create_run(request: Request, body: RunCreate):
        if not body.input.strip():
            raise ApiError(422, "INVALID_REQUEST", "Task input must not be blank.")
        return envelope(request, await service.start(body))

    @app.get("/api/runs", response_model=Envelope[list[RunView]])
    async def list_runs(
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        return envelope(request, storage.runs(offset, limit))

    @app.get("/api/runs/{run_id}", response_model=Envelope[RunView])
    async def get_run(request: Request, run_id: str):
        return envelope(request, storage.get_run(run_id))

    @app.get("/api/runs/{run_id}/steps", response_model=Envelope[list[RunStep]])
    async def steps(request: Request, run_id: str):
        return envelope(
            request, [asdict(step) for step in storage.get_run(run_id).steps]
        )

    @app.get("/api/runs/{run_id}/events", response_model=Envelope[list[RunEvent]])
    async def events(
        request: Request, run_id: str, after_event_id: int = Query(0, ge=0)
    ):
        return envelope(
            request,
            [
                event
                for event in storage.get_run(run_id).events
                if event["event_id"] > after_event_id
            ],
        )

    @app.get("/api/approvals", response_model=Envelope[list[ApprovalView]])
    async def inbox(request: Request):
        return envelope(request, storage.approvals(pending_only=True))

    @app.get(
        "/api/runs/{run_id}/approvals", response_model=Envelope[list[ApprovalView]]
    )
    async def approvals(request: Request, run_id: str):
        storage.get_run(run_id)
        return envelope(request, storage.approvals(run_id))

    @app.post("/api/runs/{run_id}/approve", response_model=Envelope[DecisionView])
    async def decide(request: Request, run_id: str, body: ApprovalDecision):
        result = await service.decide(
            run_id, body.approval_id, body.decision, request.state.request_id
        )
        approval = next(
            a for a in storage.approvals(run_id) if a["approval_id"] == body.approval_id
        )
        return envelope(
            request,
            {
                "run_id": run_id,
                "status": result.run.status,
                "approval": approval,
                "replayed": result.replayed,
            },
        )

    @app.post(
        "/api/runs/{run_id}/resume", status_code=202, response_model=Envelope[RunView]
    )
    async def resume(request: Request, run_id: str):
        return envelope(request, await service.resume(run_id))

    return app


app = create_app()
