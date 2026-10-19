# P0 事实矩阵 — 2026-10-19 Day 4

PASS = 本条限定范围有可运行断言；PARTIAL = 只实现部分；NOT_TESTED = 尚无实现/未执行，不能视为通过；FAIL = 已验证不满足。
Day 4 当前全量测试为 **155 项**，独立 JSONL 集为 **42 条**；分别统计，不将 pytest 项数当成 eval 样本数。当前证据为 `evidence/day4/`；下面各天交付表保留对应历史范围，不倒填历史。

## Day 4 交付清单

| 要求 | 结果 | 证据与范围 |
|---|---|---|
| 先跑 Day 3 基线 | PASS | day4/baseline-pytest.txt：143 passed |
| 30–50 条可追溯 JSONL EvalCase | PASS | examples/evals/mock.jsonl：42 条；来源、固定期望、工具/禁止工具/草案数、标签及判定版本齐全 |
| 自研独立 runner、JSON/Markdown、失败门槛 | PASS | evals.py；day4/mock-a/report.json、report.md；故意错误期望与 CLI 非零退出测试 |
| 恶意工具结果不能绕过写权限 | PASS | 两个 injection case 先真实读出恶意结果再提出写请求；无授权为 TOOL_FORBIDDEN，有授权仍 WAITING_APPROVAL，草案均为 0 |
| Schema/未知工具/禁用/超时/错误/输出大小/模型终态/上限 | PASS | 42 条用例报告与原安全回归；非法 Schema 注册另有 test_malformed_tool_schema_is_rejected_before_handler_execution |
| 批准/拒绝/重复与并发/跨进程恢复/未知写结果 | PASS | JSONL 对应 approval-*；两个 Runtime worker 恢复原上下文；原 Uvicorn 重启测试保留 |
| 实际指标、Mock 与 Live 分开 | PASS | metrics.py / test_metrics.py；wall-clock、工具调用/错误率；Mock tokens/cost 为 unknown；合成 usage 另标 synthetic_mock_usage |
| 两批比较 | PASS | day4/comparison.json：42 unchanged、0 regressions；数据集/模式/fixture/judge 不一致拒绝 |
| 四页 UI 与 Playwright | PASS | day4/browser-summary.json；workbench.png、trace.png、approval.png、evals.png、comparison.png |
| 新克隆候选环境 Quickstart | PASS | day4/clean-checkout/summary.json 和安装/pytest/build/eval/browser 原始日志；本机新 clone + 未提交候选覆盖、新 venv/npm ci，非公共 GitHub HEAD 或全新 OS |
| CI 格式/pytest/Mock eval/构建/浏览器任一失败即 fail | PASS | .github/workflows/ci.yml 已配置，同类门槛本机实际执行；没有 Live secrets/continue-on-error |
| 云端 GitHub Actions 运行 | NOT_TESTED | 本次未推送/触发工作流，不宣称远端 CI 已绿 |
| Docker Compose | PARTIAL | Compose/镜像/nginx 已配置；docker-status.txt：环境无 Docker，容器运行 NOT_TESTED |
| 外部 Live 质量评测 | NOT_TESTED | 未进行真实模型质量评测；Mock 成绩不代表模型任务质量 |

## Day 3 历史交付与数据库不变量

