"""HTTP evaluation jobs execute the bundled suite and persist their reports."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from agentforge.api import create_app
from agentforge.eval_service import EvalJobs
from agentforge.evals import atomic_json
from agentforge.tools import RuntimeFault


def test_eval_api_executes_mock_suite_compares_and_survives_app_restart(tmp_path):
    database = tmp_path / "demo.db"
    with TestClient(create_app(database)) as client:
        assert client.post("/api/evals/run", json={"mode": "live"}).status_code == 422
        assert (
            client.post("/api/evals/run", json={"dataset": "../private"}).status_code
            == 422
        )
        created = client.post("/api/evals/run", json={"mode": "mock"})
        assert created.status_code == 202
        eval_id = created.json()["data"]["eval_id"]
        for _ in range(600):
            report = client.get(f"/api/evals/{eval_id}").json()["data"]
            if report["status"] != "RUNNING":
                break
            time.sleep(0.1)
        assert report["status"] == "COMPLETED"
        assert report["summary"] == {"total": 42, "passed": 42, "failed": 0}
        assert report["metrics"]["model_tokens"] is None
        assert all(result["checks"] for result in report["results"])
        compared = client.get(
            "/api/evals/compare",
            params={"baseline_id": eval_id, "candidate_id": eval_id},
        )
        assert compared.status_code == 200
        assert compared.json()["data"]["unchanged"] == 42
        assert client.get("/api/evals/not-a-uuid").status_code == 404
        spec = client.get("/openapi.json").json()
        assert "/api/evals/run" in spec["paths"]
    with TestClient(create_app(database)) as client:
        assert (
            client.get(f"/api/evals/{eval_id}").json()["data"]["summary"]["passed"]
            == 42
        )
        assert client.get("/api/evals").json()["data"][0]["results"] == []


def test_interrupted_eval_is_reported_and_not_automatically_replayed(tmp_path):
    eval_id = "067072ec-4b88-4ac9-bc0a-176a09156d20"
    jobs = EvalJobs(tmp_path)
    atomic_json(
        tmp_path / eval_id / "report.json", {"eval_id": eval_id, "status": "RUNNING"}
    )
    jobs.recover()
    assert jobs.get(eval_id)["status"] == "INTERRUPTED"
    assert jobs.tasks == {}


def test_only_one_eval_job_is_allowed_and_shutdown_records_interruption(
    tmp_path, monkeypatch
):
    async def slow(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr("agentforge.eval_service.run_suite", slow)

    async def exercise():
        jobs = EvalJobs(tmp_path)
        created = jobs.start()
        await asyncio.sleep(0)
        with pytest.raises(RuntimeFault, match="CAPACITY_REACHED"):
            jobs.start()
        await jobs.close()
        assert jobs.get(created["eval_id"])["status"] == "INTERRUPTED"

    asyncio.run(exercise())
