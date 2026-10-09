import pytest
import os
import subprocess
import tempfile
from pathlib import Path
from starlette.testclient import TestClient
from omega.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


# --- Market API contract and executable Chart Station UI checks ---

def test_market_ohlcv_default(client):
    response = client.get("/api/v1/market/ohlcv/FPT")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_bars"] == len(payload["bars"])
    assert payload["bars"]
    latest = payload["bars"][-1]
    assert latest["low"] <= latest["open"] <= latest["high"]
    assert latest["low"] <= latest["close"] <= latest["high"]
    assert latest["close"] > 0 and latest["volume"] >= 0


def test_market_ohlcv_case_insensitivity_and_whitespace(client):
    # Dimension 10: Case-Insensitive Symbol Deduplication & Canonicalization
    response_lower = client.get("/api/v1/market/ohlcv/fpt")
    assert response_lower.status_code == 200

    response_space = client.get("/api/v1/market/ohlcv/%20hpg%20")
    assert response_space.status_code == 200


def test_market_ohlcv_date_filtering(client):
    # Dimension 6: Point-in-Time (PIT) & Date Filtering
    response = client.get("/api/v1/market/ohlcv/FPT?start=2024-01-02&end=2024-03-29")
    assert response.status_code == 200
    bars = response.json()["bars"]
    assert bars
    assert all("2024-01-02" <= bar["time"] <= "2024-03-29" for bar in bars)


def test_market_ohlcv_limit_bounds(client):
    # Dimension 4 & 8: Memory Bounds & Extreme Parameter Defenses
    response = client.get("/api/v1/market/ohlcv/FPT?limit=10")
    assert response.status_code == 200
    assert response.json()["total_bars"] == 10
    assert len(response.json()["bars"]) == 10

    # Test invalid limit (0 or > 5000)
    res_zero = client.get("/api/v1/market/ohlcv/FPT?limit=0")
    assert res_zero.status_code == 422
    res_overflow = client.get("/api/v1/market/ohlcv/FPT?limit=99999")
    assert res_overflow.status_code == 422


def test_market_ohlcv_invalid_dates(client):
    # Dimension 1 & 14: Malformed Date Inputs
    res = client.get("/api/v1/market/ohlcv/FPT?start=invalid-date")
    assert res.status_code == 422


def test_market_ohlcv_rejects_non_trading_calendar_date(client):
    response = client.get("/api/v1/market/ohlcv/FPT?start=2026-08-29")
    assert response.status_code == 422


def test_market_ohlcv_nonexistent_symbol(client):
    # Dimension 10 & 11: Empty set handling for unknown symbols
    response = client.get("/api/v1/market/ohlcv/UNKNOWN999XYZ")
    assert response.status_code == 200


