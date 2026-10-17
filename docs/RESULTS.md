# 实际交付结果

## 2026-10-16：补齐 Day 1 详细清单

新增独立模型调用限制、实际使用的类型化配置/结果/状态/步骤/事件、指定采购 fixture、命名 Mock 场景及 Ruff 检查。
不重复初始化仓库，不改变历史 PRD 和原始证据；本次未实现平台后续模块。

实际执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_day1_contract.py -q --tb=short
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m ruff check src tests scripts --fix
.\.venv\Scripts\python.exe -m ruff format src tests scripts
.\.venv\Scripts\python.exe scripts/verify_day1.py
```

修改实现前的两个回归测试实际失败；原始输出在 `evidence/day1-completion/before-pytest.txt`。
统一验证脚本实际执行 `ruff check`、`ruff format --check`、`pytest -q`、9 次 CLI 和 `pip freeze`，子进程移除名称以 API_KEY 结尾的环境变量。安装开发依赖会访问包仓库；Mock 验证不需要外网/模型 Key，测试护栏阻断外部 socket 连接。

最终保存的原始摘要：

```text
All checks passed!
9 files already formatted
......................................................................   [100%]
70 passed in 0.70s
```

pytest 共 70 项、70 通过、0 失败；原有 47 项保留并新增 23 项。9 个 CLI 检查均符合状态/次数/原因与退出码断言。
正常 Demo 4 次模型调用、7 次工具调用；重复请求分别由 MAX_STEPS 和 MAX_MODEL_CALLS 终止；未知工具与工具异常均以预期失败码退出。
取消测试断言 RunState/RunStep 进入 CANCELLED 并传播取消异常。串行工具测试检查实际结果进入后续上下文并用于下次调用和最终输出。

| 证据路径（相对 docs） | 内容 |
|---|---|
| `evidence/day1-completion/ruff-check.txt` | 静态检查原始 stdout |
| `evidence/day1-completion/ruff-format.txt` | 格式检查原始 stdout |
| `evidence/day1-completion/pytest.txt` | 最终 pytest 原始 stdout |
| `evidence/day1-completion/smoke.txt` | 九次真实 CLI 检查摘要 |
| `evidence/day1-completion/*.json` | 各次 CLI 原始输出，包含实际 Run ID、步骤、事件、时间和耗时 |
| `evidence/day1-completion/environment.txt` | 实际安装版本 |

没有新增/变更 HTTP 或 OpenAPI 端点，curl 创建/查询仍未实现；没有实现 Live 适配器，Live 未测。
保留内存执行、只读工具、协作式超时和 UTF-8 字节估计预算的限制，不宣称审批恢复、任意位置恢复或 exactly-once。
Mock 默认最终摘要根据 fixture 预生成，仍不证明真实模型质量；本次未计算 p50/p95 或真实成本。

新增/修改文件完整清单、五个问答、Day 1/P0 验收与后续事项见 `deliveries/2026-10-16-day1-completion.md`。

---

## 2026-10-14 原始交付记录

范围：PRD §10 首日。Python 3.12.3 / Windows；独立 `.venv`；无模型 Key，测试阻断外部 socket 连接（允许 Windows asyncio 自用 loopback）。
直接依赖固定版本在 `pyproject.toml`；完整实测安装清单在 `evidence/day1-environment.txt`，不是部署锁文件。

## 实际命令与结果

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe scripts/verify_day1.py
```

安装成功。验证脚本使用同一个虚拟环境解释器，依次实际执行：

```text
python -m pytest -q -ra
python -m agentforge.demo
python -m agentforge.demo --max-steps 1
python -m pip freeze
```

最终原始摘要（来自验证命令 stdout）：

```text
...............................................                          [100%]
47 passed in 0.48s
Mock demo: COMPLETED, 4 model turns, 7 tool calls
Limit demo: FAILED / MAX_STEPS, exit 1
```

47 项 pytest 用例，47 通过、0 失败；参数化实例各计一项，均为人工构造的控制逻辑回归，不是 JSONL 评测集或 Live 样本。
另外两个 CLI smoke 检查均符合预期。0.48s 是该次 pytest 摘要，不是平台延迟基准；未计算 p50/p95、模型准确率或真实成本。

## 可复查证据

| 文件 | 内容 |
|---|---|
| `evidence/day1-pytest.txt` | 最终 pytest 原始 stdout |
| `evidence/day1-demo.json` | 实际 Mock CLI 运行状态、事件、输出，含真实时间戳和耗时 |
| `evidence/day1-limit.json` | 实际 MAX_STEPS 失败轨迹 |
| `evidence/day1-smoke.txt` | 根据上述 CLI 输出断言成功后生成的摘要 |
| `evidence/day1-environment.txt` | 本次环境 pip freeze |
| `evidence/day1-network-guard-failure.txt` | 首次全 socket 阻断误伤 Windows asyncio 的原始失败 stdout |

`scripts/verify_day1.py` 可重新生成证据；时间戳、UUID、耗时会变化，Mock 决策和结果不变。
最终结果覆盖之前调试时的 43 passed 和 1 failed / 46 passed，不隐瞒中间失败；NaN 故障复盘见 `FAILURE_MODES.md`。
后续首次加网络护栏产生 41 failed / 6 passed / 20 warnings（3.83s），原因是 Windows `socketpair()` 用 loopback `connect` 实现，测试基础设施阻断了事件循环创建；允许明确的本机地址后恢复通过。没有通过伪造模型/MCP SDK 响应解决问题。

## 未执行/未交付

- Live：适配器未实现，Live 未测；不是“已实现但未测”。
- MCP：SDK/协议/API 官方验证尚未执行，没有兼容性结论。
- REST/OpenAPI/curl、React/E2E、SQLite/审批/重启恢复、JSONL Evals、Compose/CI 均未交付或执行。
- 没有真实业务写入；未授权 handler 副作用为零有测试，批准/拒绝/重复批准不变量尚无实现证据。

## 文件清单（全部新增，原有 PRD 未修改）

- 根目录：`README.md`、`pyproject.toml`、`.gitignore`、`.env.example`。
- 源码：`src/agentforge/{__init__,models,tools,runtime,demo}.py`。
- 验证：`tests/conftest.py`、`tests/test_runtime.py`、`scripts/verify_day1.py`。
- 文档：`docs/{IMPLEMENTATION_PLAN,ARCHITECTURE,DECISIONS,API_CONTRACT,FAILURE_MODES,INTERVIEW_NOTES,RESULTS,FEATURE_MATRIX}.md`。
- 证据：上表 `docs/evidence/` 六个文件。
- 本地生成且被忽略：`.venv/`、Python/pytest 缓存、editable 安装元数据。

## 下次：2026-10-15

1. 官方 MCP SDK 2.x/2026-07-28 来源验证、版本/API 差异记录、确切版本锁定和真实 client/server 工具发现调用。
2. OpenAI 官方 Responses 适配器：合法续传与 provider 错误/限流测试；无 Key 时保留未实测标记。
3. FastAPI Agent/Run/Tools、统一错误/request_id/OpenAPI 与实际 curl 创建/查询。
4. React/TypeScript/Vite Workbench 使用同一公开 API；不提前做 P1/P2。
