# AgentForge

面向不同语言 Agent 应用开发者的本机单用户 Agent Harness 求职作品。
本周选择 Python 实现服务端，通过 REST/JSON/OpenAPI 提供语言无关接入，前端采用 React/TypeScript。
**当前交付：Day 2 模型接入、官方 MCP v2、REST/OpenAPI 与最小 React Workbench。**
Day 1 内存 Runtime 继续作为控制核心；不使用框架 Runner。实际验收状态见 [FEATURE_MATRIX](docs/FEATURE_MATRIX.md)。

## Day 2：启动 API 与 Workbench

要求 Python 3.12+、Node.js 22.12+。在源码仓库根目录安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
npm.cmd --prefix apps/web ci
```

两个终端分别执行：

```powershell
# 终端 1：API、内存 Runtime、自动发现固定本机 stdio MCP Server
.\.venv\Scripts\python.exe -m uvicorn agentforge.api:app --host 127.0.0.1 --port 8000
```

```powershell
# 终端 2：React/TypeScript/Vite
npm.cmd --prefix apps/web run dev
```

浏览器打开 **http://127.0.0.1:5173**，API 文档在 **http://127.0.0.1:8000/docs**，规范在 `/openapi.json`。
Linux/macOS 用 `.venv/bin/python` 和 `npm` 替换 Windows 路径/命令。
本次提供两条开发启动命令；Docker Compose 按任务允许的替代方案留到 Day 4，当前没有 Docker 验收结论。

### Mock 与 Live

Mock 默认无 Key，选择 Agent 和演示场景后启动；任务文本不会决定固定脚本的工具选择。
`procurement-demo` 默认执行两个串行本地工具；选择 `mcp-demo` 会执行两个真实 MCP 只读工具。界面显示 Mock 标签、状态、步骤和安全错误码。
可创建 Agent，设置名称、提示词、工具 allowlist、步数/调用次数、超时和预算；UI 使用同一公开 API。

Live 使用官方 OpenAI SDK Responses HTTP 接口。在启动 API 前，在对应终端设置：

```powershell
$env:OPENAI_API_KEY = "<your-key>"
$env:OPENAI_MODEL = "<model-id-available-to-your-account>"
```

应用不自动读取 `.env`；`.env.example` 仅说明变量。真实模型名和 API Key 从服务端环境读取，前端不接收或保存 Key。
任一变量缺失时，Live 创建 Run 返回 `503 / LIVE_NOT_CONFIGURED`，不退回 Mock。本次环境未配置两项变量，**Live 外部 API 未测**；离线 HTTP fixture 测试不是 Live 成果。

Responses 使用 `store=false`，按顺序重放 function_call、关联 call_id 的 function_call_output 和 reasoning 的不透明 encrypted_content；不依赖 previous_response_id，不保存/展示隐藏推理原文。
续传状态仅在本次执行内存中，尚不支持重启恢复。`store=false` 不代表自动获得账户层 Zero Data Retention；实际数据保留政策以提供商和账户配置为准。
关闭供应商自动重试；429、鉴权、网络、超时和未完成响应转为明确失败原因。单次请求设置 2048 输出 token 上限，Runtime 继续检查整体预算；成本缺价格时为 unknown。

### 非 Python 客户端：curl 创建与查询

成功响应为 `{data, request_id}`，错误为 `{error: {code, message, request_id}}`。
在 PowerShell 中通过真实 curl 与原生 JSON 解析完成，无需 Python 客户端 SDK：

```powershell
$created = curl.exe --silent --show-error --fail --noproxy "*" -X POST -H "Content-Type: application/json" --data-binary "@examples/http/create-run.json" http://127.0.0.1:8000/api/runs | ConvertFrom-Json
$runId = $created.data.run_id
curl.exe --silent --show-error --fail --noproxy "*" "http://127.0.0.1:8000/api/runs/$runId"
curl.exe --silent --show-error --fail --noproxy "*" "http://127.0.0.1:8000/api/runs/$runId/steps"
```

创建返回 HTTP 202，状态不保证同步完成，客户端轮询查询。Java/Go/TypeScript 同样可发送 HTTP/JSON 请求，不代表已经提供原生 Runtime 或官方 SDK。
端点、错误码、游标与重复提交语义见 [API_CONTRACT](docs/API_CONTRACT.md)。

### MCP 与进程限制

固定 `mcp==2.3.0`、协议 `2026-07-28`，使用 `MCPServer` / `Client`，默认通过 server/discover 探测，不手动执行旧 initialize。
只连接源码固定的本机 `python -m agentforge.mcp_server`，不接受 URL、安装命令或任意远端 Server。
同一 Registry 暴露五个工具：三个 local、两个带 mcp_ 前缀的只读 MCP 工具。权限由 Registry 决定，服务端注解不构成授权。
发现与每次调用各自管理一个 stdio 子进程；统一检查 JSON Schema、权限、超时、结果大小。没有外部 MCP 自动重试。

Agent、Run、Step、Event 均在内存，后台 Run 由当前 asyncio 进程持有，退出时取消；重启后历史清空。仅启动单个 API worker，无分布式队列、持久化或审批恢复。
本机最多四个活动 Run、二百条 Run 历史和一百个 Agent，容量满返回 409；没有多租户和 OAuth。

### Day 2 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix apps/web run build
.\.venv\Scripts\python.exe scripts/verify_day2.py
```

