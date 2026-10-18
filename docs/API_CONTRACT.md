# REST/JSON API 契约 — Day 2（2026-10-17）

源码：`src/agentforge/api.py`。默认 `http://127.0.0.1:8000`，单进程、无认证的本机单用户 Demo。
UI 与其他语言客户端使用相同公开 API，不要求 Python 客户端。实际规范在 `/openapi.json`，本次快照见 [openapi.json](evidence/day2/openapi.json)。

## 1. 统一响应

成功：`{"data": <资源或数组>, "request_id": "<服务端UUID>"}`。
错误：`{"error": {"code": "...", "message": "安全消息", "request_id": "..."}}`。
字段为 snake_case；常规控制响应携带 X-Request-ID。验证错误不回显输入、Python 类型或堆栈，供应商和 MCP 原始异常不进入错误响应。
OpenAPI 是标准规范文档，不包装 data；`/docs` 是 Swagger 文档页面。

## 2. 已实现端点

| 方法 | 路径 | 成功状态 | data 内容 |
|---|---|---|---|
| GET | `/health` | 200 | status、storage=memory、live_configured、mcp_sdk/protocol/transport |
| GET | `/api/agents` | 200 | AgentConfig 数组，不包含 Key |
| POST | `/api/agents` | 201 | 新建 AgentConfig |
| GET | `/api/agents/{agent_id}` | 200 | 单个 AgentConfig |
| GET | `/api/tools` | 200 | name、description、input_schema、permission、timeout_seconds、source |
| POST | `/api/runs` | 202 | Run 快照，不保证同步完成 |
| GET | `/api/runs` | 200 | 最新优先的 Run 快照数组 |
| GET | `/api/runs/{run_id}` | 200 | Run ID、Agent ID、mode、状态、原因、计数、预算来源、cost、output |
| GET | `/api/runs/{run_id}/steps` | 200 | RunStep 数组，按 seq 排列 |
| GET | `/api/runs/{run_id}/events` | 200 | 大于游标的 RunEvent 数组 |
| GET | `/openapi.json` | 200 | 标准 OpenAPI JSON |

列表参数：offset 默认 0 且 ≥0；limit 默认 20，范围 1–100。
事件参数：after_event_id 默认 0 且 ≥0，返回 event_id 严格大于该值的事件。
审批、恢复、取消控制端点、评测和 SSE 尚未实现，不在本次规范中宣称可调用。

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

mode 为 mock/live，默认 mock，覆盖本次使用的模型模式。Mock 场景是 two-tools/procurement/mcp；Live 使用真实任务文本，忽略演示场景。
procurement-demo 授权三个 local 工具；mcp-demo 授权两个 MCP 工具。mcp 场景应选择后者或具有对应 allowlist 的自定义 Agent。
input 长度 1–16000 字符，纯空白拒绝。

每次 POST 创建独立 ID，无请求幂等键；名称允许重复。只读 Run 可重复执行，不表示模拟写入幂等已经实现。
同一事件循环检查容量并创建资源，最多四个活动 Run、二百条 Run 历史和一百个 Agent；超限返回 409，无分布式锁或队列。
后台任务有强引用，正常服务关闭时取消；强制结束或重启会丢失全部状态，无安全点恢复保证。

## 4. 错误语义

| HTTP | code | 条件 |
|---|---|---|
| 400 | INVALID_HOST | 非本机允许的 Host |
| 404 | AGENT_NOT_FOUND / RUN_NOT_FOUND | 资源不存在 |
| 422 | INVALID_REQUEST | 字段、范围、类型非法或空白任务，不回显原始值 |
| 422 | UNKNOWN_TOOL | Agent allowlist 中包含未注册工具 |
| 409 | CAPACITY_REACHED | 本机容量限制 |
| 503 | LIVE_NOT_CONFIGURED | OPENAI_API_KEY 或 OPENAI_MODEL 缺失/为空 |
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

真实运行证据：[创建](evidence/day2/curl-create.json)、[查询](evidence/day2/curl-run.json)、[步骤](evidence/day2/curl-steps.json)。
Java、TypeScript、Go 可发送同样的 HTTP/JSON 请求；这不代表已提供这些语言的 Runtime 或官方 SDK。
