# 架构：Day 3（2026-10-18）

```mermaid
flowchart TD
  Web[React Workbench / 审批 / Trace] -->|公开 HTTP JSON 轮询| API[FastAPI]
  Other[curl / Java TS Go HTTP 客户端] --> API
  API --> Service[RunService / 单进程任务生命周期]
  Service --> Engine[自研 RuntimeEngine / 显式状态迁移]
  Engine --> Models[Mock / Responses 官方 HTTP SDK]
  Engine --> Registry[ToolRegistry / allowlist / Schema / 超时]
  Registry --> Read[本地只读工具 / MCP Client]
  Engine -->|写调用只暂停| Store[Storage / Checkpoint / 事件]
  Service -->|具体 ID 决议| Policy[Storage.decide / 后端权限检查]
  Policy -->|同一事务| Draft[内置模拟草案 INSERT]
  Draft --> DB[(SQLite WAL / schema v1)]
  Store --> DB
  DB -->|持久化 Trace / 审计查询| API
```

上图是源码结构示意。真实运行截图与 SQL 证据在 [day3](evidence/day3/summary.json)；外部 Live 未测。

主要路径：

1. `api.create_app` 启动 → `Storage.initialize/recover` → MCP 真实发现 → 读取/补齐 Agent presets。
2. `POST runs` → `RunService.start` 先存 Run → 保持强引用的后台 task → `RuntimeEngine.run`。
3. 模型结果整批校验 → 只读调用 `Registry.dispatch`；需审批调用 `Storage.pause`，原子存 pending/approval/WAITING_APPROVAL，结束当前 task。
4. `POST approve` → `RunService.decide` → `Storage.decide` 校验绑定/权限，批准则在同事务写草案、结果与安全 checkpoint；拒绝无写入；只有首次批准调度继续模型。
5. 重启 → waiting 验证原审批及上下文；已批准安全点需 `claim_resume` 验证真实草案凭据；未知写结果转待核对。终态无恢复入口。
6. `GET runs/steps/events/approvals` 从 DB 查询；RunView 过滤私有字段，摘要与事件脱敏；UI 轮询显示历史、参数/结果和异常。

模块入口：storage.py（ORM/事务/唯一约束/恢复）、service.py（任务归属/适配器重建）、runtime.py（循环与状态）、redaction.py（公开摘要）、tools.py（统一策略）。
schema 中 runs 同时存 frozen config、private model_resume_state 和 revision；steps/events/invocations/approvals 各有数据库实体；草案只有受政策层控制的原生事务写入，没有通用敏感 handler 执行器。

**边界**：单 worker、本机 SQLite、可信异步工具；恢复矩阵见 DECISIONS D014。没有分布式队列、任意外部事务或任意中断点恢复，私有 DB 不是加密存储。成本 unknown，时间来自实际执行，不提供虚构基准。

## 以下保留 Day 2 架构记录（2026-10-17）

```mermaid
flowchart TD
  Web[React Workbench] -->|公开 HTTP JSON| API[FastAPI / 内存 Run 服务]
  Curl[curl / 其他语言 HTTP 客户端] --> API
  API -->|当前进程后台任务| Engine[自研 RuntimeEngine]
  Engine --> Registry[统一 ToolRegistry / Schema / allowlist / 超时]
  Registry --> Local[三个本地只读工具]
  Registry --> Client[官方 MCP Client]
  Client -->|真实 stdio / 2026-07-28| MCP[MCPServer 两个只读工具]
  Local --> Fixture[合成 fixtures.json]
  MCP --> Fixture
  Engine --> Mock[确定性 Mock]
  Engine --> Responses[OpenAIResponsesAdapter / 官方 HTTP SDK]
  Engine --> State[内存 RunState / RunStep / RunEvent]
  State --> API
```

这是源码结构示意，不是伪造 Trace。MCP stdio 与 HTTP/UI 路径已经真实调用；Responses 外部 API 未测，仅有离线 SDK HTTP 协议测试。
入口：api.py:create_app → create_run → asyncio task → RuntimeEngine.run；模型返回的函数请求仍必须经过 Registry 校验，SDK 不承担 Loop。
模式从 AgentConfig/Run 请求决定；Live 续传协议项仅存在运行上下文，不出现在公开 RunView、步骤或事件里。
启动时发现 MCP 工具，之后每次 MCP 调用打开独立 stdio 生命周期；Web 通过 API 轮询步骤。退出/重启丢失状态，无数据库、审批恢复或分布式队列。
当前接口见 API_CONTRACT，实际证据见 evidence/day2，设计取舍见 DECISIONS D008–D011。

## 以下保留 Day 1 架构记录

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
