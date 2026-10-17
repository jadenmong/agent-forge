# 架构：2026-10-14 已实现范围

> 2026-10-16 补齐 Day 1 类型、fixture、模型调用上限与步骤记录，仍为内存 Mock Runtime。

```mermaid
flowchart TD
  CLI[合成数据 CLI Demo] --> Engine[RuntimeEngine 自研顺序循环]
  Engine --> Mock[DeterministicMockAdapter 固定脚本]
  Engine --> Registry[ToolRegistry]
  Registry --> Policy[allowlist / 权限 / 严格参数校验]
  Policy --> Tools[三个异步只读工具]
  Engine --> Events[Run 内存事件与状态]
```

入口：`src/agentforge/demo.py:main` → `RuntimeEngine.run` → `adapter.respond` → 整批预检 → `registry.dispatch` → 工具结果以 `untrusted` 数据返回模型。
每个调用顺序执行；任何失败立即终止，无自动重试。整批预检只防止已知无效请求产生部分执行；运行期间后续调用失败时，不会回滚前面已完成的只读调用。

`models.py` 的中立协议只用于首日 Mock；不是 Responses API 协议，也不承诺可直接重放供应商对象。
后续 Responses 适配器须单独维护合法的 reasoning items/function_call/call_id/续传语义。

计划的 API、React、MCP、SQLite、审批和评测边界见 `IMPLEMENTATION_PLAN.md`，不属于上图已实现部分。

## Day 1 补齐后的类型与数据流

`models.py`：AgentConfig/Limits、ModelAdapter、ToolCall、ToolResult、RunStep、RunEvent。
`tools.py`：ToolDefinition、ToolRegistry；`runtime.py`：RunState 和状态迁移。
`demo.py` 从固定 `examples/procurement/fixtures.json` 加载严格校验的模拟数据。
每次实际模型/工具操作产生 RunStep；事件引用步骤顺序号；ToolResult 仅在上下文中传递，事件不收集原始参数和结果。
步骤和事件仍仅在内存；有类型的数据结构不等于已实现存储或恢复。具体取舍见 `DECISIONS.md` D007。
