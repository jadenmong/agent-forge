# 实际交付结果

## 2026-10-19：Day 4 评测、安全回归、四页工作台与文档

先跑 Day 3 基线：**143 passed in 41.55s**，原始输出见 [baseline-pytest.txt](evidence/day4/baseline-pytest.txt)。保留 Day 1–3 源码历史、交付与原运行证据，没有覆盖旧成果或自动提交/推送。

### 日期、模式、样本数和最终结果

| 验证 | 模式/样本 | 通过 / 失败 | 证据 |
|---|---|---|---|
| 全量 pytest | 155 个程序回归项，含原 143 + 新 12 | 155 / 0 | evidence/day4/pytest.txt、pytest.xml、test-names.txt |
| 独立 eval A | Mock，42 条固定期望 JSONL | 42 / 0 | evidence/day4/mock-a/report.json、report.md |
| 独立 eval B | Mock，同 42 条 | 42 / 0 | evidence/day4/mock-b/report.json、report.md |
| 两批比较 | 同模式/数据集/fixture/judge | 0 回归、0 修复、42 未变 | evidence/day4/comparison.json |
| 真实浏览器 | 四个页面、批准 SQL 0→1、缺 Key、两批 eval 与比较 | PASS | evidence/day4/browser-summary.json、五张页面截图 |
| 新检出候选环境 | 新 venv、pip install、npm ci、pytest/build/CLI/eval/browser | PASS；pytest 155 / 0 | evidence/day4/clean-checkout/summary.json |
| 外部 Live 质量 | 未运行，0 个外部样本 | NOT_TESTED | **未进行真实模型质量评测** |
| Docker / 云端 Actions | Docker 不可用；未推送触发工作流 | NOT_TESTED | evidence/day4/docker-status.txt；工作流仅配置 |

42 是独立 EvalCase 数，不是 pytest 数；负向场景正确 FAILED/拒绝/超限也可以判 PASS，不能称真实模型任务成功率 100%。A/B 各执行完整 42 条，不相加虚称 84 条不同用例。浏览器和新检出重复验证也不计入独立 pytest 项数。

