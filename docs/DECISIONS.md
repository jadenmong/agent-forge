# 设计决策

> 当前最新为文末 D012–D015（Day 3，2026-10-18）。前面各节保留对应日期的历史范围，不能把其中“尚未实现”当作最新状态；当前验收见 FEATURE_MATRIX。

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

## D007 — 2026-10-16：补齐 Day 1 详细清单

原首日里程碑概括不能代替详细任务验收。新增 `AgentConfig`、`ToolResult`、`RunStep`、`RunEvent`；将原 `Tool` 和 `Run` 分别改名为 `ToolDefinition`、`RunState`，实际接入执行链路。
配置和协议边界使用严格 Pydantic 模型；可变运行状态/步骤使用 dataclass；内部事件用 TypedDict 保持现有 JSON 结构。TypedDict 提供类型声明，不进行运行时校验；事件仅由可信源码构造，不接收外部事件写入。
没有为旧的内部 Python 名称添加别名或并存配置接口；检查并修改了仓库内全部调用方。CLI 命令保持可运行，尚无公开 REST 契约变更。

`RuntimeEngine.run` 统一接收 `config=AgentConfig(...)`，避免工具权限/提示词/limits 分散传参。当前仅允许 mock 配置，不接受虚假 Live 模式。
`max_steps` 限制决策轮次；`max_model_calls` 单独配置并限制模型调用尝试数，包含异常/超时尝试。当前每轮恰有一次调用且没有重试，所以计数相同；同时触及时优先记录 MAX_STEPS，不虚构不同计数。
`RunStep.seq` 是全部 model/tool 操作的顺序号，与决策轮次 `step_count` 不同；事件 step_id 引用操作顺序号，创建 Run 时为 0。
成功、失败、超时和取消都会结束当前步骤，记录耗时与安全原因码。取消仍传播 CancelledError；可传入 RunState 观察终态，无后台任务管理或恢复能力。

采购事实迁至 `examples/procurement/fixtures.json`，固定源码路径加载并校验；不允许模型指定文件。保持源码 checkout + editable 安装，不提前增加 wheel 资源复制机制。
命名 Mock 场景定义在 demo_adapter；适配器支持 repeat_last，用新 call ID 重复行为，验证上限而非重复 ID 拒绝。tool-error 只在显式演示参数下给本地工具注入异常，不伪造官方 SDK 返回。

