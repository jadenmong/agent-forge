# P0 事实矩阵 — 2026-10-17 Day 2

PASS = 本条限定范围有可运行断言；PARTIAL = 只实现部分；NOT_TESTED = 尚无实现/未执行，不能视为通过；FAIL = 已验证不满足。
当前全量测试为 107 项，原 Day 1 套件为 70 项。当前证据为 `evidence/day2/`；下面 Day 1 表格保留原验收范围与证据，不用后续成果倒填历史。

## Day 2 交付清单

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
| §1.2.2 | 自研 Loop、零/一/多调用、连续调用、顺序、终止 | runtime.py / models.py；test_zero_tool_final_answer、test_serial_tools_return_results_before_next_model_call、test_demo_multi_tool_and_continuation、test_limits_terminate | PASS | `python -m agentforge.demo`；day1-completion/demo.json；Mock 内存运行 |
| §1.2.3 | Tool Registry、Schema、权限、超时、错误、≥3 本地工具 | tools.py / demo.py；test_schema_matches_strict_validation、test_invalid_args_never_execute、test_policy_blocks_side_effects、test_tool_failures | PASS | CLI 调用三个只读工具；需审批工具当前全部阻断，非审批执行能力 |
| §1.2.4 | MCP Adapter 与官方 SDK 实际调用 | mcp_server.py / mcp_adapter.py / test_mcp_adapter.py | PASS | SDK 2.3.0 / 2026-07-28 / stdio 工具发现调用实测；day2/health.json、pytest.txt |
| §1.2.5 | Checkpoint/Recovery | 无 | NOT_TESTED | Run/事件仅内存，无安全点恢复 |
| §1.2.6 | Human Approval + 幂等草案 | 无；test_policy_blocks_side_effects 仅验证阻断 | NOT_TESTED | 没有审批 ID、决议或写入路径 |
| §1.2.7 | Trace Studio | runtime.RunState.emit / models.RunStep / api.py / Workbench | PARTIAL | API 可查询事件，UI 有真实步骤；day2/workbench.png；无完整历史 UI/参数结果详情/持久化 |
| §1.2.8 | Evals | 只有 pytest 回归 | NOT_TESTED | 无 JSONL、指标/两批比较或 Live 质量结果 |
| §1.2.9 | 安全护栏 | tools.py / runtime.py；test_policy_blocks_side_effects、test_events_exclude_sensitive_input_arguments_results_and_final、test_untrusted_injection_cannot_change_policy、test_limits_terminate | PARTIAL | 默认空 allowlist、只读与限流通过；未完成审批/恢复与 Live 护栏，不声称通用安全 |
| §1.2.10 | API、OpenAPI、curl、部署文档 | api.py / README / API_CONTRACT | PARTIAL | HTTP/OpenAPI/curl/两个开发命令实测；day2/openapi.json、curl-run.json；Compose 仍待 Day 4 |

## 首日里程碑与最终硬门槛

| 验收项 | 结果 | 证据 |
|---|---|---|
| §10 首日 Runner/Registry/状态机/单测 | PASS | runtime.py、tools.py、70 个测试；day1-completion/pytest.txt |
| pytest 全绿 | PASS | day2/pytest.txt：107 passed；day1-regression.txt：原 70 项 |
| 未批准写入 0（当前无批准路径） | PASS | test_policy_blocks_side_effects；副作用断言为空，仅限当前阻断策略 |
| 拒绝后写入 0 | NOT_TESTED | 拒绝协议未实现 |
| 重复批准最多写入 1 | NOT_TESTED | 审批与数据库幂等未实现 |
| 完整采购 Mock Demo：审批→恢复→结果 | PARTIAL | day1-completion/demo.json 仅只读比较；无审批恢复 |
| 中断/进程重启恢复 | NOT_TESTED | 无持久化 |
| 无明文 Key | PARTIAL | 首日不配置/使用 Key；尚未建立专门 secret scan gate |
| README Mock 命令有效 | PASS | scripts/verify_day1.py；day1-completion/smoke.txt / environment.txt |
| Trace 显示真实事件 | PARTIAL | API events 与真实 UI 步骤；day2/workbench.png；尚无完整 Trace Studio |
| UI E2E happy path | PASS | verify_day2.py；day2/summary.json、workbench.png、workbench-mcp.png |
| OpenAPI 可获取、curl 创建/查询 | PASS | day2/openapi.json、curl-create.json、curl-run.json、curl-steps.json |
| 30–50 条有来源评测/故障集 | PARTIAL | 70 个 pytest 实例来源为手工构造，缺审批/MCP/重启类和独立 JSONL 评测，不替代最终评测集 |
| Live 真实模型 | NOT_TESTED | 适配器已实现，外部 API 无 Key 未运行；离线 fixture 不替代 Live |

Day 1 清单与 Day 2 的 Mock/MCP/API/UI 核心路径已通过；Live 外部 API 未测，最终平台 P0 **未全部通过**。持久化、审批恢复、幂等写入、Evals 和 Docker 仍待后续交付。
