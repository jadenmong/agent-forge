# REST/JSON API 契约状态

2026-10-14：**没有 HTTP 服务、没有新增或变更的 OpenAPI 端点**。
当前 CLI 不是公开 REST API；无法用 curl 创建 Run，不提供会误导为可执行的伪地址。

## 10/15 待实现的最小接口（计划，未交付）

| 方法 | 路径 | 意图 |
|---|---|---|
| GET | `/health` | 健康状态 |
| GET/POST | `/api/agents` | 配置列表/创建 |
| GET | `/api/agents/{id}` | 查询配置 |
| GET | `/api/tools` | 工具能力与权限 |
| POST | `/api/runs` | 创建启动 Run |
| GET | `/api/runs` | 分页列表 |
| GET | `/api/runs/{id}` | 状态与结果 |
| GET | `/api/runs/{id}/events` | 事件游标查询 |
| GET | `/openapi.json` | 实际生成规范 |

审批/恢复/取消/评测按 PRD §6 在对应模块交付时增加。SSE 为 P1。
接口交付时确定统一成功结构及错误结构、request_id、snake_case、HTTP 状态码、幂等和冲突处理，并与生成的 OpenAPI 一起测试。
公开错误不包含 Python 类型/类名/堆栈或供应商原始错误。

语言无关的客户端通过普通 HTTP/JSON 使用相同公开接口；将提供并实测 curl 创建和查询流程。
非 Python 客户端可以调用 API，并不意味着已开发 Java/Go/Node Runtime 或官方客户端 SDK。
