# 2026-10-14 实际交付结果

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
