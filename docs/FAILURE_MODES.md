# 故障与边界证据

## Day 2（2026-10-17）真实发现与回归

| 故障 | 发现/修复 | 证据 |
|---|---|---|
| MCP SDK 最低 Pydantic 版本冲突 | mcp 2.3.0 要求 ≥2.12；升级 2.11.7→2.14.1、刷新 editable 元数据，pip check 无冲突，70 项回归通过 | DECISIONS D008；day2/environment.txt、day1-regression.txt |
| stdio 普通 dict 仅返回文本 | 实际 Client 返回 structured_content=null。改成显式输出模型，真正产生可校验结构化结果 | day2/initial-mcp-failure.txt；test_stdio_discovery_and_real_tool_call |
| 异步上下文异常组吞掉应用原因 | 生命周期异常组曾把 MCP_INVALID_RESULT 变成 MCP_UNAVAILABLE；业务结果校验移出资源块，已知安全原因从异常组解包 | mcp_adapter.connect/call；test_mcp_tool_error_preserves_safe_error_code |
| Windows GBK 输出 Vite Unicode 符号失败 | 统一脚本首次打印构建结果出现 UnicodeEncodeError；为终端输出设置 backslashreplace，原始文件仍保留 UTF-8 stdout | verify_day2.py；day2/web-build.txt |
| TypeScript CSS 导入声明缺失 | 初次 build 出现 TS2882；补 vite/client 类型声明后构建通过 | apps/web/src/vite-env.d.ts；day2/web-build.txt |

外部错误均为安全原因码，无无限重试：

- `test_provider_errors_are_sanitized_and_not_retried`：401/403/429/400/500，断言只发一次请求，原文不进事件。
- `test_model_termination_and_invalid_continuation_do_not_execute_tools`：未完成/空响应/拒绝/无效 JSON/缺少续传状态，工具执行数为零。
- `test_incomplete_function_call_is_not_dispatched`：未完成函数请求不分派。
- `test_mcp_registry_rejects_malicious_arguments_before_dispatch`：穿越样式字符串、错误类型、缺参、额外 command 字段均拒绝。
- `test_real_server_rejects_invalid_supplier_without_registry`：直接调用真实 SDK Server 也拒绝非法 supplier。
- `test_slow_mcp_tool_becomes_structured_failure_without_retry`：真实 SDK 客户端/服务端超时，tool.failed 含 MCP_TIMEOUT，调用一次。
- `test_stdio_server_disconnect_is_explicit`：实际测试子进程在调用时退出，得到 MCP_UNAVAILABLE。
- `test_api_missing_live_configuration_is_readable`、`test_empty_live_environment_does_not_break_agent_creation`：无 Key/模型不产生假成功或空指针。
- `test_create_agent_and_enforce_its_allowlist`：API 创建无权限 Agent，Run 失败且工具执行数为零。

OpenAI 测试为明确标记的合成 HTTP fixture，经官方 SDK 解析，不是外部 API 成功记录；MCP 测试使用真实 SDK 对端，未替换 SDK 返回值。
本次仍未覆盖审批、重启恢复、幂等写入或 Evals；这些功能尚未实现。协议兼容范围限于固定本机服务的工具子集。

## 以下为 Day 1 历史记录

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
