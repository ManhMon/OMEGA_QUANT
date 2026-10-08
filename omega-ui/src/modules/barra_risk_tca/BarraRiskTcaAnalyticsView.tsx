import React, { useState, useEffect } from 'react';
import { RefreshCw, ShieldAlert } from 'lucide-react';
import {
  useBarraDecomposition, useStressScenarios, usePreTradeImpact, usePostTradeReport,
  useRoutingDiagnostics, useCallerBarra, useStressSimulation, useLiquidityConstraints,
} from '../../hooks/useBarraRiskTca';
import { BARRA_FACTORS, formatRiskMetric, riskErrorMessage } from '../../api/advancedQuant';
import type { BarraRequest, StressRequest, LiquidityRequest, TcaImpactRequest } from '../../api/advancedQuant';
import { useUiStore } from '../../store/uiStore';
import { CircuitBreakerStatusStrip } from './CircuitBreakerStatusStrip';
import { ContagionGraphCanvas } from './ContagionGraphCanvas';
import { useTranslation } from '../../i18n';

const panelClass = 'flex flex-col gap-3 rounded-xl border border-white/10 bg-zinc-900/40 p-4 min-w-0';
const inputClass = 'w-full rounded-lg border border-white/10 bg-zinc-950 p-2 text-zinc-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400';
const buttonClass = 'rounded-lg border border-white/10 bg-zinc-800 px-3 py-2 text-zinc-100 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400';