统一脚本需要 8000/5173 空闲：运行检查与测试后，启动临时服务，实际调用 curl，再用 Playwright 操作 Workbench；结束时清理自己启动的进程。
Windows 优先使用已安装的 Edge；其他环境先执行 `.venv/bin/python -m playwright install chromium`。首次依赖/浏览器安装需要网络，安装后的 Mock、MCP、HTTP 和浏览器验证只访问本机。
证据写入 `docs/evidence/day2/`，兼容性结论以真实集成测试和运行结果为准。

## Day 1 CLI（保留，无需模型 Key）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m ruff format --check src tests scripts
.\.venv\Scripts\python.exe -m agentforge.demo
.\.venv\Scripts\python.exe -m pytest -q
```

重跑格式检查、pytest 和 9 个 CLI 检查并保存原始证据：

```powershell
.\.venv\Scripts\python.exe scripts/verify_day1.py
```

Day 1 补齐时记录：70 项 pytest 通过、0 失败；9 个 CLI 检查符合预期，证据在 `docs/evidence/day1-completion/`。当前完整测试结果以 Day 2 为准；原始 10/14 证据保留。

Linux/macOS 使用 `.venv/bin/python` 替换上述虚拟环境解释器路径。
首次安装依赖需要访问包仓库或已有 wheel 缓存；安装完成后演示与测试不访问网络。

Demo 通过三个只读工具完成合成供应商报价、交期保修和总价查询：4 轮模型响应、7 次顺序工具调用，输出明确标记 `mock`。
数据来自 `examples/procurement/fixtures.json`，按严格模型校验，并检查 A/B/C 不重复。计算工具使用请求中的整数单价与数量。
需要保留源码 checkout 并按上面命令 editable 安装；尚未实现 fixture 的独立 wheel 打包。
这是固定脚本验证控制流，不是模型智能、实时供应商信息或采购建议。默认最终文本在脚本组装时根据 fixture 生成，不对工具输出进行智能判断。不会生成草案或订单。

限制终止演示（预期退出码 1、`FAILED / MAX_STEPS`）：

```powershell
.\.venv\Scripts\python.exe -m agentforge.demo --max-steps 1
```

## Mock 场景

使用 `python -m agentforge.demo --scenario <名称>`；上面的虚拟环境解释器路径同样适用。

| 场景 | 行为 / 预期终止 |
|---|---|
| `procurement`（默认） | 三个工具、4 轮模型响应，`COMPLETED / FINAL_ANSWER` |
| `direct` | 直接回复，零工具调用 |
| `single-tool` | 一次工具调用后回到模型 |
| `two-tools` | 两轮各调用一个工具，再回到模型完成 |
| `unknown-tool` | 请求未注册工具，`FAILED / UNKNOWN_TOOL` |
| `repeat` | 用新 call ID 持续请求同一只读工具，直到上限终止 |
| `tool-error` | 显式注入本地模拟工具异常，`FAILED / TOOL_ERROR` |

独立模型调用次数上限演示（预期退出码 1）：

```powershell
.\.venv\Scripts\python.exe -m agentforge.demo --scenario repeat --max-model-calls 2
```

同一 call ID 重复时立即拒绝，原因是 `DUPLICATE_CALL_ID`；新 ID 的重复行为由次数、时间和预算上限限制。
失败演示退出码 1 是预期行为，不等于测试失败。

## 已实现与边界

- 自研 `model → calls → results → model` 顺序循环，零/单/多调用，拒绝重复 call ID。
- 使用 `AgentConfig`、`ModelAdapter`、`ToolDefinition`、`ToolCall`、`ToolResult`、`RunState`、`RunStep`、`RunEvent`；工具结果实际经由 `ToolResult` 回到模型。
- Pydantic v2 生成工具 JSON Schema，并在执行入口严格校验；allowlist 默认空。
- 只读默认；禁用和需审批工具均阻断。尚无“已批准”通道。
- `max_steps`、`max_model_calls`、工具次数、wall time、调用超时、token 配额、输入/输出大小限制。模型调用尝试计数包含失败请求；当前无重试，每轮只请求一次模型，两项计数通常相同。
- CLI 输出 Run ID、状态、终止原因、逐操作步骤及事件。调用方取消协程时记录 CANCELLED 和步骤状态，再传播取消异常；可通过传入的 `RunState` 查看结果。
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