### 实际命令与原始摘要

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts --fix
.\.venv\Scripts\python.exe -m ruff format src tests scripts
.\.venv\Scripts\python.exe -u scripts/verify_day4.py
.\.venv\Scripts\python.exe -u scripts/verify_clean_checkout.py
```

统一脚本实际执行 Ruff check/format check、pytest -q --junitxml、两次独立 eval、compare、npm run build、pip check/freeze、真实 Playwright 和 curl；子进程移除 API Key。最终原始摘要：

```text
All checks passed!
32 files already formatted
155 passed in 77.14s (0:01:17)
```

独立评测实际命令（统一脚本传入临时隔离输出目录，保存 report.json/md）：

```powershell
python -m agentforge.evals run --output <临时目录>/mock-a
python -m agentforge.evals run --output <临时目录>/mock-b
python -m agentforge.evals compare docs/evidence/day4/mock-a/report.json docs/evidence/day4/mock-b/report.json --output docs/evidence/day4/comparison.json
npm.cmd --prefix apps/web run build
```

两次 runner stdout 都包含 `"mode":"mock", "total":42, "passed":42, "failed":0, "live_quality_evaluation":"NOT_RUN"`（原文件保留标准空格）。完整命令输出在 mock-a-stdout.txt、mock-b-stdout.txt、compare-stdout.txt 和 web-build.txt。
前端 tsc/Vite 构建退出 0；浏览器脚本实际输出：

```text
PASS: four-page Playwright, native SQL invariants, two Mock batches, comparison, missing Live key and curl.
```

### 实测指标、配置与限制

独立 A/B 均记录 **93 次实际工具尝试、6 次工具失败，错误率 6/93**。失败来自主动注入的 wall-time/工具超时/异常/非 JSON/NaN/超大结果，并都满足固定预期；不是线上自然错误率。每例有 wall_clock_seconds，批次 A/B duration_seconds 分别约 16.735/15.266 秒，仅为这两次观察，不构成 p50/p95、供应商速度或性能提升结论。

Mock model_tokens=null、cost=null，含合成 usage 的预算场景也如此；合成值另标 synthetic_mock_usage/synthetic_usage_tokens。Live 只有所有模型尝试均有真实响应 usage 才汇总 tokens；缺失仍 unknown，价格未配置不假设 $0。没有任何外部模型质量样本或成本数字。

报告记录每例实际 limits（默认 8 步/8 模型/16 工具/30 秒活动执行/10 秒模型超时/64000 预算代理，边界 case 各自覆盖）、judge=state_tools_side_effects_events_v1、automatic_retries=0、数据集/fixture/核心源码摘要。
dataset_sha256=`2dcab0ad937d6fa46cefeb3692437e6dbff3261db634d4e9f9e479c77d7c7c7d`；核心源码摘要覆盖 runtime/tools/storage/evals，安装版本见 environment.txt；新检出演练另记录候选文件摘要。

每例 SQLite 草案数来自实际查询。两个 injection case 均先由工具返回恶意结果，模型脚本收到 untrusted 数据后故意请求写入；一个被 allowlist 拒绝，一个仍等待人工审批，草案都为 0。不是“真实模型抗注入准确率”。

restart-approval 使用两个固定 Runtime worker 进程：第一个写等待点并退出，第二个核对原 ID/上下文再批准。原真实 Uvicorn 进程重启测试继续包含于 pytest。未知写结果/安全点等故障构造仍按 Day 3 边界说明，不扩大到任意位置恢复或任意外部副作用 exactly-once。

### 新增自动化测试名称

以下 12 项来自实际 JUnit；另强化原 test_reported_usage_over_budget_blocks_tool，检查合成 usage 不进入真实 tokens 字段。

```text
tests.test_eval_api::test_eval_api_executes_mock_suite_compares_and_survives_app_restart
tests.test_eval_api::test_interrupted_eval_is_reported_and_not_automatically_replayed
tests.test_eval_api::test_only_one_eval_job_is_allowed_and_shutdown_records_interruption
tests.test_evals::test_bundled_mock_dataset_executes_all_cases_and_records_evidence
tests.test_evals::test_wrong_expected_side_effect_is_reported_failed_not_skipped
tests.test_evals::test_dataset_rejects_duplicate_ids_and_unsupported_modes
tests.test_evals::test_compare_reports_rejects_mismatched_cases_and_tracks_regressions
tests.test_evals::test_cli_fails_when_a_case_has_wrong_expectations
tests.test_evals::test_malformed_tool_schema_is_rejected_before_handler_execution
tests.test_metrics::test_mock_usage_is_not_reported_as_real_tokens_or_free_cost
tests.test_metrics::test_live_usage_is_counted_only_when_all_model_attempts_have_usage
tests.test_metrics::test_metrics_count_actual_tool_failures_and_wall_clock_waiting
```

完整 155 项名称见 [test-names.txt](evidence/day4/test-names.txt)。42 条评测的每项 case_id/期望/实际值/checks 都保存在两份独立报告，不以 pytest 参数化数量替代。

### 中间失败与证据

| 文件（相对 docs） | 含义 |
|---|---|
| evidence/day4/initial-eval-failure.txt | runner 模块不存在时需求测试先实际失败 |
| evidence/day4/synthetic-usage-before-fix.txt | 旧 provider_reported 语义的实际失败；修复后全量通过 |
| evidence/day4/initial-browser-failure.txt | Playwright 精确/宽松 label 歧义的实际失败摘录与定位修复，非完整 stderr |
| evidence/day4/initial-clean-checkout-failure.txt | 首次新环境在浏览器错误输出捕获时遇 Windows GBK/UTF-8 解码问题；保留摘录后修复重演 |
| evidence/day4/ruff-check.txt / ruff-format.txt / pytest.txt / web-build.txt | 最终检查/测试/构建原始输出 |
| evidence/day4/mock-a/report.json / report.md、mock-b 同名文件 | 两次独立运行的完整机器/人工可读报告 |
| evidence/day4/comparison.json / browser-eval.json / browser-summary.json | CLI 对比和实际浏览器批次/断言 |
| evidence/day4/workbench.png / trace.png / approval.png / evals.png / comparison.png | 五张真实浏览器截图 |
| evidence/day4/curl-create.json / curl-query.json / openapi.json / health.json | 实际语言无关 HTTP 和生成规范 |
| evidence/day4/clean-checkout/ | 新检出安装/测试/构建/演示/eval/浏览器日志及候选源码摘要 |
| evidence/day4/environment.txt / pip-check.txt / docker-status.txt | 实际安装环境、依赖检查及 Docker 未测状态 |

### 当前仍未声称的能力

本机 clone 再覆盖未提交候选文件，验证新 venv/npm ci；不是公共 GitHub HEAD 已更新，也不是全新 OS，浏览器使用已安装 Edge/Chromium。
该环境最终 pytest 原始末行为 `155 passed in 113.32s (0:01:53)`；演练脚本末行为 `PASS: clean candidate checkout, new venv, npm ci, tests, build, eval and browser.`，见 clean-checkout/pytest.txt、browser.txt、summary.json。该次执行不增加独立测试用例数。
最终另用 Python 检查全部 22 份 Markdown 的本地链接（0 个失效）、Day 4 JSON/JUnit、两批逐项断言、注入草案数、合成 usage 标记和四个新 OpenAPI 路径；新检出演练的 50 个可执行源码/测试/脚本/前端/部署候选文件摘要均与交付源码一致。`git diff --check` 对源码与文档通过，原始失败输出的空白保持不动。
CI 已配置并在本机跑同类门槛，云端 Actions 未触发；Compose/镜像/nginx 已提供，但 Docker 不可用，容器未测。单进程、文件报告、同步 SQLite、有限脱敏，不是生产平台。
未进行真实模型质量评测。SSE 仍属 P1，当前轮询满足本次核心流程。
完整文件清单、五个问答、API 及验收见 [Day 4 交付](deliveries/2026-10-19-day4.md)。

---



## 2026-10-18：Day 3 持久化、审批中断/恢复与 Trace

先实际运行原 Day 2 全量测试：**107 passed in 13.05s**，见 [baseline-pytest.txt](evidence/day3/baseline-pytest.txt)。
增加 SQLAlchemy==2.0.55 并安装，原接口目录随审批写工具/preset 扩展，API 测试改用隔离 SQLite。
最终 **143 项、143 通过、0 失败**，比基线增加 36 项：persistence 30、approval_api 4、真实 API 进程重启 1、Responses SQLite 续传 1。参数化实例各计一项，不将浏览器检查重复计入 pytest。

### 实际命令与原始摘要

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m ruff format src tests scripts
.\.venv\Scripts\python.exe -u scripts/verify_day3.py
.\.venv\Scripts\python.exe -m pip check
```

