# P0 事实矩阵 — 2026-10-16 Day 1 补齐

PASS = 本条限定范围有可运行断言；PARTIAL = 只实现部分；NOT_TESTED = 尚无实现/未执行，不能视为通过；FAIL = 已验证不满足。
测试位于 `tests/test_runtime.py` 和 `tests/test_day1_contract.py`；本次执行证据为 `evidence/day1-completion/`。原首日证据保留，不用补齐后的结果倒填历史。

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
| §1.2.1 | Agent Studio | models.AgentConfig/Limits | PARTIAL | 配置类型已接入 Runtime；无配置 API/UI 或 Live |
| §1.2.2 | 自研 Loop、零/一/多调用、连续调用、顺序、终止 | runtime.py / models.py；test_zero_tool_final_answer、test_serial_tools_return_results_before_next_model_call、test_demo_multi_tool_and_continuation、test_limits_terminate | PASS | `python -m agentforge.demo`；day1-completion/demo.json；Mock 内存运行 |
| §1.2.3 | Tool Registry、Schema、权限、超时、错误、≥3 本地工具 | tools.py / demo.py；test_schema_matches_strict_validation、test_invalid_args_never_execute、test_policy_blocks_side_effects、test_tool_failures | PASS | CLI 调用三个只读工具；需审批工具当前全部阻断，非审批执行能力 |
| §1.2.4 | MCP Adapter 与官方 SDK 实际调用 | 无 | NOT_TESTED | 未安装/锁定/验证 MCP，不声明兼容 |
| §1.2.5 | Checkpoint/Recovery | 无 | NOT_TESTED | Run/事件仅内存，无安全点恢复 |
| §1.2.6 | Human Approval + 幂等草案 | 无；test_policy_blocks_side_effects 仅验证阻断 | NOT_TESTED | 没有审批 ID、决议或写入路径 |
| §1.2.7 | Trace Studio | runtime.RunState.emit / models.RunStep | PARTIAL | CLI 真实步骤/事件/实测耗时；day1-completion/demo.json；无 UI/参数结果详情/持久化 |
| §1.2.8 | Evals | 只有 pytest 回归 | NOT_TESTED | 无 JSONL、指标/两批比较或 Live 质量结果 |
| §1.2.9 | 安全护栏 | tools.py / runtime.py；test_policy_blocks_side_effects、test_events_exclude_sensitive_input_arguments_results_and_final、test_untrusted_injection_cannot_change_policy、test_limits_terminate | PARTIAL | 默认空 allowlist、只读与限流通过；未完成审批/恢复与 Live 护栏，不声称通用安全 |
| §1.2.10 | API、OpenAPI、curl、部署文档 | README.md / API_CONTRACT.md | PARTIAL | README 本机 Mock 命令实测；无 HTTP/curl/Compose |

## 首日里程碑与最终硬门槛

| 验收项 | 结果 | 证据 |
|---|---|---|
| §10 首日 Runner/Registry/状态机/单测 | PASS | runtime.py、tools.py、70 个测试；day1-completion/pytest.txt |
| pytest 全绿 | PASS | day1-completion/pytest.txt：70 passed |
| 未批准写入 0（当前无批准路径） | PASS | test_policy_blocks_side_effects；副作用断言为空，仅限当前阻断策略 |
| 拒绝后写入 0 | NOT_TESTED | 拒绝协议未实现 |
| 重复批准最多写入 1 | NOT_TESTED | 审批与数据库幂等未实现 |
| 完整采购 Mock Demo：审批→恢复→结果 | PARTIAL | day1-completion/demo.json 仅只读比较；无审批恢复 |
| 中断/进程重启恢复 | NOT_TESTED | 无持久化 |
| 无明文 Key | PARTIAL | 首日不配置/使用 Key；尚未建立专门 secret scan gate |
| README Mock 命令有效 | PASS | scripts/verify_day1.py；day1-completion/smoke.txt / environment.txt |
| Trace 显示真实事件 | PARTIAL | day1-completion/demo.json 真实事件；无 Trace UI |
| UI E2E happy path | NOT_TESTED | 无前端 |
| OpenAPI 可获取、curl 创建/查询 | NOT_TESTED | 无 HTTP 服务 |
| 30–50 条有来源评测/故障集 | PARTIAL | 70 个 pytest 实例来源为手工构造，缺审批/MCP/重启类和独立 JSONL 评测，不替代最终评测集 |
| Live 真实模型 | NOT_TESTED | 未实现、未运行 |

用户明确列出的 Day 1 清单已通过；最终平台 P0 **未全部通过**。不可根据 Runtime 测试通过宣传完整平台已交付。
