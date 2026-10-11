import React, { useEffect, useRef, useState } from 'react';
import { apiClient, type MacroObservation, type MacroNewsLatestResponse, type VSIGreedFearResponse, type SectorContagionResponse, type LLMMacroIntelligenceResponse } from '../../api/client';
import { useUiStore } from '../../store/uiStore';

const loaders = {
  news: (signal: AbortSignal) => apiClient.getMacroNewsLatest({ limit: 100 }, signal),
  vsi: (signal: AbortSignal) => apiClient.getVSISentiment(undefined, signal),
  contagion: (signal: AbortSignal) => apiClient.getSectorContagion(signal),
  intelligence: (signal: AbortSignal) => apiClient.getLLMMacroAnalysis(signal),
};
const control = 'min-h-11 rounded border border-zinc-600 bg-zinc-900 px-3 text-zinc-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300 disabled:opacity-50';

function Observation<T extends MacroObservation & { as_of: string }>({ title, load, children }: {
  title: string; load: (signal: AbortSignal) => Promise<T>; children: (data: T) => React.ReactNode;
}) {
  const [data, setData] = useState<T | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [revision, setRevision] = useState(0);
  const busy = useRef(true);
  const vi = useUiStore((s) => s.locale === 'vi');
  useEffect(() => {
    const controller = new AbortController();
    busy.current = true; setState('loading'); setData(null);
    void load(controller.signal).then((value) => {
      if (!controller.signal.aborted) { setData(value); setState('ready'); }
    }).catch(() => {
      if (!controller.signal.aborted) { setData(null); setState('error'); }
    }).finally(() => { if (!controller.signal.aborted) busy.current = false; });
    return () => controller.abort();
  }, [load, revision]);
  return <section aria-label={title} aria-busy={state === 'loading'} className="min-w-0 rounded-lg border border-zinc-700 bg-zinc-900/60 p-4">
    <header className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <h3 className="text-lg font-semibold text-zinc-100">{title}</h3>
      <button type="button" className={control} disabled={state === 'loading'} aria-label={`${vi ? 'Làm mới' : 'Refresh'} ${title}`} onClick={() => {
        if (busy.current) return;
        busy.current = true; setRevision((n) => n + 1);
      }}>{state === 'error' ? (vi ? 'Thử lại' : 'Retry') : (vi ? 'Làm mới' : 'Refresh')}</button>
    </header>
    {state === 'loading' && <p role="status">{vi ? 'Đang tải dữ liệu…' : 'Loading observation…'}</p>}
    {state === 'error' && <p role="alert">{vi ? 'Dữ liệu không khả dụng hoặc không hợp lệ.' : 'Observation unavailable or invalid.'}</p>}
    {data && state === 'ready' && <>
      <p className="mb-3 break-words text-sm text-zinc-300">{data.is_synthetic ? (vi ? 'MÔ PHỎNG — Không phải dữ liệu thực' : 'SIMULATION — Not live evidence') : (vi ? 'Dữ liệu quan sát — Nguồn gốc chưa được xác minh PIT' : 'Observed — Not PIT-verified')} · {data.source}<br />{vi ? 'Thời điểm' : 'As of'}: <time dateTime={data.as_of}>{data.as_of}</time></p>
      {children(data)}
    </>}
  </section>;
}

