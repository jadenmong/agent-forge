# 2026-10-16：AgentForge Day 1 补齐交付

## 1. 本次结论

用户列出的 Day 1 详细清单已补齐并验证。完整平台 P0 尚未完成；HTTP/前端/MCP/Live/持久化/审批/Evals 均不计入本次通过范围。
PRD 原文和既有 Git 历史保留。本次为本地实现与验证，不包含自动提交/推送。

## 2. 新增与修改文件

### 新增

- [fixtures.json](../../examples/procurement/fixtures.json)：合成采购数据，A/B/C 价格、交期、保修和演示数量/预算。
- [test_day1_contract.py](../../tests/test_day1_contract.py)：23 个新增参数化测试实例。
- 本交付记录。
- `docs/evidence/day1-completion/`：before-pytest.txt、ruff-check.txt、ruff-format.txt、pytest.txt、environment.txt、smoke.txt，以及 demo/direct/single-tool/two-tools/unknown-tool/tool-error/repeat-steps/repeat-model/limit 九个 JSON。

### 修改

- `.gitignore`：忽略 Ruff 缓存。
- `pyproject.toml`：固定 Ruff 0.11.13 开发依赖与基础 lint 配置。
- [models.py](../../src/agentforge/models.py)：AgentConfig/Limits、ToolResult、RunStep、RunEvent、重复脚本模式。
- [tools.py](../../src/agentforge/tools.py)：ToolDefinition、返回 ToolResult。
- [runtime.py](../../src/agentforge/runtime.py)：RunState、配置入口、模型调用计数/上限、真实步骤、取消收尾。
- [demo.py](../../src/agentforge/demo.py)：固定 fixture 加载/校验、场景选择、独立模型调用上限 CLI。
- [test_runtime.py](../../tests/test_runtime.py)：迁移已有调用到新类型和配置入口；保留原 47 项断言与场景，按要求统一格式。
- [verify_day1.py](../../scripts/verify_day1.py)：标准检查、70 项测试与九次 CLI，独立保存新证据。
- [README](../../README.md)、[架构](../ARCHITECTURE.md)、[决策](../DECISIONS.md)、[面试笔记](../INTERVIEW_NOTES.md)、[失败模式](../FAILURE_MODES.md)、[结果](../RESULTS.md)、[API 契约](../API_CONTRACT.md)、[事实矩阵](../FEATURE_MATRIX.md)。

## 3. 架构决策与边界

- 统一用 AgentConfig 传入 allowlist、提示词和限制；ToolResult 实际承载工具结果进入模型上下文。
- 运行状态/步骤使用 dataclass，内部事件使用 TypedDict，配置/协议边界使用严格 Pydantic。内部类型不是外部 REST 协议。
- max_steps 与 max_model_calls 独立配置；当前每轮一次请求、无重试，两项计数通常一致。失败请求也计入尝试次数，两项同时触发时优先 MAX_STEPS。
- RunStep.seq 记录全部 model/tool 操作；step_count 记录决策轮次，二者不能混淆。
- 相同 call ID 立即拒绝；新 ID 重复行为通过次数和预算终止，无语义去重或 exactly-once 承诺。
- 取消协程时结束当前步骤、记录 CANCELLED，再传播取消；外部可传入 RunState 观察，没有持久化或恢复。
- fixture 使用项目固定路径，严格校验；仅支持源码 checkout + editable 安装，未增加 wheel 资源打包。
- tool-error 是显式本地故障注入，未伪造 SDK。默认 Mock 最终摘要由 fixture 预生成，不代表模型智能分析。
- 超时仍依赖协作式取消，token 预算仍用缺 usage 时的 UTF-8 字节代理，成本 unknown。

取舍、替代方案与为何不用 LangGraph 见 DECISIONS D007 和 INTERVIEW_NOTES。

## 4. 实际验证

先运行两个新回归测试，复现 `max_model_calls` 不支持和 fixture 缺失：

```text
2 failed in 0.31s
```

