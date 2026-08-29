import React, { useEffect, useState, useRef } from 'react';
import { Network, RefreshCw, AlertTriangle, ShieldCheck, ShieldAlert } from 'lucide-react';
import { advancedQuantApi, ContagionRiskGraphResponse } from '../../api/advancedQuant';

export const ContagionGraphCanvas: React.FC = () => {
  const [data, setData] = useState<ContagionRiskGraphResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rafRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    let timeoutId: NodeJS.Timeout;
    const startDebounce = () => {
      timeoutId = setTimeout(() => {
        rafRef.current = requestAnimationFrame(async () => {
          setIsLoading(true);
          setError(null);
          try {
            const res = await advancedQuantApi.getContagionGraph(controller.signal);
            setData(res);
          } catch (err: any) {
            if (err?.name !== 'AbortError') {
              setError(err?.message || 'Failed to fetch contagion graph');
            }
          } finally {
            setIsLoading(false);
          }
        });
      }, 500);
    };

    startDebounce();

    return () => {
      clearTimeout(timeoutId);
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }
      controller.abort();
    };
  }, []);

  const handleManualRefresh = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsLoading(true);
    setError(null);
    try {
      const res = await advancedQuantApi.getContagionGraph(controller.signal);
      setData(res);
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        setError(err?.message || 'Failed to fetch contagion graph');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 p-3.5 rounded-xl border border-white/10 bg-zinc-950/70 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
        <div className="flex items-center gap-2">
          <Network className="w-4 h-4 text-cyan-400" />
          <span className="font-bold text-zinc-100 uppercase tracking-wider">
            Cross-Market Contagion Network Topology
          </span>
        </div>
        <button
          onClick={handleManualRefresh}
          disabled={isLoading}
          className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-400 border border-white/5"
          title="Refresh Contagion Topology"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-cyan-400' : ''}`} />
        </button>
      </div>

      {isLoading ? (
        <div className="py-8 flex items-center justify-center gap-2 text-zinc-500">
          <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
          <span>Mapping systemic risk transmission channels...</span>
        </div>
      ) : error ? (
        <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/20 text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{error}</span>
        </div>
      ) : data ? (
        <div className="flex flex-col gap-3">
          {/* Top Banner Status */}
          <div className="flex items-center justify-between p-2.5 rounded bg-zinc-900/60 border border-white/5">
            <div className="flex items-center gap-2">
              {data.is_safe ? <ShieldCheck className="w-4 h-4 text-emerald-400" /> : <ShieldAlert className="w-4 h-4 text-amber-400" />}
              <span>Stress Level: <strong className="text-zinc-100">{data.stress_level}</strong></span>
            </div>
            <div className="flex items-center gap-4 text-zinc-400 text-[11px]">
              <span>Risk Multiplier: <strong className="text-cyan-300">{(data.risk_multiplier * 100).toFixed(0)}%</strong></span>
              <span>Dominant Source: <strong className="text-purple-300">{data.dominant_source}</strong></span>
            </div>
          </div>

          {/* Node and Transmission Table */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Global Nodes */}
            <div className="p-3 rounded-lg bg-zinc-900/40 border border-white/5 flex flex-col gap-2">
              <span className="text-[11px] font-bold text-zinc-300 border-b border-white/5 pb-1">
                Monitored Market Indices
              </span>
              <div className="flex flex-col gap-1.5">
                {data.nodes.map((n) => (
                  <div key={n.id} className="flex items-center justify-between p-2 rounded bg-zinc-950/60 text-[11px]">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${n.type === 'target' ? 'bg-emerald-400' : 'bg-cyan-400'}`} />
                      <span className="font-bold text-zinc-200">{n.label}</span>
                    </div>
                    <span className="text-zinc-400">Stress: {(n.stress * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Edge Spillover Channels */}
            <div className="p-3 rounded-lg bg-zinc-900/40 border border-white/5 flex flex-col gap-2">
              <span className="text-[11px] font-bold text-zinc-300 border-b border-white/5 pb-1">
                Active Spillover Channels
              </span>
              <div className="flex flex-col gap-1.5">
                {data.edges.map((e, idx) => (
                  <div key={idx} className="flex items-center justify-between p-2 rounded bg-zinc-950/60 text-[11px]">
                    <div className="flex items-center gap-1.5 text-zinc-300 font-semibold">
                      <span>{e.source}</span>
                      <span className="text-zinc-600">→</span>
                      <span>{e.target}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-cyan-300">Corr: {e.correlation.toFixed(2)}</span>
                      <span className="text-amber-400 font-bold">+{e.transmission_bps} bps</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="text-[11px] text-zinc-400 bg-zinc-900/40 p-2.5 rounded border border-white/5">
            <strong>Risk Narrative:</strong> {data.narrative}
          </div>
        </div>
      ) : null}
    </div>
  );
};
export default ContagionGraphCanvas;