| 要求 | 结果 | 测试/实际证据 |
|---|---|---|
| 先跑原 Day 2 测试 | PASS | day3/baseline-pytest.txt：107 passed |
| SQLite/SQLAlchemy 持久化 Run/Step/Event/Invocation/Approval/model_resume_state | PASS | storage.py；test_draft_has_real_database_uniqueness_constraints；day3/environment.txt；SQLite schema v1 自动初始化 |
| 状态机、绑定参数审批、后端权限 | PASS | test_allowed_state_transitions / test_forbidden_state_transitions；test_api_rejects_bound_parameter_override_and_cross_run_approval |
| 未批准草案 0 | PASS | test_unapproved_write_is_persisted_pending_with_zero_drafts；database-assertions.json：before_approval.purchase_drafts=0 |
| 拒绝后草案 0 | PASS | test_rejection_never_creates_draft / test_api_rejection_is_audited_and_never_writes；database-assertions.json：rejected_run=0 |
| 批准后草案 1，重复/并发仍 1 | PASS | 两类真实 DB 并发测试；真实 HTTP 首次并发批准；database-assertions.json：after_approve=1、after_12_concurrent_replays=1 |
| 真实 API 进程重启，ID/任务上下文不变 | PASS | test_real_process_restart_restores_same_approval_context_and_one_draft；verify_day3.py 第二次浏览器验收；database-assertions.json 相同私有状态摘要 |
| 已批准安全点可恢复；未知写结果不重发 | PASS | test_confirmed_local_write_checkpoint_can_resume_without_repeating_write；test_unknown_write_outcome_requires_reconciliation_without_replay；这些为构造 DB 故障状态，不是任意点强杀 |
| 终态不恢复 RUNNING | PASS | test_terminal_run_is_never_resumed；真实 HTTP resume=409 |
| UI 审批/拒绝、Trace 参数结果/异常/审批/Checkpoint | PASS | day3/waiting-approval.png、approved-trace.png、failure-trace.png；summary.json |
| Trace 脱敏、私有上下文不经 API 返回 | PASS | test_trace_tables_store_redacted_summaries_not_private_tool_data；test_trace_redacts_secrets_and_pii_without_mangling_digest；仅已知字段规则 |
| OpenAPI 与 curl 创建/查询/批准重放 | PASS | day3/openapi.json、curl-create.json、curl-query.json、curl-approval-replay.json |
| 全量回归、格式、前端构建 | PASS | day3/pytest.txt：143 passed；ruff-check.txt、ruff-format.txt、web-build.txt |

以上 PASS 限于表中定义的本机 Mock/合成数据路径；不是对任意恢复位置、外部 Live 或生产安全的通过声明。

## Day 2 历史交付清单

| 要求 | 源码/测试 | 结果 | 证据及边界 |
|---|---|---|---|
| 先跑 Day 1 回归 | test_runtime.py / test_day1_contract.py | PASS | day2/day1-regression.txt：70 passed；升级依赖后也保持通过 |
| Responses 适配器、函数/续传/错误处理 | openai_adapter.py；test_responses_tool_continuation_keeps_call_ids_and_encrypted_reasoning、provider/terminal tests | PARTIAL | 离线真实 SDK HTTP 解析通过；外部 Live 无 Key 未测 |
| 官方 MCP 2.x / 2026-07-28 / 至少两个只读工具 | mcp_server.py / mcp_adapter.py；test_stdio_discovery_and_real_tool_call | PASS | mcp==2.3.0，真实 stdio；day2/health.json、pytest.txt；只验证工具子集 |
| 统一工具元数据/Schema/权限/超时 | tools.py；test_mcp_registry_rejects_malicious_arguments_before_dispatch、原权限/参数测试 | PASS | 五个工具；API metadata 与实际 Registry 共用定义 |
| FastAPI / OpenAPI / Run steps events | api.py；test_api_mock_run_executes_two_tools_and_exposes_steps_and_events、test_openapi_metadata_and_schema | PASS | day2/openapi.json、curl-create.json、curl-run.json、curl-steps.json |
| React/TS Workbench 创建选择 Agent、运行、Mock/Live、步骤、错误 | apps/web/src/main.tsx；verify_day2.py 真实浏览器 | PASS | day2/workbench.png、workbench-mcp.png、summary.json；两个真实本地工具和两个真实 MCP 工具 |
| MCP 成功/超时/断连/异常参数、API 真 Mock Run | test_mcp_adapter.py / test_api.py | PASS | day2/pytest.txt：107 passed，全量包含原测试；无互联网/模型 Key |
| 两条明确本机开发命令或 Docker | README API 8000 / Web 5173 | PASS | 本次验证脚本实际启动两个服务；采用任务允许的开发命令方案，Docker 仍未做 |
| curl 语言无关创建/查询 | verify_day2.py 调用真实 curl | PASS | day2/curl-create.json、curl-run.json、curl-steps.json |

