import React, { useEffect, useState, useRef } from 'react';
import { X, Building2, RefreshCw, AlertTriangle, Users, Truck, DollarSign } from 'lucide-react';
import { advancedQuantApi, CorporateGraphResponse } from '../../api/advancedQuant';

interface CorporateGraphDrawerProps {
  symbol: string;
  isOpen: boolean;
  onClose: () => void;
}

export const CorporateGraphDrawer: React.FC<CorporateGraphDrawerProps> = ({ symbol, isOpen, onClose }) => {
  const [data, setData] = useState<CorporateGraphResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rafRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Clear stale state on symbol/open change
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
            const res = await advancedQuantApi.getCorporateGraph(symbol, controller.signal);
            setData(res);
          } catch (err: any) {
            if (err?.name !== 'AbortError') {
              setError(err?.message || 'Failed to fetch corporate network graph');
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
  }, [symbol, isOpen]);

  const handleManualRefresh = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsLoading(true);
    setError(null);
    try {
      const res = await advancedQuantApi.getCorporateGraph(symbol, controller.signal);
      setData(res);
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        setError(err?.message || 'Failed to fetch corporate network graph');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const getNodeIcon = (cat: string) => {
    switch (cat) {
      case 'FOCUS_COMPANY':
        return <Building2 className="w-4 h-4 text-emerald-400" />;
      case 'MAJOR_SHAREHOLDER':
        return <Users className="w-4 h-4 text-cyan-400" />;
      case 'FOREIGN_INVESTOR':
        return <Users className="w-4 h-4 text-purple-400" />;
      case 'SUPPLIER':
        return <Truck className="w-4 h-4 text-amber-400" />;
      case 'CUSTOMER':
        return <DollarSign className="w-4 h-4 text-sky-400" />;
      default:
        return <Building2 className="w-4 h-4 text-zinc-400" />;
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-all font-mono">
      <div className="w-full max-w-2xl h-full bg-zinc-950 border-l border-white/10 flex flex-col shadow-2xl animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10 bg-zinc-900/60">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-wider">
                Corporate Topology Drawer: {symbol}
              </h2>
              <span className="text-[11px] text-zinc-400">
                Institutional Ownership, Subsidiaries & Supply Network
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleManualRefresh}
              disabled={isLoading}
              className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-100 border border-white/5 transition-all"
              title="Refresh Corporate Network"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-emerald-400' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-100 border border-white/5 transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
          {isLoading ? (
            <div className="py-12 flex items-center justify-center gap-2 text-zinc-500">
              <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
              <span>Synthesizing corporate ownership & Tier-1 supply chain topology...</span>
            </div>
          ) : error ? (
            <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/20 text-rose-300 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-400" />
              <span>{error}</span>
            </div>
          ) : data ? (
            <div className="flex flex-col gap-3">
              <div className="p-2.5 rounded bg-zinc-900/60 border border-white/5 flex items-center justify-between text-[11px]">
                <span className="text-zinc-400">Sector Classification: <strong className="text-zinc-100">{data.sector}</strong></span>
                <span className="text-emerald-400 font-bold">{data.nodes_count} Nodes | {data.edges_count} Edges</span>
              </div>

              {/* Dual Table: Entities vs Relationships */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {/* Entities (Nodes) */}
                <div className="p-3 rounded-lg bg-zinc-900/40 border border-white/5 flex flex-col gap-2">
                  <span className="text-[11px] font-bold text-zinc-300 border-b border-white/5 pb-1">
                    Corporate Entities & Stakeholders
                  </span>
                  <div className="flex flex-col gap-1.5 max-h-72 overflow-y-auto">
                    {data.nodes.map((n) => (
                      <div key={n.id} className="flex items-center justify-between p-2 rounded bg-zinc-950/60 text-[11px]">
                        <div className="flex items-center gap-2">
                          {getNodeIcon(n.category)}
                          <div className="flex flex-col">
                            <span className="font-bold text-zinc-200">{n.label}</span>
                            <span className="text-[10px] text-zinc-500">{n.role}</span>
                          </div>
                        </div>
                        {n.ownership_pct > 0 && (
                          <span className="text-cyan-300 font-semibold">{n.ownership_pct}%</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Relationships (Edges) */}
                <div className="p-3 rounded-lg bg-zinc-900/40 border border-white/5 flex flex-col gap-2">
                  <span className="text-[11px] font-bold text-zinc-300 border-b border-white/5 pb-1">
                    Ownership Stakes & Commercial Links
                  </span>
                  <div className="flex flex-col gap-1.5 max-h-72 overflow-y-auto">
                    {data.edges.map((e, idx) => (
                      <div key={idx} className="flex items-center justify-between p-2 rounded bg-zinc-950/60 text-[11px]">
                        <div className="flex flex-col">
                          <span className="text-zinc-300 font-semibold">{e.label}</span>
                          <span className="text-[10px] text-zinc-500">{e.relation}</span>
                        </div>
                        <span className="text-amber-400 font-bold">{e.weight}% Intensity</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
export default CorporateGraphDrawer;