function NewsFeed({ data }: { data: MacroNewsLatestResponse }) {
  const [search, setSearch] = useState(''), [polarity, setPolarity] = useState('ALL'), [sector, setSector] = useState('ALL');
  const vi = useUiStore((s) => s.locale === 'vi');
  const sectors = [...new Set(data.items.map((item) => item.sector).filter((value): value is string => !!value))].sort();
  const items = data.items.filter((item) => (polarity === 'ALL' || item.polarity === polarity) && (sector === 'ALL' || item.sector === sector) &&
    [item.title, item.source, item.symbol, item.summary].join(' ').toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  return <>
    <div className="mb-4 flex flex-wrap gap-3">
      <label className="flex min-w-0 flex-1 flex-col gap-1">{vi ? 'Tìm tin' : 'Search news'}<input type="search" maxLength={256} className={control + ' w-full'} value={search} onChange={(e) => setSearch(e.target.value)} /></label>
      <label className="flex flex-col gap-1">{vi ? 'Cảm xúc' : 'Sentiment'}<select className={control} value={polarity} onChange={(e) => setPolarity(e.target.value)}>{['ALL', 'BULLISH', 'BEARISH', 'NEUTRAL'].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label className="flex min-w-0 flex-col gap-1">{vi ? 'Ngành' : 'Sector'}<select className={control + ' max-w-full'} value={sector} onChange={(e) => setSector(e.target.value)}><option value="ALL">{vi ? 'Tất cả ngành' : 'All sectors'}</option>{sectors.map((value) => <option key={value}>{value}</option>)}</select></label>
    </div>
    <p role="status" className="mb-2 text-sm text-zinc-300">{items.length} / {data.items.length} {vi ? 'tin trong bản chụp' : 'snapshot articles'}</p>
    {!items.length && <p>{vi ? 'Không có tin phù hợp.' : 'No news matching filters.'}</p>}
    <ol className="divide-y divide-zinc-700">{items.map((item) => <li key={item.news_id} className="py-4">
      <article className="break-words">
        <h4 className="text-base font-semibold">{item.title}</h4>
        <p className="my-2 text-sm text-zinc-300">{item.source} · {item.symbol || '—'} · {item.sector || '—'} · {item.polarity} · {item.sentiment_score.toFixed(2)}</p>
        {item.summary && <p className="max-w-prose whitespace-pre-wrap text-base leading-relaxed text-zinc-200">{item.summary}</p>}
        <p className="mt-2 text-sm text-zinc-300">{vi ? 'Xuất bản' : 'Published'}: <time dateTime={item.published_at}>{item.published_at}</time><br />{vi ? 'Khả dụng' : 'Available'}: <time dateTime={item.available_at}>{item.available_at}</time></p>
        {!!item.macro_tags.length && <p className="mt-2 text-sm">{item.macro_tags.join(' · ')}</p>}
      </article>
    </li>)}</ol>
  </>;
}

function SentimentGauge({ data }: { data: VSIGreedFearResponse }) {
  const vi = useUiStore((s) => s.locale === 'vi');
  if (!data.article_count) return <p role="status">{vi ? 'VSI không khả dụng — chưa có mẫu tin.' : 'VSI unavailable — No article samples.'}</p>;
  return <>
    <p className="font-sans text-5xl font-semibold">{data.score.toFixed(1)}<span className="text-base text-zinc-300"> / 100</span></p>
    <p className="my-2">{data.level.replaceAll('_', ' ').toUpperCase()} · {data.article_count} {vi ? 'tin' : 'articles'}</p>
    <meter aria-label="VSI greed-fear score" min={0} max={100} value={data.score} className="h-6 w-full accent-amber-400">{data.score} / 100</meter>
    <p className="mb-3 flex justify-between text-sm text-zinc-300"><span>0 · {vi ? 'Sợ hãi cực độ' : 'Extreme fear'}</span><span>100 · {vi ? 'Tham lam cực độ' : 'Extreme greed'}</span></p>
    <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3">{[['BULLISH', data.bullish_ratio], ['NEUTRAL', data.neutral_ratio], ['BEARISH', data.bearish_ratio]].map(([name, value]) => <div key={name}><dt className="text-sm text-zinc-300">{name}</dt><dd>{(Number(value) * 100).toFixed(1)}%</dd></div>)}</dl>
    {!!data.history_7d.length && <details className="mt-4"><summary className="min-h-11 cursor-pointer focus-visible:outline-2 focus-visible:outline-amber-300">{vi ? 'Lịch sử VSI' : 'VSI history'}</summary><div className="overflow-auto"><table className="w-full text-left text-sm"><caption>{vi ? 'Mẫu tại từng thời điểm riêng biệt' : 'Samples at independent historical cutoffs'}</caption><thead><tr><th scope="col">{vi ? 'Thời điểm' : 'Cutoff'}</th><th scope="col">VSI</th><th scope="col">{vi ? 'Số tin' : 'Articles'}</th></tr></thead><tbody>{data.history_7d.map((point) => <tr key={point.as_of}><th scope="row" className="py-2 font-normal">{point.as_of}</th><td className="tabular-nums">{point.article_count ? point.vsi_score.toFixed(1) : '—'}</td><td>{point.article_count}</td></tr>)}</tbody></table></div></details>}
  </>;
}

function ContagionMatrix({ data }: { data: SectorContagionResponse }) {
  const vi = useUiStore((s) => s.locale === 'vi');
  if (!data.nodes.length) return <p>{vi ? 'Không có dữ liệu ngành.' : 'No sector observations.'}</p>;
  const targets = [...new Set(data.nodes.flatMap((node) => [node.sector, ...node.correlated_sectors.map((edge) => edge.sector)]))].sort();
  return <>
    <p className="mb-3">{vi ? 'Chỉ số' : 'Index'}: {data.overall_contagion_index.toFixed(1)} / 100 · {data.systemic_risk_level}</p>
    <div className="overflow-auto" tabIndex={0} role="region" aria-label={vi ? 'Bảng lan truyền ngành' : 'Sector relationship table'}>
      <table className="w-full text-left text-sm tabular-nums"><caption className="mb-2 text-left text-zinc-300">{vi ? 'Trọng số tương quan có hướng; — là không được báo cáo, không phải 0' : 'Directed correlation weights; — means not reported, not zero'}</caption>
        <thead><tr><th scope="col" className="p-2">{vi ? 'Ngành nguồn' : 'Source sector'}</th><th scope="col" className="p-2">{vi ? 'Áp lực / 100' : 'Stress / 100'}</th><th scope="col" className="p-2">{vi ? 'Truyền dẫn' : 'Transmission'}</th>{targets.map((target) => <th key={target} scope="col" className="p-2">{target}</th>)}</tr></thead>
        <tbody>{data.nodes.map((node) => <tr key={node.sector} className="border-t border-zinc-700"><th scope="row" className="p-2 font-normal">{node.sector}<br />{node.contagion_level} · {node.trend_24h}<br />Δ {node.sentiment_delta.toFixed(2)}</th><td className="p-2">{node.stress_score.toFixed(1)}</td><td className="p-2">{(node.transmission_risk * 100).toFixed(1)}%</td>{targets.map((target) => {
          const edge = node.correlated_sectors.find((item) => item.sector === target);
          return <td key={target} className="p-2" title={`${node.sector} / ${target}`}>{edge ? edge.correlation_weight.toFixed(2) : '—'}</td>;
        })}</tr>)}</tbody>
      </table>
    </div>
  </>;
}

function IntelligenceSummary({ data }: { data: LLMMacroIntelligenceResponse }) {
  const vi = useUiStore((s) => s.locale === 'vi');
  return <div className="break-words text-base leading-relaxed">
    <p className="text-sm text-zinc-300">{data.model} · {data.prompt_version} · {vi ? 'Độ tin cậy' : 'Confidence'} {(data.sentiment_confidence * 100).toFixed(1)}%</p>
    <p className="my-3 whitespace-pre-wrap">{data.regime_summary}</p><p className="mb-3 font-semibold">{data.executive_verdict}</p>
    {[[vi ? 'Rủi ro chính' : 'Primary risks', data.primary_risks], [vi ? 'Chất xúc tác' : 'Catalysts', data.catalysts]].map(([title, values]) => <div key={String(title)} className="mb-3"><h4 className="font-semibold">{String(title)}</h4><ul className="list-inside list-disc">{(values as string[]).map((value, i) => <li key={i}>{value}</li>)}</ul></div>)}
    <h4 className="font-semibold">{vi ? 'Tác động ngành' : 'Sector impacts'}</h4><dl>{Object.entries(data.sector_impacts).map(([sector, impact]) => <div key={sector} className="my-2"><dt className="font-semibold">{sector}</dt><dd>{impact}</dd></div>)}</dl>
    <p className="mt-3 text-sm">Tags: {data.macro_tags.join(' · ') || '—'}<br />{vi ? 'Thực thể' : 'Entities'}: {data.key_entities.join(' · ') || '—'}</p>
  </div>;
}

export const MacroNewsHubView: React.FC = () => {
  const vi = useUiStore((s) => s.locale === 'vi');
  return <section data-testid="macro-news-hub-view" aria-label={vi ? 'Trung tâm tin tức vĩ mô' : 'Macro News Hub'} className="min-w-0 select-text space-y-4">
    <header><h2 className="text-xl font-semibold">{vi ? 'Trung tâm tin tức vĩ mô' : 'Macro News Hub'}</h2><p className="mt-2 text-sm text-zinc-300">{vi ? 'Bản chụp theo yêu cầu. Không có luồng trực tiếp; mô phỏng được ghi rõ.' : 'On-demand snapshots. No live stream; simulations explicitly labeled.'}</p></header>
    <div className="grid min-w-0 grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Observation title={vi ? 'Tin mới nhất' : 'Latest news'} load={loaders.news}>{(data) => <NewsFeed data={data} />}</Observation>
      <div className="min-w-0 space-y-4">
        <Observation title="Vietnam Sentiment Index (VSI)" load={loaders.vsi}>{(data) => <SentimentGauge data={data} />}</Observation>
        <Observation title={vi ? 'Tóm tắt thông minh LLM' : 'LLM intelligence summary'} load={loaders.intelligence}>{(data) => <IntelligenceSummary data={data} />}</Observation>
      </div>
    </div>
    <Observation title={vi ? 'Ma trận lan truyền ngành' : 'Sector contagion matrix'} load={loaders.contagion}>{(data) => <ContagionMatrix data={data} />}</Observation>
  </section>;
};

export default MacroNewsHubView;
