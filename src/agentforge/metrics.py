"""Observed Run metrics; estimates and synthetic usage are never model tokens."""

from datetime import datetime, timezone

from .models import StrictModel


class RunMetrics(StrictModel):
    tool_calls: int
    tool_errors: int
    tool_error_rate: float | None
    wall_clock_seconds: float | None
    model_tokens: int | None
    token_source: str
    cost: None = None


def run_metrics(run):
    responses = [e["payload"] for e in run.events if e["type"] == "model.responded"]
    measured = (
        run.mode == "live"
        and bool(responses)
        and len(responses) == run.model_call_count
        and all(isinstance(e.get("usage_tokens"), int) for e in responses)
    )
    errors = sum(s.kind == "tool" and s.status == "FAILED" for s in run.steps)
    latency = None
    if run.started_at:
        end = (
            datetime.fromisoformat(run.finished_at)
            if run.finished_at
            else datetime.now(timezone.utc)
        )
        latency = max(0, (end - datetime.fromisoformat(run.started_at)).total_seconds())
    return RunMetrics(
        tool_calls=run.tool_call_count,
        tool_errors=errors,
        tool_error_rate=errors / run.tool_call_count if run.tool_call_count else None,
        wall_clock_seconds=latency,
        model_tokens=sum(e["usage_tokens"] for e in responses) if measured else None,
        token_source="provider_reported" if measured else "unknown",
    )
