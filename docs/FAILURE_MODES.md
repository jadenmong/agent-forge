# 故障与边界证据

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