统一脚本实际依次执行 Ruff check/format check、pytest -q --junitxml、npm run build、启动真实 API/Web、浏览器等待/重启/批准/拒绝/失败路径、SQL 查询和 curl。仅使用本机临时端口/临时 SQLite，清理自己的进程；移除验证子进程的 API_KEY 环境变量。不访问外部模型服务，依赖安装需包仓库或缓存。

最终保存的原始摘要：

```text
All checks passed!
24 files already formatted
143 passed in 36.79s
```

前端 tsc --noEmit 与 vite build 成功；统一脚本 summary.status=PASS。实际 pip check 输出：

```text
No broken requirements found.
```

上面的秒数是本次测试命令摘要，不是平台吞吐/p50/p95。没有真实成本或 Live 质量数字。

交付文档完成后，另用 Python 校验全部 18 份 Markdown 的本地链接、Day 3 JSON/JUnit 和四个新增 OpenAPI 路径，实际输出为：

```text
Markdown links: 18 files checked, 0 broken
Day 3 evidence: valid JSON; JUnit 143 passed / 0 failed / 0 errors; 4 new OpenAPI endpoints verified
```

`git -c core.safecrlf=false diff --check` 退出 0；`git ls-files -- '*.db' '*.db-wal' '*.db-shm' '.env'` 没有输出。三张截图均实际打开检查。

