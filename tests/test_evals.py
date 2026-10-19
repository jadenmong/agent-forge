"""Independent evaluations must inspect real state and fail closed."""

import asyncio
import json
import subprocess
import sys

import pytest

from agentforge.evals import DEFAULT_DATASET, compare_reports, load_cases, run_suite


def test_bundled_mock_dataset_executes_all_cases_and_records_evidence(tmp_path):
    cases = load_cases(DEFAULT_DATASET)
    assert 30 <= len(cases) <= 50
    report = asyncio.run(run_suite(cases, tmp_path / "eval"))
    assert report["summary"] == {"total": len(cases), "passed": len(cases), "failed": 0}
    assert report["mode"] == "mock"
    assert report["live_quality_evaluation"] == "NOT_RUN"
    assert all(result["run_id"] and result["checks"] for result in report["results"])
    assert all(
        result["metrics"]["model_tokens"] is None for result in report["results"]
    )
    assert all(result["metrics"]["cost"] is None for result in report["results"])
    restart = next(r for r in report["results"] if r["scenario"] == "restart-approval")
    assert restart["observations"]["same_approval_and_context_restored"] is True
    assert restart["observations"]["drafts_before_approval"] == 0
    assert (tmp_path / "eval/report.json").exists()
    assert "Mock" in (tmp_path / "eval/report.md").read_text(encoding="utf-8")


def test_wrong_expected_side_effect_is_reported_failed_not_skipped(tmp_path):
    case = load_cases(DEFAULT_DATASET)[0].model_copy(
        update={"expected_side_effects": {"purchase_drafts": 1}}
    )
    report = asyncio.run(run_suite([case], tmp_path / "wrong"))
    assert report["summary"] == {"total": 1, "passed": 0, "failed": 1}
    assert report["results"][0]["checks"]["side_effects"] is False
    assert "FAIL" in (tmp_path / "wrong/report.md").read_text(encoding="utf-8")


def test_dataset_rejects_duplicate_ids_and_unsupported_modes(tmp_path):
    case = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8").splitlines()[0])
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(case) + "\n" + json.dumps(case), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        load_cases(path)
    case["mode"] = "live"
    path.write_text(json.dumps(case), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(path)


def test_compare_reports_rejects_mismatched_cases_and_tracks_regressions(tmp_path):
    cases = load_cases(DEFAULT_DATASET)[:1]
    first = asyncio.run(run_suite(cases, tmp_path / "a"))
    second = asyncio.run(run_suite(cases, tmp_path / "b"))
    assert compare_reports(first, second)["regressions"] == []
    second["results"][0]["passed"] = False
    assert compare_reports(first, second)["regressions"] == [cases[0].case_id]
    second["dataset_sha256"] = "different"
    with pytest.raises(ValueError, match="Incomparable"):
        compare_reports(first, second)


def test_cli_fails_when_a_case_has_wrong_expectations(tmp_path):
    case = load_cases(DEFAULT_DATASET)[0].model_dump(mode="json")
    case["expected_side_effects"] = {"purchase_drafts": 1}
    path = tmp_path / "wrong.jsonl"
    path.write_text(json.dumps(case), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge.evals",
            "run",
            "--dataset",
            str(path),
            "--output",
            str(tmp_path / "output"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["failed"] == 1


def test_malformed_tool_schema_is_rejected_before_handler_execution():
    from jsonschema import SchemaError

    from agentforge.demo import EmptyArgs
    from agentforge.tools import ToolDefinition

    effects = []

    async def handler(args):
        effects.append("executed")

    with pytest.raises(SchemaError):
        ToolDefinition(
            "bad_schema",
            "synthetic",
            EmptyArgs,
            handler,
            input_schema={"type": "not-a-json-schema-type"},
        )
    assert effects == []
