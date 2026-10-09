import type { OrderbookData } from '../../api/client';
import { validateOrderbook } from '../../hooks/useMarketData';

export function OrderbookDepth({ data, isLoading, isError = false, onRetry }: {
  data?: OrderbookData; isLoading: boolean; isError?: boolean; onRetry?: () => void;
}) {
  let book: OrderbookData | undefined;
  try { if (data) book = validateOrderbook(data, data.symbol, 20); } catch { book = undefined; }
  const maxVolume = Math.max(1, ...(book ? [...book.bids, ...book.asks].map((level) => level.volume) : []));
  return <section aria-label="Orderbook depth" className="min-w-0 rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-xs text-zinc-300">
    <h2 className="font-semibold">Orderbook depth · observed L2</h2>
    {isLoading ? <p role="status">Loading orderbook…</p> : isError || !book ? <div>
      <p role="status">Observed L2 feed unavailable. No synthetic depth displayed.</p>
      {onRetry && <button className="mt-3 rounded border border-white/20 px-3 py-2 focus-visible:outline" onClick={onRetry}>Retry orderbook</button>}
    </div> : <>
      <p>{book.symbol} · {book.exchange} · {book.timestamp}</p>
      <p>Spread: {book.spread.toLocaleString()} VND · {book.spread_bps.toFixed(2)} bps</p>
      <p>Bids: {book.total_bid_depth.toLocaleString()} shares · Asks: {book.total_ask_depth.toLocaleString()} shares</p>
      <div className="overflow-auto"><table className="w-full text-right tabular-nums">
        <caption>VND full prices · volume in shares · bars relative to largest level</caption>
        <thead><tr>{['Side', 'Level', 'Price', 'Volume', 'Orders', 'Depth'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
        <tbody>{(['bids', 'asks'] as const).flatMap((side) => book[side].map((level) => <tr key={`${side}-${level.level}`}>
          <th scope="row">{side === 'bids' ? 'Bid' : 'Ask'}</th><td>{level.level}</td><td>{level.price.toLocaleString()}</td><td>{level.volume.toLocaleString()}</td><td>{level.orders}</td>
          <td><meter min={0} max={maxVolume} value={level.volume} aria-label={`${side} level ${level.level} volume`} className="w-16" /></td>
        </tr>))}</tbody>
      </table></div>
    </>}
  </section>;
}
