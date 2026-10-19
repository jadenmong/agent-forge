# REST/JSON API 契约 — Day 3（2026-10-18）

源码：`src/agentforge/api.py`。默认 `http://127.0.0.1:8000`，单进程、无认证的本机单用户 Demo。
UI 与其他语言客户端使用相同公开 API，不要求 Python 客户端。实际规范在 `/openapi.json`，本次快照见 [openapi.json](evidence/day3/openapi.json)。

## 1. 统一响应

成功：`{"data": <资源或数组>, "request_id": "<服务端UUID>"}`。
错误：`{"error": {"code": "...", "message": "安全消息", "request_id": "..."}}`。
字段为 snake_case；常规控制响应携带 X-Request-ID。验证错误不回显输入、Python 类型或堆栈，供应商和 MCP 原始异常不进入错误响应。
OpenAPI 是标准规范文档，不包装 data；`/docs` 是 Swagger 文档页面。

## 2. 已实现端点

| 方法 | 路径 | 成功状态 | data 内容 |
|---|---|---|---|
| GET | `/health` | 200 | status、storage=sqlite、schema_version=1、live_configured、mcp_sdk/protocol/transport |
| GET | `/api/agents` | 200 | AgentConfig 数组，不包含 Key |
| POST | `/api/agents` | 201 | 新建 AgentConfig |
| GET | `/api/agents/{agent_id}` | 200 | 单个 AgentConfig |
| GET | `/api/tools` | 200 | name、description、input_schema、permission、timeout_seconds、source |
| POST | `/api/runs` | 202 | Run 快照，不保证同步完成 |
| GET | `/api/runs` | 200 | 最新优先的 Run 快照数组 |
| GET | `/api/runs/{run_id}` | 200 | Run ID、Agent ID、mode、状态、原因、计数、预算来源、cost、output、input_summary、开始/结束时间、活动秒数与审批等待秒数 |
| GET | `/api/runs/{run_id}/steps` | 200 | RunStep 数组，按 seq 排列，含 arguments_summary / result_summary、实测耗时、安全错误码 |
| GET | `/api/runs/{run_id}/events` | 200 | 大于游标的 RunEvent 数组 |
| GET | `/api/approvals` | 200 | 当前可操作的 PENDING 且 Run 为 WAITING_APPROVAL 的审批数组 |
| GET | `/api/runs/{run_id}/approvals` | 200 | 指定 Run 的待审及已决审批审计数组 |
| POST | `/api/runs/{run_id}/approve` | 200 | run_id、当前 status、approval、replayed；批准或拒绝 |
| POST | `/api/runs/{run_id}/resume` | 202 | 安全恢复后的 Run 快照；不是任意断点重跑 |
| GET | `/openapi.json` | 200 | 标准 OpenAPI JSON |

列表参数：offset 默认 0 且 ≥0；limit 默认 20，范围 1–100。
事件参数：after_event_id 默认 0 且 ≥0，返回 event_id 严格大于该值的事件。
取消控制端点、评测和 SSE 尚未实现；界面使用轮询。公开 Run/Step/Event 不暴露 config_snapshot 或私有 model_resume_state。

## 3. 创建 Agent 与 Run

Agent 请求 name 必填；system_prompt、model_adapter（mock/openai）、allowed_tools 字符串数组、limits 可选。
limits 包含 max_steps、max_model_calls、max_tool_calls、wall_seconds、model_timeout_seconds、max_tokens，范围见 OpenAPI。
allowlist 只允许注册工具；空数组表示无工具权限。真实模型名来自服务端 OPENAI_MODEL；客户端不能提交 Key 或出站 URL。

Run 请求示例：

```json
{
  "agent_id": "procurement-demo",
  "mode": "mock",
  "input": "Compare synthetic supplier quotations. Read-only demo.",
  "mock_scenario": "two-tools"
}
```

mode 为 mock/live，默认 mock，覆盖本次使用的模型模式。Mock 场景是 two-tools/procurement/mcp/purchase/budget-low；Live 使用真实任务文本，忽略演示场景。
procurement-demo 授权三个 local 只读工具；mcp-demo 授权两个 MCP 工具；purchase-demo 额外授权需审批的 create_purchase_draft。场景与 Agent 权限必须匹配，模型请求不能提升权限。
input 长度 1–16000 字符，纯空白拒绝。

每次 POST 创建独立 ID，无请求级幂等键；名称允许重复。相同审批及绑定调用可幂等重放，不对不同 Run 的重复业务任务去重。
单个 API worker 最多四个活动执行任务、二百条持久化 Run 和一百个 Agent；超限返回 409，等待审批已释放活动任务槽位，无分布式锁或队列。
后台任务有强引用，正常服务关闭时取消活动任务；WAITING_APPROVAL 和历史均保留于 SQLite，启动执行安全点检查。恢复规则见下。

## 4. 错误语义

