"""Real Strategy Lab payloads, adversarial adapters, React lifecycle and browser reflow."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".ly_state/session"
spec = importlib.util.spec_from_file_location("strategy_ui_contract_fixtures", ROOT / "tests/api/test_strategy_contracts.py")
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)
strategy = contracts.strategy
market = contracts.market


@pytest.fixture(scope="module")
def strategy_runtime():
    suite = EVIDENCE / "slice5_strategy_ui.generated.test.tsx"
    config = EVIDENCE / "slice5_strategy_ui.vitest.config.mjs"
    for path in [suite, config]:
        assert not path.exists(), f"Refuse to overwrite {path}"
    suite.write_text(VITEST, encoding="utf-8", newline="\n")
    config.write_text("export default " + json.dumps({"test": {"environment": "jsdom", "globals": True, "include": [suite.as_posix()], "testTimeout": 20000}}), encoding="utf-8", newline="\n")
    yield suite, config
    suite.unlink()
    config.unlink()


def run_vitest(runtime, category=None):
    _, config = runtime
    command = ["node", str(ROOT / "omega-ui/node_modules/vitest/vitest.mjs"), "run", "--config", str(config), "--reporter=verbose"]
    if category:
        command += ["-t", rf"Strategy analytics > {category}\b"]
    result = subprocess.run(command, cwd=ROOT / "omega-ui", capture_output=True, text=True, encoding="utf-8", timeout=120)
    (EVIDENCE / f"slice5_vitest_{category or 'full'}.log").write_text(result.stdout + result.stderr, encoding="utf-8", newline="\n")
    if result.returncode:
        pytest.fail(result.stdout + result.stderr, pytrace=False)


@pytest.mark.parametrize("category", ["contract", "numeric", "schema", "pit", "network", "lifecycle", "view"])
def test_strategy_adversarial_vitest(strategy_runtime, category):
    run_vitest(strategy_runtime, category)


def test_strategy_backend_payload_contracts(market, strategy_runtime):
    client, _, body = market
    read = {"strategy_id": "TEST_STRATEGY", "as_of": contracts.CUTOFF}
    diagnostics = contracts.get(client, "overfitting-diagnostics")
    equity = contracts.get(client, "strategy-equity-curve")
    chrono = client.post("/api/v1/quant/walk-forward", json=body)
    cpcv_body = {**body, "evaluation_method": "COMBINATORIAL_PURGED_K_FOLD", "n_splits": 6, "n_test_splits": 2}
    cpcv = client.post("/api/v1/quant/walk-forward", json=cpcv_body)
    assert all(r.status_code == 200 for r in [diagnostics, equity, chrono, cpcv])
    path = EVIDENCE / "slice5_strategy_backend_payloads.json"
    assert not path.exists()
    path.write_text(json.dumps({"read": read, "diagnostics": diagnostics.json(), "equity": equity.json(), "chronological": chrono.json(), "chronologicalRequest": body, "cpcv": cpcv.json(), "cpcvRequest": cpcv_body}), encoding="utf-8", newline="\n")
    try:
        run_vitest(strategy_runtime, "backend")
    finally:
        path.unlink()


def test_strategy_vitest_full(strategy_runtime):
    run_vitest(strategy_runtime)


def test_strategy_browser_reflow_and_keyboard(tmp_path):
    from playwright.sync_api import sync_playwright

    runner = tmp_path / "strategy_browser.cjs"
    script = tmp_path / "strategy.js"
    css = tmp_path / "strategy.css"
    runner.write_text(r'''
const fs=require('node:fs'),path=require('node:path'),root=process.argv[2];
async function main(){
 const text=fs.readFileSync(path.join(root,'tests/test_ui_strategy_lab.py'),'utf8'),source=text.slice(text.lastIndexOf("import React, { act }"));
 const fixtures=source.slice(source.indexOf("const cutoff ="),source.indexOf("const copy ="));
 const entry=`import React from 'react';import {createRoot} from 'react-dom/client';import {WalkForwardHeatmap,CumulativeEquityCurve,DeflatedSharpeGauge,OverfittingMetricsTable} from './src/modules/strategy_lab/StrategyLabView';${fixtures}createRoot(document.getElementById('root')).render(<main className="grid min-w-0 gap-4"><WalkForwardHeatmap data={walk}/><div className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-2"><DeflatedSharpeGauge data={diagnostics}/><OverfittingMetricsTable data={diagnostics}/></div><CumulativeEquityCurve data={equity}/></main>);`;
 require(path.join(root,'omega-ui/node_modules/esbuild')).buildSync({stdin:{contents:entry,loader:'tsx',resolveDir:path.join(root,'omega-ui')},bundle:true,format:'iife',define:{'import.meta.env':'{}'},outfile:process.argv[3]});
 const {compile}=require('node:module').createRequire(path.join(root,'omega-ui/package.json'))('@tailwindcss/node');
 const compiler=await compile('@import "tailwindcss";',{base:path.join(root,'omega-ui'),onDependency:()=>{}});
 const view=fs.readFileSync(path.join(root,'omega-ui/src/modules/strategy_lab/StrategyLabView.tsx'),'utf8');
 const classes=[...view.matchAll(/(?:className=|const \w+Class = )['"]([^'"]+)['"]/g)].flatMap(m=>m[1].split(/\s+/));
 fs.writeFileSync(process.argv[4],compiler.build([...classes,'grid','gap-4','min-w-0','grid-cols-1','lg:grid-cols-2']));
}main().catch(e=>{console.error(e);process.exitCode=1;});
''', encoding="utf-8", newline="\n")
    result = subprocess.run(["node", str(runner), str(ROOT), str(script), str(css)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    if result.returncode:
        pytest.fail(result.stdout + result.stderr, pytrace=False)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = '<html><head><style>' + css.read_text(encoding="utf-8") + '</style></head><body style="background:#09090b;padding:16px;color:#f4f4f5"><div id="root"></div></body></html>'
        page.route('https://strategy.test/**', lambda route: route.fulfill(body=html, content_type='text/html'))
        page.goto('https://strategy.test/')
        page.add_script_tag(path=str(script))
        try:
            page.get_by_role("heading", name="CumulativeEquityCurve").wait_for(timeout=5000)
        except Exception:
            pytest.fail(str(errors), pytrace=False)
        for width in [320, 768, 1440]:
            page.set_viewport_size({"width": width, "height": 1100})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), str(width)
            assert page.get_by_role("meter").is_visible()
            page.get_by_role("button", name="Fold 1 IS Sharpe 1.00").focus()
            assert page.evaluate("document.activeElement.getAttribute('aria-label')") == "Fold 1 IS Sharpe 1.00"
            page.get_by_role("slider", name="Equity observation").focus()
            page.keyboard.press("End")
            assert page.get_by_role("slider").input_value() == "1"
            assert page.get_by_role("img", name="Gross, net and benchmark equity in VND on one shared axis").is_visible()
            page.screenshot(path=str(EVIDENCE / f"slice5_strategy_{width}.png"), full_page=True)
        assert not errors, str(errors)
        browser.close()


VITEST = r'''
import React, { act } from '../../omega-ui/node_modules/react/index.js';
import { createRoot } from '../../omega-ui/node_modules/react-dom/client.js';
import { describe, it, expect, vi, afterEach } from '../../omega-ui/node_modules/vitest/dist/index.js';
import * as api from '../../omega-ui/src/api/advancedQuant';
import { useStrategyLab } from '../../omega-ui/src/hooks/useStrategyLab';
import { StrategyLabView, WalkForwardHeatmap, CumulativeEquityCurve, DeflatedSharpeGauge, OverfittingMetricsTable } from '../../omega-ui/src/modules/strategy_lab/StrategyLabView';
import { useUiStore } from '../../omega-ui/src/store/uiStore';
import fs from 'node:fs';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
const cutoff = '2023-12-31T08:30:00Z', read = {strategy_id:'TEST_STRATEGY',as_of:cutoff};
const integrity = {content_sha256:'a'.repeat(64),effective_cutoff:cutoff};
const diagnostics = {status:'success', strategy_id:'TEST_STRATEGY', trials_tested:2,pbo:.1,deflated_sharpe_ratio:.96,observed_sharpe:.1,expected_max_sharpe:.02,variance_of_trials:.01,skewness:0,kurtosis:3,fdr_q_values:[],is_overfitted:false,verdict:'EMPIRICAL_DIAGNOSTICS_ONLY',provenance:null,probabilistic_sharpe_ratio:.97,trial_distribution:[{trial_id:'A',sharpe:1},{trial_id:'B',sharpe:.5}],metric_unavailable_reason:null,pbo_method:'CSCV_8_BLOCKS_EMPIRICAL_RANK',sharpe_unit:'PER_BAR',statistical_assumption:'IID_APPROXIMATION_CORRELATED_TRIALS_NOT_INDEPENDENT',trial_distribution_sharpe_unit:'ANNUALIZED_252',provenance_verification:'CONTENT_INTEGRITY_ONLY_NOT_AUTHENTICATED_LINEAGE',diagnostic_basis:'PERSISTED_STRATEGY_TRIALS',requested_trials_tested:null,input_integrity:integrity};
const equity = {status:'success',strategy_id:'TEST_STRATEGY',price_scale:'VND_FULL',provenance_verification:'CONTENT_INTEGRITY_ONLY_NOT_AUTHENTICATED_LINEAGE',cost_model:'PERSISTED_AGGREGATE_FEE_RETURNS_NO_ASSUMED_COSTS',benchmark_id:'VNINDEX',equity_curve:[{date:'2023-03-01T08:30:00Z',gross_equity:1e9,net_equity:1e9,benchmark_equity:1e9,drawdown_pct:0,fees_vnd:0},{date:'2023-03-02T08:30:00Z',gross_equity:1.02e9,net_equity:1.01e9,benchmark_equity:1e9,drawdown_pct:0,fees_vnd:1e7}],total_fees_vnd:1e7,gross_return_pct:2,net_return_pct:1,benchmark_return_pct:0,max_drawdown_pct:0,provenance:null,input_integrity:integrity};
const walkRequest = {universe:['FPT'],start_date:'2023-03-01',end_date:'2023-03-03',n_splits:3,n_test_splits:1,as_of:cutoff};
const folds=Array.from({length:3},(_,fold)=>({fold,train_size:2,test_size:2,in_sample_sharpe:1,out_of_sample_sharpe:.5,in_sample_return_pct:2,out_of_sample_return_pct:1,max_drawdown_pct:0,train_start:'2023-03-01T08:30:00Z',train_end:'2023-03-02T08:30:00Z',train_label_end:'2023-03-03T08:30:00Z',test_start:'2023-03-01T08:30:00Z',test_end:'2023-03-02T08:30:00Z',decision_time:null,train_indices:[2,3],test_indices:[0,1],purged_size:0,embargo_size:0,gross_oos_return_pct:2,oos_observations:2}));
const walk={status:'success',task_type:'WALK_FORWARD_CPCV',job_id:'12345678-1234-1234-1234-123456789012',dataset_id:'market_2015_now',n_splits:3,n_test_splits:1,total_folds:3,mean_oos_sharpe:.5,median_oos_sharpe:.5,std_oos_sharpe:0,mean_oos_return_pct:1,worst_drawdown_pct:0,pbo:null,deflated_sharpe_ratio:null,folds,provenance:null,evaluation_method:'COMBINATORIAL_PURGED_K_FOLD',historical_pit_verified:false,historical_timing_validated:false,excluded_incomplete_sessions:0,coverage_policy:'COMPLETE_CASE_INTERSECTION',strategy_definition:'FIXED_EQUAL_WEIGHT_DAILY_REBALANCE',price_scale:'VND_FULL',oos_return_pct:1,gross_oos_return_pct:2,metric_unavailable_reason:'Retrospective only',cost_model:'DECLARED_DAILY_COMMISSION_PLUS_SLIPPAGE_BPS',provenance_verification:'VALIDATED_MARKET_METADATA_NOT_AUTHENTICATED_LINEAGE'};
const copy = v => structuredClone(v), bad=[null,undefined,true,'1',[],{},NaN,Infinity,-Infinity,1e13];
let root, container;
const flush = async(fn=()=>{})=>act(async()=>{await fn();await Promise.resolve();await Promise.resolve();});
const mount=async element=>{container=document.createElement('div');document.body.append(container);root=createRoot(container);await flush(()=>root.render(element));};
const deferred=()=>{let resolve,reject;return {promise:new Promise((a,b)=>{resolve=a;reject=b}),get resolve(){return resolve},get reject(){return reject}};};
afterEach(async()=>{if(root)await flush(()=>root.unmount());root=null;container?.remove();vi.restoreAllMocks();vi.useRealTimers();});

describe('Strategy analytics',()=>{
 it('contract accepts exact DTOs, null undefined metrics, proxy labels, immutable requests',()=>{
  api.validateStrategyDiagnostics(diagnostics,read);api.validateStrategyEquity(equity,read);api.validateStrategyWalk(walk,walkRequest);
  const request=copy(walkRequest),snapshot=api.validateStrategyWalkRequest(request);request.universe[0]='HPG';expect(snapshot.universe[0]).toBe('FPT');
  const d=copy(diagnostics);for(const k of ['pbo','deflated_sharpe_ratio','probabilistic_sharpe_ratio','observed_sharpe','expected_max_sharpe','variance_of_trials','skewness','kurtosis'])d[k]=null;d.metric_unavailable_reason='DEGENERATE_RETURN_DISTRIBUTION';d.is_overfitted=true;d.verdict='INSUFFICIENT_STATISTICAL_EVIDENCE';api.validateStrategyDiagnostics(d,read);
  const proxy=copy(diagnostics);Object.assign(proxy,{diagnostic_basis:'EMPIRICAL_INSTRUMENT_PROXY',provenance_verification:'EMPIRICAL_MARKET_PROXY_NOT_STRATEGY_EVIDENCE',verdict:'EMPIRICAL_MARKET_PROXY_NOT_STRATEGY_VALIDATION',requested_trials_tested:20,input_integrity:{...integrity,max_included_available_at:cutoff,selected_proxy:'A',excluded_incomplete_sessions:0}});api.validateStrategyDiagnostics(proxy,{...read,trials_tested:20});
  expect(api.formatStrategyMetric(0)).toBe('0.00');expect(api.formatStrategyMetric(null)).toBe('--');
 });
 it('numeric rejects nonfinite, overflow, zero capital, negative fees, bogus divisors',()=>{
  for(const v of bad){for(const k of ['pbo','observed_sharpe','variance_of_trials']){const d=copy(diagnostics);d[k]=v;if(v!==null)expect(()=>api.validateStrategyDiagnostics(d,read)).toThrow();}
   for(const k of ['net_equity','gross_equity','benchmark_equity','fees_vnd']){const e=copy(equity);e.equity_curve[1][k]=v;expect(()=>api.validateStrategyEquity(e,read)).toThrow();}
   for(const k of ['initial_capital','n_splits','embargo_pct','slippage_bps'])if(v!==undefined)expect(()=>api.validateStrategyWalkRequest({...walkRequest,[k]:v}),`${k}: ${v}`).toThrow();
  }
  for(const v of [0,-1])expect(()=>api.validateStrategyWalkRequest({...walkRequest,initial_capital:v})).toThrow();
  for(const v of [0,-1]){const e=copy(equity);e.equity_curve[0].net_equity=v;expect(()=>api.validateStrategyEquity(e,read)).toThrow();}
  const e=copy(equity);e.equity_curve[1].fees_vnd=-1;expect(()=>api.validateStrategyEquity(e,read)).toThrow();
  const w=copy(walk);w.folds[0].test_size=0;expect(()=>api.validateStrategyWalk(w,walkRequest)).toThrow();
 });
 it('schema rejects missing extra corrupt duplicate partial and resource-bound data',()=>{
  for(const [value,validate] of [[diagnostics,v=>api.validateStrategyDiagnostics(v,read)],[equity,v=>api.validateStrategyEquity(v,read)],[walk,v=>api.validateStrategyWalk(v,walkRequest)]]){
   for(const v of [null,[],{},true,'success'])expect(()=>validate(v)).toThrow();
   for(const k of Object.keys(value)){const v=copy(value);delete v[k];expect(()=>validate(v),k).toThrow();}
   expect(()=>validate({...value,role_id:13})).toThrow();
  }
  for(const mutate of [e=>e.equity_curve=[],e=>e.equity_curve=Array(10002).fill(e.equity_curve[0]),e=>e.equity_curve[1].date=e.equity_curve[0].date,e=>e.price_scale='VND_THOUSAND',e=>e.net_return_pct=5,e=>e.max_drawdown_pct=10,e=>e.total_fees_vnd=0,e=>e.equity_curve[1].drawdown_pct=-1]){const e=copy(equity);mutate(e);expect(()=>api.validateStrategyEquity(e,read)).toThrow();}
  for(const mutate of [w=>w.folds=[],w=>w.folds[1].fold=0,w=>w.folds[0].test_indices=[2,3],w=>w.total_folds=2,w=>w.folds[0].oos_observations=1,w=>w.folds[0].legacy=1,w=>w.historical_pit_verified=true,w=>w.provenance={source:'caller_sample'}]){const w=copy(walk);mutate(w);expect(()=>api.validateStrategyWalk(w,walkRequest)).toThrow();}
  const d=copy(diagnostics);d.trial_distribution[1].trial_id='A';expect(()=>api.validateStrategyDiagnostics(d,read)).toThrow();
  expect(()=>api.validateStrategyRead({...read,strategy_id:'../x --flag'})).toThrow();expect(()=>api.validateStrategyWalkRequest({...walkRequest,universe:[]})).toThrow();expect(()=>api.validateStrategyWalkRequest({...walkRequest,universe:['A','A']})).toThrow();expect(()=>api.validateStrategyWalkRequest({...walkRequest,n_splits:20,n_test_splits:5})).toThrow();
 });
 it('pit enforces inclusive cutoff, timezone and 15:30 ICT close, rejects future and invalid calendars',()=>{
  const e=copy(equity);e.input_integrity.effective_cutoff=e.equity_curve[1].date;api.validateStrategyEquity(e,{...read,as_of:'2023-03-02T15:30:00+07:00'});
  for(const date of ['2023-03-02T08:29:59Z','2023-03-02T08:30:00','2023-02-30T08:30:00Z','2023-03-04T08:30:00Z','2099-01-01T08:30:00Z']){const v=copy(equity);v.equity_curve[1].date=date;expect(()=>api.validateStrategyEquity(v,read)).toThrow();}
  expect(()=>api.validateStrategyRead({...read,as_of:'2099-01-01T00:00:00Z'})).toThrow();expect(()=>api.validateStrategyWalkRequest({...walkRequest,as_of:'2023-03-03T08:29:59Z'})).toThrow();
  for(const v of ['2023-12-31T08:30:01Z','2023-12-30T08:30:00Z']){const d=copy(diagnostics);d.input_integrity.effective_cutoff=v;expect(()=>api.validateStrategyDiagnostics(d,read)).toThrow();}
 });
 it('network exact endpoints no blind POST retries safe errors cancellation timeout',async()=>{
  const requests=[];vi.stubGlobal('fetch',vi.fn(async(url,init)=>{requests.push([url,init]);return {ok:true,json:async()=>String(url).includes('walk-forward')?walk:String(url).includes('strategy-equity')?equity:diagnostics};}));
  await api.advancedQuantApi.runWalkForwardCpcv(walkRequest);await api.advancedQuantApi.getOverfittingDiagnostics('TEST_STRATEGY',undefined,undefined,cutoff);await api.advancedQuantApi.getStrategyEquity(read);
  expect(requests[0][0]).toContain('/api/v1/quant/walk-forward');expect(requests[0][1].method).toBe('POST');expect(JSON.parse(requests[0][1].body)).toEqual(walkRequest);expect(requests[1][0]).toContain('strategy_id=TEST_STRATEGY');expect(requests[1][0]).not.toContain('trials_tested');expect(requests[2][0]).toContain('/api/v1/quant/strategy-equity-curve');
  for(const status of [401,403,422,424,429,500]){fetch.mockClear();fetch.mockResolvedValue({ok:false,status,json:async()=>({detail:'https://user:SECRET@host/?token=SECRET'})});await expect(api.advancedQuantApi.runWalkForwardCpcv(walkRequest)).rejects.toThrow('Strategy analytics unavailable');expect(fetch).toHaveBeenCalledTimes(1);}
  fetch.mockRejectedValue(new Error('https://user:SECRET@host'));await expect(api.advancedQuantApi.getStrategyEquity(read)).rejects.not.toThrow('SECRET');
  const controller=new AbortController();controller.abort();await expect(api.advancedQuantApi.getStrategyEquity(read,controller.signal)).rejects.toMatchObject({name:'AbortError'});
  vi.useFakeTimers();fetch.mockImplementation((_url,init)=>new Promise((_,reject)=>init.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))));
  const pending=api.advancedQuantApi.getStrategyEquity(read);const rejected=expect(pending).rejects.toThrow('Strategy analytics unavailable');await vi.advanceTimersByTimeAsync(10001);await rejected;
  vi.unstubAllGlobals();
 });
 it('lifecycle aborts stale reads runs and unmount; fails closed on corruption and snapshot mismatch',async()=>{
  let handle,params=read,wreq=walkRequest;const reads=[],runs=[];
  vi.spyOn(api.advancedQuantApi,'getOverfittingDiagnostics').mockImplementation((id,_n,signal)=>{const d=deferred();reads.push({id,signal,d});return d.promise;});
  vi.spyOn(api.advancedQuantApi,'getStrategyEquity').mockResolvedValue(equity);
  vi.spyOn(api.advancedQuantApi,'runWalkForwardCpcv').mockImplementation((_r,signal)=>{const d=deferred();runs.push({d,signal});return d.promise;});
  function Probe(){handle=useStrategyLab(params,wreq);return <output>{handle.diagnostics?.strategy_id??handle.diagnosticsError??'Loading'}</output>;}
  await mount(<Probe/>);expect(runs).toHaveLength(0);await flush(()=>reads[0].d.resolve(diagnostics));expect(handle.diagnostics.strategy_id).toBe('TEST_STRATEGY');
  await flush(()=>{void handle.runWalkForward();});await flush(()=>{void handle.runWalkForward();});expect(runs[0].signal.aborted).toBe(true);await flush(()=>runs[0].d.resolve(walk));expect(handle.walk).toBeNull();await flush(()=>runs[1].d.resolve(walk));expect(handle.walk.total_folds).toBe(3);
  params={...read,strategy_id:'OTHER'};await flush(()=>root.render(<Probe/>));expect(reads[0].signal.aborted).toBe(true);expect(handle.diagnostics).toBeNull();expect(handle.walk).toBeNull();
  await flush(()=>reads[1].d.resolve(diagnostics));expect(handle.diagnostics).toBeNull();expect(handle.diagnosticsError).toBeTruthy();
  params=read;await flush(()=>root.render(<Probe/>));const mismatch=copy(diagnostics);mismatch.input_integrity.content_sha256='b'.repeat(64);await flush(()=>reads[2].d.resolve(mismatch));expect(handle.diagnostics).toBeNull();expect(handle.equity).toBeNull();expect(handle.diagnosticsError).toContain('disagree');
  await flush(()=>{handle.refresh();reads[2].d.resolve(diagnostics);});expect(reads[2].signal.aborted).toBe(true);expect(handle.diagnostics).toBeNull();await flush(()=>reads[3].d.reject(new Error('SECRET https://user:SECRET@host')));expect(handle.diagnosticsError).not.toContain('SECRET');
  params={...read,as_of:''};await flush(()=>root.render(<Probe/>));expect(handle.valid).toBe(false);expect(handle.equity).toBeNull();
  params=read;await flush(()=>root.render(<Probe/>));const latest=reads.at(-1);await flush(()=>root.unmount());root=null;expect(latest.signal.aborted).toBe(true);await flush(()=>latest.d.resolve(diagnostics));
 });
 it('lifecycle rejects malformed equity and accepts equivalent timezone snapshots independently',async()=>{
  let handle;const equivalent=copy(equity);equivalent.input_integrity.effective_cutoff='2023-12-31T15:30:00+07:00';
  vi.spyOn(api.advancedQuantApi,'getOverfittingDiagnostics').mockResolvedValue(diagnostics);
  const getEquity=vi.spyOn(api.advancedQuantApi,'getStrategyEquity').mockResolvedValue(equivalent);
  function Probe(){handle=useStrategyLab(read,walkRequest);return null;}
  await mount(<Probe/>);await flush();expect(handle.diagnostics).not.toBeNull();expect(handle.equity).not.toBeNull();
  getEquity.mockResolvedValue({...equity,equity_curve:[]});await flush(()=>handle.refresh());await flush();expect(handle.equity).toBeNull();expect(handle.equityError).toBeTruthy();expect(handle.diagnostics).not.toBeNull();
 });
 it('view preserves tabs accessible numerical equivalents explicit calculation and error states',async()=>{
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date(cutoff));
  useUiStore.setState({activeSubTabs:{strategy_lab:'lab'},activeFeatureId:null});
  vi.spyOn(api.advancedQuantApi,'getOverfittingDiagnostics').mockResolvedValue({...diagnostics,strategy_id:'ALPHA_HRP_V2'});
  vi.spyOn(api.advancedQuantApi,'getStrategyEquity').mockResolvedValue({...equity,strategy_id:'ALPHA_HRP_V2'});
  const run=vi.spyOn(api.advancedQuantApi,'runWalkForwardCpcv').mockRejectedValue(new Error('SECRET'));
  await mount(<StrategyLabView/>);await flush();expect(run).not.toHaveBeenCalled();expect(container.querySelectorAll('nav button')).toHaveLength(5);expect(container.querySelector('meter').getAttribute('aria-label')).toBe('Deflated Sharpe confidence');expect(container.querySelector('svg[role=img]')).not.toBeNull();expect(container.querySelectorAll('table').length).toBeGreaterThanOrEqual(3);
  await flush(()=>[...container.querySelectorAll('button')].find(b=>b.textContent.includes('Run walk-forward')).click());expect(container.textContent).not.toContain('SECRET');expect(container.querySelector('[role=alert]')).not.toBeNull();
  const input=[...container.querySelectorAll('input')].find(e=>e.parentElement.textContent.includes('Decision cutoff'));await flush(()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'');input.dispatchEvent(new Event('input',{bubbles:true}));});expect(container.textContent).toContain('Previous results hidden');expect(container.querySelector('meter')).toBeNull();
 });
 it('view chart focus hover readout zero range and null metric render safely',async()=>{
  await mount(<><WalkForwardHeatmap data={walk}/><CumulativeEquityCurve data={equity}/><DeflatedSharpeGauge data={diagnostics}/><OverfittingMetricsTable data={diagnostics}/></>);
  const cell=container.querySelector('button[aria-label*="IS Sharpe"]');await flush(()=>cell.focus());expect(container.textContent).toContain('Fold 1 IS Sharpe 1.00');
  const slider=container.querySelector('input[type=range]');await flush(()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(slider,'1');slider.dispatchEvent(new Event('input',{bubbles:true}));});expect(container.textContent).toContain('2023-03-02');
  const constant=copy(equity);constant.equity_curve.forEach(p=>{p.gross_equity=p.net_equity=p.benchmark_equity=1e9;});await flush(()=>root.render(<CumulativeEquityCurve data={constant}/>));expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
 });
 it.skipIf(!fs.existsSync(new URL('./slice5_strategy_backend_payloads.json',import.meta.url)))('backend actual route payloads pass strict frontend contracts',()=>{
  const path=new URL('./slice5_strategy_backend_payloads.json',import.meta.url);
  const v=JSON.parse(fs.readFileSync(path,'utf8'));api.validateStrategyDiagnostics(v.diagnostics,v.read);api.validateStrategyEquity(v.equity,v.read);api.validateStrategyWalk(v.chronological,v.chronologicalRequest);api.validateStrategyWalk(v.cpcv,v.cpcvRequest);
  for(const key of ['effective_cutoff','as_of','requested_pit_cutoff']){const corrupt=copy(v.chronological);corrupt.provenance[key]='2023-12-30T08:30:00Z';expect(()=>api.validateStrategyWalk(corrupt,v.chronologicalRequest)).toThrow();}
  for(const date of ['2023-03-02T08:29:59Z','2023-03-04T08:30:00Z']){const corrupt=copy(v.cpcv);corrupt.folds[0].train_start=date;expect(()=>api.validateStrategyWalk(corrupt,v.cpcvRequest)).toThrow();}
 });
});
'''
