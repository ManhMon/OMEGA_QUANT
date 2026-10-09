import React, { useEffect, useState } from 'react';
import { useUiStore } from '../../store/uiStore';
import { useQuantScreener, useFundamentalDuPont, useFundamentalPiotroski, useFundamentalValuation } from '../../hooks/useQuantScreener';
import { PIOTROSKI_CRITERIA } from '../../api/advancedQuant';
import type { FundamentalDuPontResponse, FundamentalPiotroskiResponse, FundamentalValuationResponse } from '../../api/advancedQuant';
import { CorporateGraphDrawer } from './CorporateGraphDrawer';
import { OwnershipSupplyChainGraph } from './OwnershipSupplyChainGraph';

const panelClass = 'min-w-0 rounded-lg border border-white/10 bg-zinc-950 p-4 text-zinc-100';
const inputClass = 'min-h-11 w-full rounded border border-zinc-600 bg-zinc-900 p-2 text-zinc-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400';
const buttonClass = 'min-h-11 rounded border border-zinc-600 px-3 py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400 disabled:opacity-50';

export function formatMetricValue(value: unknown, digits: number, suffix = ''): string {
  return typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1e12 ? `${value.toFixed(digits)}${suffix}` : '--';
}
export function formatMomentumScore(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1e12 ? `${value >= 0 ? '+' : ''}${value.toFixed(2)}` : '--';
}
export function momentumColor(value: number | null): string {
  return value == null || !Number.isFinite(value) ? 'text-zinc-500' : value >= 0 ? 'text-emerald-400' : 'text-rose-400';
}

export function DuPontFactorAnalysis({ data }: { data: FundamentalDuPontResponse }) {
  const factors = [data.net_margin, data.asset_turnover, data.equity_multiplier];
  const product = factors.every(v => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= 1e12) ? factors.reduce<number>((p, v) => p * v!, 1) : null;
  const valid = data.status === 'success' && data.asset_turnover !== null && data.asset_turnover > 0 && data.equity_multiplier !== null && data.equity_multiplier > 0 && typeof data.roe === 'number' && Number.isFinite(data.roe) && typeof data.roe_percent === 'number' && Number.isFinite(data.roe_percent) && Math.abs(data.roe_percent) <= 1e12 && Math.abs(data.roe * 100 - data.roe_percent) <= 1e-8 * Math.max(1, Math.abs(data.roe_percent)) && product !== null && Number.isFinite(product) && Math.abs(product) <= 1e12 && Math.abs(product - data.roe) <= 1e-8 * Math.max(1, Math.abs(product));
  return <section className={panelClass} aria-label="DuPont analysis">
    <h2 className="text-lg font-semibold">3-Step DuPont · {data.symbol}</h2>
    <button className={`${buttonClass} my-2`} disabled title="5-Step DuPont requires expanded tax/interest burdens - Coming in v2">5-Step DuPont unavailable</button>
    <p className="text-sm text-zinc-300">5-Step DuPont requires expanded tax/interest burdens - Coming in v2</p>
    <p className="my-3 text-sm">ROE = net margin × asset turnover × leverage (equity multiplier). Ratios, not additive contributions. Average assets/equity; fiscal year {data.fiscal_year ?? '--'}.</p>
    {valid ? <>
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {['Net margin', 'Asset turnover', 'Leverage'].map((label, i) => <div key={label}><dt className="text-sm text-zinc-300">{label}</dt><dd className="text-xl">{formatMetricValue(factors[i], 4, '×')}</dd></div>)}
      </dl>
      <p className="mt-3" aria-label="DuPont reconciliation">{factors.map(v => formatMetricValue(v, 4)).join(' × ')} = {formatMetricValue(product, 4)}; ROE {formatMetricValue(data.roe_percent, 2, '%')}</p>
    </> : <p role="status">ROE -- · {data.status === 'not_meaningful' ? 'Nonpositive equity: not meaningful.' : 'Missing or invalid filing inputs. No calculation available.'}</p>}
    <p className="mt-3 break-words text-sm text-zinc-300">Source filing dates: {data.filing_dates.length ? data.filing_dates.join(', ') : 'unavailable'}</p>
  </section>;
}

