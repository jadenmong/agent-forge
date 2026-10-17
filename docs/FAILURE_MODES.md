# 故障与边界证据

## 2026-10-16 Day 1 补齐：先失败、后修复

新增两个回归测试，修改源码前实际结果为 `2 failed in 0.31s`，原始输出见 `evidence/day1-completion/before-pytest.txt`：

- `test_model_call_limit_stops_repeated_requests`：Limits 不接受 max_model_calls，验证缺少独立上限。
- `test_required_fixture_exists`：要求的 fixture 文件不存在。

补齐后新增覆盖：

| 故障/边界 | 断言测试 |
|---|---|
| 持续请求同一工具，但使用新 call ID | test_endless_mock_is_terminated_at_each_limit：分别触发步数/模型调用/工具次数上限，状态 FAILED、原因准确 |
| 恰好用尽模型调用额度并返回最终答案 | test_model_call_limit_allows_final_response_at_boundary：正常完成 |
| 串行两工具后回到模型 | test_serial_tools_return_results_before_next_model_call：结果关联与数据依赖正确 |
| fixture 不是实际数据源 | test_tools_load_actual_fixture_values：修改价格与交期，返回值和总价随之变化 |
| fixture JSON 损坏/负数/供应商重复 | test_invalid_fixture_is_rejected：严格校验拒绝 |
| 模型调用失败 | test_failed_model_attempt_is_counted_and_step_finalized：计入尝试次数，步骤 FAILED |
| 取消后缺少可检查状态 | test_cancellation_preserves_observable_state_and_steps：CANCELLED、步骤收尾、事件完整并传播取消 |
| 复用已完成 RunState | test_runtime_cannot_reuse_completed_state：拒绝且不增加事件 |

本次原始结果在 `evidence/day1-completion/pytest.txt`，CLI 故障轨迹在同目录 `unknown-tool.json`、`tool-error.json`、`repeat-steps.json`、`repeat-model.json`。

## 2026-10-14 原始故障记录

来源：手工构造的离线故障注入，测试在 `tests/test_runtime.py`。

| 故障 | 当前处置 | 测试 |
|---|---|---|
| 未知工具/非法参数 | 失败且不调用 handler | test_unknown_tool / test_invalid_args_never_execute |
| 禁用/非 allowlist/未审批写入 | 策略拒绝，副作用列表为空 | test_policy_blocks_side_effects |
| 批次后部请求非法 | 整批不执行 | test_batch_preflight_no_partial_execution |
| 重复 call ID（同批/跨轮） | DUPLICATE_CALL_ID，不重放 | test_duplicate_call_id_in_batch / test_duplicate_call_id_across_rounds |
| 工具异常/超时/NaN/非 JSON/过大 | tool.failed + run.failed；不泄漏异常原文 | test_tool_failures |
| 模型异常/超时/非法协议 | 明确失败码，无供应商原文 | test_model_failures |
| 步数/调用数/token 超限 | 明确失败，超预算响应不触发工具 | test_limits_terminate / test_reported_usage_over_budget_blocks_tool |
| 运行 wall time 超限 | 取消协作式工具、执行 finally | test_wall_timeout_during_tool_cleans_up |
| 工具内容诱导越权写入 | 内容不改变代码权限 | test_untrusted_injection_cannot_change_policy |
| 终态再次运行 | 拒绝状态迁移 | test_terminal_state_cannot_restart |
| 取消上层任务 | 传播 CancelledError 并清理 | test_caller_cancellation_propagates |

## 实际发现：非 JSON 模型参数检查顺序

添加 `test_non_json_model_arguments_fail_without_executing[nan]` 后曾出现：

```text
FAILED tests/test_runtime.py::test_non_json_model_arguments_fail_without_executing[nan]
1 failed, 46 passed in 0.63s
```

期望 `MODEL_PROTOCOL_ERROR`，实际 `INVALID_TOOL_ARGUMENTS`。原因：先调用 Pydantic JSON 模式会把 NaN 归一化，丢失原始无效值。
修复：对 `model_dump()` 原始值先执行 `json.dumps(..., allow_nan=False)` 与大小检查，再进入模型计费和工具预检。
最终复测见 `RESULTS.md`。此测试只注入项目自定义 Mock 协议对象，不伪装官方 SDK 返回。

## 尚未验证的风险

- MCP 断连/输出协议错误、供应商 429/5xx/续传、审批拒绝/重复批准、进程重启：对应模块尚未实现。
- 协作式 async 超时不能强制打断 CPU 阻塞或忽略取消的 handler；没有通用沙箱保证。
- 默认只读和执行策略可以阻止示例注入中的写入，不证明能检测所有 Prompt Injection。
- 没有磁盘 checkpoint；进程退出后事件和状态丢失，不得宣称恢复成功。
