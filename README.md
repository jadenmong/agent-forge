# AgentForge

面向不同语言 Agent 应用开发者的本机单用户 Agent Harness 求职作品。
本周选择 Python 实现服务端，计划通过 REST/JSON/OpenAPI 提供语言无关接入，前端采用 React/TypeScript。
**当前交付：2026-10-16 补齐 Day 1 Mock Runtime 详细清单；HTTP API、UI、MCP、Live、持久化和审批尚未实现。**

## 本地运行（Python 3.12+，无需模型 Key）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m ruff format --check src tests scripts
.\.venv\Scripts\python.exe -m agentforge.demo
.\.venv\Scripts\python.exe -m pytest -q
```

重跑格式检查、pytest 和 9 个 CLI 检查并保存原始证据：

```powershell
.\.venv\Scripts\python.exe scripts/verify_day1.py
```

当前结果：70 项 pytest 通过、0 失败；9 个 CLI 检查符合预期。证据保存到 `docs/evidence/day1-completion/`，原首日证据保留。

Linux/macOS 使用 `.venv/bin/python` 替换上述虚拟环境解释器路径。
首次安装依赖需要访问包仓库或已有 wheel 缓存；安装完成后演示与测试不访问网络。

Demo 通过三个只读工具完成合成供应商报价、交期保修和总价查询：4 轮模型响应、7 次顺序工具调用，输出明确标记 `mock`。
数据来自 `examples/procurement/fixtures.json`，按严格模型校验，并检查 A/B/C 不重复。计算工具使用请求中的整数单价与数量。
需要保留源码 checkout 并按上面命令 editable 安装；尚未实现 fixture 的独立 wheel 打包。
这是固定脚本验证控制流，不是模型智能、实时供应商信息或采购建议。默认最终文本在脚本组装时根据 fixture 生成，不对工具输出进行智能判断。不会生成草案或订单。

限制终止演示（预期退出码 1、`FAILED / MAX_STEPS`）：

```powershell
.\.venv\Scripts\python.exe -m agentforge.demo --max-steps 1
```

## Mock 场景

使用 `python -m agentforge.demo --scenario <名称>`；上面的虚拟环境解释器路径同样适用。

| 场景 | 行为 / 预期终止 |
|---|---|
| `procurement`（默认） | 三个工具、4 轮模型响应，`COMPLETED / FINAL_ANSWER` |
| `direct` | 直接回复，零工具调用 |
| `single-tool` | 一次工具调用后回到模型 |
| `two-tools` | 两轮各调用一个工具，再回到模型完成 |
| `unknown-tool` | 请求未注册工具，`FAILED / UNKNOWN_TOOL` |
| `repeat` | 用新 call ID 持续请求同一只读工具，直到上限终止 |
| `tool-error` | 显式注入本地模拟工具异常，`FAILED / TOOL_ERROR` |

独立模型调用次数上限演示（预期退出码 1）：

```powershell
.\.venv\Scripts\python.exe -m agentforge.demo --scenario repeat --max-model-calls 2
```

同一 call ID 重复时立即拒绝，原因是 `DUPLICATE_CALL_ID`；新 ID 的重复行为由次数、时间和预算上限限制。
失败演示退出码 1 是预期行为，不等于测试失败。

## 已实现与边界

- 自研 `model → calls → results → model` 顺序循环，零/单/多调用，拒绝重复 call ID。
- 使用 `AgentConfig`、`ModelAdapter`、`ToolDefinition`、`ToolCall`、`ToolResult`、`RunState`、`RunStep`、`RunEvent`；工具结果实际经由 `ToolResult` 回到模型。
- Pydantic v2 生成工具 JSON Schema，并在执行入口严格校验；allowlist 默认空。
- 只读默认；禁用和需审批工具均阻断。尚无“已批准”通道。
- `max_steps`、`max_model_calls`、工具次数、wall time、调用超时、token 配额、输入/输出大小限制。模型调用尝试计数包含失败请求；当前无重试，每轮只请求一次模型，两项计数通常相同。
- CLI 输出 Run ID、状态、终止原因、逐操作步骤及事件。调用方取消协程时记录 CANCELLED 和步骤状态，再传播取消异常；可通过传入的 `RunState` 查看结果。
- 内存事件带时间、顺序游标、模式、关联 ID 与实测耗时；不保存输入/参数/结果/最终文本原文到事件。
- 未知 usage 使用 UTF-8 字节数估算限流，不是真实 token 统计；价格未配置，成本为 `null`（unknown）。

仅运行可信、协作式异步本地工具；超时依赖事件循环取消，不是进程隔离，不保证阻塞或忽略取消的代码能被强制终止。
没有任意代码、shell、URL 或文件访问工具。没有重启恢复或 exactly-once 承诺。
CLI 最终结果是公开的合成 Demo 数据；运行上下文仅在内存存在，不适合输入真实敏感信息。

## 文档与证据

- [PRD](docs/PRD.md)：范围及验收依据（保留原文）。
- [一页实施清单](docs/IMPLEMENTATION_PLAN.md) · [架构](docs/ARCHITECTURE.md)
- [决策](docs/DECISIONS.md) · [接口契约](docs/API_CONTRACT.md)
- [实际测试结果](docs/RESULTS.md) · [P0 事实矩阵](docs/FEATURE_MATRIX.md)
- [故障案例](docs/FAILURE_MODES.md) · [面试问答](docs/INTERVIEW_NOTES.md)

Codex 负责本次代码实现；候选人参与需求、技术决策、审核、验收与面试讲解，具体参与记录由本人确认。
项目仓库：[jadenmong/agent-forge](https://github.com/jadenmong/agent-forge)。尚无 Docker Compose 启动路径。
