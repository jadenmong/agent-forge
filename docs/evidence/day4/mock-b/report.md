# AgentForge Mock 回归报告

日期（UTC）：2026-10-19T02:27:24.318924+00:00

此报告检查状态、协议与政策正确性，不评估真实模型任务质量。未进行真实模型质量评测。

样本 42；通过 42；失败 0。

Dataset SHA-256：`2dcab0ad937d6fa46cefeb3692437e6dbff3261db634d4e9f9e479c77d7c7c7d`

工具错误率包含刻意注入的故障；耗时含本地运行/审批/恢复，不是供应商性能基准。Mock tokens 和成本均为 unknown。

| case_id | 结果 | 实际状态 / 原因 | 工具调用 | 错误率 | wall-clock s |
|---|---|---|---:|---:|---:|
| normal-direct | PASS | COMPLETED / FINAL_ANSWER | 0 | None | 0.033569 |
| normal-single | PASS | COMPLETED / FINAL_ANSWER | 1 | 0.0 | 0.058517 |
| normal-serial | PASS | COMPLETED / FINAL_ANSWER | 2 | 0.0 | 0.102527 |
| normal-multi | PASS | COMPLETED / FINAL_ANSWER | 7 | 0.0 | 0.404849 |
| schema-missing | PASS | FAILED / INVALID_TOOL_ARGUMENTS | 0 | None | 0.022023 |
| schema-wrong-type | PASS | FAILED / INVALID_TOOL_ARGUMENTS | 0 | None | 0.033115 |
| schema-negative | PASS | FAILED / INVALID_TOOL_ARGUMENTS | 0 | None | 0.023419 |
| schema-extra-command | PASS | FAILED / INVALID_TOOL_ARGUMENTS | 0 | None | 0.02588 |
| unknown-tool | PASS | FAILED / UNKNOWN_TOOL | 0 | None | 0.024584 |
| allowlist-blocked | PASS | FAILED / TOOL_FORBIDDEN | 0 | None | 0.02202 |
| explicit-denied | PASS | FAILED / TOOL_FORBIDDEN | 0 | None | 0.025196 |
| batch-preflight | PASS | FAILED / UNKNOWN_TOOL | 0 | None | 0.024715 |
| duplicate-call-id | PASS | FAILED / DUPLICATE_CALL_ID | 1 | 0.0 | 0.0712 |
| limit-steps | PASS | FAILED / MAX_STEPS | 2 | 0.0 | 0.109726 |
| limit-model-calls | PASS | FAILED / MAX_MODEL_CALLS | 2 | 0.0 | 0.097931 |
| limit-tool-calls | PASS | FAILED / MAX_TOOL_CALLS | 1 | 0.0 | 0.064537 |
| limit-input-budget | PASS | FAILED / TOKEN_BUDGET | 0 | None | 0.015394 |
| limit-reported-budget | PASS | FAILED / TOKEN_BUDGET | 0 | None | 0.024232 |
| limit-wall-time | PASS | FAILED / WALL_TIME_LIMIT | 1 | 1.0 | 0.220585 |
| tool-timeout | PASS | FAILED / TOOL_TIMEOUT | 1 | 1.0 | 0.077895 |
| tool-error | PASS | FAILED / TOOL_ERROR | 1 | 1.0 | 0.040442 |
| tool-large | PASS | FAILED / TOOL_OUTPUT_TOO_LARGE | 1 | 1.0 | 0.043546 |
| tool-non-json | PASS | FAILED / TOOL_ERROR | 1 | 1.0 | 0.041579 |
| tool-nan | PASS | FAILED / TOOL_ERROR | 1 | 1.0 | 0.04914 |
| model-timeout | PASS | FAILED / MODEL_TIMEOUT | 0 | None | 0.049178 |
| model-error | PASS | FAILED / MODEL_ERROR | 0 | None | 0.021621 |
| model-invalid | PASS | FAILED / MODEL_PROTOCOL_ERROR | 0 | None | 0.027741 |
| model-incomplete | PASS | FAILED / MODEL_INCOMPLETE | 0 | None | 0.021417 |
| model-large | PASS | FAILED / MODEL_OUTPUT_TOO_LARGE | 0 | None | 0.021746 |
| provider-auth | PASS | FAILED / PROVIDER_AUTH | 0 | None | 0.021691 |
| provider-rate-limit | PASS | FAILED / PROVIDER_RATE_LIMIT | 0 | None | 0.022305 |
| approval-pending | PASS | WAITING_APPROVAL / APPROVAL_REQUIRED | 7 | 0.0 | 0.441632 |
| approval-approve | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 0.57242 |
| approval-reject | PASS | CANCELLED / APPROVAL_REJECTED | 7 | 0.0 | 0.523853 |
| approval-repeat-approve | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 0.638947 |
| approval-concurrent-approve | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 0.683857 |
| approval-restart-approval | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 2.590636 |
| approval-decision-conflict | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 0.593798 |
| approval-safe-resume | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 0.988623 |
| approval-unknown-write | PASS | RECONCILIATION_REQUIRED / WRITE_OUTCOME_UNKNOWN | 7 | 0.0 | 0.629715 |
| injection-no-permission | PASS | FAILED / TOOL_FORBIDDEN | 1 | 0.0 | 0.110247 |
| injection-needs-human | PASS | WAITING_APPROVAL / APPROVAL_REQUIRED | 1 | 0.0 | 0.10186 |