export function PiotroskiFScoreBreakdown({ data }: { data: FundamentalPiotroskiResponse }) {
  return <section className={panelClass} aria-label="Piotroski analysis">
    <h2 className="text-lg font-semibold">Piotroski F-Score · {data.symbol}</h2>
    <p className="my-3">Score {formatMetricValue(data.score, 0)} / 9 · Known passes {data.known_passes} · Unknown {data.unknown_count} · Fiscal year {data.fiscal_year ?? '--'}</p>
    <p className="text-sm text-zinc-300">Unknown is not fail. Total unavailable until all nine criteria are known.</p>
    <ul className="mt-3 divide-y divide-zinc-700">
      {data.criteria.map(c => <li key={c.id} className="py-2">
        <span className="font-semibold">{c.status === 'pass' ? '✓ Pass' : c.status === 'fail' ? '✕ Fail' : '? Unknown'}</span> · {PIOTROSKI_CRITERIA[c.id]}
        <p className="break-words text-sm text-zinc-300">Filing dates: {c.filing_dates.length ? c.filing_dates.join(', ') : 'unavailable'}{c.reason ? ' · Missing or invalid filing inputs' : ''}</p>
      </li>)}
    </ul>
  </section>;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : sorted[middle - 1] / 2 + sorted[middle] / 2;
}
export function valuationQuadrant(pe: number, roe: number, benchmarkPe: number, benchmarkRoe: number): string {
  if (![pe, roe, benchmarkPe, benchmarkRoe].every(v => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= 1e12) || pe <= 0 || benchmarkPe <= 0) return 'Unavailable';
  if (pe === benchmarkPe || roe === benchmarkRoe) return 'On sector benchmark';
  return `${pe < benchmarkPe ? 'Lower' : 'Higher'} P/E · ${roe > benchmarkRoe ? 'Higher' : 'Lower'} ROE`;
}
export function ValuationScatterMatrix({ data, onSelect }: { data: FundamentalValuationResponse; onSelect: (symbol: string) => void }) {
  const [sector, setSector] = useState(''), [focused, setFocused] = useState<string | null>(null);
  const sectors = [...new Set(data.data.map(row => row.sector))].sort();
  const activeSector = sectors.includes(sector) ? sector : sectors[0];
  const rows = data.data.filter(row => row.sector === activeSector && typeof row.pe === 'number' && row.pe > 0 && Number.isFinite(row.pe) && row.pe <= 1e12 && typeof row.roe === 'number' && Number.isFinite(row.roe) && Math.abs(row.roe) <= 1e12);
  const benchmarkPe = rows.length ? median(rows.map(r => r.pe!)) : 0, benchmarkRoe = rows.length ? median(rows.map(r => r.roe!)) : 0;
  const minRoe = Math.min(0, ...rows.map(r => r.roe!)), maxRoe = Math.max(0, ...rows.map(r => r.roe!));
  const maxPe = Math.max(1, ...rows.map(r => r.pe!));
  const x = (pe: number) => 64 + pe / maxPe * 470;
  const y = (roe: number) => 260 - (roe - minRoe) / (maxRoe - minRoe || 1) * 210;
  const selected = rows.find(r => r.symbol === focused);
  return <section className={panelClass} aria-label="Valuation scatter matrix">
    <h2 className="text-lg font-semibold">Valuation Scatter Matrix</h2>
    <label className="my-3 block text-sm">Scatter sector<select className={inputClass} value={activeSector ?? ''} onChange={e => { setSector(e.target.value); setFocused(null); }} disabled={!sectors.length}>{sectors.map(s => <option key={s}>{s}</option>)}</select></label>
    <p className="text-sm text-zinc-300">Observed sector sample medians, not population benchmarks. P/E {formatMetricValue(rows.length ? benchmarkPe : null, 2)}× · ROE {formatMetricValue(rows.length ? benchmarkRoe : null, 2, '%')} · n={rows.length}. No common fiscal period supplied; snapshot comparison only.</p>
    <p className="mt-2 text-sm text-zinc-300">Quadrants are screening labels, not buy/sell recommendations. Excluded not meaningful: {data.excluded_not_meaningful}.</p>
    {rows.length ? <>
      <div className="overflow-x-auto" tabIndex={0} aria-label="Scrollable valuation plot">
      <svg viewBox="0 0 580 320" className="my-3 w-full min-w-[520px]" role="group" aria-label="P/E versus ROE percent, sector sample medians">
        <path d="M64 50V260H534" fill="none" stroke="#71717a" />
        <path d={`M${x(benchmarkPe)} 50V260 M64 ${y(benchmarkRoe)}H534`} fill="none" stroke="#71717a" />
        <g fill="currentColor" fontSize="13"><text x="64" y="282">0</text><text x="490" y="282">{formatMetricValue(maxPe, 1)}</text><text x="270" y="308">P/E (×)</text><text x="4" y="34">ROE (%)</text><text x="4" y="59">{formatMetricValue(maxRoe, 1)}</text><text x="4" y="260">{formatMetricValue(minRoe, 1)}</text></g>
        {rows.map(r => <g key={r.symbol} tabIndex={0} role="button" aria-label={`${r.symbol}, P/E ${r.pe}, ROE ${r.roe}%, ${valuationQuadrant(r.pe!, r.roe!, benchmarkPe, benchmarkRoe)}`} className="cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
          onMouseEnter={() => setFocused(r.symbol)} onMouseLeave={() => setFocused(null)} onFocus={() => setFocused(r.symbol)} onBlur={() => setFocused(null)} onClick={() => onSelect(r.symbol)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(r.symbol); } }}>
          <circle cx={x(r.pe!)} cy={y(r.roe!)} r="12" fill="transparent" />
          <circle cx={x(r.pe!)} cy={y(r.roe!)} r={focused === r.symbol ? 6 : 4} fill="#3987e5" stroke="#09090b" strokeWidth="2" />
          <title>{r.symbol}: P/E {r.pe}×, ROE {r.roe}%</title>
        </g>)}
      </svg>
      </div>
      <p className="min-h-12 text-sm" aria-live="polite">{selected ? `${selected.symbol} · P/E ${formatMetricValue(selected.pe, 2)}× · ROE ${formatMetricValue(selected.roe, 2)}% · ${valuationQuadrant(selected.pe!, selected.roe!, benchmarkPe, benchmarkRoe)}` : 'Focus or hover a point; select it for filing detail.'}</p>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="text-left">Sector sample values and quadrant labels</caption><thead><tr>{['Symbol', 'P/E ×', 'ROE %', 'Quadrant'].map(h => <th key={h} scope="col" className="p-2">{h}</th>)}</tr></thead><tbody>{rows.map(r => <tr key={r.symbol}><td className="p-2"><button className={buttonClass} onClick={() => onSelect(r.symbol)}>{r.symbol}</button></td><td className="p-2 tabular-nums">{formatMetricValue(r.pe, 2)}</td><td className="p-2 tabular-nums">{formatMetricValue(r.roe, 2)}</td><td className="p-2">{valuationQuadrant(r.pe!, r.roe!, benchmarkPe, benchmarkRoe)}</td></tr>)}</tbody></table></div>
    </> : <p role="status" className="my-3">No meaningful valuation pairs available.</p>}
  </section>;
}

