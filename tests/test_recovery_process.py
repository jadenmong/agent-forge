"""Real API process restart and SQLite assertions, with only loopback traffic."""

import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentforge.storage import PurchaseDraftRow, Storage

ROOT = Path(__file__).resolve().parents[1]


class ApiProcess:
    def __init__(self, database_path, log_path, *, port=0):
        if not port:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().endswith("API_KEY")
        }
        environment["AGENTFORGE_DB_PATH"] = str(database_path)
        environment.pop("OPENAI_MODEL", None)
        self.log = log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "agentforge.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                self.url.rsplit(":", 1)[1],
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=environment,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.client = httpx.Client(base_url=self.url, timeout=10, trust_env=False)
        for _ in range(120):
            if self.process.poll() is not None:
                self.stop()
                raise AssertionError("API process exited during startup")
            try:
                if self.client.get("/health").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        self.stop()
        raise AssertionError("API process startup timed out")

    def stop(self):
        self.client.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.log.close()


def wait_status(client, run_id, expected):
    for _ in range(150):
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        run = response.json()["data"]
        if run["status"] == expected:
            return run
        assert run["status"] in {"CREATED", "RUNNING", "WAITING_APPROVAL"}, run
        time.sleep(0.05)
    raise AssertionError(f"Run did not reach {expected}")


def count_drafts(path, run_id):
    store = Storage(path)
    try:
        with Session(store.engine) as session:
            return session.scalar(
                select(func.count())
                .select_from(PurchaseDraftRow)
                .where(PurchaseDraftRow.run_id == run_id)
            )
    finally:
        store.close()


def test_real_process_restart_restores_same_approval_context_and_one_draft(tmp_path):
    database = tmp_path / "restart.db"
    first = ApiProcess(database, tmp_path / "first.log")
    task = "Compare the synthetic quotations and prepare a draft; wait for approval."
    try:
        response = first.client.post(
            "/api/runs",
            json={
                "agent_id": "purchase-demo",
                "mode": "mock",
                "input": task,
                "mock_scenario": "purchase",
            },
        )
        assert response.status_code == 202
        run_id = response.json()["data"]["run_id"]
        wait_status(first.client, run_id, "WAITING_APPROVAL")
        approval = first.client.get(f"/api/runs/{run_id}/approvals").json()["data"][0]
        assert approval["status"] == "PENDING" and count_drafts(database, run_id) == 0
        store = Storage(database)
        checkpoint = store.get_run(run_id).model_resume_state
        store.close()
        assert checkpoint["context"][1]["text"] == task
    finally:
        first.stop()

    second = ApiProcess(database, tmp_path / "second.log")
    try:
        assert (
            second.client.get(f"/api/runs/{run_id}").json()["data"]["status"]
            == "WAITING_APPROVAL"
        )
        restored = second.client.get(f"/api/runs/{run_id}/approvals").json()["data"][0]
        assert (
            restored["approval_id"],
            restored["run_id"],
            restored["args_digest"],
            restored["request_payload"],
        ) == (
            approval["approval_id"],
            run_id,
            approval["args_digest"],
            approval["request_payload"],
        )
        store = Storage(database)
        assert store.get_run(run_id).model_resume_state == checkpoint
        store.close()
        assert count_drafts(database, run_id) == 0
        body = {"approval_id": approval["approval_id"], "decision": "approve"}

        def approve(_):
            with httpx.Client(
                base_url=second.url, timeout=15, trust_env=False
            ) as client:
                return client.post(f"/api/runs/{run_id}/approve", json=body)

        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(approve, range(12)))
        assert all(response.status_code == 200 for response in responses), [
            response.text for response in responses
        ]
        assert (
            sum(not response.json()["data"]["replayed"] for response in responses) == 1
        )
        completed = wait_status(second.client, run_id, "COMPLETED")
        assert completed["model_call_count"] == 5 and completed["tool_call_count"] == 8
        assert count_drafts(database, run_id) == 1
        assert (
            second.client.post(f"/api/runs/{run_id}/approve", json=body).status_code
            == 200
        )
        assert count_drafts(database, run_id) == 1
        assert second.client.post(f"/api/runs/{run_id}/resume").status_code == 409
        assert (
            second.client.get(f"/api/runs/{run_id}").json()["data"]["status"]
            == "COMPLETED"
        )
        events = second.client.get(f"/api/runs/{run_id}/events").json()["data"]
        types = [event["type"] for event in events]
        assert {
            "run.checkpointed",
            "run.checkpoint_restored",
            "approval.requested",
            "approval.approved",
            "run.resumed",
            "run.completed",
        } <= set(types)
        assert types.count("approval.approved") == types.count("run.resumed") == 1
        assert "model_resume_state" not in completed
    finally:
        second.stop()