| HTTP | code | 条件 |
|---|---|---|
| 400 | INVALID_HOST | 非本机允许的 Host |
| 404 | AGENT_NOT_FOUND / RUN_NOT_FOUND / APPROVAL_NOT_FOUND | 资源或绑定审批不存在 |
| 422 | INVALID_REQUEST | 字段、范围、类型非法或空白任务，不回显原始值 |
| 422 | UNKNOWN_TOOL | Agent allowlist 中包含未注册工具 |
| 409 | CAPACITY_REACHED | 本机容量限制 |
| 409 | APPROVAL_CONFLICT | 审批已作相反决定或 Run 状态不再允许审批 |
| 409 | CHECKPOINT_INVALID / STALE_RUN_STATE | 绑定、完整性或 revision 校验失败，未提交写入 |
| 409 | UNSAFE_RESUME_POINT | 终态、未知写结果、模型/只读调用中断等不支持恢复 |
| 409 | LIVE_MODEL_CHANGED | 恢复时服务端模型与冻结的模型配置不同 |
| 503 | LIVE_NOT_CONFIGURED | OPENAI_API_KEY 或 OPENAI_MODEL 缺失/为空 |
| 503 | STORAGE_BUSY | 本地数据库忙，先查询决议再重试 |
| 500 | INTERNAL_ERROR | 未预期错误，不返回内部异常 |

Run 接受后的模型/工具错误体现在 `status=FAILED` 与 stop_reason，查询本身不因此变成 HTTP 500。
例如 MCP_TIMEOUT/MCP_UNAVAILABLE/MCP_TOOL_ERROR、PROVIDER_RATE_LIMIT/PROVIDER_AUTH/PROVIDER_UNAVAILABLE、MODEL_INCOMPLETE、MAX_STEPS、TOKEN_BUDGET。
工具越权、未知名称和非法参数在执行前拒绝，无无限重试或未知副作用自动补发。
cost 缺少价格为 null（unknown）；token_accounting 区分 provider_reported 和 utf8_bytes_estimate，后者不是真实账单。

## 5. curl 与证据

在项目根目录的 PowerShell 中运行，不依赖 Python 客户端 SDK：

```powershell
$created = curl.exe --silent --show-error --fail --noproxy "*" -X POST -H "Content-Type: application/json" --data-binary "@examples/http/create-run.json" http://127.0.0.1:8000/api/runs | ConvertFrom-Json
$runId = $created.data.run_id
curl.exe --silent --show-error --fail --noproxy "*" "http://127.0.0.1:8000/api/runs/$runId"
curl.exe --silent --show-error --fail --noproxy "*" "http://127.0.0.1:8000/api/runs/$runId/steps"
```

真实运行证据：[创建](evidence/day3/curl-create.json)、[查询](evidence/day3/curl-query.json)、[审批重放](evidence/day3/curl-approval-replay.json)。
Java、TypeScript、Go 可发送同样的 HTTP/JSON 请求；这不代表已提供这些语言的 Runtime 或官方 SDK。

## 6. 审批绑定与恢复协议

`POST /api/runs/{run_id}/approve` 只接收：

```json
{"approval_id":"<GET approvals 返回的 ID>","decision":"approve"}
```

decision 也可为 reject。禁止额外字段，包括 arguments、supplier、quantity。服务端用 approval_id 关联数据库中 run_id/call_id/tool_name/validated_args；SHA-256 摘要同时绑定这些字段。摘要用于一致性检查，不是签名或身份认证。

ApprovalView 包含 approval_id、run_id、call_id、tool_name、request_payload（具体 Demo 参数）、args_digest、status、created_at、decided_at、effect。批准前 UI 必须展示该具体副作用；后端再次检查冻结的工具 allowlist、权限、参数和预算。

批准在一个 SQLite 事务中提交决议、本地草案、工具结果及 AFTER_APPROVED_TOOL checkpoint，再异步继续模型；200 不保证模型已完成。拒绝记录 REJECTED，Run 变 CANCELLED / APPROVAL_REJECTED，无草案。相同决议重复返回 200/replayed=true，不重复工具执行或新增审批事件；相反决议返回 409。结果可用 GET approvals/events 审计；数据库保留原决议的 request_id。没有提供登录用户身份审计。

草案对 approval_id、idempotency_key、(run_id,call_id) 有唯一约束。数据库事务保证范围仅为本地模拟草案，不外推到 HTTP/ERP 外部副作用。

| 重启时状态/断点 | 行为 | 客户端下一步 |
|---|---|---|
| WAITING_APPROVAL 且绑定有效 | 保留同一 ID/上下文，追加恢复事件 | 正常 approve/reject |
| WAITING_APPROVAL 绑定损坏 | FAILED / CHECKPOINT_INVALID | 查看 Trace；不执行 |
| RUNNING + AFTER_APPROVED_TOOL | 标记 INTERRUPTED | POST resume；再次验证数据库草案凭据、审批、结果上下文 |
| RUNNING 中模型/只读操作 | INTERRUPTED | resume 返回 409；可新建 Run |
| RUNNING 且写工具结果未知 | RECONCILIATION_REQUIRED | 人工核对，无自动重发或核对控制 API |
| CREATED 尚未开始 | FAILED / PROCESS_NOT_STARTED | 可新建 Run |
| COMPLETED / FAILED / CANCELLED | 保持终态 | resume 返回 409 |

resume 无需请求体；不能用它批准 pending 调用。公开 Trace 是脱敏摘要，私有精确上下文不提供导出接口。
完整 curl 审批步骤见 [README](../README.md)；自动化真实 SQL/进程证据见 [database-assertions.json](evidence/day3/database-assertions.json)。
