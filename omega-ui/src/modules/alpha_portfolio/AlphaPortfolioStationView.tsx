import React, { useState } from 'react';
import { usePortfolioState, usePortfolioDynamicUniverse } from '../../hooks/usePortfolioState';
import { formatAlphaMetric, validatePortfolioRequest } from '../../api/advancedQuant';
import type { TargetPortfolioState, PortfolioUniverseRequest, ProvenanceEnvelope } from '../../api/advancedQuant';

const panelClass = 'min-w-0 break-words rounded-xl border border-white/10 bg-zinc-900 p-4 flex flex-col gap-3';
const controlClass = 'min-w-0 min-h-11 rounded-lg border border-white/20 bg-zinc-950 p-2 text-zinc-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400';
const metric = formatAlphaMetric;

function PortfolioProvenance({ value }: { value: ProvenanceEnvelope }) {
  return <details className="break-all"><summary className="cursor-pointer min-h-11">Backend PIT provenance · caller inputs are filters, not verified observations</summary>
    <dl className="grid gap-1"><dt>Source / dataset / version</dt><dd>{value.source} / {value.dataset_id} / {value.dataset_version}</dd>
      <dt>Decision / effective cutoff (UTC)</dt><dd>{value.as_of} / {value.effective_cutoff}</dd>
      <dt>Latest available observation</dt><dd>{value.max_included_available_at}</dd>
      <dt>Computed / cutoff resolution</dt><dd>{value.computed_at} / {value.cutoff_resolution}</dd>
      <dt>Content SHA-256 (backend supplied)</dt><dd>{value.content_hash}</dd>
      <dt>Synthetic</dt><dd>false; estimates are not broker balances or realized performance.</dd></dl>
  </details>;
}

function PortfolioHistoryChart({ rows, title, unit }: { rows: { timestamp: string; value: number }[]; title: string; unit: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const min = Math.min(0, ...rows.map((r) => r.value)), max = Math.max(0, ...rows.map((r) => r.value));
  const span = max - min || 1, start = Date.parse(rows[0].timestamp), duration = Date.parse(rows.at(-1)!.timestamp) - start || 1;
  const x = (i: number) => 64 + (Date.parse(rows[i].timestamp) - start) / duration * 640;
  const y = (value: number) => 24 + (max - value) / span * 140;
  const line = rows.map((row, i) => `${x(i)},${y(row.value)}`).join(' ');
  const index = Math.min(hover ?? rows.length - 1, rows.length - 1), point = rows[index];
  return <section className={panelClass} aria-label={title}><h2 className="font-bold">{title}</h2>
    <svg viewBox="0 0 760 210" className="w-full min-h-44 max-h-72" role="img" aria-label={`${title}, ${unit}. Exact values in table below.`}>
      {[min, max].map((value, i) => <g key={i}><line x1="64" x2="704" y1={y(value)} y2={y(value)} stroke="#3f3f46" /><text x="4" y={y(value) + 4} fill="#d4d4d8" fontSize="11">{metric(value, 1)}</text></g>)}
      <polygon points={`64,${y(0)} ${line} 704,${y(0)}`} fill="#3b82f6" fillOpacity="0.1" />
      <polyline points={line} fill="none" stroke="#3b82f6" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <line x1={x(index)} x2={x(index)} y1="24" y2="164" stroke="#a1a1aa" />
      <circle cx={x(index)} cy={y(point.value)} r="4" fill="#3b82f6" stroke="#18181b" strokeWidth="2" />
      <text x="64" y="193" fill="#d4d4d8" fontSize="11">{rows[0].timestamp.slice(0, 10)}</text>
      <text x="704" y="193" textAnchor="end" fill="#d4d4d8" fontSize="11">{rows.at(-1)!.timestamp.slice(0, 10)}</text>
      <rect x="64" y="20" width="640" height="150" fill="transparent" onPointerMove={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        const time = start + Math.max(0, Math.min(1, (event.clientX - bounds.left) / (bounds.width || 1))) * duration;
        setHover(rows.reduce((best, row, i) => Math.abs(Date.parse(row.timestamp) - time) < Math.abs(Date.parse(rows[best].timestamp) - time) ? i : best, 0));
      }} onPointerLeave={() => setHover(null)} />
    </svg>
    <label className="flex flex-wrap items-center gap-2">Inspect observation<input aria-label={`${title} observation`} type="range" min="0" max={rows.length - 1} value={index} onChange={(event) => setHover(Number(event.target.value))} className="min-h-11 flex-1" /></label>
    <output aria-live="polite">{point.timestamp}: {metric(point.value)} {unit}</output>
    <details><summary className="cursor-pointer min-h-11">Exact data table</summary><div className="overflow-x-auto"><table className="w-full text-left text-zinc-200 tabular-nums [&_th]:p-2 [&_td]:p-2 [&_caption]:text-zinc-200"><caption>{title} · {unit}</caption><thead><tr><th scope="col">Session (UTC)</th><th scope="col">Value</th></tr></thead><tbody>{rows.map((row) => <tr key={row.timestamp}><th scope="row">{row.timestamp}</th><td>{metric(row.value)}</td></tr>)}</tbody></table></div></details>
  </section>;
}

