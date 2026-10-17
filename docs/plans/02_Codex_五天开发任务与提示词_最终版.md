# AgentForge — Codex 五天开发任务与可复制提示词（最终版 v2.0）

> 目标：2026-10-18 周日 23:00（UTC+8）前冻结 MVP；2026-10-19 周一可用于求职展示。
> 这是给 **Codex** 执行的任务书，不表示任何代码已经完成。使用方法：将 `01_AgentForge_产品需求与技术架构_最终版.md` 放到项目根目录 `docs/PRD.md`，按顺序给 Codex 发送下列指令。
> 用户不亲自编码，但必须亲自检查验收输出，并能回答架构和项目问题。

## A. 通用总提示词：项目启动时首先发给 Codex

```text
你是 AgentForge 项目的资深 AI Agent Runtime 架构师、工程实现者与全栈开发者。**产品面向不同技术栈的 Agent 应用开发者，不限定 Python 工程师；本周 MVP 选择 Python 实现服务端 Runtime，React + TypeScript 实现前端。**

第一步请阅读 docs/PRD.md（文件来源：01_AgentForge_产品需求与技术架构_最终版.md）。这是项目的范围、契约和验收依据，若有冲突以 PRD 的 P0 为准。项目目标是在 2026-10-18 前交付可运行、可观察、可评估的本地单用户 Agent Harness 求职作品，不是生产级多租户平台。先识别已有仓库内容，不要覆盖用户未授权的代码或历史。

工程原则：
1. 核心 Agent Loop、状态机、工具策略、Checkpoint、事件存储与评测引擎必须由项目源码实现，不得把 LangGraph/Agents SDK Runner 当成“自研 Harness”。允许官方 SDK 处理模型 HTTP 请求与 MCP 规范。
2. 优先选择简单、可重复、容易解释的实现：Python 3.12+、FastAPI、Pydantic v2、SQLite/SQLAlchemy、React/TypeScript/Vite、pytest、Docker Compose。**Python 是实现语言，不是产品用户画像**；通过标准 REST/JSON/OpenAPI 与 HTTP API 为其他语言开发者提供调用能力。
3. 模型必须有 DeterministicMockAdapter，CI/绝大多数测试不得依赖 API Key 或访问互联网；另有可配置的真实 OpenAI Responses API 适配器。真实供应商错误、限制、续传协议必须正确处理。
4. 对照 MCP 2026-07-28 标准与 Python SDK 2.x 官方文档，不要照搬使用 FastMCP v1 的旧教程；使用 v2 `MCPServer` 与 `Client` 的实际锁定 API，记录 SDK/协议版本。对外声称 MCP 兼容性之前必须通过真实客户端-服务端调用测试。
5. 每个新增 P0 模块必须提供单测或集成测试，重要失败模式先写出可复现测试。测试不能只断言 HTTP 200，必须检验状态/副作用/事件等。
6. 所有模拟业务操作只作用于隔离的本地 Demo 数据；不执行任意命令，不连接真实 ERP，不产生真实采购交易。
7. 只保留有权限的工具；写入模拟数据必须经由政策层人工审批并实现幂等。禁止声称 arbitrary tool exactly-once、任意中断点一致性或生产级安全。
8. 从第一天保持 README 可用，所有图表、指标、运行记录必须来自可执行系统或清楚标为示意；绝不虚构测试/成本/延迟数字。
9. 实现时优先直接完成任务并执行测试。若外部 Key 不可用，保留 Live 路径且使用 Mock 验证，报告“Live 未测”；不得假装成功。
10. 维持 docs/DECISIONS.md、docs/INTERVIEW_NOTES.md、docs/FAILURE_MODES.md、docs/RESULTS.md、docs/API_CONTRACT.md 与 docs/FEATURE_MATRIX.md：说明“为何如此设计、替代方案、关键源码入口、API 语言无关、失败案例和证据”。
11. 对外 REST API 不暴露 Python 类名/堆栈，OpenAPI 与实际接口保持一致；至少一条 `curl` 调用可完成创建 Run、查询状态。非 Python 客户端可调用平台 API ≠ 已开发跨语言 Runtime。
12. 不要混淆项目角色。Codex 负责编码；候选人参与需求、技术决策、审核、验收与面试讲解。输出的简历表述必须准确反映实际贡献与实测成果。

从现在开始，逐日完成明确的交付任务。每次交付请输出：
- 本次新增/修改文件清单；
- 核心架构决策、实现边界和残余风险；
- 实际运行的命令、测试用例数/通过数/失败数和原始摘要（未执行则说明）；
- 一个不依赖大模型真实 Key 的演示命令；
- 5 个面试官可能追问的技术问题与参考答案；
- 下次任务需要的剩余事项；
- 新增/变更的 OpenAPI 端点及语言无关客户端调用方法；
- P0 验收表（PASS/FAIL/PARTIAL/NOT_TESTED）与证据路径。

先阅读 PRD 并生成 1 页的实施清单/目录设计，不要自行增加多租户、OAuth、复杂业务或长期规划能力。随后执行当天对应任务。若某条依赖的官方接口或版本与当前源码不一致，先验证并记录差异，不允许为了快速通过测试自行伪造 SDK 响应。
```

