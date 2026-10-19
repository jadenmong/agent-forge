"""One-process task ownership around durable Runtime checkpoints."""

import asyncio
import json
import os

from .demo import demo_adapter
from .models import AgentConfig, DeterministicMockAdapter, ModelReply, ToolCall
from .openai_adapter import OpenAIResponsesAdapter
from .redaction import redact
from .runtime import RunState, RuntimeEngine, Status
from .tools import RuntimeFault


def restore_adapter(state):
    snapshot = state.model_resume_state.get("adapter", {})
    if snapshot.get("kind") == "mock":
        return DeterministicMockAdapter(
            tuple(
                ModelReply.model_validate_json(json.dumps(reply))
                for reply in snapshot["replies"]
            ),
            repeat_last=snapshot["repeat_last"],
        )
    if snapshot.get("kind") == "openai":
        if os.environ.get("OPENAI_MODEL", "").strip() != snapshot["model"]:
            raise RuntimeFault("LIVE_MODEL_CHANGED")
        return OpenAIResponsesAdapter()
    raise RuntimeFault("UNSUPPORTED_CHECKPOINT_ADAPTER")


class RunService:
    def __init__(self, storage, registry):
        self.storage, self.registry = storage, registry
        self.tasks: dict[str, asyncio.Task] = {}

    def _capacity(self):
        if sum(not task.done() for task in self.tasks.values()) >= 4:
            raise RuntimeFault("CAPACITY_REACHED")

    def _schedule(self, state, config, adapter, task_input, *, resume=False):
        async def execute():
            try:
                await RuntimeEngine(self.registry, storage=self.storage).run(
                    adapter, task_input, config=config, state=state, resume=resume
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                current = self.storage.get_run(state.run_id)
                if (
                    current.status == Status.RUNNING
                    and current.revision == state.revision
                ):
                    current.transition(Status.FAILED)
                    current.stop_reason = "INTERNAL_ERROR"
                    current.emit("run.failed", code="INTERNAL_ERROR")
                    self.storage.save(current)
            finally:
                if isinstance(adapter, OpenAIResponsesAdapter):
                    await adapter.aclose()

        task = asyncio.create_task(execute())
        self.tasks[state.run_id] = task

        def finished(done):
            if self.tasks.get(state.run_id) is done:
                self.tasks.pop(state.run_id)
            if not done.cancelled():
                done.exception()

        task.add_done_callback(finished)

    async def start(self, body):
        self._capacity()
        if self.storage.run_count() >= 200:
            raise RuntimeFault("CAPACITY_REACHED")
        config = next(
            (agent for agent in self.storage.agents() if agent.id == body.agent_id),
            None,
        )
        if config is None:
            raise RuntimeFault("AGENT_NOT_FOUND")
        config = config.model_copy(
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
            adapter = OpenAIResponsesAdapter()
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
        state = RunState(
            agent_id=config.id, mode=body.mode, input_summary=redact(body.input)[:160]
        )
        try:
            self.storage.create_run(state, config, body.input)
            self._schedule(state, config, adapter, body.input)
        except Exception:
            if isinstance(adapter, OpenAIResponsesAdapter):
                await adapter.aclose()
            raise
        return state

    async def decide(self, run_id, approval_id, decision, request_id):
        pending = next(
            (
                a
                for a in self.storage.approvals(run_id)
                if a["approval_id"] == approval_id
            ),
            None,
        )
        if pending is None:
            raise RuntimeFault("APPROVAL_NOT_FOUND")
        adapter = None
        try:
            if pending["status"] == "PENDING" and decision == "approve":
                previous = self.tasks.get(run_id)
                if previous is not None and not previous.done():
                    await asyncio.shield(previous)
                self._capacity()
                adapter = restore_adapter(self.storage.get_run(run_id))
            result = self.storage.decide(
                run_id, approval_id, decision, self.registry, request_id=request_id
            )
            if result.resume:
                config = AgentConfig.model_validate_json(
                    json.dumps(result.run.config_snapshot)
                )
                task_input = result.run.model_resume_state["context"][1]["text"]
                self._schedule(result.run, config, adapter, task_input, resume=True)
                adapter = None
            return result
        finally:
            if isinstance(adapter, OpenAIResponsesAdapter):
                await adapter.aclose()

    async def resume(self, run_id):
        state = self.storage.get_run(run_id)
        if (
            state.status != Status.INTERRUPTED
            or state.model_resume_state.get("safe_point") != "AFTER_APPROVED_TOOL"
        ):
            raise RuntimeFault("UNSAFE_RESUME_POINT")
        self._capacity()
        adapter = restore_adapter(state)
        try:
            state = self.storage.claim_resume(run_id)
            config = AgentConfig.model_validate_json(json.dumps(state.config_snapshot))
            self._schedule(
                state,
                config,
                adapter,
                state.model_resume_state["context"][1]["text"],
                resume=True,
            )
        except Exception:
            if isinstance(adapter, OpenAIResponsesAdapter):
                await adapter.aclose()
            raise
        return state

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
