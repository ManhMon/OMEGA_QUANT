import React, { useState } from 'react';
import { Filter, Search, ChevronLeft, ChevronRight, RefreshCw, LineChart, Network } from 'lucide-react';
import { useUiStore } from '../../store/uiStore';
import { useQuantScreener } from '../../hooks/useQuantScreener';
import { CorporateGraphDrawer } from './CorporateGraphDrawer';
import { OwnershipSupplyChainGraph } from './OwnershipSupplyChainGraph';
import { useTranslation } from '../../i18n';

export const FundamentalMatrixView: React.FC = () => {
  const screenerFilters = useUiStore((state) => state.screenerFilters);
  const setScreenerFilters = useUiStore((state) => state.setScreenerFilters);
  const resetScreenerFilters = useUiStore((state) => state.resetScreenerFilters);
  const selectedTicker = useUiStore((state) => state.selectedTicker);
  const setSelectedTicker = useUiStore((state) => state.setSelectedTicker);
  const setActiveModule = useUiStore((state) => state.setActiveModule);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerSymbol, setDrawerSymbol] = useState('FPT');

  const { t } = useTranslation();
  const { data: response, isLoading, isError, isFetching } = useQuantScreener(screenerFilters);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setScreenerFilters({ search: e.target.value });
  };

  const handleSelectTicker = (ticker: string) => {
    setSelectedTicker(ticker);
  };

  const handleOpenChartStation = (e: React.MouseEvent, ticker: string) => {
    e.stopPropagation();
    setSelectedTicker(ticker);
    setActiveModule('chart_station');
  };

  const handleOpenCorporateDrawer = (e: React.MouseEvent, ticker: string) => {
    e.stopPropagation();
    setDrawerSymbol(ticker);
    setDrawerOpen(true);
  };

  const items = response?.data || [];
  const total = response?.total || 0;
  const page = response?.page || 1;
  const totalPages = response?.totalPages || 1;

  return (
    <div className="flex flex-col gap-4 pb-8">
      {/* Corporate Graph Drawer Modal */}
      <CorporateGraphDrawer
        symbol={drawerSymbol}
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />

      {/* Control / Filter Ribbon */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-zinc-950/60 border border-white/10 text-xs font-mono">
        {/* Canonical Tickers: 'FPT' 'HPG' 'MBB' 'VHM' 'MWG' 'DGC' */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Search bar */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-300">
            <Search className="w-3.5 h-3.5 text-zinc-500" />
            <input
              type="text"
              placeholder={t.fundamentalMatrix.searchPlaceholder}
              value={screenerFilters.search || ''}
              onChange={handleSearchChange}
              className="bg-transparent border-none outline-none text-zinc-200 placeholder-zinc-500 w-36 sm:w-48 text-xs font-mono"
            />
          </div>

          {/* Preset Buttons */}
          <button
            onClick={() => setScreenerFilters({ minPiotroski: screenerFilters.minPiotroski === 7 ? 0 : 7 })}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded border transition-all ${
              screenerFilters.minPiotroski === 7
                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 font-bold'
                : 'bg-zinc-900 border-white/10 hover:border-white/20 text-zinc-300'
            }`}
          >
            <Filter className="w-3.5 h-3.5 text-cyan-400" />
            <span>{t.fundamentalMatrix.fScoreFilter}</span>
          </button>

          <button
            onClick={() => setScreenerFilters({ minRoe: screenerFilters.minRoe === 15 ? 0 : 15 })}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded border transition-all ${
              screenerFilters.minRoe === 15
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 font-bold'
                : 'bg-zinc-900 border-white/10 hover:border-white/20 text-zinc-300'
            }`}
          >
            <span>{t.fundamentalMatrix.roeFilter}</span>
          </button>

          <button
            onClick={() => setScreenerFilters({ minAltmanZ: screenerFilters.minAltmanZ === 2.6 ? 0 : 2.6 })}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded border transition-all ${
              screenerFilters.minAltmanZ === 2.6
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-bold'
                : 'bg-zinc-900 border-white/10 hover:border-white/20 text-zinc-300'
            }`}
          >
            <span>Altman Z &gt; 2.6 ({t.fundamentalMatrix.altmanZFilter})</span>
          </button>

          <button
            onClick={() => setScreenerFilters({ status: screenerFilters.status === 'QUALIFIED' ? '' : 'QUALIFIED' })}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded border transition-all ${
              screenerFilters.status === 'QUALIFIED'
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 font-bold'
                : 'bg-zinc-900 border-white/10 hover:border-white/20 text-zinc-300'
            }`}
          >
            <span>{t.fundamentalMatrix.qualifiedOnly}</span>
          </button>

          {(screenerFilters.search || screenerFilters.minPiotroski || screenerFilters.minRoe || screenerFilters.minAltmanZ || screenerFilters.status) ? (
            <button
              onClick={() => resetScreenerFilters()}
              className="px-2 py-1 rounded text-[10px] text-zinc-400 hover:text-rose-300 hover:bg-rose-950/30"
            >
              {t.fundamentalMatrix.clearFilter}
            </button>
          ) : null}
        </div>

        <div className="flex items-center gap-2 text-zinc-400 text-[11px]">
          {isFetching && <RefreshCw className="w-3 h-3 text-cyan-400 animate-spin" />}
          <span>
            {t.fundamentalMatrix.screenedEquities} <span className="text-zinc-100 font-bold">{total} EQUITIES</span> ({t.fundamentalMatrix.totalUniverse})
          </span>
        </div>
      </div>

      {/* Selected Ticker Corporate Supply Chain Preview Box */}
      <OwnershipSupplyChainGraph symbol={selectedTicker || 'FPT'} />

      {/* Institutional Screener Matrix */}
      <div className="overflow-x-auto rounded-xl border border-white/10 bg-zinc-950/40">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-zinc-900/80 text-zinc-400 uppercase text-[10px] tracking-wider border-b border-white/10">
            <tr>
              <th className="px-4 py-3">{t.fundamentalMatrix.thTicker}</th>
              <th className="px-4 py-3">{t.fundamentalMatrix.thExchange}</th>
              <th className="px-4 py-3">{t.fundamentalMatrix.thSector}</th>
              <th className="px-4 py-3">{t.fundamentalMatrix.thPe}</th>
              <th className="px-4 py-3">{t.fundamentalMatrix.thPb}</th>
              <th className="px-4 py-3">{t.fundamentalMatrix.thRoe}</th>
              <th className="px-4 py-3">{t.fundamentalMatrix.thPiotroski}</th>
              <th className="px-4 py-3">{t.fundamentalMatrix.thAltmanZ}</th>
              <th className="px-4 py-3">{t.fundamentalMatrix.thMomentum}</th>
              <th className="px-4 py-3 text-right">{t.fundamentalMatrix.thStatus}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {isLoading ? (
              <tr>
                <td colSpan={10} className="px-4 py-12 text-center text-zinc-500 font-mono">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <RefreshCw className="w-6 h-6 text-cyan-400 animate-spin" />
                    <span>{t.fundamentalMatrix.loadingRecords}</span>
                  </div>
                </td>
              </tr>
            ) : isError ? (
              <tr>
                <td colSpan={10} className="px-4 py-12 text-center text-rose-400 font-mono">
                  <span>{t.fundamentalMatrix.errorRetrieving}</span>
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-4 py-12 text-center text-zinc-500 font-mono">
                  <span>{t.fundamentalMatrix.emptyMatch}</span>
                </td>
              </tr>
            ) : (
              items.map((row) => {
                const isSelected = selectedTicker === row.ticker;
                return (
                  <tr
                    key={row.ticker}
                    onClick={() => handleSelectTicker(row.ticker)}
                    className={`hover:bg-white/5 transition-colors cursor-pointer group ${
                      isSelected ? 'bg-cyan-950/30' : ''
                    }`}
                  >
                    <td className="px-4 py-3 font-bold text-zinc-100 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`h-1.5 w-1.5 rounded-full ${row.status === 'QUALIFIED' ? 'bg-emerald-400' : row.status === 'WATCH' ? 'bg-amber-400' : 'bg-zinc-600'}`} />
                        <span className="group-hover:text-cyan-300 transition-colors">{row.ticker}</span>
                      </div>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          type="button"
                          onClick={(e) => handleOpenCorporateDrawer(e, row.ticker)}
                          className="p-1 rounded hover:bg-emerald-500/20 text-emerald-400"
                          title={`View corporate graph for ${row.ticker}`}
                        >
                          <Network className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => handleOpenChartStation(e, row.ticker)}
                          className="p-1 rounded hover:bg-cyan-500/20 text-cyan-400"
                          title={`Open ${row.ticker} in Chart Station`}
                        >
                          <LineChart className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-zinc-400">{row.exchange}</td>
                    <td className="px-4 py-3 text-zinc-300">{row.sector}</td>
                    <td className="px-4 py-3 text-zinc-200">{row.pe.toFixed(1)}</td>
                    <td className="px-4 py-3 text-zinc-200">{row.pb.toFixed(1)}</td>
                    <td className="px-4 py-3 text-emerald-400 font-semibold">{row.roe.toFixed(1)}%</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded font-bold ${
                        row.piotroskiF >= 7 ? 'bg-emerald-950/60 border border-emerald-500/30 text-emerald-300' : 'bg-zinc-900 text-zinc-400'
                      }`}>
                        {row.piotroskiF}/9
                      </span>
                    </td>
                    <td className="px-4 py-3 text-cyan-300">{row.altmanZ.toFixed(2)}</td>
                    <td className={`px-4 py-3 font-semibold ${row.momentumScore >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {row.momentumScore >= 0 ? `+${row.momentumScore.toFixed(2)}` : row.momentumScore.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                        row.status === 'QUALIFIED'
                          ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-500/30'
                          : row.status === 'WATCH'
                          ? 'bg-amber-950/80 text-amber-400 border border-amber-500/30'
                          : 'bg-zinc-900 text-zinc-500 border border-zinc-800'
                      }`}>
                        {row.status}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {/* Pagination Bar */}
        <div className="p-3 border-t border-white/10 flex items-center justify-between text-xs font-mono text-zinc-400 bg-zinc-900/40">
          <div>
            {t.fundamentalMatrix.paginationShowing} <span className="text-zinc-100 font-bold">{page}</span> {t.common.of} <span className="text-zinc-100 font-bold">{totalPages}</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setScreenerFilters({ page: page - 1 })}
              className="p-1 rounded bg-zinc-900 border border-white/10 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed text-zinc-300"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-zinc-300 px-2 font-mono">{page} / {totalPages}</span>
            <button
              disabled={page >= totalPages}
              onClick={() => setScreenerFilters({ page: page + 1 })}
              className="p-1 rounded bg-zinc-900 border border-white/10 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed text-zinc-300"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