## B. Day 1 — 10 月 14 日（周三）：自研 Runtime 最小闭环

**目标：任何后端工程师运行一次命令即可看到任务完成或明确终止。**

```text
执行 AgentForge Day 1：自研 Runtime 最小闭环。严格对照 docs/PRD.md。

必须完成：
1. 初始化仓库、基础依赖、标准格式检查、pytest 和 README。
2. 定义 AgentConfig、ModelAdapter、ToolDefinition、ToolCall、ToolResult、RunState、RunStep、RunEvent 等有类型的数据结构。
3. 编写不依赖 LangGraph/Agents SDK Runner 的 RuntimeEngine，支持多轮 model -> function_tool -> model 的处理，包含 finish、fail、cancel、max steps、max model calls、timeout 等退出原因；只允许受注册表许可的工具被分派。
4. 内置 DeterministicMockAdapter，至少支持：直接回复、单次工具、串行两工具、请求未知工具、重复请求导致上限终止、工具异常。
5. 本地工具先实现 list_supplier_quotes、get_supplier_detail、calculate_total_cost，包含 JSON Schema 校验和拒绝非法参数。数据来源 examples/procurement/fixtures.json。
6. 写 CLI 演示脚本 `python -m ...`（命令须在 README 中明确），打印 Run ID、状态、每一步事件和终止原因；CLI 是开发测试入口，平台用户不被要求使用 Python。
7. 对异常、上限、未知工具、参数校验等写 pytest 单测，不允许主循环无限运行。

不在今天做：React、生产数据库、多 Agent、真实采购操作。

验收：
- 不设置任何 LLM API Key，Mock 演示成功；
- 至少有一个多工具任务确实产生工具调用并回到模型，最终出结果；
- 非法 Schema 参数不会执行工具；
- 触发最大步数后有限时间终止，记录 stop_reason；
- `pytest -q` 全绿，给出测试数量和核心失败模式测试名称；
- `docs/INTERVIEW_NOTES.md` 写清 Agent Loop 入口、状态转换、为什么不直接用 LangGraph。

请实际运行命令与测试；不要只生成代码而不验证。
```

**用户当晚验收（20–40 分钟）**：让 Codex 画出一次真实 Run 的 5 步调用链；独立复述“是谁决定选工具、是谁拥有执行权限、何时循环结束”。

## C. Day 2 — 10 月 15 日（周四）：真实模型/MCP + 交互工作台

