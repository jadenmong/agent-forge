import { useEffect, useState } from 'react';
import { api } from './api';

type Metrics = { tool_calls?: number; tool_errors?: number; tool_error_rate?: number | null; wall_clock_seconds?: number | null; model_tokens?: number | null; cost?: number | null };
type CaseResult = { case_id: string; scenario: string; passed: boolean; run_id: string | null; source?: string; tags?: string[]; checks: Record<string, boolean>; actual: { state: string; stop_reason: string; tools?: string[] }; metrics: Metrics; trace?: unknown };
type Report = { eval_id: string; status: string; mode: string; summary: { total: number; passed: number; failed: number } | null; dataset_sha256: string | null; duration_seconds: number | null; metrics: Metrics; results: CaseResult[]; error: string | null; config: Record<string, unknown> };
type Comparison = { baseline_id: string; candidate_id: string; regressions: string[]; improvements: string[]; unchanged: number; latency_note: string };
const number = (value: number | null | undefined) => value == null ? 'unknown' : value.toFixed(3);

export function Evals() {
  const [reports, setReports] = useState<Report[]>([]);
  const [selected, setSelected] = useState<Report | null>(null);
  const [baseline, setBaseline] = useState('');
  const [candidate, setCandidate] = useState('');
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [failedOnly, setFailedOnly] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const items = await api<Report[]>('/api/evals');
    setReports(items);
    return items;
  }
  async function inspect(id: string) { setSelected(await api<Report>(`/api/evals/${id}`)); }
  useEffect(() => { refresh().then(items => { if (items[0]) void inspect(items[0].eval_id).catch(e => setError(String(e.message))); }).catch(e => setError(String(e.message))); }, []);
  useEffect(() => {
    if (selected?.status !== 'RUNNING') return;
    let stopped = false;
    const timer = window.setTimeout(() => {
      api<Report>(`/api/evals/${selected.eval_id}`).then(report => {
        if (!stopped) { setSelected(report); if (report.status !== 'RUNNING') void refresh().catch(e => setError(String(e.message))); }
      }).catch(e => { if (!stopped) setError(String(e.message)); });
    }, 600);
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [selected]);

  async function start() {
    setBusy(true); setError(''); setComparison(null);
    try { const created = await api<Report>('/api/evals/run', { mode: 'mock' }); setSelected(created); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : '评测启动失败'); }
    finally { setBusy(false); }
  }
  async function compare() {
    setError(''); setBusy(true);
    try { setComparison(await api<Comparison>(`/api/evals/compare?baseline_id=${encodeURIComponent(baseline)}&candidate_id=${encodeURIComponent(candidate)}`)); }
    catch (e) { setError(e instanceof Error ? e.message : '无法比较这些批次'); }
    finally { setBusy(false); }
  }
  const completed = reports.filter(report => report.status === 'COMPLETED');
  return <section className="panel" data-page="evals">
    <h2>Evals · 确定性回归</h2><p className="notice">Mock 检查状态、协议和工具政策正确性，包含预期失败场景；通过率不是模型任务成功率。未进行真实模型质量评测。</p>
    {error && <p role="alert" className="error">{error}</p>}
    <div className="actions"><button type="button" onClick={() => void start()} disabled={busy || reports.some(report => report.status === 'RUNNING')}>运行 Mock 评测</button><button type="button" className="secondary" onClick={() => void refresh().catch(e => setError(String(e.message)))}>刷新评测</button></div>
    <label>评测批次<select value={selected?.eval_id ?? ''} onChange={e => { if (e.target.value) void inspect(e.target.value).catch(e => setError(String(e.message))); }}><option value="">选择已有批次</option>{reports.map(report => <option key={report.eval_id} value={report.eval_id}>{report.status} · {report.eval_id}</option>)}</select></label>
    {selected && <>
      <div className="runhead"><span className="badge">Mock</span><strong data-testid="eval-status">{selected.status}</strong></div><p className="mono">Eval {selected.eval_id}<br/>Dataset {selected.dataset_sha256 ?? '执行后记录'}</p>
      {selected.error && <p className="error">{selected.error}；中断批次不会自动重放，可重新发起。</p>}
      {selected.summary && <div data-testid="eval-summary"><p>样本 {selected.summary.total} · 通过 {selected.summary.passed} · 失败 {selected.summary.failed}</p><p>工具调用 {selected.metrics.tool_calls} · 工具错误 {selected.metrics.tool_errors} · 错误率 {number(selected.metrics.tool_error_rate)} · 批次耗时 {number(selected.duration_seconds)} s</p><p className="muted">模型 tokens：{selected.metrics.model_tokens ?? 'unknown'} · 成本：{selected.metrics.cost ?? 'unknown'}。错误率包含主动注入故障，wall-clock 包含本地执行／审批恢复，不能作供应商性能结论。</p></div>}
      <details><summary>本次评测配置</summary><pre>{JSON.stringify(selected.config, null, 2)}</pre></details>
      <label className="check"><input type="checkbox" checked={failedOnly} onChange={e => setFailedOnly(e.target.checked)}/>只看失败用例</label>
      <div className="tablewrap"><table><thead><tr><th>Case / 判定依据</th><th>结论</th><th>实际状态 / 原因</th><th>工具 / 错误率 / wall-clock</th></tr></thead><tbody>{selected.results.filter(result => !failedOnly || !result.passed).map(result => <tr key={result.case_id} data-testid="eval-case"><td><strong>{result.case_id}</strong><small>{result.tags?.join(' · ')}</small><details className="step-details"><summary>断言与 Trace</summary><p>{result.source}</p><p className="mono">Run {result.run_id ?? '执行异常，无可用 Run'}</p><pre>{JSON.stringify({ checks: result.checks, actual: result.actual, trace: result.trace }, null, 2)}</pre></details></td><td className={result.passed ? '' : 'error-text'}>{result.passed ? 'PASS' : 'FAIL'}</td><td>{result.actual.state}<small>{result.actual.stop_reason}</small></td><td>{result.metrics.tool_calls ?? 'unknown'} / {number(result.metrics.tool_error_rate)} / {number(result.metrics.wall_clock_seconds)} s</td></tr>)}</tbody></table></div>
    </>}
    <section className="comparison"><h3>比较两次回归</h3><p className="muted">仅比较同模式、同数据集、同 fixture 和同判定版本；耗时差异不作为性能改进结论。</p>
      <div className="numbers"><label>基线批次<select value={baseline} onChange={e => setBaseline(e.target.value)}><option value="">选择基线</option>{completed.map(report => <option key={report.eval_id} value={report.eval_id}>{report.eval_id}</option>)}</select></label><label>候选批次<select value={candidate} onChange={e => setCandidate(e.target.value)}><option value="">选择候选</option>{completed.map(report => <option key={report.eval_id} value={report.eval_id}>{report.eval_id}</option>)}</select></label></div>
      <button type="button" disabled={busy || !baseline || !candidate} onClick={() => void compare()}>比较批次</button>
      {comparison && <div data-testid="eval-comparison"><p>回归 {comparison.regressions.length} · 修复 {comparison.improvements.length} · 未变 {comparison.unchanged}</p><pre>{JSON.stringify(comparison, null, 2)}</pre></div>}
    </section>
  </section>;
}