新增开发依赖 Ruff 0.11.13，统一承担格式化和基础静态检查，避免同时配置多个格式工具；不是生产依赖，也不要求追随最新版。
配置与 check 模式参考 [Ruff 官方配置](https://docs.astral.sh/ruff/configuration/)及[格式化文档](https://docs.astral.sh/ruff/formatter/)，实际使用锁定版本运行验证。
新证据写入 `evidence/day1-completion/`，历史交付和旧证据保留。完整平台 P0 仍需后续模块验收。

## D008 — 2026-10-17：锁定依赖并验证实际 API

官方 MCP v2 文档与实际可安装版本一致，采用 mcp==2.3.0、其固定依赖 mcp-types==2.3.0；支持的本次协议为 2026-07-28，transport 为 stdio。
已读取下载 wheel 和安装后签名，确认 `mcp.server.MCPServer`、`mcp.Client`、`StdioServerParameters`、`list_tools`、`call_tool`、snake_case 字段和 `run(transport="stdio")` 实际存在，随后进行真实调用。
差异：SDK 2.3.0 要求 pydantic>=2.12，Day 1 的 2.11.7 不满足。改为固定 2.14.1，重新 editable 安装刷新项目元数据；pip check 无冲突，原 70 项测试回归通过。
其他直接依赖：openai 3.33.0、FastAPI 0.143.3、Uvicorn 0.54.0、HTTPX 0.28.1、jsonschema 4.26.0。MCP 内部使用 httpx2，不与 OpenAI/HTTPX 测试的 httpx 混用。
Python 直接依赖固定于 pyproject，完整本次环境见 evidence/day2/environment.txt，尚非跨平台传递依赖锁文件；前端固定版本并提交 package-lock.json，使用 npm ci。
官方依据：[v2 变化](https://py.sdk.modelcontextprotocol.io/whats-new/)、[Client](https://py.sdk.modelcontextprotocol.io/client/)、[协议模式](https://py.sdk.modelcontextprotocol.io/protocol-versions/)、[迁移源码](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md)。

## D009 — Responses 只承担 HTTP 和协议翻译

`openai_adapter.py` 实现 OpenAIResponsesAdapter；Runtime 仍独立控制循环和分派。真实模型名与 Key 从环境读取，无默认真实模型；缺配置在创建 Run 时返回 503，不退回 Mock。
采用 store=false 和完整有序协议重放：function_call、call_id 对应的 function_call_output，以及 reasoning 的 opaque encrypted_content。ModelReply.continuation 在内部上下文中传递，既不进入 RunView/事件，也不是持久化 checkpoint。
不保留隐藏 reasoning 原文或摘要；需要续传但缺少加密状态时显式失败。当前仅支持文本/函数工具，其他提供商输出类型明确拒绝。
未完成状态、拒绝、非法 JSON、未完成 function_call 均不执行工具。关闭 SDK 自动重试，HTTP/网络错误变为安全原因码；固定官方 API endpoint，不从客户端接收 URL。
替代方案 previous_response_id + provider store 会引入提供商存储与连续性依赖，本次不采用。store=false 本身不等于账户级 ZDR，不能作数据保留承诺。
官方依据：[Function calling](https://developers.openai.com/api/docs/guides/function-calling)、[Reasoning stateless continuation](https://developers.openai.com/api/docs/guides/reasoning)。离线 HTTP fixture 通过真实 SDK 解析，但不算外部 API 实测；本次无 Key，Live 未测。

## D010 — MCP 固定目标、同一执行策略

MCPServer 提供两个只读合成数据工具；Client 默认 auto，通过 server/discover 获得实际版本，应用拒绝非 2026-07-28。没有手写旧初始化，也没有使用 FastMCP v1。
默认 stdio 命令完全由源码固定，不提供远程 URL/安装平台。每次发现和调用各自建立并关闭子进程，避免把 SDK 的异步生命周期跨请求/任务共享；代价是每次调用有进程启动开销，适合本机 Demo。
发现结果只保留两个明确名称，加 mcp_ 前缀后加入已有 Registry，统一 allowlist、JSON Schema、权限、超时与输出大小检查。服务端 annotations 不用于授予权限。
本地继续使用严格 Pydantic；MCP 动态输入 Schema 使用 jsonschema，且拒绝额外参数。服务端返回显式 Pydantic 输出模型，产生真实 structured_content，客户端还检查结果对象和大小。
真实集成曾发现普通 dict 返回仅有文本、structured_content=null；改为结构化输出，未伪造 SDK 响应。另处理 SDK 异常组，保留已知安全错误码；断连、超时和工具错误不自动重试。
兼容结论限于已验证的 2026-07-28 stdio 工具发现/调用子集，不声称通过完整协议一致性认证或任意 MCP Server 安全。

## D011 — API、Workbench 与可观察边界

FastAPI 暴露统一 data/request_id 与 error 契约，生成实际 OpenAPI。React/TS/Vite 只调用这些公开接口，轮询 Run 与 steps；不通过前端私有状态获得执行权限。
Run 使用 asyncio.create_task 并保留强引用，正常关闭时取消；进程退出后全部 Agent/Run/Step/Event 丢失，不承诺恢复。单 worker，本机并发上限四个活动 Run，无队列或多租户。
POST 创建不提供请求级幂等，重复请求产生独立只读资源；容量满 409，具体契约见 API_CONTRACT。写工具仍未开放，审批/持久化/幂等属于 Day 3。
Live Key 永不传给浏览器；模式与 Mock 标签明确。成本缺价格为 unknown，不伪造 usage、延迟或质量指标。UI 显示步骤元数据，暂不实现完整历史 Trace/参数详情。
采用两个开发命令交付；Docker 按 Day 2 允许的替代方案留待 Day 4。Playwright 使用实际浏览器完成创建 Agent、本地两工具、MCP 两工具与缺 Key 错误路径，并保存真实截图。

## D012 — 2026-10-18：SQLite 是本机事实来源，任务仍属于一个进程

新增 storage.py，用 SQLAlchemy 2.0.55 ORM 定义七张表：agents、runs、run_steps、run_events、tool_invocations、approvals、purchase_drafts；模型续传状态是 runs.model_resume_state JSON 列，不另建表。Run 保存冻结的 Agent 配置，避免恢复时读取被替换的提示词/权限；Mock 同时保存原脚本，不从变化后的 fixture 重新生成。

SQLite WAL 允许读者与短写事务共存；外键开启，busy_timeout=5000。所有写事务 BEGIN IMMEDIATE，Run revision 拒绝陈旧快照覆盖。step/event 使用 (run_id,seq)/(run_id,event_id) 主键，event 追加不改旧记录；调用使用 (run_id,call_id)，审批另有唯一绑定。同步 DB 调用会短暂占用 API 事件循环，适合本机低并发 Demo，不是吞吐设计。

启动 initialize：空库 user_version=0 → 建表/v1；已是 v1 则幂等初始化；其他版本拒绝，保留数据。不引入 Alembic，因为之前没有持久化 schema；下一次真正改变 schema 时才实现明确升级步骤。不会自动修复手工篡改或任意损坏的 SQLite 文件。

替代方案：只存一份 Run JSON 更短，但不便数据库唯一约束、审批/草案关联查询；生产数据库/队列会扩大范围，本次不采用。RunService 只管理本进程 asyncio task，启动必须单 worker；另开服务共享同一数据库不属于支持范围。

官方依据：[SQLAlchemy SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html)、[ORM](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)。实际锁定环境和 SQL 断言见 evidence/day3/environment.txt、database-assertions.json。

## D013 — 审批属于后端政策事务，绑定调用而非放开工具

Runtime 整批预检后，REQUIRES_APPROVAL 调用先写 pending invocation、具体参数、审批及 WAITING_APPROVAL checkpoint。普通 Registry.dispatch 始终拒绝该权限；不存在通用的 approved=true 参数绕开入口。

批准接口只接受 approval_id/decision，服务端从数据库取绑定的 run_id/call_id/tool_name/validated_args，核对 SHA-256、冻结 allowlist、当前严格参数模型、调用次数和预算，再执行唯一内置写操作。SHA-256 不是密钥签名，不能防住拥有数据库改写权限的攻击者；本项目无 OAuth/用户认证。

选择把 create_purchase_draft 的 INSERT 放在审批决议同一事务中，连同结果上下文和 AFTER_APPROVED_TOOL checkpoint 原子提交。approval_id、idempotency_key、(run_id,call_id) 分别唯一。金额用整数分，当前价格/预算再校验；失败回滚决议和草案。重复同决议返回 replayed=true；相反决议 409。首次决议 request_id 持久化，事件只记一次实际决议；没有逐次重复 HTTP 请求的独立访问审计表。

这是一条刻意狭窄的内置本地写通道，不提供通用事务型外部 Tool handler。外部 HTTP/ERP 与本地 SQLite 不能原子提交，不能从这个例子推出任意工具 exactly-once。不同 Run 有不同幂等键，也不会对任意业务相似任务去重。

## D014 — 恢复矩阵优先于“从哪里都能继续”的承诺

状态迁移由 RunState.transition 显式约束：CREATED → RUNNING/FAILED/CANCELLED；RUNNING → WAITING_APPROVAL/COMPLETED/FAILED/CANCELLED/INTERRUPTED/RECONCILIATION_REQUIRED；WAITING_APPROVAL → RUNNING/CANCELLED/FAILED；INTERRUPTED → RUNNING/FAILED/CANCELLED；RECONCILIATION_REQUIRED → FAILED；终态没有出边。列在状态机里的边不代表都有公开控制 API。

| 断点 | 支持范围 |
|---|---|
| WAITING_APPROVAL | 校验原上下文/配置、pending queue、invocation、approval 参数绑定；重启保留原 ID，继续审批 |
| AFTER_APPROVED_TOOL | 若重启发现 RUNNING，先记 INTERRUPTED；仅在数据库草案凭据、已批准决议、已完成调用、上下文结果一致时显式 resume |
| 模型/只读工具 IN_FLIGHT 或 AFTER_READ_TOOL | 记录 INTERRUPTED；本次不自动或手动继续；可从头新建任务 |
| 高风险调用 RUNNING、结果未知 | RECONCILIATION_REQUIRED / WRITE_OUTCOME_UNKNOWN；禁止补发，本次无自动核对实现 |
| 终态或损坏 checkpoint | 终态保持；损坏待审任务 FAILED / CHECKPOINT_INVALID，服务可继续启动 |

持久化包含中立 context、pending_calls、适配器描述和 safe_point；OpenAI 仅保存协议所需不透明 encrypted_content，无隐藏推理原文。恢复要求环境仍配置同一模型，缺 Key 明确失败；SDK 离线续传测试不代表 Live 重启已在线验证。Mock 可跨进程完整演示。

模型/工具 I/O 前保存 IN_FLIGHT；批次恢复用 pending queue，不重复请求已经产生的函数调用。读工具结果完成虽持久化，本次尚未开放该恢复点，避免宣称任意位置一致性。人工等待不消耗活动 wall_seconds；审批等待时间单独计数。进程正常关闭会取消活动任务，已返回的 WAITING_APPROVAL 不受取消；崩溃由下次启动检测。

曾修复暂停后的 finally 再保存旧快照可能覆盖决议的问题：等待点已在事务中保存，不再二次写；revision 仍兜底。任务完成回调只移除自己持有的 task，防止旧任务删掉新的恢复任务。

## D015 — Trace、脱敏与证据不替代私有恢复状态

RunView 用明确字段过滤，API 不返回 model_resume_state/config_snapshot。模型/调用上下文及 exact demo 参数是恢复所需的私有数据库内容，不能把“脱敏 Trace”说成数据库完全没有原文。API Key 不进入配置快照，数据库文件及 WAL 已被忽略；仅适合合成数据，没有数据库加密或通用 DLP。

redaction.py 对已知秘密字段、Bearer、Key、邮箱和手机号脱敏；工具参数/结果摘要只放行 Demo 业务字段，未知内容遮盖。事件再次脱敏后入库。摘要用于定位问题；不是可拿来重放模型的完整上下文。修复过手机号规则误伤十六进制摘要中的数字段，加入单词边界并用测试约束。

UI 轮询历史、Run/steps/events 和待审批列表；失败步骤和事件可筛选。SSE 属于 P1，本次不扩展。浏览器/SQL 验收用临时数据库和自动分配本机端口，真实结束/重启 API 进程；Windows 同端口重启交给 Uvicorn 绑定，不用预探测 socket 误判 TIME_WAIT。没有停止用户已有的 5173 服务。
