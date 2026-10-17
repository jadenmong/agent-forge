# 首日面试问答（2026-10-14）

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
