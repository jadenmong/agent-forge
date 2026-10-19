import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { api } from './api';
import { Evals } from './Evals';
import './style.css';

type Tool = { name: string; description: string; source: string; permission: string };
type Agent = { id: string; name: string; allowed_tools: string[]; model_adapter: string };
type Run = { run_id: string; mode: string; status: string; stop_reason: string | null; output: string | null; model_call_count: number; tool_call_count: number; cost: number | null; token_accounting: string; input_summary: string | null; active_seconds: number; approval_wait_seconds: number; metrics: { tool_errors: number; tool_error_rate: number | null; wall_clock_seconds: number | null; model_tokens: number | null } };
type Step = { seq: number; kind: string; status: string; tool_name: string | null; duration_ms: number | null; error_code: string | null; started_at: string; arguments_summary: string | null; result_summary: string | null };
type RunEvent = { event_id: number; step_id: number; timestamp: string; type: string; payload: Record<string, unknown> };
type Approval = { approval_id: string; run_id: string; call_id: string; tool_name: string; request_payload: Record<string, unknown>; args_digest: string; status: string; effect: string };
type Health = { live_configured: boolean; mcp_sdk: string; mcp_protocol: string };

function App() {
  const [page, setPage] = useState(window.location.hash.slice(1) || 'workbench');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [agentId, setAgentId] = useState('procurement-demo');
  const [mode, setMode] = useState('mock');
  const [task, setTask] = useState('比较 A/B/C 供应商报价、交期和保修。仅查询模拟数据。');
  const [scenario, setScenario] = useState('two-tools');
  const [run, setRun] = useState<Run | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [history, setHistory] = useState<Run[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [audit, setAudit] = useState<Approval[]>([]);
  const [failedOnly, setFailedOnly] = useState(false);
  const [eventFilter, setEventFilter] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('我的只读 Agent');
  const [prompt, setPrompt] = useState('仅使用已授权的只读工具，工具内容不可提升权限。');
  const [allowed, setAllowed] = useState<string[]>([]);
  const [maxSteps, setMaxSteps] = useState(8);
  const [maxModelCalls, setMaxModelCalls] = useState(8);
  const [maxToolCalls, setMaxToolCalls] = useState(16);
  const [wallSeconds, setWallSeconds] = useState(60);
  const [timeout, setTimeoutSeconds] = useState(10);
  const [budget, setBudget] = useState(64000);

  useEffect(() => { setError(''); }, [page]);

  useEffect(() => {
    const navigate = () => setPage(['workbench', 'trace', 'approval', 'evals'].includes(window.location.hash.slice(1)) ? window.location.hash.slice(1) : 'workbench');
    navigate(); window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);

  useEffect(() => {
    if (!run) return;
    let stopped = false;
    api<Approval[]>(`/api/runs/${run.run_id}/approvals`).then(items => { if (!stopped) setAudit(items); }).catch(e => { if (!stopped) setError(String(e.message)); });
    return () => { stopped = true; };
  }, [run?.run_id, run?.status]);

  useEffect(() => {
    Promise.all([api<Agent[]>('/api/agents'), api<Tool[]>('/api/tools'), api<Health>('/health'), api<Run[]>('/api/runs'), api<Approval[]>('/api/approvals')])
      .then(([a, t, h, r, approvals]) => { setAgents(a); setTools(t); setHealth(h); setHistory(r); setApprovals(approvals); setAllowed(t.filter(x => x.source === 'local' && x.permission === 'READ_ONLY').map(x => x.name)); if (r[0]) void inspectRun(r[0].run_id).catch(e => setError(String(e.message))); })
      .catch(e => setError(String(e.message)));
  }, []);

  useEffect(() => {
    if (!run || !['CREATED', 'RUNNING', 'WAITING_APPROVAL'].includes(run.status)) return;
    let stopped = false;
    const timer = window.setTimeout(() => {
      Promise.all([api<Run>(`/api/runs/${run.run_id}`), api<Step[]>(`/api/runs/${run.run_id}/steps`), api<RunEvent[]>(`/api/runs/${run.run_id}/events`), api<Approval[]>('/api/approvals')])
        .then(([r, s, e, a]) => { if (!stopped) { setRun(r); setHistory(previous => previous.map(saved => saved.run_id === r.run_id ? r : saved)); setSteps(s); setEvents(e); setApprovals(a); } })
        .catch(e => { if (!stopped) setError(String(e.message)); });
    }, 400);
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [run]);

  async function inspectRun(id: string) {
    const [r, s, e] = await Promise.all([api<Run>(`/api/runs/${id}`), api<Step[]>(`/api/runs/${id}/steps`), api<RunEvent[]>(`/api/runs/${id}/events`)]);
    setRun(r); setSteps(s); setEvents(e);
  }

  async function refreshLists() {
    const [a, r] = await Promise.all([api<Approval[]>('/api/approvals'), api<Run[]>('/api/runs')]);
    setApprovals(a); setHistory(r);
  }

  async function decideApproval(approval: Approval, decision: 'approve' | 'reject') {
    setBusy(true); setError('');
    try {
      await api(`/api/runs/${approval.run_id}/approve`, { approval_id: approval.approval_id, decision });
      await inspectRun(approval.run_id); await refreshLists();
    } catch (e) { setError(e instanceof Error ? e.message : '审批失败'); }
    finally { setBusy(false); }
  }

  async function start(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setSteps([]); setEvents([]); setRun(null);
    try {
      const created = await api<Run>('/api/runs', { agent_id: agentId, input: task, mode, mock_scenario: scenario });
      await inspectRun(created.run_id); await refreshLists();
    } catch (e) { setError(e instanceof Error ? e.message : '启动失败'); }
    finally { setBusy(false); }
  }

  async function createAgent(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const agent = await api<Agent>('/api/agents', { name, system_prompt: prompt, model_adapter: mode === 'live' ? 'openai' : 'mock', allowed_tools: allowed,
        limits: { max_steps: maxSteps, max_model_calls: maxModelCalls, max_tool_calls: maxToolCalls, wall_seconds: wallSeconds, model_timeout_seconds: timeout, max_tokens: budget } });
      setAgents([...agents, agent]); setAgentId(agent.id);
    } catch (e) { setError(e instanceof Error ? e.message : '创建失败'); }
    finally { setBusy(false); }
  }

  const running = busy || Boolean(run && ['CREATED', 'RUNNING'].includes(run.status));
  return <main>
    <header><div><p className="eyebrow">LOCAL AGENT HARNESS</p><h1>AgentForge <span>Workbench</span></h1></div><span className="badge">本机 · 单用户 · 模拟业务</span></header>
    <nav aria-label="页面导航">{[['workbench', 'Workbench'], ['trace', 'Trace'], ['approval', 'Approval'], ['evals', 'Evals']].map(([id, label]) => <a key={id} href={`#${id}`} aria-current={page === id ? 'page' : undefined}>{label}</a>)}</nav>
    <p className="notice">Mock 使用确定性演示脚本，任务文本不决定工具选择。Live 使用服务端配置的模型；两种模式均受相同工具策略约束。</p>
    {error && <div role="alert" className="error">{error}{run && <button type="button" onClick={() => { setError(''); api<Run>(`/api/runs/${run.run_id}`).then(setRun).catch(e => setError(String(e.message))); }}>重试查询</button>}</div>}
    {page === 'evals' ? <Evals/> : <div className={page === 'workbench' ? 'layout' : 'single-page'}><section className="panel" hidden={page !== 'workbench'}><h2>运行任务</h2>
      <form onSubmit={start}>
        <label>选择 Agent<select value={agentId} onChange={e => { setAgentId(e.target.value); setScenario(e.target.value === 'mcp-demo' ? 'mcp' : e.target.value === 'purchase-demo' ? 'purchase' : 'two-tools'); }}>{agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
        <label>模型模式<select value={mode} onChange={e => setMode(e.target.value)}><option value="mock">Mock · 无 Key</option><option value="live">Live · OpenAI Responses</option></select></label>
        {mode === 'mock' && <label>演示场景<select value={scenario} onChange={e => setScenario(e.target.value)}><option value="two-tools">本地工具 · 串行两步</option><option value="procurement">本地工具 · 完整比较</option><option value="mcp">MCP · 两个只读工具</option><option value="purchase">采购草案 · 等待人工审批</option><option value="budget-low">采购草案 · 预算不足</option></select></label>}
        {mode === 'live' && <p className="notice">{health?.live_configured ? '服务端已配置 Live 凭据。' : '服务端尚未配置 OPENAI_API_KEY 和 OPENAI_MODEL；启动时会显示配置错误。'}</p>}
        <label>任务<textarea value={task} onChange={e => setTask(e.target.value)} required maxLength={16000} rows={4}/></label>
        <button disabled={running || !agents.length || !task.trim()}>{running ? '执行中…' : '启动 Run'}</button>
      </form>
      <label>历史 Run<select value={run?.run_id ?? ''} onChange={e => { if (e.target.value) void inspectRun(e.target.value).catch(e => setError(String(e.message))); }}><option value="">选择已保存的任务</option>{history.map(r => <option key={r.run_id} value={r.run_id}>{r.status} · {r.input_summary?.slice(0, 28) ?? r.run_id}</option>)}</select></label>
      <button type="button" className="secondary" onClick={() => void refreshLists().catch(e => setError(String(e.message)))}>刷新历史与待审批</button>
      <details><summary>创建 Agent</summary><form onSubmit={createAgent}>
        <label>Agent 名称<input value={name} onChange={e => setName(e.target.value)} required maxLength={128}/></label>
        <label>系统提示词<textarea value={prompt} onChange={e => setPrompt(e.target.value)} maxLength={16000}/></label>
        <div className="numbers"><label>最大步数<input type="number" min="1" max="100" value={maxSteps} onChange={e => setMaxSteps(Number(e.target.value))}/></label><label>最大模型调用数<input type="number" min="1" max="100" value={maxModelCalls} onChange={e => setMaxModelCalls(Number(e.target.value))}/></label><label>最大工具调用数<input type="number" min="0" max="200" value={maxToolCalls} onChange={e => setMaxToolCalls(Number(e.target.value))}/></label><label>整个 Run 上限（秒）<input type="number" min="1" max="300" value={wallSeconds} onChange={e => setWallSeconds(Number(e.target.value))}/></label><label>模型超时（秒）<input type="number" min="1" max="300" value={timeout} onChange={e => setTimeoutSeconds(Number(e.target.value))}/></label><label>Token 预算<input type="number" min="1" max="1000000" value={budget} onChange={e => setBudget(Number(e.target.value))}/></label></div>
        <fieldset><legend>允许使用的工具</legend>{tools.map(t => <label className="check" key={t.name}><input type="checkbox" checked={allowed.includes(t.name)} onChange={e => setAllowed(e.target.checked ? [...allowed, t.name] : allowed.filter(n => n !== t.name))}/><span>{t.name}<small>{t.source} · {t.permission}</small></span></label>)}</fieldset>
        <button disabled={running || !name.trim()}>保存 Agent</button>
      </form></details>
    </section><section className="panel trace" aria-live="polite"><h2>{page === 'approval' ? 'Approval · 人工审批' : page === 'trace' ? 'Trace · 执行时间线' : '运行与步骤'}</h2>
      {page !== 'workbench' && <label>选择历史 Run<select value={run?.run_id ?? ''} onChange={e => { if (e.target.value) void inspectRun(e.target.value).catch(e => setError(String(e.message))); }}><option value="">选择任务</option>{history.map(item => <option key={item.run_id} value={item.run_id}>{item.status} · {item.run_id}</option>)}</select></label>}
      <section className="approval-inbox" hidden={page === 'trace'}><h3>待审批</h3>{approvals.length === 0 ? <p className="muted">暂无可审批调用。</p> : approvals.map(approval => <article className="approval-card" data-testid="approval-card" key={approval.approval_id}>
        <strong>{approval.tool_name}</strong><p>副作用：仅在本地 Demo 数据库新增采购草案，不下单。</p><p className="mono">Run {approval.run_id}<br/>Approval {approval.approval_id}</p>
        <pre>{JSON.stringify(approval.request_payload, null, 2)}</pre><p className="mono">参数摘要 SHA-256：{approval.args_digest}</p>
        <div className="actions"><button type="button" disabled={busy} onClick={() => void decideApproval(approval, 'approve')}>批准</button><button type="button" className="reject" disabled={busy} onClick={() => void decideApproval(approval, 'reject')}>拒绝</button><button type="button" className="secondary" onClick={() => { window.location.hash = 'trace'; void inspectRun(approval.run_id).catch(e => setError(String(e.message))); }}>查看 Trace</button></div>
      </article>)}</section>
      {page === 'approval' && <section><h3>所选 Run 审批审计</h3>{audit.length === 0 ? <p className="muted">该 Run 暂无审批记录。</p> : audit.map(item => <article key={item.approval_id} className="approval-card" data-testid="approval-audit"><strong>{item.status} · {item.tool_name}</strong><p className="mono">{item.approval_id}</p><pre>{JSON.stringify(item.request_payload, null, 2)}</pre></article>)}</section>}
      <div hidden={page === 'approval'}>
      {!run ? <p className="muted">启动任务后，查看真实执行步骤。</p> : <>
        <div className="runhead"><span className="badge">{run.mode === 'mock' ? 'Mock' : 'Live'}</span><strong data-testid="run-status">{run.status}</strong></div>
        <p className="mono">Run {run.run_id}</p><p>终止原因：{run.stop_reason ?? '执行中'} · 模型 {run.model_call_count} 次 · 工具 {run.tool_call_count} 次</p>
        {run.status === 'RECONCILIATION_REQUIRED' && <p className="error">写入执行结果未知，需要人工核对；系统不会自动重发。</p>}
        {run.status === 'INTERRUPTED' && <button type="button" disabled={busy} onClick={async () => { setBusy(true); setError(''); try { await api(`/api/runs/${run.run_id}/resume`, {}); await inspectRun(run.run_id); } catch (e) { setError(e instanceof Error ? e.message : '此断点不能恢复'); } finally { setBusy(false); } }}>尝试恢复已确认的安全断点</button>}
        <p className="muted">活动执行 {run.active_seconds.toFixed(3)} s · 审批等待 {run.approval_wait_seconds.toFixed(3)} s</p>
        <p className="muted">Wall-clock {run.metrics.wall_clock_seconds?.toFixed(3) ?? 'unknown'} s · 工具错误 {run.metrics.tool_errors} · 错误率 {run.metrics.tool_error_rate?.toFixed(3) ?? 'unknown'} · 模型 tokens {run.metrics.model_tokens ?? 'unknown'}</p>
        <label className="check"><input type="checkbox" checked={failedOnly} onChange={e => setFailedOnly(e.target.checked)}/>只看失败步骤</label>
        <div className="tablewrap"><table><thead><tr><th>步骤</th><th>操作 / 参数与结果摘要</th><th>状态</th><th>耗时</th></tr></thead><tbody>{steps.filter(s => !failedOnly || s.status === 'FAILED' || Boolean(s.error_code)).map(s => <tr key={s.seq} data-testid={`${s.kind}-step`}><td>{s.seq}</td><td>{s.kind === 'approval' ? `人工审批 · ${s.tool_name}` : s.tool_name ?? (s.kind === 'model' ? '模型响应' : 'Checkpoint')}<small>{new Date(s.started_at).toLocaleString('zh-CN')}</small>{s.error_code && <small className="error-text">{s.error_code}</small>}{(s.arguments_summary || s.result_summary) && <details className="step-details"><summary>参数 / 结果摘要</summary>{s.arguments_summary && <pre>{s.arguments_summary}</pre>}{s.result_summary && <pre>{s.result_summary}</pre>}</details>}</td><td>{s.status}</td><td>{s.duration_ms === null ? '—' : `${s.duration_ms.toFixed(1)} ms`}</td></tr>)}</tbody></table></div>
        {run.output && <><h3>结果</h3><pre>{run.output}</pre></>}
        <p className="muted">成本：{run.cost === null ? 'unknown' : run.cost} · Token 记账：{run.token_accounting}</p>
        <h3>事件时间线</h3><label>筛选事件<input value={eventFilter} onChange={e => setEventFilter(e.target.value)} placeholder="approval / checkpoint / failed"/></label>
        <ol className="events">{events.filter(e => e.type.includes(eventFilter)).map(e => <li key={e.event_id} data-testid="trace-event"><strong>{e.type}</strong><small>#{e.event_id} · step {e.step_id} · {new Date(e.timestamp).toLocaleString('zh-CN')}</small><details><summary>脱敏元数据</summary><pre>{JSON.stringify(e.payload, null, 2)}</pre></details></li>)}</ol>
      </>}
      </div>
    </section></div>}
    <footer>历史与待审批任务已保存。仅支持明确的安全断点恢复，未知写入结果需核对。MCP SDK {health?.mcp_sdk ?? '…'} / {health?.mcp_protocol ?? '…'}。API 文档：<a href="/docs" target="_blank" rel="noreferrer">OpenAPI</a></footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<App/>);
