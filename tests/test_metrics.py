"""Tokens must be observed provider usage; latency includes human waiting."""

from agentforge.metrics import run_metrics
from agentforge.models import RunStep
from agentforge.runtime import RunState


def test_mock_usage_is_not_reported_as_real_tokens_or_free_cost():
    run = RunState(model_call_count=1)
    run.emit("model.responded", usage_tokens=123, token_accounting="provider_reported")
    metrics = run_metrics(run)
    assert metrics.model_tokens is None and metrics.cost is None
    assert metrics.tool_error_rate is None and metrics.wall_clock_seconds is None


def test_live_usage_is_counted_only_when_all_model_attempts_have_usage():
    run = RunState(mode="live", model_call_count=2)
    run.emit("model.responded", usage_tokens=10)
    assert run_metrics(run).model_tokens is None
    run.emit("model.responded", usage_tokens=20)
    assert run_metrics(run).model_tokens == 30
    run.model_call_count = 3
    assert run_metrics(run).model_tokens is None


def test_metrics_count_actual_tool_failures_and_wall_clock_waiting():
    run = RunState(
        tool_call_count=2,
        started_at="2026-10-19T00:00:00+00:00",
        finished_at="2026-10-19T00:00:05+00:00",
        active_seconds=1,
        approval_wait_seconds=4,
    )
    run.steps.append(RunStep(run.run_id, 1, "tool", run.started_at, status="FAILED"))
    metrics = run_metrics(run)
    assert metrics.tool_calls == 2 and metrics.tool_errors == 1
    assert metrics.tool_error_rate == 0.5 and metrics.wall_clock_seconds == 5
