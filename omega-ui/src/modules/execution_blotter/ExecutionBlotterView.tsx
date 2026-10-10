import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useUiStore } from '../../store/uiStore';
import { PaperDaemonPanel, requestExecutionData, executionRecord, executionNumber, executionText, executionClock } from './PaperDaemonPanel';

type Row = Record<string, unknown>;
const invalid = (): never => { throw new Error('Execution data unavailable'); };
const rows = (value: unknown): Row[] => Array.isArray(value) && value.length <= 5000 ? value.map(executionRecord) : invalid();
const choice = (value: unknown, options: string[]): string => typeof value === 'string' && options.includes(value) ? value : invalid();
const boolean = (value: unknown): boolean => typeof value === 'boolean' ? value : invalid();
const count = (value: unknown): number => {
  const number = executionNumber(value, 0, 5000);
  return Number.isInteger(number) ? number : invalid();
};
const same = (left: number, right: number) => Math.abs(left - right) <= Math.max(1, Math.abs(right)) * 1e-9;
const unique = (values: string[]) => { if (new Set(values).size !== values.length) invalid(); };

export interface ExecutionOrder {
  orderId: string; parentOrderId: string | null; timestamp: string; availableAt: string;
  symbol: string; side: string; orderType: string; qty: number; price: number; filledQty: number;
  status: string; broker: string; venue: string; algoType: string; sequence: number | null;
}
interface ExecutionParent {
  id: string; symbol: string; side: string; algo: string; target: number; filled: number;
  completion: number | null; complete: boolean; slices: ExecutionOrder[];
}
interface Slippage { id: string; venue: string; side: string; quantity: number; arrival: number; price: number; fee: number; bps: number }
interface Settlement {
  id: string; symbol: string; broker: string; side: string; trade: string; expected: string;
  confirmed: boolean; brokerAt: string | null; settledAt: string | null; availableAt: string | null;
  cash: number | null; shares: number | null; skipped: string[];
}
export interface ExecutionData {
  cutoff: string; orders: ExecutionOrder[]; parents: ExecutionParent[]; standalone: ExecutionOrder[];
  points: Slippage[]; venues: { venue: string; count: number; notional: number; bps: number }[];
  excluded: number; settlements: Settlement[];
}