```text
执行 AgentForge Day 2：模型接入、MCP、API 和最小 Web Workbench。先运行 Day 1 测试确保不回归。

必须完成：
1. 实现 OpenAIResponsesAdapter；模型名/API Key 从环境变量读取，不硬编码。正确处理 Responses function_call、call_id、function_call_output、reasoning 续传项与模型终态；实测无 Key 时明确报告未测试外部 API。
2. 使用官方 MCP Python SDK 2.x，实现 demo MCPServer 和本机 MCP Client Adapter。兼容 2026-07-28 规范，支持发现至少两个只读工具并进行一次调用。不要沿用 v1 `FastMCP` 代码和过时初始化行为。固定依赖版本。
3. 工具注册表统一暴露本地工具和 MCP 工具元数据，统一 JSON Schema 校验、权限与超时入口。
4. 实现 FastAPI：health、agents、tools、创建 Run、查询 Run/steps/events，提供 `/openapi.json` 及一致的 JSON 契约；提供 `curl` 示例，确保非 Python 客户端可以操作。异步 Run 若使用后台任务需说明本机进程生命周期限制；不要声称支持分布式队列。
5. 实现 React/TS Workbench：创建/选择 Agent、输入任务、Mock/Live 选择、启动 Run、展示状态和步骤列表，清楚显示 Mock 标签；错误提示可读。
6. 写 MCP tool discovery、成功调用、断连/超时、恶意/异常参数的集成测试；API 测试至少含一次真实 Mock Run。
7. Docker Compose 本机一键启动基础前后端（或提供两个明确开发命令并在 Day 4 补 Docker）。

验收：
- 通过 UI 在 Mock 模式发起任务并看到至少两个真实工具执行步骤；
- MCP 客户端能调用本机 Server（非仅 import 成功）；
- API 未配置 Key 时不报空指针、不假装真实模型成功；
- MCP 错误转换为明确的结构化 tool error，不导致无限重试；
- README 列出实际命令、端口、环境变量和 Mock/Live 差异，以及 HTTP/OpenAPI 的通用接入方式；
- `curl` 创建 Run 并查询返回状态成功，不依赖 Python 客户端；
- pytest 全绿，记录锁定的 MCP SDK 版本。

只实现可工作的狭窄 P0，不扩展到多 Agent、任意远程 MCP 安装平台。
```

**用户当晚验收**：能在浏览器完成一次运行；解释 MCP Host/Client/Server、Tool Schema 和 `function_call` 的区别。

## D. Day 3 — 10 月 16 日（周五）：Checkpoint + HITL + Trace

```text
执行 AgentForge Day 3：持久化、审批中断/恢复和 Trace。对照 docs/PRD.md 不变量。

必须完成：
1. SQLite + SQLAlchemy 持久化 Run、RunStep、RunEvent、ToolInvocation、Approval、model_resume_state；增加必要数据库唯一约束和迁移/初始化方法。
2. 明确状态机并验证合法迁移；写入操作必须先进入 WAITING_APPROVAL、记录 pending 调用及参数摘要；模拟写工具 create_purchase_draft 必须由后端权限层控制，不能只看 prompt。
3. Approval API 和 UI：显示具体待审调用/副作用，批准时只执行绑定参数的那次调用，拒绝则不执行，并可追溯审计。
4. 实现创建采购草案的幂等键/唯一约束。重复 approve 和并发 approve 的请求不会产生第二份草案。
5. 实现明确可支持的 Checkpoint/Resume：对 WAITING_APPROVAL，重启后恢复并继续执行；对工具执行中未知完成状态，禁止盲目重复高风险写操作，转为需要核对的状态或失败并记录原因。
6. Trace Timeline：RunStep/Event 可在浏览器查看，显示开始、完成、Tool 参数和结果摘要、耗时、异常、Checkpoint、审批事件；事件脱敏。SSE 有余力则实现，轮询也可。
7. 实际执行重启恢复测试：先令 Run 等待审批，重启服务进程，查询到 pending，批准，核对只产生一份草案。

验收必须包含真实数据库断言，而不是只看页面：
- 未批准 create_purchase_draft 表记录数为 0；
- 拒绝后记录数为 0；
- 批准后记录数为 1；
- 连续/并发重复批准后记录数仍为 1；
- 重启后仍找到同一个 approval_id、run_id 与任务上下文；
- 终态不会被再次恢复到 RUNNING；
- Trace 能追溯每一步、失败原因；
- `pytest -q` 全绿，并保存自动化测试名称到 docs/RESULTS.md。

今天必须写清楚本项目“能恢复什么 / 不能恢复什么”，不得使用 exactly-once 描述任意外部副作用。
```

**用户当晚验收**：实际点击 Pause/Approve/Reject，查看 DB/Trace；解释 checkpoint vs memory vs tool idempotency。

## E. Day 4 — 10 月 17 日（周六）：Evals / Guardrails / 作品集