原始输出：[before-pytest.txt](../evidence/day1-completion/before-pytest.txt)。
随后实际安装并运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m ruff check src tests scripts --fix
.\.venv\Scripts\python.exe -m ruff format src tests scripts
.\.venv\Scripts\python.exe scripts/verify_day1.py
```

验证脚本依次运行 `ruff check`、`ruff format --check`、`pytest -q`、九个 CLI 子进程和 `pip freeze`；移除子进程 API_KEY 变量，Mock 不访问模型服务。

最终原始摘要：

```text
All checks passed!
9 files already formatted
......................................................................   [100%]
70 passed in 0.70s
```

70 项 pytest，70 通过、0 失败；另有九个 CLI 检查符合预期，不计入 pytest 数量。这些测试不是独立 JSONL Evals 或真实模型质量样本。
测试耗时仅属于此次运行，不是平台性能指标。

关键失败模式测试：

- `test_invalid_args_never_execute`
- `test_unknown_tool`
- `test_tool_failures` / `test_model_failures`
- `test_endless_mock_is_terminated_at_each_limit`
- `test_invalid_fixture_is_rejected`
- `test_failed_model_attempt_is_counted_and_step_finalized`
- `test_cancellation_preserves_observable_state_and_steps`
- `test_runtime_cannot_reuse_completed_state`

证据：[pytest](../evidence/day1-completion/pytest.txt)、[lint](../evidence/day1-completion/ruff-check.txt)、[格式](../evidence/day1-completion/ruff-format.txt)、[CLI 摘要](../evidence/day1-completion/smoke.txt)、[环境](../evidence/day1-completion/environment.txt)。

## 5. 无模型 Key 演示

在项目根目录，按 README 安装后运行：

```powershell
.\.venv\Scripts\python.exe -m agentforge.demo --scenario two-tools
```

预期：串行两工具、3 次模型调用、COMPLETED / FINAL_ANSWER。CLI 是开发测试入口，平台用户不被要求使用 Python。
正常完整比较可运行 `python -m agentforge.demo`；可通过 `--scenario repeat --max-model-calls 2` 观察受控失败，预期退出码 1。

## 6. 五个面试问题与参考答案

1. **Loop 入口在哪里，怎样证明结果回到模型？** RuntimeEngine.run 控制循环；串行工具测试检查实际报价用于下一次计算，计算结果用于最终响应。
2. **为什么不直接用 LangGraph？** PRD 和求职展示要求实现并解释控制核心；成熟框架是替代方案，自研承担更多维护成本，不能因此宣称生产优势。
3. **状态转换和取消如何处理？** CREATED → RUNNING → COMPLETED/FAILED/CANCELLED；取消时结束步骤并传播 CancelledError，外部可观察传入的 RunState。
4. **步数与模型调用数有什么区别？** 前者表示决策轮次，后者表示请求尝试预算；当前无重试所以计数一致，但可分别限额并验证终止。
5. **为什么 Mock 通过不能代表模型质量？** 请求和最终文本由确定性脚本给出；只能证明被测执行逻辑。Live 适配器未实现，Live 未测。

## 7. Day 1 验收

| 要求 | 结果 | 证据 |
|---|---|---|
| 初始化/依赖/README/格式/pytest | PASS | pyproject、README、ruff-check.txt、ruff-format.txt、pytest.txt |
| 全部指定有类型数据结构实际使用 | PASS | models/tools/runtime；test_builtin_mock_scenarios、test_tools_load_actual_fixture_values |
| 自研循环、工具授权、完成/失败/取消/各上限和超时 | PASS | runtime；原测试与 test_day1_contract.py |
| 六类必要 Mock 场景 | PASS | smoke.txt 与各场景 JSON |
| 三个本地工具/fixture/非法参数不执行 | PASS | test_tools_load_actual_fixture_values、test_invalid_args_never_execute |
| 无 Key CLI、多工具回到模型并完成 | PASS | two-tools.json；test_serial_tools_return_results_before_next_model_call |
| 最大步数有限终止并记录原因 | PASS | repeat-steps.json、limit.json；test_endless_mock_is_terminated_at_each_limit |
| 面试入口/状态/为何不用 LangGraph | PASS | INTERVIEW_NOTES.md |

## 8. 剩余 P0、接口和下次事项

| 完整平台 P0 | 状态 | 边界/证据 |
|---|---|---|
| Execution Engine / Tool Registry | PASS | 当前 Mock 内存范围，见 FEATURE_MATRIX |
| Agent Studio / Trace / 安全护栏 / API 文档部署 | PARTIAL | 有配置类型、CLI 步骤和策略，无 UI/HTTP/完整部署 |
| MCP | NOT_TESTED | 无适配器和官方版本兼容性结论 |
| Checkpoint / Human Approval | NOT_TESTED | 无 SQLite、审批 ID、幂等写入或重启恢复 |
| Evals | NOT_TESTED | 无 JSONL、指标计算或两批比较 |
| Live | NOT_TESTED | 适配器未实现、未运行 |

本次新增/变更 OpenAPI 端点：**无**。语言无关的 HTTP/curl 创建查询尚未实现；内部 Python 类型不等于已提供公开 API 或其他语言 Runtime。

下次优先补齐原 10/15 工作：先核对官方 MCP SDK/协议/API 与可用版本，记录差异，再锁定并进行真实客户端—服务端测试；实现可配置 Responses 适配器、FastAPI/OpenAPI/curl 和基础 Workbench。
SQLite/审批/Trace 属于后续工作，不以本次 Day 1 通过替代其验收。