export const BarraRiskTcaAnalyticsView: React.FC = () => {
  const barraQuery = useBarraDecomposition();
  const stressQuery = useStressScenarios();
  const postTradeQuery = usePostTradeReport();
  const routingQuery = useRoutingDiagnostics();
  const callerBarra = useCallerBarra();
  const preTrade = usePreTradeImpact();
  const simulation = useStressSimulation();
  const liquidity = useLiquidityConstraints();
  const selectedTicker = useUiStore((state) => state.selectedTicker);
  const setSelectedTicker = useUiStore((state) => state.setSelectedTicker);
  const storeSubTab = useUiStore((state) => state.activeSubTabs['barra_risk_tca']);
  const activeFeatureId = useUiStore((state) => state.activeFeatureId);
  const setActiveSubTabInStore = useUiStore((state) => state.setActiveSubTab);
  const { t } = useTranslation();
  const activeRiskTab = storeSubTab || 'circuit';

  useEffect(() => {
    if (activeFeatureId === 'F05') setActiveSubTabInStore('barra_risk_tca', 'circuit');
    else if (activeFeatureId === 'F06') setActiveSubTabInStore('barra_risk_tca', 'stress');
    else if (activeFeatureId === 'F07') setActiveSubTabInStore('barra_risk_tca', 'contagion');
    else if (activeFeatureId === 'F08') setActiveSubTabInStore('barra_risk_tca', 'liquidity');
  }, [activeFeatureId, setActiveSubTabInStore]);

  const [barraInput, setBarraInput] = useState('');
  const [stressInput, setStressInput] = useState('');
  const [liquidityInput, setLiquidityInput] = useState('');
  const [inputErrors, setInputErrors] = useState<Record<string, string>>({});
  const [impactInput, setImpactInput] = useState({ symbol: selectedTicker, order_size: '', average_daily_volume: '', volatility: '', participation_rate: '', arrival_price: '', observed_spread_bps: '', side: 'BUY' });
  const barra = callerBarra.data ?? barraQuery.data;
  const postTrade = postTradeQuery.data;
  const routing = routingQuery.data;

  const submitJson = (key: string, text: string, submit: (value: unknown) => void) => {
    setInputErrors((prev) => ({ ...prev, [key]: '' }));
    try {
      if (!text.trim() || text.length > 262144) throw new Error('INVALID_RISK_INPUT');
      submit(JSON.parse(text));
    } catch {
      setInputErrors((prev) => ({ ...prev, [key]: 'Invalid request JSON. Check the required fields.' }));
    }
  };
  const editImpact = (key: string, value: string) => {
    preTrade.reset();
    setImpactInput((prev) => ({ ...prev, [key]: value }));
    setInputErrors((prev) => ({ ...prev, impact: '' }));
  };
  const submitImpact = (event: React.FormEvent) => {
    event.preventDefault();
    preTrade.reset();
    const { symbol, side, ...numbers } = impactInput;
    if (Object.values(numbers).some((value) => !value.trim())) {
      setInputErrors((prev) => ({ ...prev, impact: 'All observed inputs are required.' }));
      return;
    }
    const request = { symbol, side, ...Object.fromEntries(Object.entries(numbers).map(([key, value]) => [key, Number(value)])) } as TcaImpactRequest;
    preTrade.mutate(request);
  };
  const error = (value: unknown) => value ? <p role="alert">{riskErrorMessage(value)}</p> : null;

  return (
    <section aria-label={t.barraRiskTca.headerTitle} className="flex flex-col gap-4 p-1 pb-10 font-mono text-xs text-zinc-200">
      <header className={panelClass}>
        <h1 className="flex items-center gap-2 text-sm font-bold"><ShieldAlert aria-hidden="true" className="h-5 w-5" />{t.barraRiskTca.headerTitle}</h1>
        <p className="text-zinc-400">{t.barraRiskTca.headerSubtitle}</p>
        <button type="button" className={buttonClass} onClick={() => { barraQuery.refetch(); stressQuery.refetch(); postTradeQuery.refetch(); routingQuery.refetch(); }}>
          <RefreshCw aria-hidden="true" className="mr-2 inline h-4 w-4" />{t.barraRiskTca.syncBtn}
        </button>
      </header>
      <nav aria-label="Risk features" className="flex flex-wrap gap-2">
        {(['circuit', 'stress', 'contagion', 'liquidity'] as const).map((tab) => (
          <button type="button" key={tab} aria-pressed={activeRiskTab === tab} className={buttonClass} onClick={() => setActiveSubTabInStore('barra_risk_tca', tab)}>{tab}</button>
        ))}
      </nav>
      {activeRiskTab === 'circuit' && <CircuitBreakerStatusStrip symbol={selectedTicker} />}
      {activeRiskTab === 'contagion' && <ContagionGraphCanvas />}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section aria-label="Barra decomposition" className={panelClass}>
          <h2 className="font-bold">{t.barraRiskTca.factorRiskDecomp}</h2>
          {!barra && <p role="status">{barraQuery.isFetching ? 'Loading Barra model…' : t.common.integrationUnavailable}</p>}
          {!barra && error(barraQuery.error)}
          <form onSubmit={(event) => { event.preventDefault(); callerBarra.reset(); submitJson('barra', barraInput, (value) => callerBarra.mutate(value as BarraRequest)); }}>
            <label htmlFor="barra-request">Caller Barra request JSON</label>
            <p id="barra-help" className="py-2 text-zinc-400">assets: symbol, sector, weight_pct, specific_risk_pct, {BARRA_FACTORS.join(', ')}. factor_covariance: 8×8; covariance_unit: annualized_pct_squared or annualized_decimal_squared. Optional specific_variances.</p>
            <textarea id="barra-request" aria-describedby="barra-help" className={inputClass} rows={5} maxLength={262144} value={barraInput} onChange={(event) => { callerBarra.reset(); setBarraInput(event.target.value); setInputErrors((prev) => ({ ...prev, barra: '' })); }} />
            <button className={buttonClass} disabled={callerBarra.isPending}>Calculate caller Barra</button>
          </form>
          {inputErrors.barra && <p role="alert">{inputErrors.barra}</p>}{error(callerBarra.error)}
          {barra && <>
            <p role="status">{barra.provenance_status}; PIT verified: false. Caller covariance estimate, not historical risk.</p>
            <dl className="grid grid-cols-2 gap-2">
              <dt>Total annualized risk (%)</dt><dd>{formatRiskMetric(barra.total_risk_annualized_pct)}</dd>
              <dt>Factor variance (%²)</dt><dd>{formatRiskMetric(barra.factor_variance)}</dd>
              <dt>Specific variance (%²)</dt><dd>{formatRiskMetric(barra.specific_variance)}</dd>
            </dl>
            <div className="overflow-x-auto"><table className="w-full text-left"><caption>Signed factor decomposition</caption><thead><tr><th>Factor</th><th>Exposure</th><th>Variance (%²)</th></tr></thead><tbody>
              {barra.factor_order.map((factor) => <tr key={factor}><th>{factor}</th><td>{formatRiskMetric(barra.factor_exposures[factor])}</td><td>{formatRiskMetric(barra.factor_variance_contributions[factor])}</td></tr>)}
            </tbody></table></div>
            <div className="overflow-x-auto"><table className="w-full text-left"><caption>Asset weights</caption><thead><tr><th>Symbol</th><th>Sector</th><th>Weight (%)</th></tr></thead><tbody>
              {barra.asset_exposures.map((asset) => <tr key={asset.symbol}><td><button type="button" className={buttonClass} onClick={() => setSelectedTicker(asset.symbol)}>{asset.symbol}</button></td><td>{asset.sector}</td><td>{formatRiskMetric(asset.weight_pct)}</td></tr>)}
            </tbody></table></div>
          </>}
        </section>
        <section aria-label="Stress scenarios" className={panelClass}>
          <h2 className="font-bold">Stress scenarios</h2>
          <p role="status">Calibrated CVaR: {stressQuery.isFetching ? 'Loading…' : 'unavailable'}</p>{error(stressQuery.error)}
          <form onSubmit={(event) => { event.preventDefault(); simulation.reset(); submitJson('stress', stressInput, (value) => simulation.mutate(value as StressRequest)); }}>
            <label htmlFor="stress-request">Stress request JSON</label>
            <p id="stress-help" className="py-2 text-zinc-400">portfolio_weights: symbol-to-weight (0–1). Optional market_shock_pct (−50–50), volatility_shock_multiplier (0.5–10), include_contagion (boolean). Historical market inputs; estimated scenario impacts, not calibrated CVaR.</p>
            <textarea id="stress-request" aria-describedby="stress-help" className={inputClass} rows={4} maxLength={262144} value={stressInput} onChange={(event) => { simulation.reset(); setStressInput(event.target.value); setInputErrors((prev) => ({ ...prev, stress: '' })); }} />
            <button className={buttonClass} disabled={simulation.isPending}>Run scenarios</button>
          </form>
          {inputErrors.stress && <p role="alert">{inputErrors.stress}</p>}{error(simulation.error)}
          {simulation.data && <>
            <p>Estimated average loss: {formatRiskMetric(simulation.data.average_loss_pct)}%</p>
            <p>Market source: {simulation.data.provenance!.source}; cutoff: {simulation.data.provenance!.effective_cutoff}. Caller weights; scenario estimate.</p>
            <div className="overflow-x-auto"><table className="w-full text-left"><caption>Stress estimates</caption><thead><tr><th>Scenario</th><th>Market shock (%)</th><th>Portfolio impact (%)</th><th>Severity</th></tr></thead><tbody>
              {simulation.data.scenarios.map((scenario) => <tr key={scenario.id}><th>{scenario.name}</th><td>{formatRiskMetric(scenario.market_shock)}</td><td>{formatRiskMetric(scenario.portfolio_impact_pct)}</td><td>{scenario.severity}</td></tr>)}
            </tbody></table></div><p>{simulation.data.recommendation}</p>
          </>}
        </section>
        <section aria-label="Liquidity constraints" className={panelClass}>
          <h2 className="font-bold">Liquidity constraints</h2>
          <form onSubmit={(event) => { event.preventDefault(); liquidity.reset(); submitJson('liquidity', liquidityInput, (value) => liquidity.mutate(value as LiquidityRequest)); }}>
            <label htmlFor="liquidity-request">Liquidity request JSON</label>
            <p id="liquidity-help" className="py-2 text-zinc-400">positions: symbol-to-positive-share-quantity. Optional max_adv_participation (0–1, exclusive zero), max_exit_days (1–30), market_impact_coefficient (0–2, exclusive zero).</p>
            <textarea id="liquidity-request" aria-describedby="liquidity-help" className={inputClass} rows={4} maxLength={262144} value={liquidityInput} onChange={(event) => { liquidity.reset(); setLiquidityInput(event.target.value); setInputErrors((prev) => ({ ...prev, liquidity: '' })); }} />
            <button className={buttonClass} disabled={liquidity.isPending}>Validate liquidity</button>
          </form>
          {inputErrors.liquidity && <p role="alert">{inputErrors.liquidity}</p>}{error(liquidity.error)}
          {liquidity.data && <>
            <p role="status">{liquidity.data.is_safe ? 'Within liquidity limits' : 'Liquidity limits exceeded'}; impact: {formatRiskMetric(liquidity.data.total_impact_bps)} bps</p>
            <p>Market source: {liquidity.data.provenance!.source}; cutoff: {liquidity.data.provenance!.effective_cutoff}. Caller positions; historical ADV.</p>
            <div className="overflow-x-auto"><table className="w-full text-left"><caption>Liquidity breakdown</caption><thead><tr><th>Symbol</th><th>Shares</th><th>ADV (shares)</th><th>Exit days</th><th>Limit exceeded</th></tr></thead><tbody>
              {liquidity.data.breakdown.map((row) => <tr key={row.symbol}><th>{row.symbol}</th><td>{formatRiskMetric(row.quantity, 0)}</td><td>{formatRiskMetric(row.adv, 0)}</td><td>{formatRiskMetric(row.exit_days)}</td><td>{row.exceeds_limit ? 'Yes' : 'No'}</td></tr>)}
            </tbody></table></div><p>{liquidity.data.violation_message}</p>
          </>}
        </section>
        <section aria-label="Pre-trade impact" className={panelClass}>
          <h2 className="font-bold">{t.barraRiskTca.preTradeTitle}</h2>
          <form onSubmit={submitImpact} className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {Object.entries(impactInput).map(([key, value]) => <label key={key} htmlFor={`impact-${key}`}>{key}{key === 'arrival_price' ? ' (VND_FULL)' : ''}
              {key === 'side' ? <select id={`impact-${key}`} className={inputClass} value={value} onChange={(event) => editImpact(key, event.target.value)}><option>BUY</option><option>SELL</option></select>
                : <input id={`impact-${key}`} className={inputClass} type={key === 'symbol' ? 'text' : 'number'} step="any" required value={value} onChange={(event) => editImpact(key, event.target.value)} />}
            </label>)}
            <button className={buttonClass} disabled={preTrade.isPending}>{preTrade.isPending ? t.barraRiskTca.calculatingImpact : t.barraRiskTca.estimateBtn}</button>
          </form>
          {inputErrors.impact && <p role="alert">{inputErrors.impact}</p>}{error(preTrade.error)}
          {preTrade.data && <>
            <p role="status">{preTrade.data.provenance_status}; PIT verified: false.</p>
            <p>{preTrade.data.symbol} {preTrade.data.side}: impact {formatRiskMetric(preTrade.data.estimated_impact_bps)} bps; observed spread {formatRiskMetric(preTrade.data.spread_cost_bps)} bps; total {formatRiskMetric(preTrade.data.total_cost_bps)} bps / {formatRiskMetric(preTrade.data.total_cost_vnd)} VND_FULL</p>
          </>}
        </section>
      </div>
      <section aria-label="Routing diagnostics" className={panelClass}>
        <h2 className="font-bold">{t.barraRiskTca.routerTitle}</h2>
        {!routing && <p role="status">{routingQuery.isFetching ? 'Loading routing…' : t.common.integrationUnavailable}</p>}{error(routingQuery.error)}
        {routing && <><p>Paper trading data only; not live broker health. Roundtrip: {formatRiskMetric(routing.avg_roundtrip_latency_ms)} ms</p>
          <ul>{routing.routers.map((router) => <li key={router.broker}>{router.broker}: {router.status}; ping {formatRiskMetric(router.ping_ms)} ms; fill {formatRiskMetric(router.fill_rate_pct)}%</li>)}</ul></>}
      </section>
      <section aria-label="Post-trade report" className={panelClass}>
        <h2 className="font-bold">{t.barraRiskTca.postTradeTitle}</h2>
        {!postTrade && <p role="status">{postTradeQuery.isFetching ? 'Loading trades…' : t.common.integrationUnavailable}</p>}{error(postTradeQuery.error)}
        {postTrade && <><p>Paper execution records; no historical PIT claim. Average shortfall: {formatRiskMetric(postTrade.summary.average_is_bps)} bps</p>
          <div className="overflow-x-auto"><table className="w-full text-left"><caption>Paper TCA</caption><thead><tr><th>Trade</th><th>Symbol</th><th>Side</th><th>Filled shares</th><th>Fill (VND_FULL)</th><th>Pre-trade impact (bps)</th><th>Shortfall (bps)</th></tr></thead><tbody>
            {postTrade.trades.map((trade) => <tr key={trade.trade_id}><th>{trade.trade_id}</th><td>{trade.symbol}</td><td>{trade.side}</td><td>{formatRiskMetric(trade.filled_quantity, 0)}</td><td>{formatRiskMetric(trade.avg_fill_price)}</td><td>{formatRiskMetric(trade.pre_trade_impact_bps)}</td><td>{formatRiskMetric(trade.implementation_shortfall_bps)}</td></tr>)}
          </tbody></table></div></>}
      </section>
    </section>
  );
};
