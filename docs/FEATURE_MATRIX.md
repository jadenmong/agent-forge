# P0 事实矩阵 — 2026-10-14

PASS = 本条限定范围有可运行断言；PARTIAL = 只实现部分；NOT_TESTED = 尚无实现/未执行，不能视为通过；FAIL = 已验证不满足。
所有相对测试名均在 `tests/test_runtime.py`，最终执行证据为 `evidence/day1-pytest.txt`。

## PRD §1.2 P0

| PRD | 能力 | 源码/测试 | 结果 | 演示/限制及证据 |
|---|---|---|---|---|
| §1.2.1 | Agent Studio | 仅 runtime.Limits | NOT_TESTED | 无 Agent 配置 API/UI |
| §1.2.2 | 自研 Loop、零/一/多调用、连续调用、顺序、终止 | runtime.py / models.py；test_zero_tool_final_answer、test_one_tool_result_is_returned_to_model、test_demo_multi_tool_and_continuation、test_limits_terminate | PASS | `python -m agentforge.demo`；day1-demo.json；Mock 内存运行 |
| §1.2.3 | Tool Registry、Schema、权限、超时、错误、≥3 本地工具 | tools.py / demo.py；test_schema_matches_strict_validation、test_invalid_args_never_execute、test_policy_blocks_side_effects、test_tool_failures | PASS | CLI 调用三个只读工具；需审批工具当前全部阻断，非审批执行能力 |
| §1.2.4 | MCP Adapter 与官方 SDK 实际调用 | 无 | NOT_TESTED | 未安装/锁定/验证 MCP，不声明兼容 |
| §1.2.5 | Checkpoint/Recovery | 无 | NOT_TESTED | Run/事件仅内存，无安全点恢复 |
| §1.2.6 | Human Approval + 幂等草案 | 无；test_policy_blocks_side_effects 仅验证阻断 | NOT_TESTED | 没有审批 ID、决议或写入路径 |
| §1.2.7 | Trace Studio | runtime.Run.emit | PARTIAL | CLI 真实元数据事件/实测耗时；day1-demo.json；无 UI/参数结果详情/持久化 |
| §1.2.8 | Evals | 只有 pytest 回归 | NOT_TESTED | 无 JSONL、指标/两批比较或 Live 质量结果 |
| §1.2.9 | 安全护栏 | tools.py / runtime.py；test_policy_blocks_side_effects、test_events_exclude_sensitive_input_arguments_results_and_final、test_untrusted_injection_cannot_change_policy、test_limits_terminate | PARTIAL | 默认空 allowlist、只读与限流通过；未完成审批/恢复与 Live 护栏，不声称通用安全 |
| §1.2.10 | API、OpenAPI、curl、部署文档 | README.md / API_CONTRACT.md | PARTIAL | README 本机 Mock 命令实测；无 HTTP/curl/Compose |

## 首日里程碑与最终硬门槛

| 验收项 | 结果 | 证据 |
|---|---|---|
| §10 首日 Runner/Registry/状态机/单测 | PASS | runtime.py、tools.py、47 个测试；day1-pytest.txt |
| pytest 全绿 | PASS | day1-pytest.txt：47 passed |
| 未批准写入 0（当前无批准路径） | PASS | test_policy_blocks_side_effects；副作用断言为空，仅限当前阻断策略 |
| 拒绝后写入 0 | NOT_TESTED | 拒绝协议未实现 |
| 重复批准最多写入 1 | NOT_TESTED | 审批与数据库幂等未实现 |
| 完整采购 Mock Demo：审批→恢复→结果 | PARTIAL | day1-demo.json 仅只读比较；无审批恢复 |
| 中断/进程重启恢复 | NOT_TESTED | 无持久化 |
| 无明文 Key | PARTIAL | 首日不配置/使用 Key；尚未建立专门 secret scan gate |
| README Mock 命令有效 | PASS | scripts/verify_day1.py；day1-smoke.txt / day1-environment.txt |
| Trace 显示真实事件 | PARTIAL | day1-demo.json 真实事件；无 Trace UI |
| UI E2E happy path | NOT_TESTED | 无前端 |
| OpenAPI 可获取、curl 创建/查询 | NOT_TESTED | 无 HTTP 服务 |
| 30–50 条有来源评测/故障集 | PARTIAL | 47 个 pytest 实例来源为手工构造，缺审批/MCP/重启类和独立 JSONL 评测，不替代最终评测集 |
| Live 真实模型 | NOT_TESTED | 未实现、未运行 |

最终 P0 **未全部通过**；本次仅完成 10/14 日里程碑。不可根据首日测试通过宣传完整平台已交付。
