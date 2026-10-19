# AgentForge 面试问答

## Day 3 五个追问（2026-10-18，当前状态）

1. **为什么不能只让 prompt 写“必须审批”？** 模型输出是不可信请求。`RuntimeEngine.run` 先通过 Registry 校验，再对 REQUIRES_APPROVAL 调用执行 `Storage.pause`；普通 dispatch 永远不能执行写工具。approve 接口只收 ID 和决议，服务端再次检查冻结的权限、参数及预算。候选人应能沿 runtime → storage → service 读出这条路径。
2. **两个人同时点批准会不会写两份？** 本机演示使用 `BEGIN IMMEDIATE` 串行化短写事务，事务内重新读决议；同决议重放返回 replayed。草案另有 approval_id、idempotency_key、(run_id,call_id) 唯一约束。数据库中决议、草案、结果、checkpoint 一起提交；真正并发 HTTP/数据库测试证明本例一份，没有声称外部 ERP exactly-once。
3. **Checkpoint 究竟保存什么，重启能从哪里继续？** 保存配置快照、精确上下文、pending calls、Mock 原脚本/Live 模型描述及 safe_point。WAITING_APPROVAL 可保持原 ID 再批准；AFTER_APPROVED_TOOL 仅凭数据库草案与结果上下文校验后 resume。模型/读工具进行中不支持继续，未知写结果转 RECONCILIATION_REQUIRED；终态不能变 RUNNING。
4. **为什么用 SQLite，不加队列或分布式锁？** 目标是本机单用户作品；WAL、短事务、唯一约束、revision 足够解释和验证。task 仍属于单个 asyncio 进程，不是可靠队列。同步 DB 会阻塞事件循环，5 秒 busy timeout 也有延迟代价；多进程 worker/生产吞吐不在范围内。schema v1 自动初始化，下一次真正改 schema 再写迁移。
5. **怎样证明系统确实恢复过，Trace 又如何避免泄密？** `test_real_process_restart_restores_same_approval_context_and_one_draft` 实际停/启 Uvicorn，比较原 run_id/approval_id/任务上下文，并发批准后 SQL COUNT=1。浏览器脚本另有恢复截图与 database-assertions.json。公开 API 过滤私有模型状态，事件/摘要脱敏；精确上下文留在私有 DB，不声称全库无原文或通用 DLP。143 项是程序回归，外部 Live 未测。

关键源码：[Loop](../src/agentforge/runtime.py)、[政策事务/恢复](../src/agentforge/storage.py)、[任务服务](../src/agentforge/service.py)、[API](../src/agentforge/api.py)、[脱敏](../src/agentforge/redaction.py)。
证据：[RESULTS](RESULTS.md)、[SQL 断言](evidence/day3/database-assertions.json)、[Trace 截图](evidence/day3/approved-trace.png)。
贡献表述：Codex 实现代码；候选人参与需求、取舍、审核、验收与讲解，不能将自动生成代码说成全部独立手写。

## 以下为历史问答，按当时交付范围保留

## Day 2 五个追问（2026-10-17，当前状态）

1. **为什么 Responses 不能把所有对象拍平成 role/content？** function_call、reasoning、function_call_output 是不同协议项，call_id 关联调用结果。适配器按顺序重放它们，只保留加密 reasoning 状态，不保存隐藏原文；store=false 与账户 ZDR 语义分开说明。
2. **如何证明 MCP 实际兼容，而非只 import 成功？** 固定官方 SDK 2.3.0，stdio 子进程完成 server/discover、tools/list、tools/call，检查实际 protocol_version=2026-07-28 和返回数据。真实断连/超时/异常参数也有测试，证据在 evidence/day2。
3. **工具 annotations 说只读，能直接信任吗？** 不能据此授权。固定 server 和工具名称，发现后纳入同一 Registry，代码检查 allowlist、JSON Schema、权限、超时与结果。模型和工具内容均不能修改权限。
4. **后台 Run 在服务退出时会怎样？** 当前仅为 asyncio 进程任务，强引用防止丢失；正常关闭取消，重启后历史和续传上下文清空。没有租约、消息队列、SQLite 或安全断点恢复，不宣称分布式可靠性。
5. **如何证明其他语言可用，哪些成绩还不能讲？** 实际 curl 创建/查询 Run，React 调同一 API 并显示真实两工具步骤；这是 HTTP 接入互操作，不是多语言 Runtime。107 项测试是控制/协议回归，Live 无 Key 未测，不能当成真实模型任务质量。

关键入口：openai_adapter.py、mcp_server.py、mcp_adapter.py、api.py、apps/web/src/main.tsx；证据见 RESULTS 和 FEATURE_MATRIX。

## Day 1 历史问答

> 2026-10-16 已按详细 Day 1 清单补充。最新执行证据见 `evidence/day1-completion/`；原首日记录见 `RESULTS.md`。