export function UnderwaterDrawdownProfile({ state }: { state: TargetPortfolioState }) {
  return <PortfolioHistoryChart key={state.provenance.content_hash} title="Underwater Drawdown profile" unit="% from prior peak" rows={state.drawdown_series.map((r) => ({ timestamp: r.timestamp, value: r.drawdown_percent }))} />;
}
export function HrpDendrogramAllocation() {
  return <section className={panelClass} aria-label="HRP dendrogram"><h2 className="font-bold">HRP dendrogram</h2><p role="status">UNAVAILABLE</p><p>The backend provides hrp_weights; the clustering linkage topology contract is not registered. No client-side clustering is fabricated.</p></section>;
}
export function PortfolioAllocationBreakdown({ state }: { state: TargetPortfolioState }) {
  return <section className={panelClass} aria-label="Portfolio allocation breakdown"><h2 className="font-bold">Target allocation / rebalance breakdown</h2>
    <p>Reference capital, not broker assets. Current holdings contract unavailable: rebalance delta, turnover and execution cost are UNAVAILABLE, not zero.</p>
    <div className="overflow-x-auto"><table className="w-full text-left text-zinc-200 tabular-nums [&_th]:p-2 [&_td]:p-2 [&_caption]:text-zinc-200"><caption>Target institutional allocation · {state.weighting_method}</caption><thead><tr>{['Symbol', 'Sector', 'HRP weight (%)', 'Target value (VND_FULL)', 'ADV20 (billion VND)', 'Alpha score', 'Current / delta'].map((h) => <th scope="col" key={h}>{h}</th>)}</tr></thead>
      <tbody>{state.holdings.map((h) => <tr key={h.symbol}><th scope="row">{h.symbol}</th><td>{h.sector}</td><td>{metric(h.weight * 100)}</td><td>{metric(h.marketValueBillionVnd * 1e9)}</td><td>{metric(h.adv20BillionVnd)}</td><td>{metric(h.alphaScore)}</td><td>UNAVAILABLE</td></tr>)}</tbody></table></div>
    <p>Unallocated reference capital: {metric(state.unallocated_cash_vnd)} VND_FULL</p>
    <button type="button" disabled className={controlClass}>Execution disengaged · TOTP required</button><p>Order routing is an explicit authorized execution action, never a preview.</p>
  </section>;
}

