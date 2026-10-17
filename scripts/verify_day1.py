"""Run actual day-one checks and save their unedited stdout as evidence."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "day1-completion"
ENVIRONMENT = {
    key: value
    for key, value in os.environ.items()
    if not key.upper().endswith("API_KEY")
}


def capture(filename, arguments, expected_code=0):
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=ENVIRONMENT,
        timeout=60,
    )
    (EVIDENCE / filename).write_text(result.stdout, encoding="utf-8")
    if result.returncode != expected_code:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(
            f"{arguments}: expected {expected_code}, got {result.returncode}"
        )
    return result.stdout


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    print(
        capture("ruff-check.txt", ["-m", "ruff", "check", "src", "tests", "scripts"]),
        end="",
    )
    print(
        capture(
            "ruff-format.txt",
            ["-m", "ruff", "format", "--check", "src", "tests", "scripts"],
        ),
        end="",
    )
    tests = capture("pytest.txt", ["-m", "pytest", "-q"])
    print(tests, end="")
    scenarios = [
        ("demo", [], "FINAL_ANSWER", 4, 7),
        ("direct", ["--scenario", "direct"], "FINAL_ANSWER", 1, 0),
        ("single-tool", ["--scenario", "single-tool"], "FINAL_ANSWER", 2, 1),
        ("two-tools", ["--scenario", "two-tools"], "FINAL_ANSWER", 3, 2),
        ("unknown-tool", ["--scenario", "unknown-tool"], "UNKNOWN_TOOL", 1, 0),
        ("tool-error", ["--scenario", "tool-error"], "TOOL_ERROR", 1, 1),
        (
            "repeat-steps",
            ["--scenario", "repeat", "--max-steps", "2"],
            "MAX_STEPS",
            2,
            2,
        ),
        (
            "repeat-model",
            ["--scenario", "repeat", "--max-model-calls", "2"],
            "MAX_MODEL_CALLS",
            2,
            2,
        ),
        ("limit", ["--max-steps", "1"], "MAX_STEPS", 1, 1),
    ]
    lines = []
    for name, flags, reason, models, tools in scenarios:
        code = 0 if reason == "FINAL_ANSWER" else 1
        run = json.loads(
            capture(
                f"{name}.json", ["-m", "agentforge.demo", *flags], expected_code=code
            )
        )
        assert run["mode"] == "mock" and run["cost"] is None
        assert run["status"] == ("COMPLETED" if code == 0 else "FAILED")
        assert run["stop_reason"] == reason
        assert (run["model_call_count"], run["tool_call_count"]) == (models, tools)
        assert all(step["status"] != "RUNNING" for step in run["steps"])
        lines.append(
            f"{name}: {run['status']} / {reason}, model_calls={models}, tool_calls={tools}, exit={code}"
        )
    summary = "\n".join(lines) + "\n"
    (EVIDENCE / "smoke.txt").write_text(summary, encoding="utf-8")
    print(summary, end="")
    capture("environment.txt", ["-m", "pip", "freeze"])


if __name__ == "__main__":
    main()