### 真实数据库与进程证据

实际浏览器演示的 Run 为 `02799461-d6d8-4efa-b029-301d967cbbd1`，approval 为 `bd86e59c-0bdd-40e3-9660-b7ad76e3c7f3`。这些是本次运行生成的 ID，重跑会变化。

| 检查点 | purchase_drafts 行数 | 其他断言 |
|---|---:|---|
| 等待审批 | 0 | 1 approval、8 invocation，其中 7 个已完成读工具/1 个 pending 写调用 |
| 真实终止并重启 API 进程 | 0 | 同一 run_id/approval_id/参数；私有 model_resume_state 摘要完全相同 |
| UI 批准后 | 1 | COMPLETED；5 次模型、8 次工具，工具结果进入后续上下文 |
| 12 次并发重复批准后 | 1 | replayed=true；步骤/事件数无第二次写入增长 |
| 独立 Run 拒绝后 | 0 | CANCELLED / APPROVAL_REJECTED |
| 完成后 POST resume | 1 | HTTP 409，不能恢复到 RUNNING |

另外 pytest 的真实 HTTP 重启测试让 **首次批准本身**受到 12 个请求并发竞争，只有一个 replayed=false，草案仍为 1；原生 Storage 线程并发也有同样断言。浏览器脚本的 12 次请求是批准后的并发重放，二者不要混淆。

事务失败测试实际在 INSERT/flush 后注入异常，回滚后审批仍待审、草案为 0。未知写结果/AFTER_APPROVED_TOOL 测试构造精确的数据库故障状态后重开 Storage，不冒充在任意执行指令处强杀。真实进程重启验收范围是 WAITING_APPROVAL。

### 本次自动化测试名称（来自实际 JUnit）

以下是新增 36 项的完整实际名称；包括参数化状态迁移实例。全量 143 项见 [test-names.txt](evidence/day3/test-names.txt)，机器记录见 [pytest.xml](evidence/day3/pytest.xml)。

<details>
<summary>展开 Day 3 测试名称</summary>

```text
tests.test_approval_api::test_api_rejects_bound_parameter_override_and_cross_run_approval
tests.test_approval_api::test_api_rejection_is_audited_and_never_writes
tests.test_approval_api::test_api_approve_continues_same_context_and_audits_exact_call
tests.test_approval_api::test_budget_failure_is_persisted_with_zero_drafts
tests.test_openai_adapter::test_encrypted_continuation_survives_sqlite_approval_checkpoint
tests.test_persistence::test_unapproved_write_is_persisted_pending_with_zero_drafts
tests.test_persistence::test_rejection_never_creates_draft
tests.test_persistence::test_sequential_and_concurrent_approve_create_only_one_draft
tests.test_persistence::test_conflicting_decision_is_rejected
tests.test_persistence::test_waiting_checkpoint_survives_new_storage_instance_and_completes
tests.test_persistence::test_pending_parameter_tampering_never_writes
tests.test_persistence::test_write_and_decision_roll_back_together
tests.test_persistence::test_unknown_write_outcome_requires_reconciliation_without_replay
tests.test_persistence::test_confirmed_local_write_checkpoint_can_resume_without_repeating_write
tests.test_persistence::test_terminal_run_is_never_resumed
tests.test_persistence::test_draft_has_real_database_uniqueness_constraints
tests.test_persistence::test_allowed_state_transitions[CREATED-RUNNING]
tests.test_persistence::test_allowed_state_transitions[RUNNING-WAITING_APPROVAL]
tests.test_persistence::test_allowed_state_transitions[WAITING_APPROVAL-RUNNING]
tests.test_persistence::test_allowed_state_transitions[WAITING_APPROVAL-CANCELLED]
tests.test_persistence::test_allowed_state_transitions[RUNNING-INTERRUPTED]
tests.test_persistence::test_allowed_state_transitions[RUNNING-RECONCILIATION_REQUIRED]
tests.test_persistence::test_allowed_state_transitions[INTERRUPTED-RUNNING]
tests.test_persistence::test_allowed_state_transitions[RECONCILIATION_REQUIRED-FAILED]
tests.test_persistence::test_forbidden_state_transitions[COMPLETED-RUNNING]
tests.test_persistence::test_forbidden_state_transitions[FAILED-RUNNING]
tests.test_persistence::test_forbidden_state_transitions[CANCELLED-RUNNING]
tests.test_persistence::test_forbidden_state_transitions[CREATED-COMPLETED]
tests.test_persistence::test_forbidden_state_transitions[WAITING_APPROVAL-COMPLETED]
tests.test_persistence::test_forbidden_state_transitions[RECONCILIATION_REQUIRED-RUNNING]
tests.test_persistence::test_corrupted_waiting_checkpoint_fails_closed_on_startup
tests.test_persistence::test_trace_redacts_secrets_and_pii_without_mangling_digest
tests.test_persistence::test_trace_tables_store_redacted_summaries_not_private_tool_data
tests.test_persistence::test_resume_cannot_replace_frozen_configuration
tests.test_persistence::test_newer_schema_is_rejected_without_dropping_data
tests.test_recovery_process::test_real_process_restart_restores_same_approval_context_and_one_draft
```

