import React, { useEffect, useState } from 'react';
import { advancedQuantApi, formatStrategyMetric } from '../../api/advancedQuant';
import type { ConformalPredictResponse, StrategyDiagnostics, StrategyEquity, StrategyWalkForward, StrategyWalkForwardRequest } from '../../api/advancedQuant';
import { useStrategyLab } from '../../hooks/useStrategyLab';
import { useUiStore } from '../../store/uiStore';
import { VarianceExplorer } from './VarianceExplorer';

const panelClass = 'min-w-0 rounded-xl border border-white/10 bg-zinc-900 p-4 text-zinc-100';
const inputClass = 'min-h-11 w-full min-w-0 rounded border border-white/20 bg-zinc-950 px-2 text-sm text-zinc-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400';
const buttonClass = 'min-h-11 rounded border border-white/20 px-3 text-sm text-zinc-100 hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400 disabled:opacity-50';
const cellClass = 'p-2 text-right tabular-nums';
const metric = (v: unknown) => formatStrategyMetric(v);

export function WalkForwardHeatmap({ data }: { data: StrategyWalkForward | null }) {
  const [hover, setHover] = useState<string | null>(null);
  const shade = (v: number | null) => v === null || v === 0 ? '#27272a' : v < 0 ? `rgba(217,119,6,${.15 + Math.min(Math.abs(v) / 3, 1) * .65})` : `rgba(59,130,246,${.15 + Math.min(v / 3, 1) * .65})`;
  return <section className={panelClass} aria-label="Walk-forward heatmap">
    <h2 className="text-base font-semibold">WalkForwardHeatmap</h2>
    {!data ? <p className="mt-2 text-sm text-zinc-300">No evaluation yet. Run the calculation explicitly.</p> : <>
      <p className="mt-2 break-words text-sm text-zinc-300">{data.evaluation_method} · {data.coverage_policy} · fixed equal-weight daily rebalance</p>
      <p className="text-sm text-zinc-300">{data.historical_timing_validated ? 'Timing validated; lineage not authenticated.' : 'Retrospective CPCV; not historical deployment.'}</p>
      <p className="mt-2 text-sm">Sharpe scale: −3 (amber) · 0 (neutral) · +3 (blue); values outside scale saturate.</p>
      <div className="mt-3 overflow-x-auto" tabIndex={0} aria-label="Fold results table">
        <table className="w-full text-sm"><caption className="sr-only">Fold windows, annualized Sharpe, net returns and maximum drawdown</caption>
          <thead><tr>{['Fold / OOS window', 'IS Sharpe', 'OOS Sharpe', 'Net OOS %', 'Gross OOS %', 'Max drawdown %'].map((h) => <th key={h} scope="col" className={cellClass}>{h}</th>)}</tr></thead>
          <tbody>{data.folds.map((f) => <tr key={f.fold} className="border-t border-white/10">
            <th scope="row" className="p-2 text-left font-normal">#{f.fold + 1}<br />{f.test_start.slice(0, 10)} – {f.test_end.slice(0, 10)}</th>
            {(['in_sample_sharpe', 'out_of_sample_sharpe'] as const).map((k) => {
              const label = `Fold ${f.fold + 1} ${k === 'in_sample_sharpe' ? 'IS' : 'OOS'} Sharpe ${metric(f[k])}`;
              return <td key={k} className={cellClass} style={{ backgroundColor: shade(f[k]) }}><button className="min-h-11 min-w-11 rounded px-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white" aria-label={label} onMouseEnter={() => setHover(label)} onFocus={() => setHover(label)} onMouseLeave={() => setHover(null)} onBlur={() => setHover(null)}>{metric(f[k])}</button></td>;
            })}
            <td className={cellClass}>{metric(f.out_of_sample_return_pct)}</td><td className={cellClass}>{metric(f.gross_oos_return_pct)}</td><td className={cellClass}>{metric(f.max_drawdown_pct)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <p role="status" className="mt-2 min-h-6 text-sm">{hover ?? `Mean OOS Sharpe ${metric(data.mean_oos_sharpe)} · net OOS ${metric(data.oos_return_pct)}%`}</p>
      <p className="break-words text-sm text-zinc-300">{data.metric_unavailable_reason}</p>
    </>}
  </section>;
}

export function DeflatedSharpeGauge({ data }: { data: StrategyDiagnostics | null }) {
  const value = data?.deflated_sharpe_ratio;
  return <section className={panelClass} aria-label="Deflated Sharpe gauge">
    <h2 className="text-base font-semibold">DeflatedSharpeGauge</h2>
    <p className="mt-2 text-3xl font-semibold">{value == null ? '--' : `${metric(value * 100)}%`}</p>
    {value != null && <meter aria-label="Deflated Sharpe confidence" className="mt-3 h-6 w-full" min={0} max={1} low={.95} high={.95} optimum={1} value={value}>{metric(value * 100)}%</meter>}
    <p className="mt-2 text-sm text-zinc-300">DSR probability; threshold ≥ 95%, not an annualized Sharpe ratio.</p>
    <p className="mt-2 break-words text-sm">{!data ? 'Diagnostics unavailable.' : value == null ? data.metric_unavailable_reason : value >= .95 ? 'Threshold met; not strategy approval.' : 'Below confidence threshold.'}</p>
    {data && <p className="mt-2 text-sm text-zinc-300">{data.diagnostic_basis === 'EMPIRICAL_INSTRUMENT_PROXY' ? 'Instrument proxy only; not strategy evidence.' : 'Persisted trials; content integrity only, not authenticated lineage.'}</p>}
  </section>;
}

export function OverfittingMetricsTable({ data }: { data: StrategyDiagnostics | null }) {
  return <section className={panelClass} aria-label="Overfitting metrics">
    <h2 className="text-base font-semibold">OverfittingMetricsTable</h2>
    {!data ? <p className="mt-2 text-sm text-zinc-300">Diagnostics unavailable; no zero-filled metrics.</p> : <>
      <p className="mt-2 break-words text-sm">{data.verdict} · {data.trials_tested} actual trials{data.requested_trials_tested === null ? '' : ` / ${data.requested_trials_tested} requested`}</p>
      <p className="mt-2 break-words text-sm text-zinc-300">{data.statistical_assumption}</p>
      <table className="mt-3 w-full text-sm"><caption className="sr-only">Overfitting diagnostic statistics</caption><thead><tr><th scope="col" className="p-2 text-left">Metric / unit</th><th scope="col" className={cellClass}>Value</th></tr></thead>
        <tbody>{[
          ['PBO probability', data.pbo], ['DSR probability', data.deflated_sharpe_ratio], ['PSR probability', data.probabilistic_sharpe_ratio],
          ['Observed Sharpe / per bar', data.observed_sharpe], ['Expected maximum Sharpe / per bar', data.expected_max_sharpe],
          ['Trial variance / per-bar Sharpe', data.variance_of_trials], ['Skewness', data.skewness], ['Kurtosis', data.kurtosis],
        ].map(([name, v]) => <tr key={String(name)} className="border-t border-white/10"><th scope="row" className="p-2 text-left font-normal">{name}</th><td className={cellClass}>{metric(v)}</td></tr>)}</tbody>
      </table>
      <details className="mt-3"><summary className="min-h-11 cursor-pointer text-sm">Trial distribution (annualized 252)</summary><table className="w-full text-sm"><thead><tr><th scope="col" className="p-2 text-left">Trial</th><th scope="col" className={cellClass}>Sharpe</th></tr></thead><tbody>{data.trial_distribution.map((t) => <tr key={t.trial_id}><th scope="row" className="p-2 text-left font-normal">{t.trial_id}</th><td className={cellClass}>{metric(t.sharpe)}</td></tr>)}</tbody></table></details>
      <p className="mt-2 text-sm text-zinc-300">FDR q-values: {data.fdr_q_values.length ? data.fdr_q_values.map((v) => metric(v)).join(', ') : 'Unavailable (no hypothesis correction supplied).'}</p>
    </>}
  </section>;
}

const equitySeries = [
  { key: 'net_equity', label: 'Net equity', color: '#3b82f6', dash: undefined },
  { key: 'gross_equity', label: 'Gross equity', color: '#d97706', dash: '7 3' },
  { key: 'benchmark_equity', label: 'Benchmark', color: '#ec4899', dash: '2 4' },
] as const;

export function CumulativeEquityCurve({ data }: { data: StrategyEquity | null }) {
  const [selected, setSelected] = useState(0);
  const rows = data?.equity_curve ?? [], index = Math.min(selected, Math.max(0, rows.length - 1)), point = rows[index];
  const values = rows.flatMap((p) => equitySeries.map((s) => p[s.key])), low = Math.min(...values), high = Math.max(...values);
  const span = high - low || Math.max(high * .01, 1), x = (i: number) => 60 + i / Math.max(rows.length - 1, 1) * 680;
  const y = (v: number) => 220 - (v - low) / span * 180;
  // ponytail: three bounded persisted series; no client synthesis of overlapping CPCV returns.
  return <section className={panelClass} aria-label="Cumulative equity curve">
    <h2 className="text-base font-semibold">CumulativeEquityCurve</h2>
    {!data ? <p className="mt-2 text-sm text-zinc-300">Persisted equity unavailable. CPCV fold means are not a cumulative series.</p> : <>
      <p className="mt-2 text-sm text-zinc-300">VND_FULL · persisted aggregate fees · {data.benchmark_id} benchmark · content integrity only</p>
      <div className="mt-3 flex flex-wrap gap-4 text-sm">{equitySeries.map((s) => <span key={s.key} className="flex items-center gap-2"><svg width="24" height="8" aria-hidden="true"><line x1="0" y1="4" x2="24" y2="4" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} /></svg>{s.label}</span>)}</div>
      <svg viewBox="0 0 800 260" role="img" aria-label="Gross, net and benchmark equity in VND on one shared axis" className="mt-3 w-full" onPointerMove={(e) => { const box = e.currentTarget.getBoundingClientRect(); if (box.width > 0) setSelected(Math.round(Math.max(0, Math.min(1, ((e.clientX - box.left) / box.width * 800 - 60) / 680)) * (rows.length - 1))); }}>
        {[0, .5, 1].map((fraction) => <g key={fraction}><line x1="60" x2="740" y1={220 - fraction * 180} y2={220 - fraction * 180} stroke="#3f3f46" /><text x="55" y={224 - fraction * 180} textAnchor="end" fill="#d4d4d8" fontSize="12">{((low + fraction * span) / 1e9).toFixed(2)}B</text></g>)}
        {equitySeries.map((s) => <polyline key={s.key} points={rows.map((p, i) => `${x(i)},${y(p[s.key])}`).join(' ')} fill="none" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} strokeLinejoin="round" strokeLinecap="round" />)}
        <line x1={x(index)} x2={x(index)} y1="40" y2="220" stroke="#a1a1aa" />
        {point && equitySeries.map((s) => <circle key={s.key} cx={x(index)} cy={y(point[s.key])} r="4" fill={s.color} stroke="#18181b" strokeWidth="2" />)}
        <text x="60" y="250" fill="#d4d4d8" fontSize="12">{rows[0].date.slice(0, 10)}</text><text x="740" y="250" textAnchor="end" fill="#d4d4d8" fontSize="12">{rows.at(-1)!.date.slice(0, 10)}</text>
      </svg>
      <label className="mt-2 block text-sm">Equity observation<input aria-label="Equity observation" className="min-h-11 w-full" type="range" min={0} max={rows.length - 1} value={index} onChange={(e) => setSelected(Number(e.target.value))} /></label>
      {point && <p role="status" className="break-words text-sm">{point.date.slice(0, 10)} · Net {metric(point.net_equity)} VND · Gross {metric(point.gross_equity)} VND · Benchmark {metric(point.benchmark_equity)} VND</p>}
      <p className="mt-2 text-sm text-zinc-300">Net return {metric(data.net_return_pct)}% · fees {metric(data.total_fees_vnd)} VND · max drawdown {metric(data.max_drawdown_pct)}%</p>
      <details className="mt-3"><summary className="min-h-11 cursor-pointer text-sm">Equity data table</summary><div className="max-h-80 overflow-auto" tabIndex={0} aria-label="Equity data table scroll region"><table className="w-full text-sm"><thead><tr>{['Session (UTC)', 'Net VND', 'Gross VND', 'Benchmark VND', 'Drawdown %', 'Fees VND'].map((h) => <th key={h} scope="col" className={cellClass}>{h}</th>)}</tr></thead><tbody>{rows.map((p) => <tr key={p.date} className="border-t border-white/10"><th scope="row" className="p-2 text-left font-normal">{p.date}</th>{[p.net_equity, p.gross_equity, p.benchmark_equity, p.drawdown_pct, p.fees_vnd].map((v, i) => <td key={i} className={cellClass}>{metric(v)}</td>)}</tr>)}</tbody></table></div></details>
    </>}
  </section>;
}

const tabs = [['lab', 'Overview & Equity Curve'], ['cpcv', 'Walk-Forward / CPCV'], ['conformal', 'Conformal Prediction Bands'], ['overfitting', 'Overfitting Diagnostics (DSR/PBO)'], ['variance', 'Multi-Seed Variance']] as const;

export const StrategyLabView: React.FC = () => {
  const stored = useUiStore((s) => s.activeSubTabs['strategy_lab']), feature = useUiStore((s) => s.activeFeatureId), setTab = useUiStore((s) => s.setActiveSubTab);
  const tab = tabs.some(([key]) => key === stored) ? stored : 'lab';
  const [strategy, setStrategy] = useState('ALPHA_HRP_V2'), [asOf, setAsOf] = useState(() => new Date().toISOString());
  const [universe, setUniverse] = useState('FPT, HPG, MBB, MWG'), [start, setStart] = useState('2020-01-01'), [end, setEnd] = useState('2023-12-31');
  const [method, setMethod] = useState<StrategyWalkForwardRequest['evaluation_method']>('COMBINATORIAL_PURGED_K_FOLD');
  const [slippage, setSlippage] = useState('5'), [commission, setCommission] = useState('1.5');
  const walkRequest = { universe: universe.split(',').map((s) => s.trim()), start_date: start, end_date: end, n_splits: 6, n_test_splits: 2, embargo_pct: .01, label_horizon: 5, as_of: asOf, price_scale: 'VND_FULL' as const, evaluation_method: method, slippage_bps: slippage.trim() ? Number(slippage) : NaN, commission_bps: commission.trim() ? Number(commission) : NaN };
  const state = useStrategyLab({ strategy_id: strategy, as_of: asOf }, walkRequest);
  const [conformal, setConformal] = useState<ConformalPredictResponse | null>(null), [conformalError, setConformalError] = useState(false);

  useEffect(() => { const mapping: Record<string, string> = { F15: 'cpcv', F16: 'conformal', F17: 'overfitting' }; if (feature && mapping[feature]) setTab('strategy_lab', mapping[feature]); }, [feature, setTab]);
  useEffect(() => {
    if (tab !== 'conformal') return;
    const controller = new AbortController(); setConformal(null); setConformalError(false);
    void advancedQuantApi.getMarketConformal('VNM', 5, controller.signal).then((v) => {
      if (controller.signal.aborted) return;
      if (!v || v.status !== 'success' || v.symbol !== 'VNM' || !Number.isFinite(v.point_forecast_price) || v.point_forecast_price <= 0 || !Array.isArray(v.intervals) || !v.intervals.length || v.intervals.length > 10 || v.intervals.some((p) => !p || !Number.isFinite(p.confidence_level) || p.confidence_level <= 0 || p.confidence_level >= 1 || !Number.isFinite(p.lower_price) || !Number.isFinite(p.upper_price) || p.lower_price <= 0 || p.lower_price > p.upper_price)) { setConformalError(true); return; }
      setConformal(v);
    }).catch(() => { if (!controller.signal.aborted) setConformalError(true); });
    return () => controller.abort();
  }, [tab]);

  return <div className="flex h-full min-w-0 flex-col gap-4 overflow-y-auto font-mono text-zinc-100">
    <nav aria-label="Strategy Lab sections" className="flex flex-wrap gap-2">{tabs.map(([key, label]) => <button key={key} className={buttonClass} aria-pressed={tab === key} onClick={() => setTab('strategy_lab', key)}>{label}</button>)}</nav>
    {tab === 'variance' ? <VarianceExplorer /> : tab === 'conformal' ? <section className={panelClass}><h2 className="text-base font-semibold">Conformal Risk Bands (VNM)</h2><p className="mt-2 text-sm text-zinc-300">Separate market forecast; not strategy trial evidence.</p>{conformalError ? <p role="alert">Conformal data unavailable.</p> : !conformal ? <p role="status">Loading conformal bands...</p> : <><p className="mt-2">Point forecast {metric(conformal.point_forecast_price)} VND</p><table className="mt-3 w-full text-sm"><thead><tr><th scope="col">Confidence</th><th scope="col">Lower VND</th><th scope="col">Upper VND</th></tr></thead><tbody>{conformal.intervals.map((p, i) => <tr key={i}><th scope="row">{metric(p.confidence_level * 100)}%</th><td className={cellClass}>{metric(p.lower_price)}</td><td className={cellClass}>{metric(p.upper_price)}</td></tr>)}</tbody></table></>}</section> : <>
      <section className={panelClass} aria-label="Strategy analytics controls">
        <h1 className="text-lg font-semibold">Strategy Lab Visual Analytics</h1>
        <p className="mt-2 text-sm text-zinc-300">Persisted strategy diagnostics/equity and fixed equal-weight market evaluation are separate experiments.</p>
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="min-w-0 text-sm">Strategy<select aria-label="Strategy" className={inputClass} value={strategy} onChange={(e) => setStrategy(e.target.value)}><option value="ALPHA_HRP_V2">Alpha HRP v2</option><option value="MOMENTUM_VN30">Momentum VN30</option><option value="QUALITY_BARRA">Quality Barra</option></select></label>
          <label className="min-w-0 text-sm">Decision cutoff (timezone required)<input className={inputClass} value={asOf} onChange={(e) => setAsOf(e.target.value)} /></label>
          <label className="min-w-0 text-sm">Start date<input className={inputClass} type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
          <label className="min-w-0 text-sm">End date<input className={inputClass} type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
          <label className="min-w-0 text-sm">Market universe<input className={inputClass} maxLength={1900} value={universe} onChange={(e) => setUniverse(e.target.value)} /></label>
          <label className="min-w-0 text-sm">Evaluation method<select className={inputClass} value={method} onChange={(e) => setMethod(e.target.value as StrategyWalkForwardRequest['evaluation_method'])}><option value="COMBINATORIAL_PURGED_K_FOLD">Retrospective CPCV</option><option value="CHRONOLOGICAL_WALK_FORWARD">Chronological walk-forward</option></select></label>
          <label className="min-w-0 text-sm">Daily slippage (bps)<input className={inputClass} type="number" min="0" max="500" step="any" value={slippage} onChange={(e) => setSlippage(e.target.value)} /></label>
          <label className="min-w-0 text-sm">Daily commission (bps)<input className={inputClass} type="number" min="0" max="100" step="any" value={commission} onChange={(e) => setCommission(e.target.value)} /></label>
        </div>
        <p className="mt-3 text-sm text-zinc-300">6 splits · 2 test splits · 1% embargo · 5-bar label horizon · 1,000,000,000 VND reference capital</p>
        <div className="mt-3 flex flex-wrap gap-3"><button className={buttonClass} disabled={!state.valid || state.running} onClick={() => void state.runWalkForward()}>{state.running ? 'Running evaluation...' : 'Run walk-forward / CPCV calculation'}</button><button className={buttonClass} disabled={!state.valid || state.loading} onClick={state.refresh}>Reload diagnostics and equity</button></div>
        {!state.valid && <p role="alert" className="mt-3">Invalid strategy inputs. Previous results hidden.</p>}
        {state.loading && <p role="status" className="mt-3">Loading diagnostics and persisted equity...</p>}
        {[state.diagnosticsError, state.equityError, state.walkError].filter(Boolean).map((error, i) => <p key={i} role="alert" className="mt-2 break-words">{error}</p>)}
      </section>
      {(tab === 'lab' || tab === 'cpcv') && <WalkForwardHeatmap key={JSON.stringify(walkRequest)} data={state.walk} />}
      {(tab === 'lab' || tab === 'overfitting') && <div className="grid grid-cols-1 gap-4 lg:grid-cols-2"><DeflatedSharpeGauge data={state.diagnostics} /><OverfittingMetricsTable data={state.diagnostics} /></div>}
      {tab === 'lab' && <CumulativeEquityCurve key={`${strategy}:${asOf}`} data={state.equity} />}
    </>}
  </div>;
};
