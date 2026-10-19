"""Offline regression, real local HTTP/curl, and browser verification for Day 2."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/day2"
ENV = {k: v for k, v in os.environ.items() if not k.upper().endswith("API_KEY")}
ENV.pop("OPENAI_MODEL", None)


def capture(name, command, *, cwd=ROOT, timeout=60):
    result = subprocess.run(
        command,
        cwd=cwd,
        env=ENV,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    (EVIDENCE / name).write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        (EVIDENCE / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        raise RuntimeError(f"{name} failed with exit {result.returncode}")
    return result.stdout


def wait_http(url):
    import httpx

    for _ in range(150):
        try:
            response = httpx.get(url, timeout=1, trust_env=False)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Local service did not become ready: {url}")


def main():
    # Windows redirected consoles may use GBK while Vite emits Unicode symbols.
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    temporary = TemporaryDirectory(prefix="agentforge-day2-")
    ENV["AGENTFORGE_DB_PATH"] = str(Path(temporary.name) / "demo.db")
    print(
        capture(
            "ruff-check.txt",
            [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"],
        ),
        end="",
    )
    print(
        capture(
            "ruff-format.txt",
            [
                sys.executable,
                "-m",
                "ruff",
                "format",
                "--check",
                "src",
                "tests",
                "scripts",
            ],
        ),
        end="",
    )
    print(
        capture(
            "day1-regression.txt",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_runtime.py",
                "tests/test_day1_contract.py",
                "-q",
            ],
        ),
        end="",
    )
    print(
        capture("pytest.txt", [sys.executable, "-m", "pytest", "-q"], timeout=120),
        end="",
    )
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    print(
        capture("web-build.txt", [npm, "run", "build"], cwd=ROOT / "apps/web"), end=""
    )
    for port in (8000, 5173):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    processes = []
    handles = []
    try:
        for name, command, cwd in [
            (
                "api",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "agentforge.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                ROOT,
            ),
            (
                "web",
                [
                    shutil.which("node"),
                    "node_modules/vite/bin/vite.js",
                    "--host",
                    "127.0.0.1",
                ],
                ROOT / "apps/web",
            ),
        ]:
            handle = (EVIDENCE / f"{name}.log").open("w", encoding="utf-8")
            handles.append(handle)
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=ENV,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            )
        wait_http("http://127.0.0.1:8000/health")
        wait_http("http://127.0.0.1:5173")
        curl = shutil.which("curl.exe") or shutil.which("curl")
        base = [curl, "--silent", "--show-error", "--fail", "--noproxy", "*"]
        body = EVIDENCE / "curl-request.json"
        body.write_text(
            json.dumps(
                {
                    "agent_id": "procurement-demo",
                    "mode": "mock",
                    "input": "Read-only synthetic comparison",
                }
            ),
            encoding="utf-8",
        )
        created = json.loads(
            capture(
                "curl-create.json",
                [
                    *base,
                    "-X",
                    "POST",
                    "-H",
                    "Content-Type: application/json",
                    "--data-binary",
                    f"@{body}",
                    "http://127.0.0.1:8000/api/runs",
                ],
            )
        )
        run_id = created["data"]["run_id"]
        for _ in range(100):
            snapshot = json.loads(
                capture(
                    "curl-run.json", [*base, f"http://127.0.0.1:8000/api/runs/{run_id}"]
                )
            )
            if snapshot["data"]["status"] not in {"CREATED", "RUNNING"}:
                break
            time.sleep(0.05)
        assert (
            snapshot["data"]["status"] == "COMPLETED"
            and snapshot["data"]["tool_call_count"] == 2
        )
        capture(
            "curl-steps.json", [*base, f"http://127.0.0.1:8000/api/runs/{run_id}/steps"]
        )
        capture("openapi.json", [*base, "http://127.0.0.1:8000/openapi.json"])
        capture("health.json", [*base, "http://127.0.0.1:8000/health"])
        with sync_playwright() as playwright:
            edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
            browser = playwright.chromium.launch(
                headless=True, **({"channel": "msedge"} if edge.exists() else {})
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.goto("http://127.0.0.1:5173")
            expect(page.get_by_label("选择 Agent").locator("option")).to_have_count(3)
            page.get_by_text("创建 Agent", exact=True).click()
            page.get_by_label("Agent 名称").fill("Browser verified agent")
            page.get_by_role("button", name="保存 Agent").click()
            expect(page.get_by_label("选择 Agent").locator("option")).to_have_count(4)
            expect(
                page.get_by_label("选择 Agent").locator("option:checked")
            ).to_have_text("Browser verified agent")
            page.get_by_role("button", name="启动 Run").click()
            expect(page.get_by_test_id("run-status")).to_have_text(
                "COMPLETED", timeout=15000
            )
            expect(page.get_by_test_id("tool-step")).to_have_count(2)
            assert all(
                "COMPLETED" in text
                for text in page.get_by_test_id("tool-step").all_text_contents()
            )
            page.screenshot(path=str(EVIDENCE / "workbench.png"), full_page=True)
            page.get_by_label("选择 Agent").select_option("mcp-demo")
            page.get_by_role("button", name="启动 Run").click()
            expect(page.get_by_test_id("run-status")).to_have_text(
                "COMPLETED", timeout=20000
            )
            expect(page.get_by_test_id("tool-step")).to_have_count(2)
            expect(page.get_by_test_id("tool-step").first).to_contain_text(
                "mcp_", timeout=20000
            )
            page.screenshot(path=str(EVIDENCE / "workbench-mcp.png"), full_page=True)
            page.get_by_label("模型模式").select_option("live")
            page.get_by_role("button", name="启动 Run").click()
            expect(page.get_by_role("alert")).to_contain_text("LIVE_NOT_CONFIGURED")
            browser.close()
        summary = {
            "curl": "PASS: created and queried a real Mock Run, 2 tool steps",
            "browser": "PASS: created Agent, ran 2 local tools and 2 MCP tools, missing Live key error visible",
            "live_external_api": "NOT_TESTED: OPENAI_API_KEY and OPENAI_MODEL not configured",
            "mcp_sdk": "2.3.0",
            "mcp_protocol": "2026-07-28",
            "transport": "stdio",
        }
        (EVIDENCE / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        capture("environment.txt", [sys.executable, "-m", "pip", "freeze"])
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for handle in handles:
            handle.close()
        temporary.cleanup()


if __name__ == "__main__":
    main()
