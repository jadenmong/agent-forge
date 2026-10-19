"""Day 4 gates and real four-page browser flow; only loopback and Mock."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/day4"
sys.path.insert(0, str(ROOT / "tests"))
from test_recovery_process import ApiProcess, count_drafts  # noqa: E402


def capture(name, command, env, *, cwd=ROOT, timeout=240):
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    (EVIDENCE / name).parent.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{name}: exit {result.returncode}")
    return result.stdout


def browser_check(env):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        web_port = sock.getsockname()[1]
    with TemporaryDirectory(prefix="agentforge-day4-ui-") as temporary:
        database = Path(temporary) / "demo.db"
        api = ApiProcess(database, EVIDENCE / "api.log")
        web = None
        web_log = (EVIDENCE / "web.log").open("w", encoding="utf-8")
        try:
            web_env = {**env, "AGENTFORGE_API_PORT": api.url.rsplit(":", 1)[1]}
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
                env=web_env,
                stdout=web_log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            web_url = f"http://127.0.0.1:{web_port}"
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
            else:
                raise RuntimeError("Web startup timed out")
            with sync_playwright() as playwright:
                edge = Path(
                    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
                )
                browser = playwright.chromium.launch(
                    headless=True, **({"channel": "msedge"} if edge.exists() else {})
                )
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1100})
                    page_errors = []
                    page.on("pageerror", lambda error: page_errors.append(str(error)))
                    page.goto(web_url)
                    expect(
                        page.get_by_label("选择 Agent").locator("option")
                    ).to_have_count(3)
                    page.get_by_label("选择 Agent").select_option("purchase-demo")
                    page.get_by_role("textbox", name="任务", exact=True).fill(
                        "Compare synthetic quotations; create a demo draft only after my approval."
                    )
                    page.get_by_role("button", name="启动 Run", exact=True).click()
                    expect(page.get_by_test_id("run-status")).to_have_text(
                        "WAITING_APPROVAL", timeout=15000
                    )
                    pending = api.client.get("/api/approvals").json()["data"][0]
                    assert count_drafts(database, pending["run_id"]) == 0
                    page.screenshot(
                        path=str(EVIDENCE / "workbench.png"), full_page=False
                    )
                    page.get_by_role("link", name="Approval", exact=True).click()
                    expect(page.get_by_test_id("approval-card")).to_contain_text(
                        pending["approval_id"]
                    )
                    page.screenshot(
                        path=str(EVIDENCE / "approval.png"), full_page=False
                    )
                    page.get_by_role("button", name="批准", exact=True).click()
                    page.get_by_role("link", name="Trace", exact=True).click()
                    expect(page.get_by_test_id("run-status")).to_have_text(
                        "COMPLETED", timeout=15000
                    )
                    assert count_drafts(database, pending["run_id"]) == 1
                    tool = page.get_by_test_id("tool-step").filter(
                        has_text="create_purchase_draft"
                    )
                    expect(tool).to_contain_text("COMPLETED")
                    tool.locator("summary").click()
                    page.get_by_label("筛选事件").fill("approval")
                    expect(
                        page.get_by_test_id("trace-event").filter(
                            has_text="approval.approved"
                        )
                    ).to_have_count(1)
                    page.screenshot(path=str(EVIDENCE / "trace.png"), full_page=True)
                    page.reload()
                    expect(page.get_by_test_id("run-status")).to_have_text(
                        "COMPLETED", timeout=15000
                    )
                    page.get_by_role("link", name="Workbench", exact=True).click()
                    page.get_by_label("模型模式").select_option("live")
                    page.get_by_role("button", name="启动 Run", exact=True).click()
                    expect(page.get_by_role("alert")).to_contain_text(
                        "LIVE_NOT_CONFIGURED"
                    )
                    page.get_by_label("模型模式").select_option("mock")
                    page.get_by_role("link", name="Evals", exact=True).click()
                    expect(page.get_by_role("alert")).to_have_count(0)
                    page.get_by_role(
                        "button", name="运行 Mock 评测", exact=True
                    ).click()
                    expect(page.get_by_test_id("eval-status")).to_have_text(
                        "COMPLETED", timeout=90000
                    )
                    expect(page.get_by_test_id("eval-summary")).to_contain_text(
                        "样本 42 · 通过 42 · 失败 0"
                    )
                    expect(page.get_by_test_id("eval-case")).to_have_count(42)
                    first = api.client.get("/api/evals").json()["data"][0]["eval_id"]
                    page.get_by_role(
                        "button", name="运行 Mock 评测", exact=True
                    ).click()
                    expect(page.get_by_test_id("eval-status")).to_have_text(
                        "RUNNING", timeout=10000
                    )
                    expect(page.get_by_test_id("eval-status")).to_have_text(
                        "COMPLETED", timeout=90000
                    )
                    second = api.client.get("/api/evals").json()["data"][0]["eval_id"]
                    assert first != second
                    page.get_by_label("基线批次").select_option(first)
                    page.get_by_label("候选批次").select_option(second)
                    page.get_by_role("button", name="比较批次", exact=True).click()
                    expect(page.get_by_test_id("eval-comparison")).to_contain_text(
                        "回归 0 · 修复 0 · 未变 42"
                    )
                    page.evaluate("window.scrollTo(0, 0)")
                    page.screenshot(path=str(EVIDENCE / "evals.png"), full_page=False)
                    comparison = page.get_by_test_id("eval-comparison")
                    comparison.scroll_into_view_if_needed()
                    page.screenshot(
                        path=str(EVIDENCE / "comparison.png"), full_page=False
                    )
                    report = api.client.get(f"/api/evals/{second}").json()["data"]
                    for case in report["results"]:
                        assert case["passed"]
                        if case["scenario"].startswith("injection-"):
                            assert (
                                case["actual"]["side_effects"]["purchase_drafts"] == 0
                            )
                    assert not page_errors, page_errors
                    (EVIDENCE / "browser-eval.json").write_text(
                        json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    (EVIDENCE / "browser-summary.json").write_text(
                        json.dumps(
                            {
                                "status": "PASS",
                                "pages": ["Workbench", "Trace", "Approval", "Evals"],
                                "drafts_before": 0,
                                "drafts_after": 1,
                                "eval_cases": 42,
                                "passed": 42,
                                "failed": 0,
                                "baseline_id": first,
                                "candidate_id": second,
                                "console_exceptions": page_errors,
                                "live_missing_key": "LIVE_NOT_CONFIGURED",
                                "comparison": "0 regressions / 42 unchanged",
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                finally:
                    browser.close()
            curl = shutil.which("curl.exe") or shutil.which("curl")
            flags = [curl, "--silent", "--show-error", "--fail", "--noproxy", "*"]
            created = json.loads(
                capture(
                    "curl-create.json",
                    [
                        *flags,
                        "-H",
                        "Content-Type: application/json",
                        "--data-binary",
                        "@examples/http/create-run.json",
                        f"{api.url}/api/runs",
                    ],
                    env,
                )
            )
            run_id = created["data"]["run_id"]
            for _ in range(100):
                run = api.client.get(f"/api/runs/{run_id}").json()["data"]
                if run["status"] == "COMPLETED":
                    break
                time.sleep(0.1)
            assert (
                run["status"] == "COMPLETED" and run["metrics"]["model_tokens"] is None
            )
            capture("curl-query.json", [*flags, f"{api.url}/api/runs/{run_id}"], env)
            capture("openapi.json", [*flags, f"{api.url}/openapi.json"], env)
            capture("health.json", [*flags, f"{api.url}/health"], env)
        finally:
            api.stop()
            if web is not None:
                web.terminate()
                try:
                    web.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    web.kill()
                    web.wait(timeout=5)
            web_log.close()


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-only", action="store_true")
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().endswith("API_KEY")
    }
    env.pop("OPENAI_MODEL", None)
    if not args.browser_only:
        for filename, command in [
            ("ruff-check.txt", ["ruff", "check", "src", "tests", "scripts"]),
            (
                "ruff-format.txt",
                ["ruff", "format", "--check", "src", "tests", "scripts"],
            ),
            ("pytest.txt", ["pytest", "-q", f"--junitxml={EVIDENCE / 'pytest.xml'}"]),
        ]:
            print(
                capture(filename, [sys.executable, "-m", *command], env),
                end="",
                flush=True,
            )
        cases = ET.parse(EVIDENCE / "pytest.xml").findall(".//testcase")
        (EVIDENCE / "test-names.txt").write_text(
            "\n".join(
                f"{case.attrib['classname']}::{case.attrib['name']}" for case in cases
            )
            + "\n",
            encoding="utf-8",
        )
        with TemporaryDirectory(prefix="agentforge-day4-evals-") as temporary:
            for name in ("mock-a", "mock-b"):
                destination = Path(temporary) / name
                print(
                    capture(
                        f"{name}-stdout.txt",
                        [
                            sys.executable,
                            "-m",
                            "agentforge.evals",
                            "run",
                            "--output",
                            str(destination),
                        ],
                        env,
                    ),
                    end="",
                    flush=True,
                )
                (EVIDENCE / name).mkdir(exist_ok=True)
                for filename in ("report.json", "report.md"):
                    shutil.copy2(destination / filename, EVIDENCE / name / filename)
            print(
                capture(
                    "compare-stdout.txt",
                    [
                        sys.executable,
                        "-m",
                        "agentforge.evals",
                        "compare",
                        str(EVIDENCE / "mock-a/report.json"),
                        str(EVIDENCE / "mock-b/report.json"),
                        "--output",
                        str(EVIDENCE / "comparison.json"),
                    ],
                    env,
                ),
                end="",
                flush=True,
            )
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        print(
            capture("web-build.txt", [npm, "run", "build"], env, cwd=ROOT / "apps/web"),
            end="",
            flush=True,
        )
        capture("pip-check.txt", [sys.executable, "-m", "pip", "check"], env)
        capture("environment.txt", [sys.executable, "-m", "pip", "freeze"], env)
        docker = shutil.which("docker")
        (EVIDENCE / "docker-status.txt").write_text(
            "NOT_TESTED: Docker executable is not installed. Compose configuration supplied; no container execution claim.\n"
            if docker is None
            else "Docker executable detected; container execution requires separate verification.\n",
            encoding="utf-8",
        )
    browser_check(env)
    print(
        "PASS: four-page Playwright, native SQL invariants, two Mock batches, comparison, missing Live key and curl.",
        flush=True,
    )


if __name__ == "__main__":
    main()
