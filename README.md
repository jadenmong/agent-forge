# AgentForge

面向不同语言 Agent 应用开发者的本机单用户 Agent Harness 求职作品。
本周选择 Python 实现服务端，计划通过 REST/JSON/OpenAPI 提供语言无关接入，前端采用 React/TypeScript。
**当前交付：2026-10-14 首日 Mock Runtime；HTTP API、UI、MCP、Live、持久化和审批尚未实现。**

## 本地运行（Python 3.12+，无需模型 Key）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m agentforge.demo
.\.venv\Scripts\python.exe -m pytest -q -ra
```

重跑测试与两个 CLI 检查并保存原始证据：`.\.venv\Scripts\python.exe scripts/verify_day1.py`。

Linux/macOS 使用 `.venv/bin/python` 替换上述虚拟环境解释器路径。
首次安装依赖需要访问包仓库或已有 wheel 缓存；安装完成后演示与测试不访问网络。

Demo 通过三个只读工具完成合成供应商报价、交期保修和总价查询：4 轮模型响应、7 次顺序工具调用，输出明确标记 `mock`。
这是固定脚本验证控制流，不是模型智能、实时供应商信息或采购建议。不会生成草案或订单。

限制终止演示（预期退出码 1、`FAILED / MAX_STEPS`）：

```powershell
.\.venv\Scripts\python.exe -m agentforge.demo --max-steps 1
```

## 已实现与边界

- 自研 `model → calls → results → model` 顺序循环，零/单/多调用，拒绝重复 call ID。
- Pydantic v2 生成工具 JSON Schema，并在执行入口严格校验；allowlist 默认空。
- 只读默认；禁用和需审批工具均阻断。尚无“已批准”通道。
- 模型轮数、工具次数、wall time、调用超时、token 配额、输入/输出大小限制。
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