## 用户 Day 1 详细清单

| 要求 | 源码/验证 | 结果 | 证据与边界 |
|---|---|---|---|
| 仓库、依赖、标准格式检查、pytest、README | pyproject.toml / README / scripts/verify_day1.py | PASS | ruff-check.txt、ruff-format.txt、pytest.txt、environment.txt；现有 main 保留，不重写历史 |
| AgentConfig / ModelAdapter / ToolDefinition / ToolCall / ToolResult / RunState / RunStep / RunEvent 类型 | models.py / tools.py / runtime.py；test_builtin_mock_scenarios、test_tools_load_actual_fixture_values、test_cancellation_preserves_observable_state_and_steps | PASS | 类型实际参与配置、分派、上下文与步骤；事件 TypedDict 为内部类型声明，无外部事件写入入口 |
| 自研多轮循环、完成/失败/取消/步数/模型调用次数/超时 | runtime.py；test_endless_mock_is_terminated_at_each_limit、test_model_failures、test_cancellation_preserves_observable_state_and_steps | PASS | repeat-steps.json、repeat-model.json；无框架 Runner，仅内存 |
| Mock 直接回复/单工具/串行两工具/未知工具/重复请求上限/工具异常 | models.py / demo.py；test_builtin_mock_scenarios、test_endless_mock_is_terminated_at_each_limit | PASS | direct.json、single-tool.json、two-tools.json、unknown-tool.json、repeat-steps.json、tool-error.json |
| 三个工具、fixture 数据源和严格参数校验 | examples/procurement/fixtures.json / demo.py / tools.py；test_tools_load_actual_fixture_values、test_invalid_fixture_is_rejected、test_invalid_args_never_execute | PASS | 数据源变化和无效数据均有断言；只支持源码 checkout + editable 安装 |
| python -m CLI，输出 Run ID/状态/步骤事件/终止原因 | demo.py / README / verify_day1.py | PASS | demo.json、smoke.txt；CLI 是开发测试入口，没有要求平台用户使用 Python |
| 异常/上限/未知工具/参数测试；多工具结果回到模型 | tests；test_serial_tools_return_results_before_next_model_call、test_tool_failures、test_unknown_tool、test_limits_terminate | PASS | pytest.txt；Mock 控制正确性，不是 Live 质量或 JSONL Evals |
| 面试说明 Loop 入口、状态转换、为何不用 LangGraph | INTERVIEW_NOTES.md 的“本次补齐后的五个重点追问” | PASS | 解释设计选择与维护成本，不宣称生产优越性 |

## PRD §1.2 P0