export function validateExecutionData(values: unknown[], cutoff: string): ExecutionData {
  if (values.length !== 4) return invalid();
  const clock = executionClock(cutoff);
  if (clock > Date.now()) return invalid();
  const [blotter, timeline, slippage, settlement] = values.map(executionRecord);
  for (const response of [blotter, timeline, slippage, settlement]) {
    if (response.status !== 'success' || response.price_unit !== 'VND_FULL' || response.provenance !== 'RECORDED' ||
        executionClock(response.effective_cutoff) !== clock || executionClock(response.timestamp) < clock || executionClock(response.timestamp) > Date.now()) return invalid();
  }
  const order = (row: Row): ExecutionOrder => {
    const event = executionClock(row.timestamp), available = executionClock(row.availableAt);
    const qty = executionNumber(row.qty, 0, 1e8), filledQty = executionNumber(row.filledQty, 0, qty);
    const status = choice(row.status, ['FILLED', 'PARTIALLY_FILLED', 'PENDING', 'ROUTING', 'CANCELLED', 'REJECTED']);
    const price = executionNumber(row.price, 0, 1e8);
    if (event > available || available > clock || price * qty > 1e12 ||
        status === 'FILLED' && filledQty !== qty || status === 'PARTIALLY_FILLED' && !(filledQty > 0 && filledQty < qty) ||
        ['PENDING', 'ROUTING', 'CANCELLED', 'REJECTED'].includes(status) && filledQty !== 0 || filledQty > 0 && price < 100 ||
        typeof row.symbol !== 'string' || !/^[A-Z0-9]{1,16}$/.test(row.symbol)) return invalid();
    return { orderId: executionText(row.orderId), parentOrderId: row.parentOrderId === null ? null : executionText(row.parentOrderId),
      timestamp: row.timestamp as string, availableAt: row.availableAt as string, symbol: row.symbol,
      side: choice(row.side, ['BUY', 'SELL']), orderType: choice(row.orderType, ['LO', 'ATO', 'ATC', 'MP']), qty, price, filledQty,
      status, broker: executionText(row.broker), venue: choice(row.venue, ['HOSE', 'HNX', 'UPCOM', 'PAPER', 'UNKNOWN']),
      algoType: choice(row.algoType, ['TWAP', 'VWAP', 'DIRECT']), sequence: row.sequence === null ? null : count(row.sequence) };
  };
  const orders = rows(blotter.orders).map(order);
  if (count(blotter.count) !== orders.length) return invalid();
  unique(orders.map((row) => row.orderId));
  const parents = rows(timeline.parents).map((row): ExecutionParent => {
    const id = executionText(row.parent_order_id), symbol = executionText(row.symbol);
    const side = choice(row.side, ['BUY', 'SELL']), algo = choice(row.algo_type, ['TWAP', 'VWAP', 'DIRECT']);
    const target = executionNumber(row.target_qty, 0, 1e8), filled = executionNumber(row.filled_qty, 0, target);
    const completion = row.completion_pct === null ? null : executionNumber(row.completion_pct, 0, 100);
    const complete = boolean(row.sequence_complete), slices = rows(row.slices).map(order);
    if (!slices.length || slices.some((slice, index) => slice.parentOrderId !== id || slice.symbol !== symbol || slice.side !== side ||
        slice.algoType !== algo || slice.sequence === null || index > 0 && slice.sequence! <= slices[index - 1].sequence!) ||
        !same(slices.reduce((sum, slice) => sum + slice.filledQty, 0), filled) || slices.reduce((sum, slice) => sum + slice.qty, 0) > target ||
        (target === 0 ? completion !== null : completion === null || !same(completion, filled / target * 100)) ||
        complete !== slices.every((slice, index) => slice.sequence === index)) return invalid();
    return { id, symbol, side, algo, target, filled, completion, complete, slices };
  });
  const standalone = rows(timeline.standalone).map(order);
  const leaves = [...standalone, ...parents.flatMap((parent) => parent.slices)];
  if (leaves.length + parents.length > 5000 || standalone.some((row) => row.parentOrderId !== null)) return invalid();
  unique([...parents.map((row) => row.id), ...leaves.map((row) => row.orderId)]);
  const indexed = new Map(leaves.map((row) => [row.orderId, row]));
  for (const item of orders) {
    const leaf = indexed.get(item.orderId);
    if (leaf && JSON.stringify(leaf) !== JSON.stringify(item)) return invalid();
    if (!leaf && !parents.some((parent) => parent.id === item.orderId)) return invalid();
  }
  if (slippage.benchmark !== 'ARRIVAL_PRICE' || slippage.sign_convention !== 'POSITIVE_IS_COST' || slippage.fees_included !== true) return invalid();
  const points = rows(slippage.points).map((row): Slippage => {
    const id = executionText(row.order_id), leaf = indexed.get(id);
    const quantity = executionNumber(row.quantity, 1e-12, 1e8), arrival = executionNumber(row.arrival_price, 100, 1e8);
    const price = executionNumber(row.executed_price, 100, 1e8), fee = executionNumber(row.fee_vnd);
    const side = choice(row.side, ['BUY', 'SELL']), venue = executionText(row.venue), bps = executionNumber(row.slippage_bps, -1e12);
    const notional = arrival * quantity;
    if (!leaf || leaf.filledQty !== quantity || leaf.price !== price || leaf.side !== side || leaf.venue !== venue || notional > 1e12 ||
        !same(bps, ((side === 'BUY' ? 1 : -1) * (price - arrival) / arrival + fee / notional) * 10000)) return invalid();
    return { id, venue, side, quantity, arrival, price, fee, bps };
  });
  unique(points.map((row) => row.id));
  const excluded = count(slippage.excluded_missing_benchmark_or_fee);
  if (points.length + excluded !== leaves.filter((row) => row.filledQty > 0).length) return invalid();
  const venues = rows(slippage.venues).map((row) => {
    const venue = executionText(row.venue), selected = points.filter((point) => point.venue === venue);
    const notional = selected.reduce((sum, point) => sum + point.arrival * point.quantity, 0);
    const value = executionNumber(row.arrival_notional_vnd, 1e-12);
    const bps = executionNumber(row.average_slippage_bps, -1e12);
    if (!selected.length || count(row.count) !== selected.length || !same(value, notional) ||
        !same(bps, selected.reduce((sum, point) => sum + point.bps * (point.arrival * point.quantity / notional), 0))) return invalid();
    return { venue, count: selected.length, notional, bps };
  });
  unique(venues.map((row) => row.venue));
  if (venues.length !== new Set(points.map((row) => row.venue)).size) return invalid();
  if (settlement.calendar_timezone !== 'Asia/Ho_Chi_Minh' || settlement.forecast_policy !== 'T_PLUS_2_TRADING_DAYS_15_30_ICT_NOT_CONFIRMATION') return invalid();
  const settlements = rows(settlement.settlements).map((row): Settlement => {
    const id = executionText(row.order_id), leaf = indexed.get(id);
    const trade = executionClock(row.trade_at), expected = executionClock(row.expected_settlement_at);
    const confirmed = boolean(row.confirmed), side = choice(row.side, ['BUY', 'SELL']);
    const expectedIct = new Date(expected + 7 * 3600000);
    if (!leaf || !leaf.filledQty || trade !== executionClock(leaf.timestamp) || trade > clock || expected <= trade || side !== leaf.side ||
        row.symbol !== leaf.symbol || row.broker !== leaf.broker || expectedIct.getUTCHours() !== 15 || expectedIct.getUTCMinutes() !== 30 ||
        expectedIct.getUTCSeconds() !== 0 || expectedIct.getUTCMilliseconds() !== 0) return invalid();
    const fields = ['broker_effective_at', 'settlement_effective_at', 'confirmation_available_at', 'cash_available_vnd', 'shares_available'];
    if (confirmed) {
      const broker = executionClock(row.broker_effective_at), settled = executionClock(row.settlement_effective_at), available = executionClock(row.confirmation_available_at);
      if (broker < trade || broker > available || settled < expected || settled > available || available > clock ||
          executionNumber(row.shares_available, 0, leaf.filledQty) > leaf.filledQty ||
          side === 'BUY' && executionNumber(row.cash_available_vnd) !== 0 || side === 'SELL' && row.shares_available !== 0) return invalid();
      executionNumber(row.cash_available_vnd);
    } else if (fields.some((field) => row[field] !== null)) return invalid();
    if (!Array.isArray(row.skipped_closed_dates) || row.skipped_closed_dates.length > 366 || row.skipped_closed_dates.some((day) => {
      if (typeof day !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return true;
      const date = executionClock(`${day}T00:00:00+07:00`);
      return date <= trade - 86400000 || date >= expected;
    })) return invalid();
    unique(row.skipped_closed_dates as string[]);
    return { id, symbol: executionText(row.symbol), broker: executionText(row.broker), side, trade: row.trade_at as string,
      expected: row.expected_settlement_at as string, confirmed, brokerAt: row.broker_effective_at as string | null,
      settledAt: row.settlement_effective_at as string | null, availableAt: row.confirmation_available_at as string | null,
      cash: row.cash_available_vnd as number | null, shares: row.shares_available as number | null, skipped: row.skipped_closed_dates as string[] };
  });
  unique(settlements.map((row) => row.id));
  if (settlements.length !== leaves.filter((row) => row.filledQty > 0).length) return invalid();
  return { cutoff, orders, parents, standalone, points, venues, excluded, settlements };
}

export const useExecutionData = () => useQuery({
  queryKey: ['execution-slice13'],
  queryFn: async ({ signal }) => {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
    const timeout = setTimeout(abort, 10000);
    const cutoff = new Date().toISOString();
    try {
      const values = await Promise.all(['blotter', 'timeline', 'slippage-distribution', 'settlement-timeline'].map((route) =>
        requestExecutionData(`/api/v1/execution/${route}?${new URLSearchParams({ as_of: cutoff })}`, controller.signal)));
      return validateExecutionData(values, cutoff);
    } catch {
      controller.abort();
      return invalid();
    } finally {
      clearTimeout(timeout);
      signal.removeEventListener('abort', abort);
    }
  },
  retry: false, retryOnMount: false, refetchOnWindowFocus: false, refetchOnReconnect: false,
  enabled: (query) => query.state.status !== 'error', staleTime: Infinity,
});

const clockLabel = (value: string) => new Date(value).toLocaleString('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', hour12: false });
const cell = 'p-2 text-left tabular-nums';
const panel = 'rounded-xl border border-white/10 bg-zinc-950 p-4 text-sm text-zinc-200 overflow-x-auto';

