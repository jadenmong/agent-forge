# 故障与边界证据

## Day 4（2026-10-19）评测与指标故障

| 故障/边界 | 验证与处理 | 证据 |
|---|---|---|
| runner 尚未实现 | 先写数据集执行、错误期望、比较等需求测试，实际 import 失败；随后实现 | day4/initial-eval-failure.txt |
| 合成 Mock usage 被旧逻辑标成 provider_reported | 强化已有预算测试先失败，再标为 synthetic_mock_usage；事件 usage_tokens 留空，合成值另放 synthetic_usage_tokens；真实模型 tokens 仍 unknown | day4/synthetic-usage-before-fix.txt；test_reported_usage_over_budget_blocks_tool、test_mock_usage_is_not_reported_as_real_tokens_or_free_cost |
| 只断言评测 HTTP 202 会掩盖错误判定 | 故意设置 direct case 期望草案 1，实际 0 时必须 FAIL；CLI 返回 1；不跳过 | test_wrong_expected_side_effect_is_reported_failed_not_skipped、test_cli_fails_when_a_case_has_wrong_expectations |
| Mock 被误当 Live 质量 | schema mode 仅 mock、API 拒绝 live；每份报告 NOT_RUN；UI/README 明示未进行真实模型质量评测 | 42 条报告、test_dataset_rejects_duplicate_ids_and_unsupported_modes、test_eval_api_executes_mock_suite_compares_and_survives_app_restart |
| 恶意 tool result 诱导写入 | 真实 untrusted_note 工具返回注入文本，后续脚本请求写；无权限失败、有权限仍待审；草案 0 | 两个 injection-* case；观察字段 malicious_result_returned/model_received_untrusted_result 都必须 true |
| retryable 被理解成会重试 | 超时/限流只分类，无自动重试；工具超时判定包含实际尝试 1 次 | tool-timeout / provider-rate-limit case；config.automatic_retries=0 |
| runner 意外异常会不会漏记？ | 异常转换为明确 EVAL_ERROR，计失败而非 skip；所有用例都有 results 项 | evals.run_suite；固定 suite 总数与报告数核对 |
| 不同数据集的“提升”被混比 | 比较前核对模式、数据集、fixture、judge、case IDs；不一致拒绝 | test_compare_reports_rejects_mismatched_cases_and_tracks_regressions；API 409 |
| eval task 随进程退出丢失 | 运行中报告启动后标 INTERRUPTED；不自动重放整批操作 | test_interrupted_eval_is_reported_and_not_automatically_replayed、test_only_one_eval_job_is_allowed_and_shutdown_records_interruption |
| Playwright 任务输入定位失败 | 精确 label 未匹配；宽松 label 又匹配历史下拉。改用 textbox 角色和精确可访问名称 | day4/initial-browser-failure.txt：实际失败摘录，非完整 stderr |
| 新环境的浏览器失败输出又触发解码错误 | Windows 子进程 stderr 编码与父进程 UTF-8 捕获不一致；统一 Python IO 为 UTF-8，并保留不可解码字节为转义，重新演练候选检出 | day4/initial-clean-checkout-failure.txt；clean-checkout 日志 |

42 条是 Codex 依据 PRD/现有失败模式构造的离线控制回归，不是经过人工评审的 Live 标签集。负向场景正确失败可判 PASS；工具错误率含故障注入，不能当线上可靠性。真实进程恢复分别验证 Runtime worker 和原 Uvicorn 安全等待点，不扩大任意恢复声明。
本机新的 venv/npm ci 演练与容器是不同证据；Docker 不可用时容器运行未测。CI 配置存在不表示云端已执行，不能用本机结果填成远端 CI 通过。

## Day 3（2026-10-18）失败复现、恢复与范围

