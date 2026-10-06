import React, { useState } from 'react';
import {
  ShieldAlert,
  Calculator,
  ReceiptText,
  Layers,
  TrendingDown,
  RefreshCw,
  Zap,
  Server,
  Play,
  LineChart
} from 'lucide-react';
import {
  useBarraDecomposition,
  useStressScenarios,
  usePreTradeImpact,
  usePostTradeReport,
  useRoutingDiagnostics,
} from '../../hooks/useBarraRiskTca';
import { useUiStore } from '../../store/uiStore';
import { CircuitBreakerStatusStrip } from './CircuitBreakerStatusStrip';
import { HistoricalStressScenarioPicker } from './HistoricalStressScenarioPicker';
import { ContagionGraphCanvas } from './ContagionGraphCanvas';
import { LiquidityConstraintTable } from './LiquidityConstraintTable';
import { useTranslation } from '../../i18n';

export const BarraRiskTcaAnalyticsView: React.FC = () => {
  const { data: barra, refetch: refetchBarra, isError: isBarraError } = useBarraDecomposition();
  const { data: stress, refetch: refetchStress } = useStressScenarios();
  const { data: postTrade, refetch: refetchPostTrade } = usePostTradeReport();
  const { data: routing, refetch: refetchRouting } = useRoutingDiagnostics();
  const preTradeMutation = usePreTradeImpact();

  const selectedTicker = useUiStore((state) => state.selectedTicker);
  const setSelectedTicker = useUiStore((state) => state.setSelectedTicker);
  const setActiveModule = useUiStore((state) => state.setActiveModule);
  const { t } = useTranslation();

  const [activeRiskTab, setActiveRiskTab] = useState<'circuit' | 'stress' | 'contagion' | 'liquidity'>('circuit');

  const handleSelectSymbol = (symbol: string) => {
    setSelectedTicker(symbol);
  };

  const handleOpenChartStation = (e: React.MouseEvent, symbol: string) => {
    e.stopPropagation();
    setSelectedTicker(symbol);
    setActiveModule('chart_station');
  };

  // Pre-Trade Impact Calculator State
  const [calcSymbol, setCalcSymbol] = useState('FPT');
  const [calcSize, setCalcSize] = useState(15000);
  const [calcAdv, setCalcAdv] = useState(1250000);
  const [calcVol, setCalcVol] = useState(0.02);
  const [calcPrice, setCalcPrice] = useState(138500);
  const [calcSide, setCalcSide] = useState<'BUY' | 'SELL'>('BUY');
  const [calcParticipation, setCalcParticipation] = useState(0.10);

  const handleRunImpactCalc = () => {
    preTradeMutation.mutate({
      symbol: calcSymbol,
      order_size: calcSize,
      average_daily_volume: calcAdv,
      volatility: calcVol,
      arrival_price: calcPrice,
      side: calcSide,
      participation_rate: calcParticipation,
    });
  };

  const impactResult = preTradeMutation.data;

  if (!barra || !stress || !postTrade || !routing || isBarraError) return (
    <section aria-label={t.barraRiskTca.headerTitle}>
      <p role="alert">{t.common.integrationUnavailable}</p>
      <button type="button" onClick={() => { refetchBarra(); refetchStress(); refetchPostTrade(); refetchRouting(); }}>{t.common.retry}</button>
    </section>
  );

  return (
    <div className="flex flex-col gap-4 p-1 pb-10">
      {/* Top Banner Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-xl border border-white/10 bg-zinc-900/60 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-sm font-bold font-mono tracking-wide text-zinc-100 uppercase">
              {t.barraRiskTca.headerTitle}
            </h1>
            <p className="text-[11px] font-mono text-zinc-400">
              {t.barraRiskTca.headerSubtitle}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 font-mono text-xs">
          <button
            onClick={() => {
              refetchBarra();
              refetchStress();
              refetchPostTrade();
              refetchRouting();
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 bg-zinc-800/80 hover:bg-zinc-700/80 text-zinc-300 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>{t.barraRiskTca.syncBtn}</span>
          </button>
        </div>
      </div>

      {/* Phase 2 Modular Risk Control Center (Tabbed Sub-Panels) */}
      <div className="flex flex-col gap-3 rounded-xl border border-white/10 bg-zinc-900/40 p-4 font-mono text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-emerald-400" />
            <span className="font-bold text-zinc-200 uppercase tracking-wider">
              Real-Time Risk Controls & Stress Testing
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <button
              onClick={() => setActiveRiskTab('circuit')}
              className={`px-3 py-1.5 rounded-lg border transition-all ${
                activeRiskTab === 'circuit'
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 font-bold'
                  : 'bg-zinc-950 text-zinc-400 border-white/5 hover:text-zinc-200'
              }`}
            >
              Circuit Breaker
            </button>
            <button
              onClick={() => setActiveRiskTab('stress')}
              className={`px-3 py-1.5 rounded-lg border transition-all ${
                activeRiskTab === 'stress'
                  ? 'bg-purple-500/20 text-purple-300 border-purple-500/40 font-bold'
                  : 'bg-zinc-950 text-zinc-400 border-white/5 hover:text-zinc-200'
              }`}
            >
              Stress Scenarios
            </button>
            <button
              onClick={() => setActiveRiskTab('contagion')}
              className={`px-3 py-1.5 rounded-lg border transition-all ${
                activeRiskTab === 'contagion'
                  ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 font-bold'
                  : 'bg-zinc-950 text-zinc-400 border-white/5 hover:text-zinc-200'
              }`}
            >
              Contagion Graph
            </button>
            <button
              onClick={() => setActiveRiskTab('liquidity')}
              className={`px-3 py-1.5 rounded-lg border transition-all ${
                activeRiskTab === 'liquidity'
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-bold'
                  : 'bg-zinc-950 text-zinc-400 border-white/5 hover:text-zinc-200'
              }`}
            >
              Liquidity Constraints
            </button>
          </div>
        </div>

        <div>
          {activeRiskTab === 'circuit' && <CircuitBreakerStatusStrip symbol={selectedTicker} />}
          {activeRiskTab === 'stress' && <HistoricalStressScenarioPicker />}
          {activeRiskTab === 'contagion' && <ContagionGraphCanvas />}
          {activeRiskTab === 'liquidity' && <LiquidityConstraintTable />}
        </div>
      </div>

      {/* Grid 1: Barra Factor Radar + Stress Matrix */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Barra 8-Factor Decomposition (7 Cols) */}
        <div className="lg:col-span-7 flex flex-col gap-3 rounded-xl border border-white/10 bg-zinc-900/40 p-4">
          <div className="flex items-center justify-between border-b border-white/5 pb-3">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              <span className="text-xs font-mono font-bold text-zinc-200 uppercase">
                {t.barraRiskTca.factorRiskDecomp} ({barra?.model || 'BARRA_VN_V3'})
              </span>
            </div>
            <div className="flex items-center gap-3 text-[10px] font-mono">
              <span className="text-zinc-400">
                {t.barraRiskTca.factorRisk} <strong className="text-cyan-400">{barra?.factor_risk_pct ?? 11.25}%</strong>
              </span>
              <span className="text-zinc-400">
                {t.barraRiskTca.specificRisk} <strong className="text-purple-400">{barra?.specific_risk_pct ?? 3.57}%</strong>
              </span>
              <span className="text-zinc-400">
                {t.barraRiskTca.rSquared} <strong className="text-emerald-400">{barra?.portfolio_r_squared ?? 0.759}</strong>
              </span>
            </div>
          </div>

          {/* Factor Breakdown Bars */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
            {barra?.factors.map((f) => (
              <div
                key={f.name}
                className="p-2.5 rounded-lg border border-white/5 bg-zinc-950/60 flex flex-col gap-1.5"
              >
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span className="text-zinc-200 font-semibold">{f.name}</span>
                  <span className={f.exposure >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                    {f.exposure >= 0 ? `+${f.exposure.toFixed(2)}` : f.exposure.toFixed(2)} β
                  </span>
                </div>
                <div className="w-full bg-zinc-800/80 rounded-full h-1.5 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      f.variance_contribution_pct > 20
                        ? 'bg-emerald-400'
                        : f.variance_contribution_pct > 10
                        ? 'bg-cyan-400'
                        : 'bg-amber-400'
                    }`}
                    style={{ width: `${Math.min(100, f.variance_contribution_pct * 1.8)}%` }}
                  />
                </div>
                <div className="flex items-center justify-between text-[9px] font-mono text-zinc-500">
                  <span>{t.barraRiskTca.varContribution} {f.variance_contribution_pct}%</span>
                  <span>{t.barraRiskTca.tStat} {f.t_stat.toFixed(2)}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Asset-Level Factor Exposure Table */}
          <div className="mt-2 rounded-lg border border-white/5 overflow-x-auto bg-zinc-950/40">
            <table className="w-full text-left text-[11px] font-mono">
              <thead className="bg-zinc-900/80 text-zinc-400 uppercase text-[9px] border-b border-white/5">
                <tr>
                  <th className="px-3 py-2">{t.barraRiskTca.thTicker}</th>
                  <th className="px-3 py-2">{t.barraRiskTca.thSector}</th>
                  <th className="px-3 py-2">{t.barraRiskTca.thWeight}</th>
                  <th className="px-3 py-2">{t.barraRiskTca.thBeta}</th>
                  <th className="px-3 py-2">{t.barraRiskTca.thSmb}</th>
                  <th className="px-3 py-2">{t.barraRiskTca.thHml}</th>
                  <th className="px-3 py-2">{t.barraRiskTca.thMom}</th>
                  <th className="px-3 py-2">{t.barraRiskTca.thSpecificRisk}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {barra?.asset_exposures.map((a) => {
                  const isSelected = selectedTicker === a.symbol;
                  return (
                    <tr
                      key={a.symbol}
                      onClick={() => handleSelectSymbol(a.symbol)}
                      className={`hover:bg-white/5 cursor-pointer transition-colors group ${
                        isSelected ? 'bg-cyan-950/30' : ''
                      }`}
                    >
                      <td className="px-3 py-2 font-bold text-zinc-100 flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          <span className="group-hover:text-cyan-300 transition-colors">{a.symbol}</span>
                        </div>
                        <button
                          type="button"
                          onClick={(e) => handleOpenChartStation(e, a.symbol)}
                          className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-cyan-500/20 text-cyan-400 transition-opacity"
                          title={`Open ${a.symbol} in Chart Station`}
                        >
                          <LineChart className="w-3 h-3" />
                        </button>
                      </td>
                      <td className="px-3 py-2 text-zinc-400">{a.sector}</td>
                      <td className="px-3 py-2 text-emerald-400 font-semibold">{a.weight_pct}%</td>
                      <td className="px-3 py-2 text-zinc-300">{a.market_beta.toFixed(2)}</td>
                      <td className="px-3 py-2 text-cyan-300">+{a.size_smb.toFixed(2)}</td>
                      <td className="px-3 py-2 text-amber-300">+{a.value_hml.toFixed(2)}</td>
                      <td className="px-3 py-2 text-purple-300">+{a.momentum.toFixed(2)}</td>
                      <td className="px-3 py-2 text-zinc-400">{a.specific_risk_pct}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Stress Scenarios & CVaR Tail Risk (5 Cols) */}
        <div className="lg:col-span-5 flex flex-col gap-3 rounded-xl border border-white/10 bg-zinc-900/40 p-4">
          <div className="flex items-center justify-between border-b border-white/5 pb-3">
            <div className="flex items-center gap-2">
              <TrendingDown className="w-4 h-4 text-rose-400" />
              <span className="text-xs font-mono font-bold text-zinc-200 uppercase">
                {t.barraRiskTca.stressTitle}
              </span>
            </div>
            <span className="text-[10px] font-mono text-zinc-500">{t.barraRiskTca.stressType}</span>
          </div>

          {/* CVaR Summary Badges */}
          <div className="grid grid-cols-3 gap-2">
            <div className="p-2.5 rounded-lg border border-rose-500/20 bg-rose-950/20 flex flex-col">
              <span className="text-[10px] font-mono text-zinc-400">{t.barraRiskTca.cvar95}</span>
              <span className="text-base font-bold font-mono text-rose-400">
                -{stress?.cvar_95_pct ?? 1.95}%
              </span>
            </div>
            <div className="p-2.5 rounded-lg border border-rose-500/30 bg-rose-950/30 flex flex-col">
              <span className="text-[10px] font-mono text-zinc-400">{t.barraRiskTca.cvar99}</span>
              <span className="text-base font-bold font-mono text-rose-300">
                -{stress?.cvar_99_pct ?? 2.68}%
              </span>
            </div>
            <div className="p-2.5 rounded-lg border border-amber-500/20 bg-amber-950/20 flex flex-col">
              <span className="text-[10px] font-mono text-zinc-400">{t.barraRiskTca.var95}</span>
              <span className="text-base font-bold font-mono text-amber-400">
                -{stress?.var_95_pct ?? 1.42}%
              </span>
            </div>
          </div>

          {/* Risk Warning Box */}
          {stress?.risk_warning && (
            <div className="p-2.5 rounded-lg border border-amber-500/20 bg-amber-500/10 text-[11px] font-mono text-amber-300 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 shrink-0 text-amber-400" />
              <span>{stress.risk_warning}</span>
            </div>
          )}

          {/* Stress Scenarios Cards List */}
          <div className="flex flex-col gap-2 max-h-[380px] overflow-y-auto pr-1">
            {stress?.scenarios.map((sc) => (
              <div
                key={sc.scenario_id}
                className="p-3 rounded-lg border border-white/5 bg-zinc-950/60 flex flex-col gap-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-zinc-100">{sc.name}</span>
                  <span
                    className={`text-[9px] font-mono px-1.5 py-0.5 rounded font-bold ${
                      sc.risk_level === 'CRITICAL'
                        ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                        : sc.risk_level === 'HIGH'
                        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                        : 'bg-zinc-800 text-zinc-300'
                    }`}
                  >
                    {sc.risk_level}
                  </span>
                </div>
                <p className="text-[10px] font-mono text-zinc-400 leading-relaxed">{sc.description}</p>
                <div className="flex items-center justify-between text-[10px] font-mono pt-1 border-t border-white/5">
                  <span className="text-rose-400 font-semibold">
                    Portfolio: {sc.estimated_portfolio_pnl_pct}% (Max Loss: {sc.max_loss_vnd_billion}B)
                  </span>
                  <span className="text-zinc-500">
                    Bench: {sc.benchmark_pnl_pct}% (Alpha: +{sc.alpha_resilience_pct}%)
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Grid 2: Pre-Trade Almgren-Chriss Impact Engine + Smart Router Diagnostics */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Pre-Trade Almgren-Chriss Impact Calculator (6 Cols) */}
        <div className="lg:col-span-6 flex flex-col gap-3 rounded-xl border border-white/10 bg-zinc-900/40 p-4">
          <div className="flex items-center justify-between border-b border-white/5 pb-3">
            <div className="flex items-center gap-2">
              <Calculator className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-mono font-bold text-zinc-200 uppercase">
                {t.barraRiskTca.preTradeTitle}
              </span>
            </div>
            <span className="text-[10px] font-mono text-zinc-500">{t.barraRiskTca.impactModel}</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs font-mono">
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">{t.barraRiskTca.symbolLabel}</label>
              <input
                type="text"
                value={calcSymbol}
                onChange={(e) => setCalcSymbol(e.target.value.toUpperCase())}
                className="w-full px-2.5 py-1.5 rounded-lg border border-white/10 bg-zinc-950 text-zinc-100 font-mono"
              />
            </div>
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">{t.barraRiskTca.orderSizeLabel}</label>
              <input
                type="number"
                value={calcSize}
                onChange={(e) => setCalcSize(Number(e.target.value))}
                className="w-full px-2.5 py-1.5 rounded-lg border border-white/10 bg-zinc-950 text-zinc-100 font-mono"
              />
            </div>
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">{t.barraRiskTca.advLabel}</label>
              <input
                type="number"
                value={calcAdv}
                onChange={(e) => setCalcAdv(Number(e.target.value))}
                className="w-full px-2.5 py-1.5 rounded-lg border border-white/10 bg-zinc-950 text-zinc-100 font-mono"
              />
            </div>
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">{t.barraRiskTca.arrivalPriceLabel}</label>
              <input
                type="number"
                value={calcPrice}
                onChange={(e) => setCalcPrice(Number(e.target.value))}
                className="w-full px-2.5 py-1.5 rounded-lg border border-white/10 bg-zinc-950 text-zinc-100 font-mono"
              />
            </div>
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">{t.barraRiskTca.sideLabel}</label>
              <select
                value={calcSide}
                onChange={(e) => setCalcSide(e.target.value as 'BUY' | 'SELL')}
                className="w-full px-2.5 py-1.5 rounded-lg border border-white/10 bg-zinc-950 text-zinc-100 font-mono"
              >
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </select>
            </div>
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">{t.barraRiskTca.volLabel}</label>
              <input
                type="number"
                step="0.005"
                value={calcVol}
                onChange={(e) => setCalcVol(Number(e.target.value))}
                className="w-full px-2.5 py-1.5 rounded-lg border border-white/10 bg-zinc-950 text-zinc-100 font-mono"
              />
            </div>
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">{t.barraRiskTca.participationLabel}</label>
              <input
                type="number"
                step="0.01"
                value={calcParticipation}
                onChange={(e) => setCalcParticipation(Number(e.target.value))}
                className="w-full px-2.5 py-1.5 rounded-lg border border-white/10 bg-zinc-950 text-zinc-100 font-mono"
              />
            </div>
          </div>

          <button
            onClick={handleRunImpactCalc}
            disabled={preTradeMutation.isPending}
            className="mt-1 w-full py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5" />
            <span>{preTradeMutation.isPending ? t.barraRiskTca.calculatingImpact : t.barraRiskTca.estimateBtn}</span>
          </button>

          {/* Calculation Output */}
          {impactResult && (
            <div className="p-3.5 rounded-lg border border-emerald-500/20 bg-emerald-950/20 flex flex-col gap-2 font-mono text-xs">
              <div className="flex items-center justify-between text-emerald-400 font-bold border-b border-emerald-500/20 pb-1.5">
                <span>{t.barraRiskTca.estimatedImpact} {impactResult.estimated_impact_bps} BPS</span>
                <span className="text-zinc-200">{t.barraRiskTca.totalCost} {impactResult.total_cost_bps} BPS</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px] text-zinc-300">
                <div>{t.barraRiskTca.orderNotional} {(impactResult.order_notional_vnd / 1_000_000).toFixed(1)}M VND</div>
                <div>{t.barraRiskTca.execPrice} {impactResult.estimated_execution_price.toLocaleString()} VND</div>
                <div>{t.barraRiskTca.spreadCost} {impactResult.spread_cost_bps} bps</div>
                <div>{t.barraRiskTca.timingRisk} {impactResult.timing_risk_bps} bps</div>
                <div>{t.barraRiskTca.advFootprint} {impactResult.order_adv_pct}%</div>
                <div className="text-cyan-300 font-bold">
                  {t.barraRiskTca.recommended} {impactResult.recommended_algo} ({impactResult.recommended_duration_min} min)
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Smart Order Router & Broker Diagnostics (6 Cols) */}
        <div className="lg:col-span-6 flex flex-col gap-3 rounded-xl border border-white/10 bg-zinc-900/40 p-4">
          <div className="flex items-center justify-between border-b border-white/5 pb-3">
            <div className="flex items-center gap-2">
              <Server className="w-4 h-4 text-cyan-400" />
              <span className="text-xs font-mono font-bold text-zinc-200 uppercase">
                {t.barraRiskTca.routerTitle}
              </span>
            </div>
            <span className="text-[10px] font-mono text-emerald-400">
              {t.barraRiskTca.roundtripLatency} {routing?.avg_roundtrip_latency_ms ?? 7.4}ms
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {routing?.routers.map((r) => (
              <div
                key={r.broker}
                className="p-2.5 rounded-lg border border-white/5 bg-zinc-950/60 flex flex-col gap-1"
              >
                <div className="flex items-center justify-between text-xs font-mono font-bold">
                  <span className="text-zinc-100">{r.broker}</span>
                  <span className={`text-[9px] px-1.5 py-0.2 rounded ${r.status === 'HEALTHY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-300'}`}>
                    {r.status}
                  </span>
                </div>
                <div className="text-[10px] font-mono text-zinc-400">{r.channel}</div>
                <div className="flex items-center justify-between text-[10px] font-mono text-zinc-400 pt-1 border-t border-white/5">
                  <span>Ping: {r.ping_ms}ms</span>
                  <span className="text-emerald-400">Fill: {r.fill_rate_pct}%</span>
                </div>
              </div>
            ))}
          </div>

          {/* Active Slicing Queues */}
          <div className="mt-1 flex flex-col gap-1.5">
            <span className="text-[10px] font-mono text-zinc-400 uppercase font-semibold">
              {t.barraRiskTca.activeQueuesTitle}
            </span>
            {routing?.active_queues.map((q) => (
              <div
                key={q.queue_id}
                className="p-2 rounded-lg border border-white/5 bg-zinc-950/80 flex items-center justify-between text-[11px] font-mono"
              >
                <div className="flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-amber-400" />
                  <span className="font-bold text-zinc-200">{q.symbol}</span>
                  <span className="text-zinc-400">[{q.algo}]</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-zinc-400">
                    {t.barraRiskTca.slicesLabel} {q.active_slices}/{q.total_slices}
                  </span>
                  <span className="text-emerald-400 font-bold">{q.completion_pct}%</span>
                  <span className="text-[10px] text-cyan-300">OBI: {q.obi_pressure > 0 ? `+${q.obi_pressure}` : q.obi_pressure}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Grid 3: Post-Trade TCA Blotter & Implementation Shortfall Report */}
      <div className="rounded-xl border border-white/10 bg-zinc-900/40 p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between border-b border-white/5 pb-3">
          <div className="flex items-center gap-2">
            <ReceiptText className="w-4 h-4 text-purple-400" />
            <span className="text-xs font-mono font-bold text-zinc-200 uppercase">
              {t.barraRiskTca.postTradeTitle}
            </span>
          </div>
          <div className="flex items-center gap-3 text-[10px] font-mono">
            <span className="text-zinc-400">
              {t.barraRiskTca.avgIs} <strong className="text-emerald-400">{postTrade?.summary.average_is_bps ?? 10.79} bps</strong>
            </span>
            <span className="text-zinc-400">
              {t.barraRiskTca.avgSlippage} <strong className="text-cyan-400">{postTrade?.summary.average_slippage_bps ?? 10.70} bps</strong>
            </span>
            <span className="text-zinc-400">
              {t.barraRiskTca.tradedVolume} <strong className="text-zinc-200">{postTrade?.summary.total_traded_value_billion_vnd ?? 4.825}B VND</strong>
            </span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[11px] font-mono">
            <thead className="bg-zinc-900/80 text-zinc-400 uppercase text-[9px] border-b border-white/5">
              <tr>
                <th className="px-3 py-2.5">{t.barraRiskTca.thTradeId}</th>
                <th className="px-3 py-2.5">{t.barraRiskTca.thTime}</th>
                <th className="px-3 py-2.5">{t.barraRiskTca.symbolLabel}</th>
                <th className="px-3 py-2.5">{t.barraRiskTca.sideLabel}</th>
                <th className="px-3 py-2.5">{t.barraRiskTca.thFilledParent}</th>
                <th className="px-3 py-2.5">{t.barraRiskTca.thAvgFill}</th>
                <th className="px-3 py-2.5">{t.barraRiskTca.thBenchmark}</th>
                <th className="px-3 py-2.5">{t.barraRiskTca.thImpactBps}</th>
                <th className="px-3 py-2.5">{t.barraRiskTca.thSlippageBps}</th>
                <th className="px-3 py-2.5">{t.barraRiskTca.thIsBps}</th>
                <th className="px-3 py-2.5">{t.barraRiskTca.thBrokerAlgo}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {postTrade?.trades.map((tRow) => (
                <tr key={tRow.trade_id} className="hover:bg-white/5 transition-colors">
                  <td className="px-3 py-2.5 font-bold text-zinc-300">{tRow.trade_id}</td>
                  <td className="px-3 py-2.5 text-zinc-400">{tRow.timestamp}</td>
                  <td className="px-3 py-2.5 font-bold text-zinc-100 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                    <span>{tRow.symbol}</span>
                  </td>
                  <td className={`px-3 py-2.5 font-bold ${tRow.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {tRow.side}
                  </td>
                  <td className="px-3 py-2.5 text-zinc-300">
                    {tRow.filled_quantity.toLocaleString()} / {tRow.parent_quantity.toLocaleString()}
                  </td>
                  <td className="px-3 py-2.5 text-zinc-200">{tRow.avg_fill_price.toLocaleString()}</td>
                  <td className="px-3 py-2.5 text-zinc-400">{tRow.benchmark_price.toLocaleString()}</td>
                  <td className="px-3 py-2.5 text-cyan-300">+{tRow.pre_trade_impact_bps.toFixed(1)}</td>
                  <td className="px-3 py-2.5 text-amber-300">+{tRow.post_trade_slippage_bps.toFixed(1)}</td>
                  <td className="px-3 py-2.5 font-bold text-emerald-400">+{tRow.implementation_shortfall_bps.toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-zinc-400">
                    {tRow.broker} ({tRow.algo})
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
