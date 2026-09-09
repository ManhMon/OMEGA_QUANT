import { useEffect, useRef, useState } from 'react';
import { apiClient, ControlDynamicUniverseParams, DynamicUniverseItem } from '../../../api/client';
import { useUiStore } from '../../../store/uiStore';
import type { AlphasTabProps } from '../controlCenterTypes';

export function AlphasTab({ runOperation, onCompute, universe, setUniverse }: AlphasTabProps) {
  const [items, setItems] = useState<DynamicUniverseItem[]>([]); const [filters, setFilters] = useState<ControlDynamicUniverseParams>({ universe_preset: 'default', top_n: 20, sector_filter: '' }); const addToast = useUiStore((state) => state.addToast); const generation = useRef(0);
  useEffect(() => { const controller = new AbortController(); const current = ++generation.current; const params = { ...filters, sector_filter: filters.sector_filter || undefined }; void apiClient.getControlDynamicUniverse(params, controller.signal).then((response) => { const { items: next, hasInvalidItems } = parseDynamicUniverseItems(response); if (current === generation.current) { setItems(next); if (hasInvalidItems) addToast({ type: 'error', title: 'Alpha telemetry failed', message: 'Invalid alpha telemetry response.' }); } }).catch((error) => { if (!controller.signal.aborted && current === generation.current) { setItems([]); addToast({ type: 'error', title: 'Alpha telemetry failed', message: error instanceof Error ? error.message : 'Unexpected telemetry error.' }); } }); return () => controller.abort(); }, [addToast, filters]);
  return <section className="space-y-3 font-mono"><div className="grid gap-2 sm:grid-cols-3"><input aria-label="Universe preset" value={filters.universe_preset} onChange={(event) => setFilters({ ...filters, universe_preset: event.target.value })} className="rounded border border-white/10 bg-zinc-900 p-2 text-xs" /><input aria-label="Top ranked symbols" type="number" min="1" value={filters.top_n} onChange={(event) => setFilters({ ...filters, top_n: Number(event.target.value) || 1 })} className="rounded border border-white/10 bg-zinc-900 p-2 text-xs" /><input aria-label="Sector filter" value={filters.sector_filter} onChange={(event) => setFilters({ ...filters, sector_filter: event.target.value })} className="rounded border border-white/10 bg-zinc-900 p-2 text-xs" /></div><input aria-label="Alpha universe" value={universe} onChange={(event) => setUniverse(event.target.value)} className="w-full rounded border border-white/10 bg-zinc-900 p-2 text-xs" /><button className="rounded bg-cyan-400 px-3 py-2 text-xs font-bold text-zinc-950" onClick={() => void runOperation('Compute alphas', () => onCompute({ universe: universe.split(',').map((symbol) => symbol.trim()).filter(Boolean), alpha_families: ['MOMENTUM'] }))}>COMPUTE ALPHAS</button><p className="text-xs text-zinc-400">{items.length} ranked symbols</p><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{items.map((item) => <div key={item.symbol} className="rounded border border-white/10 bg-zinc-900 p-3 text-xs"><b>{item.rank}. {item.symbol}</b><p className="mt-1 text-zinc-400">{item.sector} | {item.status_label}</p></div>)}</div></section>;
}

function isDynamicUniverseItem(item: unknown): item is DynamicUniverseItem {
  if (!item || typeof item !== 'object') return false;
  const value = item as Record<string, unknown>;
  return Number.isFinite(value.rank) && typeof value.symbol === 'string' && value.symbol.trim() !== '' && typeof value.sector === 'string' && value.sector.trim() !== '' && ['QUALIFIED', 'WATCH', 'DISTRESS', 'DELISTED'].includes(value.status_label as string);
}

function parseDynamicUniverseItems(response: unknown): { items: DynamicUniverseItem[]; hasInvalidItems: boolean } {
  if (!response || typeof response !== 'object' || !Array.isArray((response as { items?: unknown }).items)) throw new Error('Invalid alpha telemetry response.');
  const items = (response as { items: unknown[] }).items;
  return { items: items.filter(isDynamicUniverseItem), hasInvalidItems: items.some((item) => !isDynamicUniverseItem(item)) };
}
