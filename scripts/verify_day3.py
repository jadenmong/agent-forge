"""Real SQLite, process restart, approval UI and curl verification; no model key."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentforge.storage import (
    ApprovalRow,
    EventRow,
    InvocationRow,
    PurchaseDraftRow,
    StepRow,
    Storage,
    digest,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/day3"
sys.path.insert(0, str(ROOT / "tests"))
from test_recovery_process import ApiProcess, count_drafts, wait_status  # noqa: E402


def capture(name, command, environment, *, cwd=ROOT, timeout=150):
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    (EVIDENCE / name).write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        (EVIDENCE / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        raise RuntimeError(f"{name}: exit {result.returncode}")
    return result.stdout


def sql_counts(path, run_id):
    store = Storage(path)
    try:
        with Session(store.engine) as session:
            counts = {
                table.__tablename__: session.scalar(
                    select(func.count())
                    .select_from(table)
                    .where(table.run_id == run_id)
                )
                for table in (
                    StepRow,
                    EventRow,
                    InvocationRow,
                    ApprovalRow,
                    PurchaseDraftRow,
                )
            }
            run = store.get_run(run_id)
            counts["model_resume_state_digest"] = digest(run.model_resume_state)
            counts["model_call_count"] = run.model_call_count
            counts["tool_call_count"] = run.tool_call_count
            return counts
    finally:
        store.close()


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().endswith("API_KEY")
    }
    env.pop("OPENAI_MODEL", None)
    for filename, args in [
        ("ruff-check.txt", ["ruff", "check", "src", "tests", "scripts"]),
        ("ruff-format.txt", ["ruff", "format", "--check", "src", "tests", "scripts"]),
        ("pytest.txt", ["pytest", "-q", f"--junitxml={EVIDENCE / 'pytest.xml'}"]),
    ]:
        print(capture(filename, [sys.executable, "-m", *args], env), end="")
    cases = ET.parse(EVIDENCE / "pytest.xml").findall(".//testcase")
    (EVIDENCE / "test-names.txt").write_text(
        "\n".join(
            f"{case.attrib['classname']}::{case.attrib['name']}" for case in cases
        )
        + "\n",
        encoding="utf-8",
    )
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    print(
        capture("web-build.txt", [npm, "run", "build"], env, cwd=ROOT / "apps/web"),
        end="",
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        web_port = sock.getsockname()[1]
    web_url = f"http://127.0.0.1:{web_port}"
    with TemporaryDirectory(prefix="agentforge-day3-") as temporary:
        database = Path(temporary) / "demo.db"
        api = web = None
        web_log = (EVIDENCE / "web.log").open("w", encoding="utf-8")
        try:
            api = ApiProcess(database, EVIDENCE / "api-before-restart.log")
            api_port = int(api.url.rsplit(":", 1)[1])
            env["AGENTFORGE_API_PORT"] = str(api_port)
            web = subprocess.Popen(
                [
                    shutil.which("node"),
                    "node_modules/vite/bin/vite.js",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                ],
                cwd=ROOT / "apps/web",
                env=env,
                stdout=web_log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            for _ in range(100):
                try:
                    if (
                        httpx.get(web_url, timeout=1, trust_env=False).status_code
                        == 200
                    ):
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            assertions = {}
            with sync_playwright() as playwright:
                edge = Path(
                    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
                )
                browser = playwright.chromium.launch(
                    headless=True, **({"channel": "msedge"} if edge.exists() else {})
                )
                page = browser.new_page(viewport={"width": 1440, "height": 1100})
                page.goto(web_url)
                expect(page.get_by_label("选择 Agent").locator("option")).to_have_count(
                    3
                )
                page.get_by_label("选择 Agent").select_option("purchase-demo")
                page.get_by_role("button", name="启动 Run").click()
                expect(page.get_by_test_id("run-status")).to_have_text(
                    "WAITING_APPROVAL", timeout=15000
                )
                pending = api.client.get("/api/approvals").json()["data"][0]
                run_id, approval_id = pending["run_id"], pending["approval_id"]
                expect(page.get_by_test_id("approval-card")).to_contain_text(
                    approval_id
                )
                before = sql_counts(database, run_id)
                assert before["purchase_drafts"] == 0
                assertions["before_approval"] = before
                page.screenshot(
                    path=str(EVIDENCE / "waiting-approval.png"), full_page=True
                )
                api.stop()
                api = ApiProcess(
                    database, EVIDENCE / "api-after-restart.log", port=api_port
                )
                restored = api.client.get(f"/api/runs/{run_id}/approvals").json()[
                    "data"
                ][0]
                assert (
                    restored["approval_id"] == approval_id
                    and restored["request_payload"] == pending["request_payload"]
                    and restored["args_digest"] == pending["args_digest"]
                )
                after_restart = sql_counts(database, run_id)
                assert (
                    after_restart["model_resume_state_digest"]
                    == before["model_resume_state_digest"]
                    and after_restart["purchase_drafts"] == 0
                )
                assertions["after_process_restart"] = after_restart
                page.reload()
                expect(page.get_by_test_id("approval-card")).to_contain_text(
                    approval_id
                )
                page.get_by_role("button", name="批准", exact=True).click()
                expect(page.get_by_test_id("run-status")).to_have_text(
                    "COMPLETED", timeout=15000
                )
                assert count_drafts(database, run_id) == 1
                assertions["after_approve"] = sql_counts(database, run_id)
                body = {"approval_id": approval_id, "decision": "approve"}

                def replay(_):
                    with httpx.Client(
                        base_url=api.url, trust_env=False, timeout=15
                    ) as client:
                        response = client.post(f"/api/runs/{run_id}/approve", json=body)
                        assert (
                            response.status_code == 200
                            and response.json()["data"]["replayed"]
                        )

                with ThreadPoolExecutor(max_workers=6) as pool:
                    list(pool.map(replay, range(12)))
                assert count_drafts(database, run_id) == 1
                assertions["after_12_concurrent_replays"] = sql_counts(database, run_id)
                write_row = page.get_by_test_id("tool-step").filter(
                    has_text="create_purchase_draft"
                )
                expect(write_row).to_contain_text("COMPLETED")
                write_row.locator("summary").click()
                page.get_by_label("筛选事件").fill("approval")
                expect(
                    page.get_by_test_id("trace-event").filter(
                        has_text="approval.approved"
                    )
                ).to_have_count(1)
                page.screenshot(
                    path=str(EVIDENCE / "approved-trace.png"), full_page=True
                )
                assert api.client.post(f"/api/runs/{run_id}/resume").status_code == 409
                for name, route in [
                    ("run", f"/api/runs/{run_id}"),
                    ("steps", f"/api/runs/{run_id}/steps"),
                    ("events", f"/api/runs/{run_id}/events"),
                    ("approval", f"/api/runs/{run_id}/approvals"),
                ]:
                    (EVIDENCE / f"persisted-{name}.json").write_text(
                        json.dumps(
                            api.client.get(route).json(), ensure_ascii=False, indent=2
                        ),
                        encoding="utf-8",
                    )
                page.get_by_label("选择 Agent").select_option("purchase-demo")
                page.get_by_role("button", name="启动 Run").click()
                expect(page.get_by_test_id("run-status")).to_have_text(
                    "WAITING_APPROVAL", timeout=15000
                )
                rejected = api.client.get("/api/approvals").json()["data"][0]
                assert count_drafts(database, rejected["run_id"]) == 0
                page.get_by_role("button", name="拒绝", exact=True).click()
                expect(page.get_by_test_id("run-status")).to_have_text(
                    "CANCELLED", timeout=15000
                )
                assert count_drafts(database, rejected["run_id"]) == 0
                assertions["rejected_run"] = {
                    "run_id": rejected["run_id"],
                    **sql_counts(database, rejected["run_id"]),
                }
                page.get_by_label("演示场景").select_option("budget-low")
                page.get_by_role("button", name="启动 Run").click()
                expect(page.get_by_test_id("run-status")).to_have_text(
                    "FAILED", timeout=15000
                )
                page.get_by_label("筛选事件").fill("failed")
                expect(page.get_by_test_id("trace-event")).to_contain_text(
                    "DEMO_BUDGET_EXCEEDED"
                )
                page.screenshot(
                    path=str(EVIDENCE / "failure-trace.png"), full_page=True
                )
                browser.close()
            curl = shutil.which("curl.exe") or shutil.which("curl")
            flags = [curl, "--silent", "--show-error", "--fail", "--noproxy", "*"]
            created = json.loads(
                capture(
                    "curl-create.json",
                    [
                        *flags,
                        "-X",
                        "POST",
                        "-H",
                        "Content-Type: application/json",
                        "--data-binary",
                        "@examples/http/create-run.json",
                        f"{api.url}/api/runs",
                    ],
                    env,
                )
            )
            read_id = created["data"]["run_id"]
            wait_status(api.client, read_id, "COMPLETED")
            capture("curl-query.json", [*flags, f"{api.url}/api/runs/{read_id}"], env)
            request_file = EVIDENCE / "curl-approve-request.json"
            request_file.write_text(json.dumps(body), encoding="utf-8")
            replayed = json.loads(
                capture(
                    "curl-approval-replay.json",
                    [
                        *flags,
                        "-X",
                        "POST",
                        "-H",
                        "Content-Type: application/json",
                        "--data-binary",
                        f"@{request_file}",
                        f"{api.url}/api/runs/{run_id}/approve",
                    ],
                    env,
                )
            )
            assert replayed["data"]["replayed"] and count_drafts(database, run_id) == 1
            capture("openapi.json", [*flags, f"{api.url}/openapi.json"], env)
            capture("health.json", [*flags, f"{api.url}/health"], env)
            assertions["run_id"], assertions["approval_id"] = run_id, approval_id
            assertions["same_approval_and_context_restored"] = True
            (EVIDENCE / "database-assertions.json").write_text(
                json.dumps(assertions, indent=2), encoding="utf-8"
            )
            summary = {
                "status": "PASS",
                "pytest_cases": len(cases),
                "database_invariants": "0 before approval; 1 after approve and 12 concurrent replays; 0 for rejected Run",
                "restart": "real API process stopped/restarted; same run_id, approval_id, parameters and private context digest",
                "ui": "waiting approval, approved tool arguments/result, checkpoint/approval events, rejection and budget failure verified",
                "live_external_api": "NOT_TESTED; verification subprocesses have no API key",
            }
            (EVIDENCE / "summary.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )
            print(json.dumps(summary, indent=2))
            capture("environment.txt", [sys.executable, "-m", "pip", "freeze"], env)
        finally:
            if api is not None:
                api.stop()
            if web is not None:
                web.terminate()
                try:
                    web.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    web.kill()
                    web.wait(timeout=5)
            web_log.close()


if __name__ == "__main__":
    main()