export const SmartExecutionTimeline: React.FC<{ data: ExecutionData }> = ({ data }) => <section aria-label="Smart Execution Timeline" className={panel}>
  <h3 className="font-bold">Smart Execution Timeline</h3>
  {!data.parents.length && !data.standalone.length && <p role="status">No recorded execution events.</p>}
  {data.parents.map((parent) => <article key={parent.id} className="my-3 border-l-2 border-zinc-500 pl-3">
    <h4>{parent.id} · {parent.symbol} · {parent.side} · {parent.algo}</h4>
    <p>{parent.filled} / {parent.target} shares · {parent.completion === null ? 'Completion unavailable (zero target)' : `${parent.completion.toFixed(2)}% complete`} · {parent.complete ? 'Sequence complete' : 'Sequence gaps'}</p>
    <ol>{parent.slices.map((slice) => <li key={slice.orderId}><time dateTime={slice.timestamp}>{clockLabel(slice.timestamp)} ICT</time> · Slice {slice.sequence} · {slice.orderId} · {slice.status} · {slice.filledQty} / {slice.qty} shares</li>)}</ol>
  </article>)}
  <ol>{data.standalone.map((row) => <li key={row.orderId}><time dateTime={row.timestamp}>{clockLabel(row.timestamp)} ICT</time> · {row.orderId} · {row.symbol} · {row.side} · {row.status} · {row.filledQty} / {row.qty} shares</li>)}</ol>
