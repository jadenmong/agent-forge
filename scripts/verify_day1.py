"""Run actual day-one checks and save their unedited stdout as evidence."""

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"


def capture(filename, arguments, expected_code=0):
    result = subprocess.run(
        [sys.executable, *arguments], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", env=None,
    )
    (EVIDENCE / filename).write_text(result.stdout, encoding="utf-8")
    if result.returncode != expected_code:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"{arguments}: expected {expected_code}, got {result.returncode}")
    return result.stdout


def main():
    EVIDENCE.mkdir(exist_ok=True)
    tests = capture("day1-pytest.txt", ["-m", "pytest", "-q", "-ra"])
    print(tests, end="")
    demo = json.loads(capture("day1-demo.json", ["-m", "agentforge.demo"]))
    limited = json.loads(capture(
        "day1-limit.json", ["-m", "agentforge.demo", "--max-steps", "1"], expected_code=1))
    assert demo["status"] == "COMPLETED" and demo["mode"] == "mock"
    assert (demo["step_count"], demo["tool_call_count"]) == (4, 7)
    assert demo["cost"] is None
    assert limited["status"] == "FAILED" and limited["stop_reason"] == "MAX_STEPS"
    summary = "Mock demo: COMPLETED, 4 model turns, 7 tool calls\nLimit demo: FAILED / MAX_STEPS, exit 1\n"
    (EVIDENCE / "day1-smoke.txt").write_text(summary, encoding="utf-8")
    print(summary, end="")
    capture("day1-environment.txt", ["-m", "pip", "freeze"])


if __name__ == "__main__":
    main()