| 故障/风险 | 行为与验证 | 证据 |
|---|---|---|
| 模块未实现时先跑持久化需求测试 | 保存实际失败输出，再补 SQLite/审批/恢复实现 | evidence/day3/initial-persistence-failure.txt |
| 待审 checkpoint 损坏导致启动报错 | 先复现；修为单 Run FAILED / CHECKPOINT_INVALID，不执行、不拖垮其他任务 | checkpoint-redaction-failure.txt；test_corrupted_waiting_checkpoint_fails_closed_on_startup |
| 手机号正则误伤 SHA-256 中数字段 | 增加边界；摘要保持不变，Key/Bearer/PII 仍遮盖 | checkpoint-redaction-failure.txt；test_trace_redacts_secrets_and_pii_without_mangling_digest |
| 参数替换或跨 Run 审批 | JSON extra=forbid；从 DB 绑定读取，哈希/上下文/权限再次校验 | test_api_rejects_bound_parameter_override_and_cross_run_approval；test_pending_parameter_tampering_never_writes |
| INSERT 后、事务提交前异常 | 注入实际 flush 后异常，SQL 查询草案 0、审批仍 PENDING；可安全重试 | test_write_and_decision_roll_back_together |
| 并发首次批准/重复批准 | 原生线程和真实 HTTP 请求竞争，只有一次首次决议和一条草案 | test_sequential_and_concurrent_approve_create_only_one_draft；test_real_process_restart_restores_same_approval_context_and_one_draft |
| 暂停 task 的旧快照或清理回调覆盖新恢复任务 | WAITING_APPROVAL 已原子保存，不在 finally 再写；revision 拒绝旧版本；回调比对 task 身份 | runtime.py / service.py；上述并发与 API 继续测试 |
| 正在执行的写调用完成情况未知 | 构造持久化 RUNNING 写 invocation，重开 Storage 执行启动恢复，转 RECONCILIATION_REQUIRED，拒绝 resume，无第二次写入 | test_unknown_write_outcome_requires_reconciliation_without_replay |
| 已提交草案后进程未能继续模型 | 从真实提交的 AFTER_APPROVED_TOOL checkpoint 重开 Store，核对草案凭据再 resume，草案仍 1 | test_confirmed_local_write_checkpoint_can_resume_without_repeating_write |
| 终态恢复/替换配置 | 状态迁移拒绝；resume 409 或 CHECKPOINT_INVALID | test_terminal_run_is_never_resumed；test_resume_cannot_replace_frozen_configuration |
| 预算不足 | 参数模型拒绝，不创建审批或草案；Trace 显示 DEMO_BUDGET_EXCEEDED | test_budget_failure_is_persisted_with_zero_drafts；failure-trace.png |
| 本机 5173 被已有服务占用 | 验证器改用临时端口，Vite 支持限定 localhost API 端口；不结束用户服务 | scripts/verify_day3.py；web.log |
| Windows 重启同端口预探测遇 TIME_WAIT | 测试 helper 不再提前 bind 固定重启端口，实际服务负责绑定 | tests/test_recovery_process.py；真实浏览器重启验收通过 |

明确区分：**WAITING_APPROVAL 是真实 API 进程终止/重启测试**；未知写结果与“事务提交后模型前”是精确构造的数据库故障状态及存储重开测试，不冒充在任意机器指令处强杀成功。当前内置草案与决议同库事务，没有连接真实 ERP。数据库文件损坏、磁盘丢失、DB 管理员恶意改写和跨节点容灾不在保证内。

原始最终结果为 [pytest.txt](evidence/day3/pytest.txt)，完整测试名称为 [test-names.txt](evidence/day3/test-names.txt)。公开 Trace 不返回私有上下文；私有 SQLite 仍含精确 Demo 输入，不是加密保险箱或通用 DLP。Live 外部 API 未测，续传测试使用明确的合成 HTTP fixture。

恢复能力仅按 [DECISIONS D014](DECISIONS.md) 声明；模型/只读调用中断不可继续、未知写入不补发。没有 arbitrary tool exactly-once 声明。

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