```text
执行 AgentForge Day 4：评测、安全回归、文档和前端完善。

必须完成：
1. 创建 30–50 条可追溯 EvalCase（JSONL），每条有 case_id、scenario、mode、input、expected state、expected tools/forbidden tools、预期副作用、标签和判定逻辑。
2. 为 Mock adapter 提供对应确定性脚本/用例实现，执行独立 eval runner；输出机器可读 JSON 和 Markdown 报告；严格区分 Mock 状态/协议正确性 与 Live 模型任务质量。
3. 配置敏感工具保护、允许列表、参数校验、工具返回上限、调用次数、超时预算、模型错误终态；注入攻击通过恶意 tool result 模拟，验证不能绕过工具政策。
4. 评测包含边界：malformed schema、unknown tool、retryable timeout、nonretryable error、循环上限、预算上限、重复 approve、拒绝、重启后审批恢复、Prompt Injection 和禁止工具请求。
5. 统计并展示实际 run 的 tool calls、错误率、wall-clock latency、模型 tokens（真实 usage 才记录），可选真实模型小样本测试；不能编造成本或假设 $0。
6. 完善四个页面：Workbench / Trace / Approval / Evals；核心流程优先于动画；加入至少一个 Playwright 关键路径。
7. README 包括 Quickstart、架构图、问题定义、Mock/Live 区别、项目局限、测试命令、截图、演示脚本、跨语言 HTTP 使用示例；docs/DECISIONS.md、FAILURE_MODES.md、INTERVIEW_NOTES.md、RESULTS.md、API_CONTRACT.md、FEATURE_MATRIX.md 内容完整。文档明确“跨语言使用 REST API”与“多语言 Runtime”的不同。
8. 配置 CI 执行格式检查、单测、Mock eval，任一失败则 fail；不应在 PR CI 中使用付费 Live API。

验收：
- `pytest -q` + 评测命令 + 前端构建命令都实际通过；
- Mock 回归中硬性不变量均通过；若有失败，必须在报告中显式标注并解决，不允许通过跳过/删用例伪装；
- 恶意工具响应无法绕过写权限；
- README 按全新克隆环境演练成功；
- `docs/RESULTS.md` 明确日期、模式、样本数、通过数、失败数、配置、局限；
- 如 Live 未跑，则写“未进行真实模型质量评测”。
```

**用户当天验收**：能解释为什么 Mock 全绿不等于 Agent 任务质量好；能拿出具体失败案例讲优化。

## F. Day 5 — 10 月 18 日（周日）：冻结、重测、求职材料

```text
执行 AgentForge Day 5：MVP 冻结、回归、面试交付。禁止新增大功能。

必须完成：
1. 严格执行完整验收清单：离线 Quickstart、Mock 完整任务、拒绝审批、批准审批、重启恢复、工具超时、超限终止、MCP 断连、Mock eval、前端构建、E2E 测试。
2. 审阅 PRD 所有 P0 需求，在 docs/FEATURE_MATRIX.md 将状态标为 PASS/FAIL/NOT_TESTED/PARTIAL，标注测试名称和源码路径。任何未实现项不得隐瞒。额外检查平台受众没有被限制为 Python 工程师，且 README 不能宣称已支持跨语言插件执行。
3. 处理影响 Demo 的 P0 缺陷，不做无关重构；依赖固定版本，验证全新 `git clone` 环境运行。
4. 完善技术文档，明确运行时 Loop、状态机、MCP adapter、Checkpoint/Idempotency、Trace/Event/Evals 的关键源码入口和典型代码片段。
5. 输出一段 5 分钟演示脚本：启动、从浏览器或 `curl` 发起正常多工具任务、查看 trace、触发高危写工具、拒绝/批准、重启恢复、查看 eval 报告。
6. 形成可用于简历的“证据清单”：实现功能、实际测试通过数、评测集规模、结果截图与脚本、真实完成的优化及 before/after；没有实测的数据一律用占位符。
7. 如果仓库干净且符合 P0，打 `v0.1.0` tag；如存在阻塞未解决，不要宣称 release 完成。
8. 在 docs/INTERVIEW_NOTES.md 输出 60 秒项目介绍、3 分钟技术架构讲解、15 分钟深挖路线与最值得解释的 6 个技术决策。

最终请提供可复制的：
- 启动/测试/评测命令；
- 实际测试摘要、Git commit 与 tag（如果有）；
- 功能验收表；
- Demo 脚本；
- 简历 bullet 草稿（不得虚构数据和生产经验）；
- 尚未解决的问题清单及优先级。
```