export const AlphaPortfolioStationView: React.FC = () => {
  const [input, setInput] = useState({ as_of: '', min_adv_billion: '20', top_n: '30', sector_cap: '0.3', min_score: '0.25' });
  let request: PortfolioUniverseRequest | null = null;
  try {
    const { as_of, ...numbers } = input;
    if (Object.values(numbers).some((value) => !value.trim())) throw new Error('Invalid inputs');
    request = validatePortfolioRequest({ ...(as_of ? { as_of } : {}), ...Object.fromEntries(Object.entries(numbers).map(([key, value]) => [key, Number(value)])) }, true);
  } catch { /* Invalid inputs hide both result sets. */ }
  const state = usePortfolioState(request === null ? null : request.as_of ? { as_of: request.as_of } : {});
  const universe = usePortfolioDynamicUniverse(request);
  const status = (query: typeof state | typeof universe) => query.errorMessage ? <p role="alert">{query.errorMessage}</p> : !query.data ? <p role="status">{query.isFetching ? 'Loading portfolio data…' : 'Portfolio data unavailable.'}</p> : null;
  return <section aria-label="Alpha Portfolio Station" className="flex min-w-0 flex-col gap-4 pb-10 text-sm text-zinc-200">
    <header className={panelClass}><h1 className="text-lg font-bold">Alpha Portfolio Station</h1><p>Target institutional allocation · read-only estimates · VND_FULL</p><p>Reference AUM: candidate_market_cap_reference_not_broker_assets. NAV: fixed-weight daily basket estimate, not realized performance.</p></header>
    <form className="flex flex-wrap gap-3" onSubmit={(event) => { event.preventDefault(); state.refresh(); universe.refresh(); }}>
      {Object.entries(input).map(([key, value]) => <label key={key} className="flex w-full min-w-0 flex-col gap-1 sm:w-auto" htmlFor={`portfolio-${key}`}>{({ as_of: 'Decision time (ISO, explicit timezone; blank = server now)', min_adv_billion: 'Minimum ADV (billion VND)', top_n: 'Maximum candidates', sector_cap: 'Sector cap (fraction)', min_score: 'Minimum score' })[key as keyof typeof input]}
        <input id={`portfolio-${key}`} className={controlClass} type={key === 'as_of' ? 'text' : 'number'} step={key === 'top_n' ? '1' : 'any'} maxLength={64} value={value} aria-invalid={request === null} aria-describedby={request === null ? 'portfolio-invalid' : undefined} onChange={(event) => setInput((previous) => ({ ...previous, [key]: event.target.value }))} />
      </label>)}<button type="submit" className={controlClass} disabled={request === null}>Refresh reads</button>
    </form>
    {request === null && <p id="portfolio-invalid" role="alert">Invalid portfolio inputs. Use bounded numbers and a past timezone-aware decision time.</p>}
    <section className={panelClass} aria-label="Target portfolio state"><h2 className="font-bold">Reference capital / estimated allocation</h2>{status(state)}{state.data && <><dl className="grid gap-2 sm:grid-cols-2"><dt>Reference capital AUM (VND_FULL)</dt><dd>{metric(state.data.total_aum_vnd)}</dd><dt>Maximum estimated drawdown (%)</dt><dd>{metric(state.data.maxDrawdownEstimatePercent)}</dd></dl><PortfolioProvenance value={state.data.provenance} /></>}</section>
    <HrpDendrogramAllocation />
    {state.data && <><PortfolioAllocationBreakdown state={state.data} /><PortfolioHistoryChart key={`nav-${state.data.provenance.content_hash}`} title="Estimated NAV history" unit="VND_FULL" rows={state.data.nav_history.map((r) => ({ timestamp: r.timestamp, value: r.nav_vnd }))} /><UnderwaterDrawdownProfile state={state.data} /></>}
    <section className={panelClass} aria-label="Dynamic universe"><h2 className="font-bold">Dynamic universe</h2>{status(universe)}{universe.data && <>
      <p>{universe.data.total_selected} selected / {universe.data.total_evaluated} evaluated. Sector weights represent equal-count exposure, not capital allocation.</p>
      {!universe.data.symbols.length && <p role="status">No eligible candidates satisfy the requested filters and sector cap.</p>}
      <div className="overflow-x-auto"><table className="w-full text-left text-zinc-200 tabular-nums [&_th]:p-2 [&_td]:p-2 [&_caption]:text-zinc-200"><caption>Liquidity, alpha scores and lifecycle</caption><thead><tr>{['Symbol', 'Sector', 'Score', 'ADV (billion VND)', 'Status'].map((h) => <th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{universe.data.selected_details.map((d) => <tr key={d.symbol}><th scope="row">{d.symbol}</th><td>{d.sector}</td><td>{metric(d.score)}</td><td>{metric(d.adv_billion_vnd)}</td><td>{d.status}</td></tr>)}</tbody></table></div>
      <dl>{Object.entries(universe.data.sector_weights).map(([sector, weight]) => <div key={sector} className="flex gap-3"><dt>{sector}</dt><dd>{metric(weight * 100)}% of candidates</dd></div>)}</dl><PortfolioProvenance value={universe.data.provenance} />
    </>}</section>
  </section>;
};