| PRD | 能力 | 源码/测试 | 结果 | 演示/限制及证据 |
|---|---|---|---|---|
| §1.2.1 | Agent Studio | models.AgentConfig/Limits、api.py、apps/web/src/main.tsx | PARTIAL | 配置 API/UI 与 Mock 已实测，Live 适配器实现但外部 API 未测；day2/workbench.png |
| §1.2.2 | 自研 Loop、零/一/多调用、连续调用、顺序、终止 | runtime.py / models.py；test_zero_tool_final_answer、test_serial_tools_return_results_before_next_model_call、test_demo_multi_tool_and_continuation、test_limits_terminate | PASS | CLI 保留内存运行；HTTP 已持久化并跨审批继续；day3/pytest.txt |
| §1.2.3 | Tool Registry、Schema、权限、超时、错误、≥3 本地工具 | tools.py / demo.py / storage.py；test_schema_matches_strict_validation、test_invalid_args_never_execute、test_policy_blocks_side_effects、test_tool_failures | PASS | 三个本地只读、两个 MCP 只读、一个需审批工具；普通 dispatch 不放行敏感工具 |
| §1.2.4 | MCP Adapter 与官方 SDK 实际调用 | mcp_server.py / mcp_adapter.py / test_mcp_adapter.py | PASS | SDK 2.3.0 / 2026-07-28 / stdio 工具发现调用实测；day2/health.json、pytest.txt |
| §1.2.5 | Checkpoint/Recovery | storage.py / service.py；test_real_process_restart_restores_same_approval_context_and_one_draft | PASS | day3/database-assertions.json；仅 WAITING_APPROVAL 与验证过的 AFTER_APPROVED_TOOL，恢复矩阵见 DECISIONS |
| §1.2.6 | Human Approval + 幂等草案 | Storage.decide / Approval API/UI / tests | PASS | day3/waiting-approval.png、database-assertions.json；仅本地同库事务副作用 |
| §1.2.7 | Trace Studio | 持久化 steps/events / redaction.py / Workbench | PASS | day3/approved-trace.png、failure-trace.png；历史、参数/结果摘要、异常/审批/checkpoint；成本 unknown、token 明确估计来源 |
| §1.2.8 | Evals | evals.py / eval_service.py / Evals.tsx / tests | PASS | 42 条独立 JSONL Mock 回归、JSON/Markdown、指标与两批比较；day4/mock-a、mock-b、comparison.json；可选 Live 未运行 |
| §1.2.9 | 安全护栏 | tools.py / runtime.py / storage.py / redaction.py；权限、预算、审批及脱敏测试 | PARTIAL | 本机 Mock 安全路径已测；Live 外部护栏未在线测，脱敏非通用 DLP，无生产安全声明 |
| §1.2.10 | API、OpenAPI、curl、部署文档 | api.py / README / API_CONTRACT / Compose | PARTIAL | API 0.4.0、curl/开发命令及新环境已测；day4/openapi.json、curl-query.json、clean-checkout；Compose 配置有、容器未测 |

## 首日里程碑与最终硬门槛

| 验收项 | 结果 | 证据 |
|---|---|---|
| §10 首日 Runner/Registry/状态机/单测 | PASS | runtime.py、tools.py、70 个测试；day1-completion/pytest.txt |
| pytest 全绿 | PASS | day4/pytest.txt：155 项；day4/test-names.txt |
| 未批准写入 0 | PASS | 原生 SQLite COUNT=0；day3/database-assertions.json |
| 拒绝后写入 0 | PASS | SQLite COUNT=0；拒绝审计/界面已测 |
| 重复批准最多写入 1 | PASS | 首次并发批准与后续重复批准均有 SQL 断言 |
| 完整采购 Mock Demo：审批→恢复→结果 | PASS | day3/approved-trace.png；5 模型/8 工具，真实合成工具执行 |
| 中断/进程重启恢复 | PASS | 明确等待点的真实 API 重启；其他边界按恢复矩阵拒绝 |
| 无明文 Key | PARTIAL | 首日不配置/使用 Key；尚未建立专门 secret scan gate |
| README Mock 命令有效 | PASS | scripts/verify_day1.py；day1-completion/smoke.txt / environment.txt |
| Trace 显示真实事件 | PASS | day3/persisted-events.json、approved-trace.png、failure-trace.png |
| UI E2E happy path | PASS | verify_day4.py；day4/browser-summary.json、五张真实截图 |
| OpenAPI 可获取、curl 创建/查询 | PASS | day4/openapi.json、curl-create.json、curl-query.json |
| 30–50 条有来源评测/故障集 | PASS | examples/evals/mock.jsonl：42 条固定期望；day4/mock-a/report.json，逐项真实断言 |
| Live 真实模型 | NOT_TESTED | 适配器已实现，外部 API 无 Key 未运行；离线 fixture 不替代 Live |

Day 4 的离线评测、安全回归与四页核心流程已实现并验证；最终平台 P0 仍不宣称全部通过。Compose 容器和云端 CI 未运行，外部 Live 未测；SSE 为 P1。详细实际数量与最终摘要以 RESULTS 和 day4 原始证据为准。