</section>;

// ponytail: exact per-fill distribution table, not fabricated histogram bins; charting can follow a measured readability need.
export const ExecutionSlippageDistribution: React.FC<{ data: ExecutionData }> = ({ data }) => <section aria-label="Execution Slippage Distribution" className={panel}>
  <h3 className="font-bold">Execution Slippage Distribution</h3>
  <p>Arrival price benchmark · Fees included · Positive bps = cost · Negative bps = improvement</p>
  <p>{data.excluded} filled orders excluded: benchmark or explicit fee unavailable.</p>
  {!data.points.length ? <p role="status">No eligible slippage observations.</p> : <>
    <table className="w-full"><caption>Per-fill slippage · VND full prices</caption><thead><tr>{['Order', 'Venue', 'Side', 'Quantity', 'Arrival VND', 'Execution VND', 'Fee VND', 'Slippage bps'].map((label) => <th scope="col" className={cell} key={label}>{label}</th>)}</tr></thead>
      <tbody>{data.points.map((point) => <tr key={point.id}>{[point.id, point.venue, point.side, point.quantity, point.arrival, point.price, point.fee, point.bps.toFixed(2)].map((value, index) => <td className={cell} key={index}>{value}</td>)}</tr>)}</tbody></table>
    <table className="w-full"><caption>Arrival-notional weighted venue summary</caption><thead><tr>{['Venue', 'Fills', 'Arrival notional VND', 'Weighted slippage bps'].map((label) => <th scope="col" className={cell} key={label}>{label}</th>)}</tr></thead>
      <tbody>{data.venues.map((venue) => <tr key={venue.venue}>{[venue.venue, venue.count, venue.notional, venue.bps.toFixed(2)].map((value, index) => <td className={cell} key={index}>{value}</td>)}</tr>)}</tbody></table>
  </>}
</section>;

