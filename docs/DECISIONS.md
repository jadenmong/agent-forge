# 设计决策

## D001 — 2026-10-14：按当日里程碑实现

依据 PRD §10，先交付 Mock Runner、Registry、状态机及单测；不提前搭建未运行的完整平台。
单个 `src/agentforge` 包保留模块边界，替代多个可安装 packages，减少首日打包成本。未来边界确有独立发布需求再拆。
初始仓库只有 PRD，无 Git 元数据；保留文件，不初始化或重写历史。

## D002 — 自研顺序循环、显式失败

`runtime.py:RuntimeEngine.run` 是控制核心，不引入框架 Runner。每个模型响应算一步；工具调用另计数。
多调用按返回顺序执行，先整批验证权限、参数、call ID、次数预算。代替并行执行，牺牲吞吐以简化解释和副作用边界。
重复 call ID 在同一 Run 内失败；不同 ID 的相同只读请求允许执行。不是工具语义去重或 exactly-once。
工具失败立即结束 Run，不把错误自动交给模型反复尝试。

## D003 — 当前状态机与后续恢复

当前合法迁移：`CREATED → RUNNING → COMPLETED | FAILED | CANCELLED`，终态不可再次开始。
`WAITING_APPROVAL`、`INTERRUPTED`、`RECONCILIATION_REQUIRED` 尚未实现，不能用空实现冒充支持。
后续依 PRD §5 增加：审批等待点可恢复；过期 RUNNING 检测后中断；写入结果未知进入待核对、不自动重发。
今天需审批工具返回 `APPROVAL_REQUIRED` 并失败，绝不执行 handler；审批 ID、拒绝及幂等写入将在 10/16 一起实现和测试。

## D004 — 信任边界

`tools.py:ToolRegistry.validate/dispatch` 共用实际策略；只向模型展示 allowlist 中只读工具的 Schema，执行时仍检查。
参数采用 strict/extra=forbid，金额用整数分避免浮点误差。输入 Schema 由实际参数模型生成，避免手写两份契约。
仅允许可信的 async handler；`asyncio.timeout` 是协作式取消，不能约束阻塞或忽略取消的代码。进程隔离不在本周范围。
工具结果强制 JSON、禁止 NaN、最大 32000 UTF-8 字节；模型结果上限 64000 字节；无任意 shell/出站 URL/文件工具。

## D005 — 限制与观测

先检查下一次模型请求的估计体积，响应后检查累计 usage/估值，超限不执行后续工具。
缺 usage 时把序列化请求（含 tools）和响应的 UTF-8 字节数作为保守代理，不等价于 tokenizer，也不保证供应商真实 token 硬上限。
已报告 usage 使用响应值；混合来源标为 mixed。真实调用的输出配额与供应商限制须由下一日适配器单独落实。
wall time 包含模型和工具；模型/工具超时、次数/token 上限记录不同终止码。不自动重试。
首日事件仅记录元数据与测得耗时，防止日志收集原始秘密；结果仅在运行上下文和 Demo 输出中。成本 unknown 用 null，绝不捏造 $0。

## D006 — 外部协议验证尚待执行

当前没有 MCP/OpenAI 源码或依赖，不声称兼容，也没有伪造 SDK 响应。
10/15 先读取官方来源、确认实际可获得的 SDK/协议/API、锁定确切版本，再编写真实 client/server 测试。
若官方实际版本与 PRD 的 MCP 2026-07-28 / SDK 2.x 不符，记录官方证据与阻塞，不静默退回 FastMCP v1。
当前仅锁定直接依赖 Pydantic 2.11.7、pytest 8.4.1；尚非含全部传递依赖的锁文件。