**用户当天验收**：独立讲出产品场景、架构、一次完整 Run、一次失败/恢复、一次真实指标对比；准备面试。

## G. Codex 完成后，给它的严苛代码审查 Prompt

```text
请以严苛的资深 Agent Runtime / 安全工程师身份审查当前仓库，不要只给正面结论。逐项检查：
1. 核心执行循环是否真自研，是否被框架 Runner 偷换；
2. ModelAdapter 是否正确保留 Responses function_call/call_id/续传关联；
3. 状态机是否存在非法跃迁与并发竞争；
4. Checkpoint 恢复是否可能重复执行有副作用的工具；
5. Approval 是否仅由 Prompt 控制、是否存在 TOCTOU、重复审批与参数篡改；
6. MCP 工具是否越权、无输入校验、未限制超时、未限制输出大小；
7. API key/隐私/工具响应是否泄漏进日志与 Trace；
8. Eval 是否用 Mock 结果冒充真实模型质量；
9. 失败场景是否有真正的自动化断言；
10. README 能否从全新环境复现；
11. docs/PRD.md 中哪些 P0 实际没实现；
12. 产品是不是被错误描述为“Python 工程师专用”？OpenAPI/curl 是否真正可用？是否把“REST API 跨语言可调”虚称为“多语言 Runtime/插件执行已实现”？

请按 P0/P1/P2 输出风险表：证据文件与行号、复现步骤、影响、修复方案、测试方案。优先修复 P0，执行测试并如实报告。不要为了让报告变绿而修改评测预期、删除失败用例或跳过测试。
```

## H. 如果进度落后时的紧急收缩 Prompt

```text
当前项目目标是本周日交付可用于面试的最小真实 Demo。停止新功能，把开发范围缩小到：
- 自研 Agent Loop + DeterministicMockAdapter；
- JSON Schema Tool Registry、限制器；
- 本地 SQLite Checkpoint；
- 一个需人工批准的模拟写工具及其幂等；
- 真实事件 Trace（页面或 API 展示）；
- 至少一个 MCP SDK v2 实际接入的只读工具；
- 30 条有实际断言的 Mock 回归用例（若已达到 30–50 条不得减少）；
- 标准 OpenAPI 与至少一条 curl 创建/查询 Run 示例；
- 可复现 Quickstart、README 和 INTERVIEW_NOTES.

删除复杂 UI、RAG、Live streaming、多 Agent、额外页面等非硬性能力，不要删除失败测试或伪造数据。返回最小修复清单并直接执行。
```

## I. 每天交付记录模板（用户亲自确认）

```
日期：
Git Commit：
真实执行命令：
通过 / 失败 / 未执行测试：
已完成 P0：
新增风险与已知限制：
今天我独立讲得清楚的三个技术点：
我不能解释、需要补课的点：
下一次 Codex 任务：
平台语言无关的 HTTP 调用验收：
是否有新增“产品仅面向 Python 工程师”之类错误描述：
```

> **纪律：** Codex 写代码不等于用户掌握技术。每天至少进行 30–45 分钟不看文档的架构讲解与追问。


## J. Codex 使用顺序与文档一致性（请严格执行）

1. 将 `01_AgentForge_产品需求与技术架构_最终版.md` 复制到仓库 `docs/PRD.md`；其他两份放入 `docs/plans/`。
2. 给 Codex 发送 A 节总提示词，再发送当日任务（B/C/D/E/F）。若当前日期已错过某阶段，按依赖先补齐 P0，不跳过测试，不并行改同一关键文件。
3. 每日完成后使用 G 节审查，若落后则用 H 节收缩范围；不得以删测试的方式创造“全绿”。
4. 收到代码提交后，候选人亲自执行 README 的核心命令或查看录屏、Trace 和原始测试报告，并用第三份文档做口头验收。
5. 首次运行真实模型必须经候选人选择是否配置 API Key 以及允许的费用；无 Key 不阻断 Mock 项目的核心交付。
6. 对外展示前，从 `docs/FEATURE_MATRIX.md` 自动核对 README、演示脚本、简历 bullet，不允许未完成能力提前进入简历。