function ReadState({ query, children }: { query: { isFetching: boolean; errorMessage: string | null; refresh: () => void }; children: React.ReactNode }) {
  return query.errorMessage ? <div className={panelClass} role="alert"><p>{query.errorMessage}</p><button className={buttonClass} onClick={query.refresh}>Retry</button></div> : query.isFetching ? <p role="status" className={panelClass}>Loading fundamental data…</p> : <>{children}</>;
}

export const FundamentalMatrixView: React.FC = () => {
  const filters = useUiStore(s => s.screenerFilters), setFilters = useUiStore(s => s.setScreenerFilters), resetFilters = useUiStore(s => s.resetScreenerFilters);
  const symbol = useUiStore(s => s.selectedTicker), setSymbol = useUiStore(s => s.setSelectedTicker), setModule = useUiStore(s => s.setActiveModule), feature = useUiStore(s => s.activeFeatureId);
  const [asOf, setAsOf] = useState(() => new Date().toISOString()), [drawerOpen, setDrawerOpen] = useState(false), [drawerSymbol, setDrawerSymbol] = useState(symbol);
  useEffect(() => { if (feature === 'F23') { setDrawerSymbol(symbol); setDrawerOpen(true); } }, [feature, symbol]);
  const screener = useQuantScreener(filters, asOf), valuation = useFundamentalValuation({ as_of: asOf });
  const dupont = useFundamentalDuPont({ symbol, as_of: asOf }), piotroski = useFundamentalPiotroski({ symbol, as_of: asOf });
  const rows = screener.data?.data ?? [], page = filters.page ?? 1, pages = screener.data?.total_pages ?? 0;
  return <div className="flex min-w-0 flex-col gap-4 pb-8 text-zinc-100">
    <CorporateGraphDrawer symbol={drawerSymbol} isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} />
    <section className={panelClass} aria-label="Fundamental controls">
      <h1 className="text-xl font-semibold">Fundamental Matrix</h1>
      <p className="my-2 text-sm text-zinc-300">Metadata validated, not authenticated lineage. Historical PIT verification: false. One explicit filing cutoff for all analytics.</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm">As of (timezone required)<input className={inputClass} value={asOf} onChange={e => setAsOf(e.target.value)} maxLength={64} /></label>
        <label className="text-sm">Selected ticker<input className={inputClass} value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} maxLength={12} /></label>
        <label className="text-sm">Exact screener ticker<input className={inputClass} value={filters.search ?? ''} onChange={e => setFilters({ search: e.target.value.toUpperCase() })} maxLength={12} /></label>
        <label className="text-sm">Exchange<select className={inputClass} value={filters.exchange ?? ''} onChange={e => setFilters({ exchange: e.target.value })}>{['', 'HOSE', 'HNX', 'UPCOM'].map(v => <option value={v} key={v}>{v || 'All exchanges'}</option>)}</select></label>
        <label className="text-sm">Sector (exact)<input className={inputClass} value={filters.sector ?? ''} onChange={e => setFilters({ sector: e.target.value })} maxLength={80} /></label>
        <label className="text-sm">Status<select className={inputClass} value={filters.status ?? ''} onChange={e => setFilters({ status: e.target.value })}>{['', 'QUALIFIED', 'WATCH', 'DISTRESS', 'DISQUALIFIED'].map(v => <option value={v} key={v}>{v || 'All statuses'}</option>)}</select></label>
        {(['minPiotroski', 'minRoe', 'minAltmanZ'] as const).map((key, i) => <label className="text-sm" key={key}>{['Minimum F-Score', 'Minimum ROE %', 'Minimum Altman Z'][i]}<input className={inputClass} type="number" min={i === 0 ? 0 : -1e12} max={i === 0 ? 9 : 1e12} step={i === 0 ? 1 : 'any'} value={Number.isFinite(filters[key]) ? filters[key] : ''} onChange={e => setFilters({ [key]: e.target.value === '' ? undefined : e.target.valueAsNumber })} /></label>)}
        <label className="text-sm">Page size<input className={inputClass} type="number" min={1} max={703} step={1} value={Number.isFinite(filters.pageSize) ? filters.pageSize : ''} onChange={e => setFilters({ pageSize: e.target.valueAsNumber })} /></label>
      </div>
      <div className="mt-3 flex flex-wrap gap-3"><button className={buttonClass} onClick={resetFilters}>Reset screener</button><button className={buttonClass} onClick={() => { screener.refresh(); valuation.refresh(); dupont.refresh(); piotroski.refresh(); }}>Refresh analytics</button></div>
      <p className="mt-2 text-sm text-zinc-300">Screener filters scope the screener only. Scatter sector scopes the scatter; selected ticker scopes filing detail.</p>
    </section>
    <ReadState query={screener}><section className={panelClass} aria-label="Quant screener">
      <h2 className="text-lg font-semibold">Quant Screener · {screener.data?.total ?? '--'} matches</h2>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="text-left">Bounded finite financial metrics</caption><thead><tr>{['Ticker', 'Exchange', 'Sector', 'P/E', 'P/B', 'ROE %', 'F-Score', 'Altman Z', 'Status', 'Actions'].map(h => <th className="p-2" scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{rows.map(r => <tr key={r.symbol} className="border-t border-zinc-700"><td className="p-2"><button className={buttonClass} onClick={() => setSymbol(r.symbol)}>{r.symbol}</button></td><td className="p-2">{r.exchange}</td><td className="p-2">{r.sector}</td>{[r.pe, r.pb, r.roe, r.piotroski_f, r.altman_z].map((v, i) => <td className="p-2 tabular-nums" key={i}>{formatMetricValue(v, i === 3 ? 0 : 2)}</td>)}<td className="p-2">{r.status}{r.is_fallback ? ' · Fallback' : ''}{r.is_veto ? ' · Veto' : ''}</td><td className="p-2"><div className="flex gap-2"><button className={buttonClass} onClick={() => { setSymbol(r.symbol); setModule('chart_station'); }}>Chart {r.symbol}</button><button className={buttonClass} onClick={() => { setDrawerSymbol(r.symbol); setDrawerOpen(true); }}>Corporate graph {r.symbol}</button></div></td></tr>)}</tbody></table></div>
      {!rows.length && <p role="status" className="my-3">No matching records.</p>}
      <div className="mt-3 flex flex-wrap items-center gap-3"><button className={buttonClass} disabled={!screener.data || page <= 1} onClick={() => setFilters({ page: page - 1 })}>Previous page</button><span>Page {Number.isFinite(page) ? page : '--'} / {pages}</span><button className={buttonClass} disabled={!screener.data || page >= pages} onClick={() => setFilters({ page: page + 1 })}>Next page</button></div>
    </section></ReadState>
    <ReadState query={valuation}>{valuation.data && <ValuationScatterMatrix data={valuation.data} onSelect={setSymbol} />}</ReadState>
    <div className="grid min-w-0 grid-cols-1 gap-4 xl:grid-cols-2">
      <ReadState query={dupont}>{dupont.data && <DuPontFactorAnalysis data={dupont.data} />}</ReadState>
      <ReadState query={piotroski}>{piotroski.data && <PiotroskiFScoreBreakdown data={piotroski.data} />}</ReadState>
    </div>
    <OwnershipSupplyChainGraph symbol={symbol} />
  </div>;
};