export const VsdcSettlementTimelineWidget: React.FC<{ data: ExecutionData }> = ({ data }) => <section aria-label="VSDC Settlement Timeline" className={panel}>
  <h3 className="font-bold">VSDC Settlement Timeline</h3>
  <p>T+2 trading days · 15:30 ICT forecast is not settlement confirmation.</p>
  {!data.settlements.length && <p role="status">No filled orders awaiting settlement evidence.</p>}
  <ol>{data.settlements.map((row) => <li key={row.id} className="my-3 border-l-2 border-zinc-500 pl-3">
    <h4>{row.id} · {row.symbol} · {row.broker} · {row.side}</h4>
    <p>Trade: <time dateTime={row.trade}>{clockLabel(row.trade)} ICT</time></p>
    <p>Expected: <time dateTime={row.expected}>{clockLabel(row.expected)} ICT</time> · {row.confirmed ? 'Confirmed settlement' : 'Unconfirmed forecast'}</p>
    {row.skipped.length > 0 && <p>Closed dates skipped: {row.skipped.join(', ')}</p>}
    {row.confirmed ? <><p>Broker effective: {clockLabel(row.brokerAt!)} ICT · Settlement effective: {clockLabel(row.settledAt!)} ICT · Confirmation available: {clockLabel(row.availableAt!)} ICT</p><p>Available cash: {row.cash} VND · Available shares: {row.shares}</p></> : <p>Cash and share availability unknown. No broker confirmation.</p>}
  </li>)}</ol>
</section>;

export const ExecutionBlotterView: React.FC = () => {
  const query = useExecutionData();
  const selected = useUiStore((state) => state.selectedTicker);
  const setSelected = useUiStore((state) => state.setSelectedTicker);
  const setModule = useUiStore((state) => state.setActiveModule);
  const data = query.isError || query.isFetching ? undefined : query.data;
  return <div className="flex min-w-0 flex-col gap-4 font-mono">
    <PaperDaemonPanel onRefresh={() => { void query.refetch(); }} />
    <section aria-label="OMS execution data" className={panel}>
      <h2 className="font-bold">OMS Execution Blotter</h2>
      <button disabled={query.isFetching} onClick={() => { void query.refetch(); }} className="min-h-11 rounded border border-zinc-500 px-3 focus-visible:outline-2 disabled:opacity-50">Refresh execution data</button>
      {query.isFetching && <p role="status">Loading recorded execution data…</p>}
      {query.isError && <p role="alert">Execution data unavailable. Retry explicitly; no synthetic data displayed.</p>}
      {data && <><p>Paper execution · Recorded publication provenance · Cutoff {clockLabel(data.cutoff)} ICT</p><p>Most recent {data.orders.length} orders (maximum 100); timelines cover up to 5,000 records.</p>
        {!data.orders.length ? <p role="status">No recorded OMS orders.</p> : <table className="w-full"><caption>OMS orders · VND full prices</caption><thead><tr>{['Order', 'Time ICT', 'Symbol', 'Side', 'Type / Algo', 'Quantity', 'Price VND', 'Filled', 'Status', 'Broker / Venue'].map((label) => <th className={cell} scope="col" key={label}>{label}</th>)}</tr></thead>
          <tbody>{data.orders.map((row) => <tr key={row.orderId} aria-selected={selected === row.symbol}>
            <td className={cell}>{row.orderId}</td><td className={cell}>{clockLabel(row.timestamp)}</td>
            <td className={cell}><button onClick={() => setSelected(row.symbol)} className="min-h-11 px-2 underline focus-visible:outline-2">{row.symbol}</button><button aria-label={`Open ${row.symbol} in Chart Station`} onClick={() => { setSelected(row.symbol); setModule('chart_station'); }} className="min-h-11 px-2 underline focus-visible:outline-2">Chart</button></td>
            {[row.side, `${row.orderType} / ${row.algoType}`, row.qty, row.price, `${row.filledQty} (${row.qty === 0 ? 'Unavailable' : `${(row.filledQty / row.qty * 100).toFixed(0)}%`})`, row.status, `${row.broker} / ${row.venue}`].map((value, index) => <td className={cell} key={index}>{value}</td>)}
          </tr>)}</tbody></table>}
      </>}
    </section>
    {data && <><SmartExecutionTimeline data={data} /><ExecutionSlippageDistribution data={data} /><VsdcSettlementTimelineWidget data={data} /></>}
  </div>;
};