</details>

### 证据索引

| 路径（相对 docs） | 内容 |
|---|---|
| evidence/day3/pytest.txt / pytest.xml / test-names.txt | 最终原始输出、机器结果、实际测试名称 |
| evidence/day3/baseline-pytest.txt | 改实现前 107 项基线 |
| evidence/day3/initial-persistence-failure.txt | storage 未实现时四项需求先失败：4 failed in 1.22s |
| evidence/day3/checkpoint-redaction-failure.txt | 损坏 checkpoint 与摘要误脱敏的失败复现：2 failed, 26 passed in 9.37s |
| evidence/day3/ruff-check.txt / ruff-format.txt / web-build.txt | 静态检查、格式与前端构建输出 |
| evidence/day3/database-assertions.json | 真实 SQL 行数、相同私有上下文摘要、实际 ID |
| evidence/day3/waiting-approval.png / approved-trace.png / failure-trace.png | 实际浏览器截图，已查看核对 |
| evidence/day3/persisted-run.json / persisted-steps.json / persisted-events.json / persisted-approval.json | 实际 HTTP 脱敏持久化快照 |
| evidence/day3/curl-create.json / curl-query.json / curl-approval-replay.json | 真实 curl 创建/查询/决议幂等重放 |
| evidence/day3/openapi.json / health.json / environment.txt | 生成规范、SQLite/协议健康状态、实际安装版本 |
| evidence/day3/api-before-restart.log / api-after-restart.log / web.log / summary.json | 两个 API 进程与 Web 日志、断言结束后的摘要 |

初次浏览器验证遇到用户服务占用 5173；改用临时端口。随后 Windows 固定重启端口的预探测 bind 遇 TIME_WAIT；移除该预探测，由 Uvicorn 实际绑定，最终统一验证成功。没有停止已有用户服务，未伪造 SDK 返回。

### 恢复边界与剩余事项

能恢复：WAITING_APPROVAL；以及验证过草案/决议/结果凭据的 AFTER_APPROVED_TOOL。不能恢复：进行中的模型/读工具、任意指令位置、未知外部副作用。未知写结果进入 RECONCILIATION_REQUIRED 不重发；终态不可再次 RUNNING。

Live 外部 API **未测**。Responses SQLite 续传用明确合成 HTTP fixture 经官方 SDK 解析，不替代供应商在线验证。MCP 真实集成仍在全量测试中通过，兼容范围不扩大。

