import React, { useState, useEffect, useRef } from 'react';
import { Play, Clock, ArrowUpRight, ArrowDownRight, RefreshCw, AlertTriangle, CheckCircle2, LineChart } from 'lucide-react';
import { useExecutionBlotter } from '../../hooks/usePortfolioState';
import { useUiStore } from '../../store/uiStore';
import { useTranslation } from '../../i18n';
import { TotpRebalanceModal } from './TotpRebalanceModal';
import { PaperDaemonPanel } from './PaperDaemonPanel';
import { advancedQuantApi, PortfolioRebalanceExecuteResponse } from '../../api/advancedQuant';

export const ExecutionBlotterView: React.FC = () => {
  const { data: orders, isLoading, isError, refetch } = useExecutionBlotter();
  const selectedTicker = useUiStore((state) => state.selectedTicker);
  const setSelectedTicker = useUiStore((state) => state.setSelectedTicker);
  const setActiveModule = useUiStore((state) => state.setActiveModule);
  const { t } = useTranslation();

  const [isRebalanceModalOpen, setIsRebalanceModalOpen] = useState(false);
  const [rebalanceExecuting, setRebalanceExecuting] = useState(false);
  const [rebalanceStatus, setRebalanceStatus] = useState<string | null>(null);
  const [rebalanceResult, setRebalanceResult] = useState<PortfolioRebalanceExecuteResponse | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const rafIdRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
      }
    };
  }, []);

  const handleSelectSymbol = (symbol: string) => {
    setSelectedTicker(symbol);
  };

  const handleOpenChartStation = (e: React.MouseEvent, symbol: string) => {
    e.stopPropagation();
    setSelectedTicker(symbol);
    setActiveModule('chart_station');
  };

  const handleExecuteRebalance = () => {
    setIsRebalanceModalOpen(true);
  };

  const handleConfirmRebalance = async (totpCode: string) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setRebalanceExecuting(true);
    setRebalanceResult(null);
    setRebalanceStatus(t.executionBlotter.calcOrdersViaRouter);

    try {
      const res = await advancedQuantApi.executePortfolioRebalance({
        totp_code: totpCode,
        strategy_id: 'ALPHA_HRP_V2',
        target_portfolio: { FPT: 0.25, HPG: 0.25, MBB: 0.25, MWG: 0.25 },
        portfolio_value: 1_000_000_000.0,
        routing_algo: 'TWAP',
        duration_minutes: 60,
      }, controller.signal);

      if (!controller.signal.aborted) {
        if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = requestAnimationFrame(() => {
          setRebalanceResult(res);
          setRebalanceStatus(t.executionBlotter.batchSubmitted);
          setRebalanceExecuting(false);
          refetch();
          setTimeout(() => setRebalanceStatus(null), 5000);
        });
      }
    } catch (err: unknown) {
      if (!controller.signal.aborted) {
        setRebalanceExecuting(false);
        const errMsg = err instanceof Error ? err.message : 'Rebalance authorization failed';
        setRebalanceStatus(`Failed: ${errMsg}`);
        throw err;
      }
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-zinc-500 font-mono text-xs gap-3">
        <Clock className="w-8 h-8 text-cyan-400 animate-spin" />
        <span>{t.executionBlotter.connectingOms}</span>
      </div>
    );
  }

  if (isError || !orders) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-rose-400 font-mono text-xs gap-3 border border-rose-500/20 bg-rose-950/10 rounded-xl p-6">
        <AlertTriangle className="w-8 h-8 text-rose-400" />
        <span>{t.executionBlotter.failedBlotter}</span>
        <button
          onClick={() => refetch()}
          className="px-3 py-1.5 rounded bg-rose-900/60 hover:bg-rose-800 text-white flex items-center gap-1.5"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>{t.executionBlotter.reconnectBtn}</span>
        </button>
      </div>
    );
  }

  const totalExecutedVnd = orders
    .filter((o) => o.status === 'FILLED')
    .reduce((sum, o) => sum + o.filledQty * o.price, 0);

  const pendingVnd = orders
    .filter((o) => o.status === 'PENDING' || o.status === 'ROUTING')
    .reduce((sum, o) => sum + (o.qty - o.filledQty) * o.price, 0);

  return (
    <div className="flex flex-col gap-4 font-mono select-none">
      {/* Paper Trading Daemon & Execution Lifecycle Controls */}
      <PaperDaemonPanel onRefresh={refetch} />

      {/* OMS Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <div className="glass-card rounded-xl p-4 flex flex-col gap-1 border-emerald-500/20 bg-emerald-950/10">
          <div className="text-xs font-mono text-zinc-400">{t.executionBlotter.totalExecutedValue}</div>
          <div className="text-xl font-bold font-mono text-emerald-400">{totalExecutedVnd.toLocaleString()} VND</div>
          <div className="text-[10px] font-mono text-zinc-500">
            {t.executionBlotter.activeOrders}: {orders.length}
          </div>
        </div>

        <div className="glass-card rounded-xl p-4 flex flex-col gap-1 border-cyan-500/20 bg-cyan-950/10">
          <div className="text-xs font-mono text-zinc-400">{t.executionBlotter.estimatedSlippage}</div>
          <div className="text-xl font-bold font-mono text-cyan-400">-0.04%</div>
          <div className="text-[10px] font-mono text-zinc-500">{t.executionBlotter.vwapDeviation}</div>
        </div>

        <div className="glass-card rounded-xl p-4 flex flex-col gap-1 border-amber-500/20 bg-amber-950/10">
          <div className="text-xs font-mono text-zinc-400">{t.executionBlotter.pendingRoutingValue}</div>
          <div className="text-xl font-bold font-mono text-amber-400">{pendingVnd.toLocaleString()} VND</div>
          <div className="text-[10px] font-mono text-zinc-500">{t.executionBlotter.smartSlicerActive}</div>
        </div>

        <div className="glass-card rounded-xl p-4 flex flex-col gap-1 border-purple-500/20 bg-purple-950/10">
          <div className="text-xs font-mono text-zinc-400">{t.executionBlotter.brokerGateway}</div>
          <div className="text-xl font-bold font-mono text-purple-300">VCI / SSI MULTI-ROUTE</div>
          <div className="text-[10px] font-mono text-zinc-500">{t.executionBlotter.fixProtocol}</div>
        </div>
      </div>

      {/* Rebalance Executed Banner (if recently submitted) */}
      {rebalanceResult && (
        <div className="p-4 rounded-xl bg-emerald-950/30 border border-emerald-500/40 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span className="font-bold text-xs text-emerald-300">
                Institutional Rebalance Dispatched ({rebalanceResult.strategy_id})
              </span>
            </div>
            <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-bold">
              TOTP Verified
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
            <div className="bg-zinc-950/80 p-2 rounded border border-white/5">
              <span className="text-[10px] text-zinc-400">Est. Turnover:</span>
              <div className="font-bold text-emerald-400">{(rebalanceResult.estimated_turnover * 100).toFixed(1)}%</div>
            </div>
            <div className="bg-zinc-950/80 p-2 rounded border border-white/5">
              <span className="text-[10px] text-zinc-400">Est. Cost:</span>
              <div className="font-bold text-cyan-400">{rebalanceResult.estimated_cost_vnd.toLocaleString()} VND</div>
            </div>
            <div className="bg-zinc-950/80 p-2 rounded border border-white/5">
              <span className="text-[10px] text-zinc-400">Orders Dispatched:</span>
              <div className="font-bold text-zinc-200">{rebalanceResult.orders.length} child routes</div>
            </div>
            <div className="bg-zinc-950/80 p-2 rounded border border-white/5">
              <span className="text-[10px] text-zinc-400">Liquidity Violations:</span>
              <div className="font-bold text-emerald-400">{rebalanceResult.liquidity_violations.length === 0 ? 'None (Safe)' : rebalanceResult.liquidity_violations.length}</div>
            </div>
          </div>
        </div>
      )}

      {/* Execution Order Blotter Table */}
      <div className="rounded-xl border border-white/10 bg-zinc-950/40 overflow-x-auto">
        <div className="p-3 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-mono font-bold text-zinc-200 uppercase">
              {t.executionBlotter.orderLogTitle}
            </span>
          </div>

          <div className="flex items-center gap-3">
            {rebalanceStatus && (
              <span className="text-[11px] font-mono text-emerald-400 flex items-center gap-1.5 animate-pulse">
                <CheckCircle2 className="w-3.5 h-3.5" />
                {rebalanceStatus}
              </span>
            )}
            <button
              disabled={rebalanceExecuting}
              onClick={handleExecuteRebalance}
              className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-mono text-xs flex items-center gap-1.5 shadow-sm shadow-emerald-500/20"
            >
              <Play className={`w-3 h-3 ${rebalanceExecuting ? 'animate-spin' : ''}`} />
              <span>{rebalanceExecuting ? t.executionBlotter.executingStatus : t.executionBlotter.executeRebalance}</span>
            </button>
          </div>
        </div>

        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-zinc-900/80 text-zinc-400 uppercase text-[10px] tracking-wider border-b border-white/10">
            <tr>
              <th className="px-4 py-3">{t.executionBlotter.thOrderId}</th>
              <th className="px-4 py-3">{t.executionBlotter.thTime}</th>
              <th className="px-4 py-3">{t.executionBlotter.thSymbol}</th>
              <th className="px-4 py-3">{t.executionBlotter.thSide}</th>
              <th className="px-4 py-3">{t.executionBlotter.thType}</th>
              <th className="px-4 py-3">{t.executionBlotter.thAlgo}</th>
              <th className="px-4 py-3">{t.executionBlotter.thQty}</th>
              <th className="px-4 py-3">{t.executionBlotter.thPrice}</th>
              <th className="px-4 py-3">{t.executionBlotter.thFilled}</th>
              <th className="px-4 py-3">{t.executionBlotter.thBroker}</th>
              <th className="px-4 py-3 text-right">{t.executionBlotter.thStatus}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {orders.map((order) => {
              const isSelected = selectedTicker === order.symbol;
              return (
                <tr
                  key={order.orderId}
                  onClick={() => handleSelectSymbol(order.symbol)}
                  className={`hover:bg-white/5 transition-colors cursor-pointer group ${
                    isSelected ? 'bg-cyan-950/30' : ''
                  }`}
                >
                  <td className="px-4 py-3 font-semibold text-zinc-300">{order.orderId}</td>
                  <td className="px-4 py-3 text-zinc-500">{order.timestamp}</td>
                  <td className="px-4 py-3 font-bold text-zinc-100 flex items-center justify-between">
                    <span className="group-hover:text-cyan-300 transition-colors">
                      {order.symbol}
                    </span>
                    <button
                      type="button"
                      onClick={(e) => handleOpenChartStation(e, order.symbol)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-cyan-500/20 text-cyan-400 transition-opacity"
                      title={`Open ${order.symbol} in Chart Station`}
                    >
                      <LineChart className="w-3.5 h-3.5" />
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`flex items-center gap-1 font-bold ${
                      order.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'
                    }`}>
                      {order.side === 'BUY' ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                      {order.side}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-zinc-400">{order.orderType}</td>
                  <td className="px-4 py-3 text-cyan-300">{order.algoType}</td>
                  <td className="px-4 py-3 text-zinc-200">{order.qty.toLocaleString()}</td>
                  <td className="px-4 py-3 text-zinc-200">{order.price.toLocaleString()}</td>
                  <td className="px-4 py-3 text-zinc-300">
                    {order.filledQty.toLocaleString()} ({((order.filledQty / order.qty) * 100).toFixed(0)}%)
                  </td>
                  <td className="px-4 py-3 text-zinc-400">{order.broker}</td>
                  <td className="px-4 py-3 text-right">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                      order.status === 'FILLED'
                        ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-500/30'
                        : order.status === 'ROUTING'
                        ? 'bg-cyan-950/80 text-cyan-400 border border-cyan-500/30'
                        : order.status === 'PENDING'
                        ? 'bg-amber-950/80 text-amber-400 border border-amber-500/30'
                        : 'bg-rose-950/80 text-rose-400 border border-rose-500/30'
                    }`}>
                      {order.status}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* 2FA Rebalance Modal */}
      <TotpRebalanceModal
        isOpen={isRebalanceModalOpen}
        onClose={() => setIsRebalanceModalOpen(false)}
        onConfirm={handleConfirmRebalance}
        title={t.executionBlotter.executeRebalance}
        description={t.executionBlotter.calcOrdersViaRouter}
        actionType="REBALANCE"
      />
    </div>
  );
};

