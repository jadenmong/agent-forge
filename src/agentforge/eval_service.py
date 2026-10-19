"""One local evaluation task; reports persist as public JSON artifacts."""

import asyncio
import json
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .evals import DEFAULT_DATASET, atomic_json, compare_reports, load_cases, run_suite
from .tools import RuntimeFault


class EvalView(BaseModel):
    eval_id: str
    status: Literal["RUNNING", "COMPLETED", "FAILED", "INTERRUPTED"]
    mode: Literal["mock"] = "mock"
    live_quality_evaluation: Literal["NOT_RUN"] = "NOT_RUN"
    summary: dict[str, int] | None = None
    dataset_sha256: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    config: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    results: list[dict] = Field(default_factory=list)
    error: str | None = None


class EvalJobs:
    def __init__(self, root):
        self.root = Path(root)
        self.tasks = {}

    def recover(self):
        for report in self.list():
            if report["status"] == "RUNNING":
                report.update(status="INTERRUPTED", error="PROCESS_INTERRUPTED")
                atomic_json(self.root / report["eval_id"] / "report.json", report)

    def list(self):
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(
                self.root.glob("*/report.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        ]

    def get(self, eval_id):
        try:
            canonical = str(UUID(str(eval_id)))
        except ValueError:
            raise RuntimeFault("EVAL_NOT_FOUND") from None
        path = self.root / canonical / "report.json"
        if not path.exists():
            raise RuntimeFault("EVAL_NOT_FOUND")
        return json.loads(path.read_text(encoding="utf-8"))

    def start(self):
        if (
            any(not task.done() for task in self.tasks.values())
            or len(self.list()) >= 100
        ):
            raise RuntimeFault("CAPACITY_REACHED")
        cases = load_cases(DEFAULT_DATASET)
        eval_id = str(uuid4())
        directory = self.root / eval_id
        pending = EvalView(eval_id=eval_id, status="RUNNING").model_dump()
        atomic_json(directory / "report.json", pending)

        async def execute():
            try:
                await run_suite(cases, directory, eval_id=eval_id)
            except asyncio.CancelledError:
                atomic_json(
                    directory / "report.json",
                    {
                        **pending,
                        "status": "INTERRUPTED",
                        "error": "PROCESS_INTERRUPTED",
                    },
                )
                raise
            except Exception:
                atomic_json(
                    directory / "report.json",
                    {**pending, "status": "FAILED", "error": "EVAL_EXECUTION_ERROR"},
                )

        task = asyncio.create_task(execute())
        self.tasks[eval_id] = task
        task.add_done_callback(lambda done: self.tasks.pop(eval_id, None))
        return pending

    def compare(self, baseline_id, candidate_id):
        first, second = self.get(baseline_id), self.get(candidate_id)
        if first["status"] != "COMPLETED" or second["status"] != "COMPLETED":
            raise RuntimeFault("EVAL_NOT_COMPLETED")
        try:
            return compare_reports(first, second)
        except ValueError:
            raise RuntimeFault("INCOMPARABLE_EVALS") from None

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.recover()
