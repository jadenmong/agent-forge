# AgentForge 本周实施清单（一页）

依据：`PRD.md` P0、安全不变量与 §10；日期：2026-10-14（UTC+8）。
现状：开始时仅有 PRD，无代码、无 `.git`；保留原文，不初始化或改写历史。

## 范围与目录

产品服务不同语言的 Agent 应用开发者；本周只实现 Python 服务端，通过 REST/JSON/OpenAPI 接入。
采用一个可安装的 Python 包，避免首日引入多包构建；模块责任与 PRD 相同。

```text
src/agentforge/
  runtime.py          # 自研顺序 Loop、状态机、限制、运行事件
  models.py           # 协议类型、DeterministicMockAdapter；次日加 Responses
  tools.py            # 注册、Schema、allowlist、策略、超时
  demo.py             # 隔离的只读采购 Demo 与 CLI
  api.py              # 10/15：FastAPI 公开契约
  mcp_adapter.py      # 10/15：官方 SDK client/server 示例
  storage.py          # 10/16：SQLite/SQLAlchemy、checkpoint、审批幂等
  evals.py            # 10/17：JSONL、指标、两批比较
apps/web/             # 10/15 起：React/TypeScript/Vite
tests/                # 单测、集成、后续 UI E2E
docs/                 # 决策、契约、故障、结果、面试、验收矩阵
```

以上包含计划目录，未创建的模块不代表已实现。

## 逐日验收清单

| 日期 | 实施与当天验证 |
|---|---|
| 10/14 | Mock 零/一/多工具及连续调用；至少三个只读工具；非法状态/参数/工具、越权、超时、工具异常、模型异常、步数/工具数/时间/token 限制均有断言；CLI 无 Key 演示 |
| 10/15 | 验证官方 MCP 2026-07-28 与 SDK 2.x 实际可用版本/API，锁定并实测真实 client/server；Responses 续传与供应商错误；FastAPI/OpenAPI/curl；React Workbench |
| 10/16 | WAL 存储 Run/Step/Event/续传；审批绑定不可变参数；SQLite 唯一幂等键；批准/拒绝/重复批准/重启测试；Trace 与审批 UI |
| 10/17 | 30–50 条有来源的回归/故障用例；JSONL 评测与比较；Mock/Live 分报；README、Compose、故障证据 |
| 10/18 | 冻结、全回归、UI E2E、curl 与 Compose 复验；事实矩阵与准确贡献说明；条件具备再打 v0.1.0 标签 |

## 不可越过的边界

- 自研 Loop/策略/状态/存储/评测，不以框架 Runner 替代；SDK 只处理模型请求和 MCP。
- 今天仅内存执行、只读 Demo；写工具一律拒绝，不能声称审批或恢复已实现。
- 之后只承诺验证过的安全等待点恢复；外部写入结果未知须核对，不盲目重发。
- 工具结果不改变 allowlist；不执行 shell、任意 URL/文件或真实业务写入。
- 无 Key 的 Mock 验证不证明 Live 质量；成本/usage 未知就标记 unknown。
- 不增加多租户、OAuth、分布式调度、长期记忆或其他 P2；每次交付更新事实证据。