SSE 未做，采用轮询；Docker/CI、独立 JSONL Evals/两批比较仍未做。scripts/verify_day2.py 仅适配新 preset 数量与临时 DB，本次没有重跑它覆盖 Day 2 历史证据。Day 1/2 旧证据与 PRD 保留。
本次未提交/推送；候选人贡献与 Codex 编码角色分开表述。完整文件、API、五个问答与 P0 表见 [Day 3 交付](deliveries/2026-10-18-day3.md)。

---



## 2026-10-17：Day 2 模型接入、MCP、API、Workbench

执行前先运行 Day 1 `pytest -q`，原 70 项通过。SDK 安装要求升级 Pydantic 2.11.7→2.14.1；升级后再次对原两个测试文件单独回归，仍为 70 项通过。
锁定官方 mcp==2.3.0、mcp-types==2.3.0，实际 stdio protocol_version=2026-07-28。版本、API 差异与官方来源见 DECISIONS D008–D011。

实际命令包括：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
npm.cmd --prefix apps/web ci
.\.venv\Scripts\python.exe -m ruff check src tests scripts --fix
.\.venv\Scripts\python.exe -m ruff format src tests scripts
.\.venv\Scripts\python.exe scripts/verify_day2.py
.\.venv\Scripts\python.exe -m pip check
```

前端首次依赖通过 npm install --save-exact 安装并生成 package-lock；之后 README 使用 npm ci 复现。浏览器本次使用已安装 Edge 的 Playwright headless 模式。
统一验证脚本实际运行检查、原 Day 1 套件、全量 pytest、前端类型检查/构建；启动 API/Web 后用真实 curl 和浏览器验证，再结束自己启动的进程。

保存的最终原始摘要：

```text
All checks passed!
17 files already formatted
70 passed in 0.92s
107 passed in 12.97s
```

全量 107 项，107 通过、0 失败：原 70 项加 37 项新测试；原套件的再次运行不重复计入全量数量。
另外真实浏览器完成创建 Agent、Mock 两个本地工具、Mock 两个 MCP 工具和缺 Live Key 的错误路径，真实 curl 完成创建/查询/步骤。浏览器检查不计入 pytest 数量。
这些耗时只是本次命令摘要，不是平台 p50/p95 或真实模型延迟。没有真实成本/模型质量数据。

关键证据（相对 docs）：

| 路径 | 含义 |
|---|---|
| evidence/day2/pytest.txt | 全量测试原始 stdout |
| evidence/day2/day1-regression.txt | 升级后原 70 项回归 |
| evidence/day2/ruff-check.txt / ruff-format.txt | 标准检查输出 |
| evidence/day2/web-build.txt | TypeScript 与 Vite 构建原始输出 |
| evidence/day2/health.json / environment.txt | 实际协议、版本与安装环境 |
| evidence/day2/openapi.json | 实际生成规范 |
| evidence/day2/curl-create.json / curl-run.json / curl-steps.json | 真实 curl 的创建、完成状态与两工具步骤 |
| evidence/day2/workbench.png / workbench-mcp.png | 从实际运行界面保存的截图 |
| evidence/day2/summary.json | 断言全部完成后由验证脚本生成的摘要 |
| evidence/day2/initial-mcp-failure.txt | 真 stdio 的初始失败复现，structured_content 处理修复前 |

Live：适配器已实现，外部 API **未测**；本次 OPENAI_API_KEY/OPENAI_MODEL 均未配置。HTTP fixture 经官方 SDK 解析仅证明协议处理，不证明供应商在线可用性或模型质量。
MCP：真实 SDK 客户端—服务端已调用，通过发现、参数、超时和断连测试；兼容声明限于当前工具/stdio 子集。
目前数据仍在内存，没有审批、持久化、重启恢复、幂等写入或 JSONL Evals。Docker 采用任务允许的两条开发命令替代，留待 Day 4。
完整文件清单、五个面试问答和验收见 deliveries/2026-10-17-day2.md。

---

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