## 1. 你的“自研 Harness”具体在哪里？

`runtime.py:RuntimeEngine.run` 实现循环、顺序调度、次数与时间/token 限制、错误终止和状态事件；`tools.py` 实现工具策略与参数校验。
没有借用 LangGraph 或 Agents SDK Runner。目前只完成内存 Mock 路径，不能把审批、持久化和评测说成已交付。

## 2. 为什么工具既在展示时过滤，又在执行时校验？

Schema 展示不能授权。模型可以请求未展示的名称，工具文本也可以诱导它；执行入口必须再次检查注册、allowlist、权限和参数。
`test_policy_blocks_side_effects` 用实际 handler 副作用列表证明未授权工具没有执行。

## 3. 多工具调用怎么保证顺序，出错是否回滚？

先校验整批，再按模型返回顺序 await。任何执行错误立即停止；不会回滚已完成只读操作。
重复 call ID 拒绝，防止同一协议调用重放，但这不是任意工具 exactly-once；未来写入还必须有审批、数据库唯一幂等键和未知结果核对。

## 4. Mock 全绿说明什么？如何计算 token 和成本？

只说明被测控制流与边界行为符合断言，不说明真实模型质量或任务成功率。
Mock 无 usage，用包含请求/工具定义/响应的 UTF-8 字节数做代理预算；明确标为估计。
无真实价格数据时成本为 unknown。Live 适配器尚未实现，Live 未测。

## 5. 产品怎样服务 Java/Go 开发者？候选人贡献怎么表述？

产品计划通过 REST/JSON/OpenAPI 接入，各语言使用普通 HTTP 客户端；今天尚无可运行 HTTP API。
这不意味着存在多语言 Runtime 或官方 SDK。Codex 实现代码；候选人应依据实际记录说明自己参与的需求、决策、审阅、验收与讲解，不能将未做的编码或未跑的 Live 成绩写进简历。

## 本次补齐后的五个重点追问

### 1. Agent Loop 的入口和数据流是什么？

CLI `demo.py:main` 创建 AgentConfig、Registry 和 Mock，调用 `runtime.py:RuntimeEngine.run`。
Runtime 在检查限制后请求 `ModelAdapter.respond`；工具请求整批预检，通过 `ToolRegistry.dispatch` 调用 handler，将真实执行结果包装为 ToolResult 加入上下文，再请求模型。
`test_serial_tools_return_results_before_next_model_call` 检查第二个工具使用第一个工具的实际输出，并由最后一次模型响应返回计算结果。

### 2. 状态如何转换，取消后能看到什么？

当前允许 `CREATED → RUNNING → COMPLETED | FAILED | CANCELLED`，终态不可重用。
完成原因为 FINAL_ANSWER；失败有 UNKNOWN_TOOL、INVALID_TOOL_ARGUMENTS、TOOL_ERROR、MAX_STEPS、MAX_MODEL_CALLS、MODEL_TIMEOUT 等明确原因。
取消协程时记录 CANCELLED、结束活动 RunStep，并传播 CancelledError；调用方可预先传入 RunState 检查终态。
这只是内存生命周期管理，没有 WAITING_APPROVAL、持久化或恢复。测试入口：`test_cancellation_preserves_observable_state_and_steps`、`test_runtime_cannot_reuse_completed_state`。

### 3. 为什么不直接用 LangGraph？

本项目的求职展示目标和 PRD 明确要求源码实现 Loop、状态、工具策略与后续恢复控制，方便逐步解释和验证关键不变量，因此选择一个小型顺序执行器。
替代方案是使用成熟框架承担调度和状态管理，可减少需要自行维护的机制，但不满足本项目展示自研核心的验收目标。
代价是本项目要自己维护错误和取消语义、协议续传、存储一致性等逻辑，当前功能也不完整。不能据此声称自研方案在生产中优于框架。

### 4. 为什么要分别设置步数和模型调用次数？

它们分别表达决策轮次和模型请求尝试的预算，调用失败也消耗尝试次数。
当前没有重试，每轮一次调用，计数通常相等；两项上限仍可独立设置和触发。
`repeat` 场景每轮使用新 call ID，测试验证 MAX_STEPS、MAX_MODEL_CALLS 和 MAX_TOOL_CALLS 分别终止；相同 call ID 则直接拒绝。

### 5. 如何证明 fixture 与工具结果真的参与执行？

`test_tools_load_actual_fixture_values` 替换测试 fixture 的价格和交期，再实际分派三个工具，检查返回值和总价变化；无效 fixture、负数和重复供应商也会被拒绝。
默认 CLI 最终文本是组装脚本时根据 fixture 生成的预设摘要，不是模型对工具输出的智能分析。
测试中的 InspectAdapter 则检查多轮上下文和实际工具结果，证明执行闭环成立。两者均不代表真实模型质量，Live 未实现、未测。
