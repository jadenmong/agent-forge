import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Tool = { name: string; description: string; source: string; permission: string };
type Agent = { id: string; name: string; allowed_tools: string[]; model_adapter: string };
type Run = { run_id: string; mode: string; status: string; stop_reason: string | null; output: string | null; model_call_count: number; tool_call_count: number; cost: number | null; token_accounting: string };
type Step = { seq: number; kind: string; status: string; tool_name: string | null; duration_ms: number | null; error_code: string | null };
type Health = { live_configured: boolean; mcp_sdk: string; mcp_protocol: string };

async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('API 尚未就绪，请确认本地服务正在运行。');
  const payload = await response.json();
  if (!response.ok) throw new Error(`${payload.error?.message ?? '请求失败'} (${payload.error?.code ?? response.status})`);
  return payload.data as T;
}

function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [agentId, setAgentId] = useState('procurement-demo');
  const [mode, setMode] = useState('mock');
  const [task, setTask] = useState('比较 A/B/C 供应商报价、交期和保修。仅查询模拟数据。');
  const [scenario, setScenario] = useState('two-tools');
  const [run, setRun] = useState<Run | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
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

  useEffect(() => {
    Promise.all([api<Agent[]>('/api/agents'), api<Tool[]>('/api/tools'), api<Health>('/health')])
      .then(([a, t, h]) => { setAgents(a); setTools(t); setHealth(h); setAllowed(t.filter(x => x.source === 'local').map(x => x.name)); })
      .catch(e => setError(String(e.message)));
  }, []);

  useEffect(() => {
    if (!run || !['CREATED', 'RUNNING'].includes(run.status)) return;
    let stopped = false;
    const timer = window.setTimeout(() => {
      Promise.all([api<Run>(`/api/runs/${run.run_id}`), api<Step[]>(`/api/runs/${run.run_id}/steps`)])
        .then(([r, s]) => { if (!stopped) { setRun(r); setSteps(s); } })
        .catch(e => { if (!stopped) setError(String(e.message)); });
    }, 400);
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [run]);

  async function start(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setSteps([]); setRun(null);
    try {
      const created = await api<Run>('/api/runs', { agent_id: agentId, input: task, mode, mock_scenario: scenario });
      const [current, currentSteps] = await Promise.all([api<Run>(`/api/runs/${created.run_id}`), api<Step[]>(`/api/runs/${created.run_id}/steps`)]);
      setRun(current); setSteps(currentSteps);
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
    <p className="notice">Mock 使用确定性演示脚本，任务文本不决定工具选择。Live 使用服务端配置的模型；两种模式均受相同工具策略约束。</p>
    {error && <div role="alert" className="error">{error}{run && <button type="button" onClick={() => { setError(''); api<Run>(`/api/runs/${run.run_id}`).then(setRun).catch(e => setError(String(e.message))); }}>重试查询</button>}</div>}
    <div className="layout"><section className="panel"><h2>运行任务</h2>
      <form onSubmit={start}>
        <label>选择 Agent<select value={agentId} onChange={e => { setAgentId(e.target.value); setScenario(e.target.value === 'mcp-demo' ? 'mcp' : 'two-tools'); }}>{agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
        <label>模型模式<select value={mode} onChange={e => setMode(e.target.value)}><option value="mock">Mock · 无 Key</option><option value="live">Live · OpenAI Responses</option></select></label>
        {mode === 'mock' && <label>演示场景<select value={scenario} onChange={e => setScenario(e.target.value)}><option value="two-tools">本地工具 · 串行两步</option><option value="procurement">本地工具 · 完整比较</option><option value="mcp">MCP · 两个只读工具</option></select></label>}
        {mode === 'live' && <p className="notice">{health?.live_configured ? '服务端已配置 Live 凭据。' : '服务端尚未配置 OPENAI_API_KEY 和 OPENAI_MODEL；启动时会显示配置错误。'}</p>}
        <label>任务<textarea value={task} onChange={e => setTask(e.target.value)} required maxLength={16000} rows={4}/></label>
        <button disabled={running || !agents.length || !task.trim()}>{running ? '执行中…' : '启动 Run'}</button>
      </form>
      <details><summary>创建 Agent</summary><form onSubmit={createAgent}>
        <label>Agent 名称<input value={name} onChange={e => setName(e.target.value)} required maxLength={128}/></label>
        <label>系统提示词<textarea value={prompt} onChange={e => setPrompt(e.target.value)} maxLength={16000}/></label>
        <div className="numbers"><label>最大步数<input type="number" min="1" max="100" value={maxSteps} onChange={e => setMaxSteps(Number(e.target.value))}/></label><label>最大模型调用数<input type="number" min="1" max="100" value={maxModelCalls} onChange={e => setMaxModelCalls(Number(e.target.value))}/></label><label>最大工具调用数<input type="number" min="0" max="200" value={maxToolCalls} onChange={e => setMaxToolCalls(Number(e.target.value))}/></label><label>整个 Run 上限（秒）<input type="number" min="1" max="300" value={wallSeconds} onChange={e => setWallSeconds(Number(e.target.value))}/></label><label>模型超时（秒）<input type="number" min="1" max="300" value={timeout} onChange={e => setTimeoutSeconds(Number(e.target.value))}/></label><label>Token 预算<input type="number" min="1" max="1000000" value={budget} onChange={e => setBudget(Number(e.target.value))}/></label></div>
        <fieldset><legend>允许使用的工具</legend>{tools.map(t => <label className="check" key={t.name}><input type="checkbox" checked={allowed.includes(t.name)} onChange={e => setAllowed(e.target.checked ? [...allowed, t.name] : allowed.filter(n => n !== t.name))}/><span>{t.name}<small>{t.source} · {t.permission}</small></span></label>)}</fieldset>
        <button disabled={running || !name.trim()}>保存 Agent</button>
      </form></details>
    </section><section className="panel trace" aria-live="polite"><h2>运行与步骤</h2>
      {!run ? <p className="muted">启动任务后，查看真实执行步骤。</p> : <>
        <div className="runhead"><span className="badge">{run.mode === 'mock' ? 'Mock' : 'Live'}</span><strong data-testid="run-status">{run.status}</strong></div>
        <p className="mono">Run {run.run_id}</p><p>终止原因：{run.stop_reason ?? '执行中'} · 模型 {run.model_call_count} 次 · 工具 {run.tool_call_count} 次</p>
        <div className="tablewrap"><table><thead><tr><th>步骤</th><th>操作</th><th>状态</th><th>耗时</th></tr></thead><tbody>{steps.map(s => <tr key={s.seq} data-testid={s.kind === 'tool' ? 'tool-step' : 'model-step'}><td>{s.seq}</td><td>{s.tool_name ?? '模型响应'}{s.error_code && <small className="error-text">{s.error_code}</small>}</td><td>{s.status}</td><td>{s.duration_ms === null ? '—' : `${s.duration_ms.toFixed(1)} ms`}</td></tr>)}</tbody></table></div>
        {run.output && <><h3>结果</h3><pre>{run.output}</pre></>}
        <p className="muted">成本：{run.cost === null ? 'unknown' : run.cost} · Token 记账：{run.token_accounting}</p>
      </>}
    </section></div>
    <footer>状态保存在当前服务进程内，重启后清空。MCP SDK {health?.mcp_sdk ?? '…'} / {health?.mcp_protocol ?? '…'}。API 文档：<a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">OpenAPI</a></footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<App/>);
