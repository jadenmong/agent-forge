# AgentForge Mock 回归报告

日期（UTC）：2026-10-19T02:27:06.707383+00:00

此报告检查状态、协议与政策正确性，不评估真实模型任务质量。未进行真实模型质量评测。

样本 42；通过 42；失败 0。

Dataset SHA-256：`2dcab0ad937d6fa46cefeb3692437e6dbff3261db634d4e9f9e479c77d7c7c7d`

工具错误率包含刻意注入的故障；耗时含本地运行/审批/恢复，不是供应商性能基准。Mock tokens 和成本均为 unknown。

| case_id | 结果 | 实际状态 / 原因 | 工具调用 | 错误率 | wall-clock s |
|---|---|---|---:|---:|---:|
| normal-direct | PASS | COMPLETED / FINAL_ANSWER | 0 | None | 0.034165 |
| normal-single | PASS | COMPLETED / FINAL_ANSWER | 1 | 0.0 | 0.065338 |
| normal-serial | PASS | COMPLETED / FINAL_ANSWER | 2 | 0.0 | 0.131337 |
| normal-multi | PASS | COMPLETED / FINAL_ANSWER | 7 | 0.0 | 0.4537 |
| schema-missing | PASS | FAILED / INVALID_TOOL_ARGUMENTS | 0 | None | 0.025177 |
| schema-wrong-type | PASS | FAILED / INVALID_TOOL_ARGUMENTS | 0 | None | 0.026437 |
| schema-negative | PASS | FAILED / INVALID_TOOL_ARGUMENTS | 0 | None | 0.033378 |
| schema-extra-command | PASS | FAILED / INVALID_TOOL_ARGUMENTS | 0 | None | 0.0318 |
| unknown-tool | PASS | FAILED / UNKNOWN_TOOL | 0 | None | 0.026439 |
| allowlist-blocked | PASS | FAILED / TOOL_FORBIDDEN | 0 | None | 0.026525 |
| explicit-denied | PASS | FAILED / TOOL_FORBIDDEN | 0 | None | 0.022603 |
| batch-preflight | PASS | FAILED / UNKNOWN_TOOL | 0 | None | 0.037377 |
| duplicate-call-id | PASS | FAILED / DUPLICATE_CALL_ID | 1 | 0.0 | 0.072937 |
| limit-steps | PASS | FAILED / MAX_STEPS | 2 | 0.0 | 0.103099 |
| limit-model-calls | PASS | FAILED / MAX_MODEL_CALLS | 2 | 0.0 | 0.120177 |
| limit-tool-calls | PASS | FAILED / MAX_TOOL_CALLS | 1 | 0.0 | 0.073457 |
| limit-input-budget | PASS | FAILED / TOKEN_BUDGET | 0 | None | 0.017808 |
| limit-reported-budget | PASS | FAILED / TOKEN_BUDGET | 0 | None | 0.027777 |
| limit-wall-time | PASS | FAILED / WALL_TIME_LIMIT | 1 | 1.0 | 0.210185 |
| tool-timeout | PASS | FAILED / TOOL_TIMEOUT | 1 | 1.0 | 0.063582 |
| tool-error | PASS | FAILED / TOOL_ERROR | 1 | 1.0 | 0.047184 |
| tool-large | PASS | FAILED / TOOL_OUTPUT_TOO_LARGE | 1 | 1.0 | 0.043981 |
| tool-non-json | PASS | FAILED / TOOL_ERROR | 1 | 1.0 | 0.041095 |
| tool-nan | PASS | FAILED / TOOL_ERROR | 1 | 1.0 | 0.040604 |
| model-timeout | PASS | FAILED / MODEL_TIMEOUT | 0 | None | 0.057826 |
| model-error | PASS | FAILED / MODEL_ERROR | 0 | None | 0.022111 |
| model-invalid | PASS | FAILED / MODEL_PROTOCOL_ERROR | 0 | None | 0.02511 |
| model-incomplete | PASS | FAILED / MODEL_INCOMPLETE | 0 | None | 0.025606 |
| model-large | PASS | FAILED / MODEL_OUTPUT_TOO_LARGE | 0 | None | 0.02676 |
| provider-auth | PASS | FAILED / PROVIDER_AUTH | 0 | None | 0.030322 |
| provider-rate-limit | PASS | FAILED / PROVIDER_RATE_LIMIT | 0 | None | 0.022176 |
| approval-pending | PASS | WAITING_APPROVAL / APPROVAL_REQUIRED | 7 | 0.0 | 0.536508 |
| approval-approve | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 0.636837 |
| approval-reject | PASS | CANCELLED / APPROVAL_REJECTED | 7 | 0.0 | 0.469284 |
| approval-repeat-approve | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 0.649231 |
| approval-concurrent-approve | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 0.716268 |
| approval-restart-approval | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 3.603226 |
| approval-decision-conflict | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 0.754304 |
| approval-safe-resume | PASS | COMPLETED / FINAL_ANSWER | 8 | 0.0 | 0.676373 |
| approval-unknown-write | PASS | RECONCILIATION_REQUIRED / WRITE_OUTCOME_UNKNOWN | 7 | 0.0 | 0.578212 |
| injection-no-permission | PASS | FAILED / TOOL_FORBIDDEN | 1 | 0.0 | 0.11039 |
| injection-needs-human | PASS | WAITING_APPROVAL / APPROVAL_REQUIRED | 1 | 0.0 | 0.123996 |