def test_market_ohlcv_reversed_dates_rejected_before_dataset_access(monkeypatch, client):
    from omega.api.routes import market

    read = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("reversed range must not access dataset")
    )
    monkeypatch.setattr(market._market_loader, "load_market_dataset", read)

    response = client.get(
        "/api/v1/market/ohlcv/FPT?start=2026-08-28&end=2026-08-27"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "INVALID_DATE_RANGE"


def test_market_ohlcv_missing_file_fail_closed(monkeypatch, client):
    # Dimension 2 & 11: Fail-Closed on Missing Dataset
    from omega.api.routes import market
    monkeypatch.setattr(
        market._market_loader,
        "PRIMARY_MARKET_PARQUET_PATH",
        Path("nonexistent_market.parquet"),
    )
    monkeypatch.setattr(
        market._market_loader,
        "BACKUP_MARKET_PARQUET_PATH",
        Path("nonexistent_market_backup.parquet"),
    )
    response = client.get("/api/v1/market/ohlcv/FPT")
    assert response.status_code == 503


def test_market_orderbook_default(client):
    # Dimension 1 & 9: Orderbook Financial Structure & Fail-Closed Real Data Contract
    response = client.get("/api/v1/market/orderbook/FPT")
    assert response.status_code == 503
    assert response.json()["detail"] == "REAL_L2_FEED_UNAVAILABLE"


def test_market_orderbook_depth_param(client):
    # Dimension 4 & 8: Orderbook Depth Boundaries & Fail-Closed
    response = client.get("/api/v1/market/orderbook/MBB?depth=5")
    assert response.status_code == 503
    assert response.json()["detail"] == "REAL_L2_FEED_UNAVAILABLE"


def test_market_orderbook_invalid_depth(client):
    # Dimension 1 & 8: Strict Validation on Depth Range
    res_zero = client.get("/api/v1/market/orderbook/MBB?depth=0")
    assert res_zero.status_code == 422
    res_over = client.get("/api/v1/market/orderbook/MBB?depth=50")
    assert res_over.status_code == 422


def test_market_orderbook_empty_symbol(client):
    # Dimension 1: Strict Validation on Empty Symbol
    response = client.get("/api/v1/market/orderbook/%20")
    assert response.status_code == 422


def test_market_orderbook_spread_and_depth(client):
    # Dimension 8 & 9: Fail-closed verification
    response = client.get("/api/v1/market/orderbook/HPG")
    assert response.status_code == 503
    assert response.json()["detail"] == "REAL_L2_FEED_UNAVAILABLE"


def test_market_orderbook_utc_timestamp(client):
    # Dimension 6: Temporal clocks & fail-closed contract
    response = client.get("/api/v1/market/orderbook/FPT")
    assert response.status_code == 503
    assert response.json()["detail"] == "REAL_L2_FEED_UNAVAILABLE"


UI_CHECKS = r'''
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { validateCandles, validateOhlcv, validateOrderbook, aggregateCandles, useMarketOhlcv, useMarketOrderbook } from '../hooks/useMarketData';
import { LightweightChartContainer, movingAverages } from '../modules/chart_station/LightweightChartContainer';
import { OrderbookDepth } from '../modules/chart_station/OrderbookDepth';
const charts = vi.hoisted(() => [] as any[]);
vi.mock('lightweight-charts', () => ({
  ColorType: { Solid: 'solid' }, CrosshairMode: { Normal: 0 }, LineStyle: { Dashed: 2 },
  createChart: vi.fn(() => {
    const add = () => ({ setData: vi.fn(), setMarkers: vi.fn(), applyOptions: vi.fn() });
    const chart = { price: add(), sma: add(), ema: add(), volume: add(), remove: vi.fn(), applyOptions: vi.fn(), subscribeCrosshairMove: vi.fn(),
      scale: { fitContent: vi.fn(), subscribeVisibleLogicalRangeChange: vi.fn(), setVisibleLogicalRange: vi.fn() } };
    Object.assign(chart, { addCandlestickSeries: () => chart.price, addLineSeries: vi.fn().mockReturnValueOnce(chart.sma).mockReturnValueOnce(chart.ema),
      addHistogramSeries: () => chart.volume, timeScale: () => chart.scale });
    charts.push(chart); return chart;
  }),
}));
const bar = (time = '2026-08-27', close = 100000) => ({ time, open: close, high: close + 100, low: close - 100, close, volume: 1000 });
const payload = (symbol = 'FPT', bars = [bar()]) => ({ status: 'success', symbol, exchange: 'HOSE', total_bars: bars.length, bars });
const book = () => ({ status: 'success', symbol: 'FPT', exchange: 'HOSE', timestamp: '2026-08-27T08:30:00Z', reference_price: 100000,
  floor_price: 93000, ceiling_price: 107000, spread: 100, spread_bps: 10, total_bid_depth: 1000, total_ask_depth: 2000,
  bids: [{ level: 1, price: 99900, volume: 1000, orders: 2 }], asks: [{ level: 1, price: 100000, volume: 2000, orders: 3 }] });
let root: ReturnType<typeof createRoot> | undefined;
let host: HTMLDivElement;
let client: QueryClient | undefined;
const disconnect = vi.fn();
function mount(node: React.ReactNode) {
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect = disconnect; });
  act(() => root!.render(node));
}
async function settle() { await act(async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); await new Promise(resolve => setTimeout(resolve, 10)); }); }
afterEach(() => { act(() => root?.unmount()); root = undefined; host?.remove(); client?.clear(); client = undefined; vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); charts.length = 0; });
describe('Slice 9 executable UI', () => {
  it('rejects malformed, nonfinite, overflow, duplicate and incoherent bars', () => {
    for (const value of [null, {}, '', [null], [{ ...bar(), time: '2026-02-30' }], [bar(), bar()],
      ...[NaN, Infinity, -Infinity, -1, 0, 1e13, '1000', []].map(close => [{ ...bar(), close }]),
      [{ ...bar(), volume: -1 }], [{ ...bar(), low: 100001 }], Array(5001).fill(bar())]) expect(() => validateCandles(value)).toThrow();
    expect(validateCandles([])).toEqual([]);
    expect(validateOhlcv(payload(), 'FPT', 10).bars[0].close).toBe(100000);
    expect(() => validateOhlcv(payload('HPG'), 'FPT', 10)).toThrow();
    expect(() => validateOhlcv({ ...payload(), total_bars: 2 }, 'FPT', 10)).toThrow();
  });
  it('aggregates weekly/monthly UTC boundaries without modifying daily input', () => {
    const bars = [bar('2026-08-28'), bar('2026-08-31', 100050), bar('2026-09-01', 100100)];
    const original = JSON.stringify(bars);
    expect(aggregateCandles(bars, '1W').map(b => b.volume)).toEqual([1000, 2000]);
    expect(aggregateCandles(bars, '1M').map(b => b.volume)).toEqual([2000, 1000]);
    expect(JSON.stringify(bars)).toBe(original);
    expect(() => aggregateCandles(bars, '1H')).toThrow();
    expect(() => aggregateCandles([{ ...bars[0], volume: 1e12 }, { ...bars[0], time: '2026-08-29', volume: 1e12 }], '1M')).toThrow();
  });
  it('calculates seeded SMA and EMA with warmup and finite values', () => {
    const bars = Array.from({ length: 21 }, (_, i) => bar(`2026-08-${String(i + 1).padStart(2, '0')}`, i + 1));
    const { sma, ema } = movingAverages(bars);
    expect(sma.map(b => b.value)).toEqual([10.5, 11.5]); expect(ema[1].value).toBe(11.5);
    expect(movingAverages([])).toEqual({ sma: [], ema: [] });
    expect(() => movingAverages(bars, 0)).toThrow();
  });
  it('rejects synthetic/crossed/malformed depth and preserves VND_FULL', () => {
    expect(validateOrderbook(book(), 'FPT', 10).bids[0].price).toBe(99900);
    for (const patch of [{ is_synthetic: true }, { timestamp: '2026-08-27' }, { timestamp: '2999-01-01T00:00:00Z' },
      { bids: [] }, { bids: [null] }, { total_bid_depth: 0 }, { spread: NaN }, { reference_price: '100' },
      { asks: [{ level: 1, price: 99000, volume: 2000, orders: 3 }] }]) expect(() => validateOrderbook({ ...book(), ...patch }, 'FPT', 10)).toThrow();
  });
  it('mounts, updates toggles/markers, preserves zoom and cleans both charts', () => {
    const props = { symbol: 'FPT', candles: [bar()], showSMA: true, showEMA: true, showVolume: true, alphaMarkers: [] };
    mount(<LightweightChartContainer {...props} />);
    expect(charts).toHaveLength(2); expect(charts[0].price.setData).toHaveBeenCalledWith([bar()]);
    act(() => root!.render(<LightweightChartContainer {...props} showSMA={false} showVolume={false} alphaMarkers={[{ time: bar().time, side: 'BUY', price: 100000, label: 'Observed signal' }]} />));
    expect(charts[0].sma.applyOptions).toHaveBeenLastCalledWith({ visible: false });
    expect(charts[0].price.setMarkers.mock.lastCall[0][0].shape).toBe('arrowUp');
    expect(charts[0].scale.fitContent).toHaveBeenCalledTimes(1);
    expect(host.querySelector('table')?.textContent).toContain((100000).toLocaleString());
    for (const price of [Number.MIN_VALUE, 1e-310, 0.999999, NaN, Infinity, -Infinity, 0, -1, 1e12 + 1]) {
      act(() => root!.render(<LightweightChartContainer {...props} alphaMarkers={[{ time: bar().time, side: 'BUY', price, label: 'Invalid price' }]} />));
      expect(host.querySelector('[role=alert]')).not.toBeNull();
      expect(charts[0].price.setData).toHaveBeenLastCalledWith([]);
      expect(charts[0].price.setMarkers).toHaveBeenLastCalledWith([]);
      expect(charts[1].volume.setData).toHaveBeenLastCalledWith([]);
    }
    act(() => root!.render(<LightweightChartContainer {...props} />));
    expect(host.querySelector('[role=alert]')).toBeNull();
    expect(charts[0].price.setData).toHaveBeenLastCalledWith([bar()]);
    act(() => root!.unmount()); root = undefined;
    expect(charts.every(chart => chart.remove.mock.calls.length === 1)).toBe(true); expect(disconnect).toHaveBeenCalled();
  });
  it('clears every series on invalid updates without crashing accessible table', () => {
    const props = { symbol: 'FPT', candles: [bar()], showSMA: true, showEMA: true, showVolume: true, alphaMarkers: [] };
    mount(<LightweightChartContainer {...props} />);
    act(() => root!.render(<LightweightChartContainer {...props} candles={[null] as any} />));
    expect(host.querySelector('[role=alert]')).not.toBeNull();
    expect(charts[0].price.setData).toHaveBeenLastCalledWith([]); expect(charts[1].volume.setData).toHaveBeenLastCalledWith([]);
  });
  it('shows explicit L2 failure, retry and accessible depth table', () => {
    const retry = vi.fn(); mount(<OrderbookDepth isLoading={false} isError onRetry={retry} data={book()} />);
    expect(host.textContent).toContain('unavailable'); expect(host.querySelector('table')).toBeNull();
    act(() => host.querySelector('button')!.click()); expect(retry).toHaveBeenCalledOnce();
    act(() => root!.render(<OrderbookDepth isLoading={false} data={book()} />)); expect(host.querySelectorAll('meter')).toHaveLength(2);
    act(() => root!.render(<OrderbookDepth isLoading={false} data={{ ...book(), total_bid_depth: 0 }} />)); expect(host.querySelector('table')).toBeNull();
  });
  it('wires market requests, aborts obsolete keys and isolates stale results', async () => {
    let resolveOld: (value: Response) => void = () => {};
    const fetcher = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { resolveOld = resolve; }))
      .mockResolvedValue(new Response(JSON.stringify(payload('HPG')))); vi.stubGlobal('fetch', fetcher);
    client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    function Probe({ symbol }: { symbol: string }) { const query = useMarketOhlcv(symbol); return <p>{query.data?.symbol || query.status}</p>; }
    mount(<QueryClientProvider client={client}><Probe symbol="FPT" /></QueryClientProvider>); await settle();
    const oldSignal = fetcher.mock.calls[0][1].signal;
    act(() => root!.render(<QueryClientProvider client={client!}><Probe symbol="HPG" /></QueryClientProvider>)); await settle();
    expect(oldSignal.aborted).toBe(true); expect(host.textContent).toBe('HPG');
    resolveOld(new Response(JSON.stringify(payload()))); await settle(); expect(host.textContent).toBe('HPG');
    expect(fetcher.mock.calls[1][0]).toContain('/api/v1/market/ohlcv/HPG?limit=500');
  });
  it('fails closed on provider errors without retries or secret echo', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'https://user:secret@provider.invalid' }), { status: 429 }));
    vi.stubGlobal('fetch', fetcher); client = new QueryClient();
    function Probe() { const query = useMarketOrderbook('FPT'); return <p>{query.isError ? 'Unavailable' : 'Loading'}</p>; }
    mount(<QueryClientProvider client={client}><Probe /></QueryClientProvider>); await settle();
    expect(host.textContent).toBe('Unavailable'); expect(host.textContent).not.toContain('secret'); expect(fetcher).toHaveBeenCalledOnce();
  });
  it('bounds request deadlines and aborts timed-out requests', async () => {
    vi.useFakeTimers(); const fetcher = vi.fn((_url, init) => new Promise((_resolve, reject) => init.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))));
    vi.stubGlobal('fetch', fetcher); client = new QueryClient();
    function Probe() { const query = useMarketOhlcv('FPT'); return <p>{query.status}</p>; }
    mount(<QueryClientProvider client={client}><Probe /></QueryClientProvider>);
    await act(async () => { await vi.advanceTimersByTimeAsync(10010); });
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true); expect(host.textContent).toBe('error'); expect(fetcher).toHaveBeenCalledOnce();
  });
});
'''


def test_chart_station_bounded_provider_failure_and_manual_recovery():
    """Exercise the real hook with fake-clock provider failures and recovery."""
    repo = Path(__file__).resolve().parents[1]
    executable = "npm.cmd" if os.name == "nt" else "npm"
    result = subprocess.run(
        [executable, "--prefix", "omega-ui", "test", "--",
         "src/test/missing_integrations.test.tsx", "-t", "OHLCV"],
        cwd=repo, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "7 passed" in result.stdout


def test_chart_station_executable_ui():
    """Run React lifecycle/fault checks without maintaining an out-of-scope test file."""
    repo = Path(__file__).resolve().parents[1]
    directory = repo / "omega-ui" / "src" / "test"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".test.tsx", prefix="slice9_", dir=directory,
                                     encoding="utf-8", newline="\n", delete=False) as stream:
        stream.write(UI_CHECKS)
        path = Path(stream.name)
    try:
        executable = "npm.cmd" if os.name == "nt" else "npm"
        result = subprocess.run([executable, "--prefix", "omega-ui", "test", "--",
                                 str(path.relative_to(repo / "omega-ui"))],
                                cwd=repo, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=120)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
    finally:
        path.unlink(missing_ok=True)
