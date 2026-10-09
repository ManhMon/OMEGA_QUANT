"""Execute real TypeScript contracts and React lifecycle against Slice 6 payloads."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".ly_state/session"
spec = importlib.util.spec_from_file_location("fundamental_ui_fixtures", ROOT / "tests/api/test_fundamental_contracts.py")
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)
inputs = contracts.inputs


@pytest.fixture(scope="module")
def fundamental_runtime():
    suite = EVIDENCE / "slice7_fundamental.generated.test.tsx"
    config = EVIDENCE / "slice7_fundamental.vitest.config.mjs"
    assert not suite.exists() and not config.exists()
    suite.write_text(VITEST, encoding="utf-8", newline="\n")
    config.write_text("export default " + json.dumps({"test": {"environment": "jsdom", "globals": True, "include": [suite.as_posix()], "testTimeout": 20000}}), encoding="utf-8", newline="\n")
    try:
        yield config
    finally:
        suite.unlink()
        config.unlink()


def run_vitest(config, category=None):
    command = ["node", str(ROOT / "omega-ui/node_modules/vitest/vitest.mjs"), "run", "--config", str(config), "--reporter=verbose"]
    if category:
        command += ["-t", category]
    env = {**os.environ, "FUNDAMENTAL_BACKEND_PAYLOADS": str(EVIDENCE / "slice7_fundamental_payloads.json")} if category == "backend" else dict(os.environ)
    result = subprocess.run(command, cwd=ROOT / "omega-ui", env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
    (EVIDENCE / f"slice7_vitest_{category or 'full'}.log").write_text(result.stdout + result.stderr, encoding="utf-8", newline="\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Tests  11 skipped" not in result.stdout, "Vitest filter selected no runnable tests"


@pytest.mark.parametrize("category", ["contract", "numeric", "schema", "pit", "network", "lifecycle", "view"])
def test_fundamental_adversarial_vitest(fundamental_runtime, category):
    run_vitest(fundamental_runtime, category)


def test_fundamental_backend_payloads(inputs, fundamental_runtime):
    payloads = {key: contracts.get(inputs, route).json() for key, route in {
        "screener": "screener", "valuation": "fundamental/valuation-matrix",
        "dupont": "fundamental/dupont/AAA", "piotroski": "fundamental/piotroski/AAA",
    }.items()}
    payloads["cutoff"] = contracts.CUTOFF
    path = EVIDENCE / "slice7_fundamental_payloads.json"
    assert not path.exists()
    path.write_text(json.dumps(payloads), encoding="utf-8", newline="\n")
    try:
        run_vitest(fundamental_runtime, "backend")
    finally:
        path.unlink()


def test_fundamental_vitest_full(fundamental_runtime):
    run_vitest(fundamental_runtime)


def test_fundamental_browser_reflow_keyboard(tmp_path):
    from playwright.sync_api import sync_playwright
    runner, script, css = [tmp_path / name for name in ["fundamental.cjs", "fundamental.js", "fundamental.css"]]
    runner.write_text(r'''
const fs=require('node:fs'),path=require('node:path'),root=process.argv[2];
async function main(){
 const text=fs.readFileSync(path.join(root,'tests/test_ui_fundamental_matrix.py'),'utf8');
 const source=text.slice(text.lastIndexOf('import React, { act }'));
 const fixtures=source.slice(source.indexOf('const cutoff ='),source.indexOf('const copy ='));
 const entry=`import React from 'react';import {createRoot} from 'react-dom/client';import {DuPontFactorAnalysis,PiotroskiFScoreBreakdown,ValuationScatterMatrix} from './src/modules/fundamental_matrix/FundamentalMatrixView';${fixtures}createRoot(document.getElementById('root')).render(<><DuPontFactorAnalysis data={dupont}/><PiotroskiFScoreBreakdown data={piotroski}/><ValuationScatterMatrix data={valuation} onSelect={s=>document.getElementById('selection').textContent=s}/><output id="selection"/></>);`;
 require(path.join(root,'omega-ui/node_modules/esbuild')).buildSync({stdin:{contents:entry,loader:'tsx',resolveDir:path.join(root,'omega-ui')},bundle:true,format:'iife',define:{'import.meta.env':'{}'},outfile:process.argv[3]});
 const {compile}=require('node:module').createRequire(path.join(root,'omega-ui/package.json'))('@tailwindcss/node');
 const compiler=await compile('@import "tailwindcss";',{base:path.join(root,'omega-ui'),onDependency:()=>{}});
 const view=fs.readFileSync(path.join(root,'omega-ui/src/modules/fundamental_matrix/FundamentalMatrixView.tsx'),'utf8');
 const classes=[...view.matchAll(/(?:className=|const \w+Class = )['"]([^'"]+)['"]/g)].flatMap(m=>m[1].split(/\s+/));
 fs.writeFileSync(process.argv[4],compiler.build(classes));
}main().catch(e=>{console.error(e);process.exitCode=1;});
''', encoding="utf-8", newline="\n")
    result = subprocess.run(["node", str(runner), str(ROOT), str(script), str(css)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = '<html><head><style>' + css.read_text(encoding="utf-8") + '</style></head><body style="background:#09090b;color:#f4f4f5;padding:16px"><div id="root"></div></body></html>'
        page.route("https://fundamental.test/**", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.goto("https://fundamental.test/")
        page.add_script_tag(path=str(script))
        page.get_by_role("heading", name="Valuation Scatter Matrix").wait_for()
        for width in [320, 768, 1440]:
            page.set_viewport_size({"width": width, "height": 1100})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), str(width)
            point = page.get_by_role("button", name="AAA, P/E 10, ROE 20%, Lower P/E · Higher ROE")
            point.focus()
            assert page.get_by_text("AAA · P/E 10.00× · ROE 20.00%", exact=False).is_visible()
            page.keyboard.press("Enter")
            assert page.locator("#selection").inner_text() == "AAA"
            assert page.get_by_role("button", name="5-Step DuPont unavailable").is_disabled()
            page.screenshot(path=str(EVIDENCE / f"slice7_fundamental_{width}.png"), full_page=True)
        assert not errors, str(errors)
        browser.close()


VITEST = r'''
import React, { act } from '../../omega-ui/node_modules/react/index.js';
import { createRoot } from '../../omega-ui/node_modules/react-dom/client.js';
import { describe, it, expect, vi, afterEach } from '../../omega-ui/node_modules/vitest/dist/index.js';
import { QueryClient, QueryClientProvider } from '../../omega-ui/node_modules/@tanstack/react-query/build/modern/index.js';
import * as api from '../../omega-ui/src/api/advancedQuant';
import { useQuantScreener, useFundamentalDuPont, useFundamentalPiotroski, useFundamentalValuation, screenerRequest } from '../../omega-ui/src/hooks/useQuantScreener';
import { FundamentalMatrixView, DuPontFactorAnalysis, PiotroskiFScoreBreakdown, ValuationScatterMatrix, valuationQuadrant, formatMetricValue } from '../../omega-ui/src/modules/fundamental_matrix/FundamentalMatrixView';
import { useUiStore } from '../../omega-ui/src/store/uiStore';
import fs from 'node:fs';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
const cutoff = '2023-12-31T08:30:00Z';
const read = {as_of:cutoff}, symbolRead={symbol:'AAA',...read};
const proof=(dataset='hybrid_eval_full_703')=>({historical_pit_verified:false,provenance_verification:'VALIDATED_METADATA_NOT_AUTHENTICATED_LINEAGE',provenance:{source:'persisted_fundamental_inputs',dataset_id:dataset,dataset_version:'fundamental.v1',as_of:cutoff,computed_at:cutoff,requested_pit_cutoff:cutoff,effective_cutoff:cutoff,input_timezone:'Asia/Ho_Chi_Minh',normalized_timezone:'UTC',cutoff_resolution:'REQUESTED',max_included_available_at:cutoff,excluded_future_rows:0,content_hash:'a'.repeat(64),artifact_uri:null,is_synthetic:false}});
const rows=[{symbol:'AAA',sector:'Technology',exchange:'HOSE',status:'QUALIFIED',pe:10,pb:2,roe:20,piotroski_f:9,altman_z:3,is_fallback:false,is_veto:false},{symbol:'BBB',sector:'Technology',exchange:'HNX',status:'WATCH',pe:20,pb:null,roe:10,piotroski_f:null,altman_z:null,is_fallback:false,is_veto:false}];
const screener={status:'success',total:2,page:1,limit:25,total_pages:1,data:rows,...proof()};
const valuation={status:'success',total:2,excluded_not_meaningful:1,roe_unit:'percent',data:rows,...proof()};
const dupont={status:'success',symbol:'AAA',fiscal_year:2023,net_margin:0.1,asset_turnover:1,equity_multiplier:2,roe:0.2,roe_percent:20,reason:null,filing_dates:[cutoff],...proof('financial_statements_2015_now')};
const piotroski={status:'success',symbol:'AAA',fiscal_year:2023,score:9,known_passes:9,unknown_count:0,criteria:['positive_roa','positive_operating_cash_flow','improved_roa','cash_flow_exceeds_income','reduced_leverage','improved_liquidity','no_share_dilution','improved_gross_margin','improved_asset_turnover'].map(id=>({id,status:'pass',reason:null,filing_dates:[cutoff]})),...proof('financial_statements_2015_now')};
const copy = v=>structuredClone(v), bad=[undefined,true,'1',[],{},NaN,Infinity,-Infinity,1e13];
let root,container,client;
const flush=async(fn=()=>{})=>act(async()=>{await fn();await new Promise(r=>setTimeout(r,5));});
const mount=async(element,query=false)=>{container=document.createElement('div');document.body.append(container);root=createRoot(container);client=new QueryClient({defaultOptions:{queries:{retry:false}}});await flush(()=>root.render(query?<QueryClientProvider client={client}>{element}</QueryClientProvider>:element));};
const deferred=()=>{let resolve,reject;return {promise:new Promise((a,b)=>{resolve=a;reject=b}),get resolve(){return resolve},get reject(){return reject}};};
const store=useUiStore.getState();
afterEach(async()=>{vi.useRealTimers();if(root)await flush(()=>root.unmount());root=null;container?.remove();client?.clear();vi.restoreAllMocks();vi.unstubAllGlobals();useUiStore.setState(store);});

function routeFetch(){return vi.fn(async(url,init)=>({ok:true,json:async()=>String(url).includes('/dupont/')?dupont:String(url).includes('/piotroski/')?piotroski:String(url).includes('valuation-matrix')?valuation:screener}));}
describe('Fundamental analytics',()=>{
 it('contract accepts exact Slice6 DTOs and immutable requests with all filters',()=>{
  api.validateFundamentalScreener(screener,read);api.validateFundamentalValuation(valuation,read);api.validateFundamentalDuPont(dupont,symbolRead);api.validateFundamentalPiotroski(piotroski,symbolRead);
  const request={...read,page:1,limit:25,sector:'Technology',is_veto:false},snapshot=api.validateFundamentalRead(request,'screener');request.sector='Other';expect(snapshot.sector).toBe('Technology');
  expect(screenerRequest({search:'AAA',page:1,pageSize:25,minPiotroski:0,minRoe:0,minAltmanZ:0,exchange:'',sector:'',status:''},cutoff)).toEqual({...read,symbol:'AAA',page:1,limit:25,min_piotroski:0,min_roe:0,min_altman_z:0});
  const empty={...screener,total:0,total_pages:0,data:[]};api.validateFundamentalScreener(empty,read);
  api.validateFundamentalScreener({...empty,page:10},{...read,page:10});
  const unknown=copy(piotroski);unknown.criteria[0]={...unknown.criteria[0],status:'unknown',reason:'MISSING_OR_INVALID_FILING_INPUTS',filing_dates:[]};unknown.score=null;unknown.known_passes=8;unknown.unknown_count=1;api.validateFundamentalPiotroski(unknown,symbolRead);
  const unavailable={...dupont,status:'unavailable',roe:null,roe_percent:null,net_margin:null,reason:'MISSING_OR_INVALID_FILING_INPUTS'};api.validateFundamentalDuPont(unavailable,symbolRead);
  api.validateFundamentalDuPont({...unavailable,status:'not_meaningful',equity_multiplier:-2,reason:'NONPOSITIVE_EQUITY'},symbolRead);
 });
 it('numeric rejects nonfinite type confusion overflow missing divisors and false success',()=>{
  for(const v of bad){for(const k of ['pe','pb','roe','piotroski_f','altman_z']){const s=copy(screener);s.data[0][k]=v;expect(()=>api.validateFundamentalScreener(s,read)).toThrow();}
   for(const k of ['net_margin','asset_turnover','equity_multiplier','roe','roe_percent'])expect(()=>api.validateFundamentalDuPont({...dupont,[k]:v},symbolRead)).toThrow();
   for(const k of ['min_piotroski','min_roe','min_altman_z','page','limit'])expect(()=>api.validateFundamentalRead({...read,[k]:v},'screener')).toThrow();
  }
  for(const v of [null,0,-1])for(const k of ['asset_turnover','equity_multiplier'])expect(()=>api.validateFundamentalDuPont({...dupont,[k]:v},symbolRead)).toThrow();
  for(const [k,v] of [['roe',0.3],['roe_percent',30],['net_margin',1e12]])expect(()=>api.validateFundamentalDuPont({...dupont,[k]:v},symbolRead)).toThrow();
  for(const k of ['page','limit'])for(const v of [0,-1,1.5])expect(()=>api.validateFundamentalRead({...read,[k]:v},'screener')).toThrow();
  expect(()=>api.validateFundamentalRead({...read,min_piotroski:10},'screener')).toThrow();expect(()=>api.validateFundamentalRead({...read,limit:704},'screener')).toThrow();
  expect(formatMetricValue(null,2)).toBe('--');expect(formatMetricValue(NaN,2)).toBe('--');expect(formatMetricValue(1e13,2)).toBe('--');expect(formatMetricValue(0,2)).toBe('0.00');
 });
 it('schema rejects extra missing duplicated partial and inconsistent response metadata',()=>{
  for(const [value,validate] of [[screener,v=>api.validateFundamentalScreener(v,read)],[valuation,v=>api.validateFundamentalValuation(v,read)],[dupont,v=>api.validateFundamentalDuPont(v,symbolRead)],[piotroski,v=>api.validateFundamentalPiotroski(v,symbolRead)]]){
   for(const v of [null,[],{},true,'success'])expect(()=>validate(v)).toThrow();
   for(const key of Object.keys(value)){const v=copy(value);delete v[key];expect(()=>validate(v),key).toThrow();}
   expect(()=>validate({...value,role_id:13})).toThrow();
  }
  for(const key of Object.keys(screener.data[0])){const s=copy(screener);delete s.data[0][key];expect(()=>api.validateFundamentalScreener(s,read)).toThrow();}
  for(const key of Object.keys(screener.provenance)){const s=copy(screener);delete s.provenance[key];expect(()=>api.validateFundamentalScreener(s,read)).toThrow();}
  for(const [key,v] of [['score',8],['unknown_count',1],['known_passes',8],['criteria',piotroski.criteria.slice(1)]])expect(()=>api.validateFundamentalPiotroski({...piotroski,[key]:v},symbolRead)).toThrow();
  const duplicate=copy(piotroski);duplicate.criteria[1].id=duplicate.criteria[0].id;expect(()=>api.validateFundamentalPiotroski(duplicate,symbolRead)).toThrow();
  const unrecognized=copy(piotroski);unrecognized.criteria[0].id='__proto__';expect(()=>api.validateFundamentalPiotroski(unrecognized,symbolRead)).toThrow();
  for(const field of ['status','reason','filing_dates']){const v=copy(piotroski);v.criteria[0][field]='bogus';expect(()=>api.validateFundamentalPiotroski(v,symbolRead)).toThrow();}
  expect(()=>api.validateFundamentalScreener({...screener,total:3},read)).toThrow();expect(()=>api.validateFundamentalScreener({...screener,limit:10},read)).toThrow();
  expect(()=>api.validateFundamentalValuation({...valuation,data:Array(704).fill(rows[0]),total:704},read)).toThrow();
  for(const status of ['DELISTED','FROZEN','SUSPENDED','DISQUALIFIED']){const v=copy(valuation);v.data[0].status=status;expect(()=>api.validateFundamentalValuation(v,read)).toThrow();}
  for(const pe of [null,0,-1]){const v=copy(valuation);v.data[0].pe=pe;expect(()=>api.validateFundamentalValuation(v,read)).toThrow();}
  expect(()=>api.validateFundamentalScreener(screener,{...read,symbol:'BBB'})).toThrow();expect(()=>api.validateFundamentalScreener(screener,{...read,min_roe:30})).toThrow();
  for(const symbol of ['aaa','../AAA','AAA<script>','--flag','',null])expect(()=>api.validateFundamentalRead({...read,symbol},'symbol')).toThrow();
  for(const sector of ['',' Tech','Tech\n','﻿Tech'])expect(()=>api.validateFundamentalRead({...read,sector},'screener')).toThrow();
  expect(()=>screenerRequest({page:1,role_id:13})).toThrow();for(const filters of [null,[],true,'',1])expect(()=>screenerRequest(filters)).toThrow();
 });
 it('pit cutoff equality timezone session close holiday availability and provenance trust stay strict',()=>{
  api.validateFundamentalDuPont(dupont,{symbol:'AAA',as_of:'2023-12-31T15:30:00+07:00'});
  for(const [value,validate] of [[valuation,v=>api.validateFundamentalValuation(v,read)],[screener,v=>api.validateFundamentalScreener(v,read)],[dupont,v=>api.validateFundamentalDuPont(v,symbolRead)],[piotroski,v=>api.validateFundamentalPiotroski(v,symbolRead)]]){const missing=copy(value);missing.provenance.max_included_available_at=null;expect(()=>validate(missing)).toThrow();}
  const defaultRead=copy(valuation);defaultRead.provenance.requested_pit_cutoff=null;defaultRead.provenance.cutoff_resolution='AS_OF_DEFAULT';api.validateFundamentalValuation(defaultRead,{});
  for(const field of ['effective_cutoff','requested_pit_cutoff','as_of','max_included_available_at']){const v=copy(valuation);v.provenance[field]='2023-12-31T08:30:01Z';expect(()=>api.validateFundamentalValuation(v,read)).toThrow();}
  for(const date of ['2023-12-31T08:30:00','2023-02-30T08:30:00Z','2099-01-01T08:30:00Z','2023-12-31T25:30:00Z'])expect(()=>api.validateFundamentalRead({as_of:date})).toThrow();
  for(const date of ['2023-12-31T08:30:01Z','2023-12-31T08:30:00'])expect(()=>api.validateFundamentalDuPont({...dupont,filing_dates:[date]},symbolRead)).toThrow();
  expect(()=>api.validateFundamentalDuPont({...dupont,filing_dates:[cutoff,cutoff]},symbolRead)).toThrow();
  for(const [key,v] of [['historical_pit_verified',true],['provenance_verification','VERIFIED']])expect(()=>api.validateFundamentalValuation({...valuation,[key]:v},read)).toThrow();
  for(const [key,v] of [['source','caller_sample'],['is_synthetic',true],['content_hash','a'],['computed_at','2023-12-30T08:30:00Z']]){const r=copy(valuation);r.provenance[key]=v;expect(()=>api.validateFundamentalValuation(r,read)).toThrow();}
  // Filings are wall-clock observations: Sunday at 15:30 ICT remains eligible, not shifted to Monday.
  expect(api.validateFundamentalValuation(valuation,read).provenance.effective_cutoff).toBe(cutoff);
 });
 it('network exact GET routes fail closed on 429 timeout malformed JSON cancellation with secret safe errors',async()=>{
  const fetch=routeFetch();vi.stubGlobal('fetch',fetch);
  await api.advancedQuantApi.getFundamentalScreener(read);await api.advancedQuantApi.getFundamentalValuation(read);await api.advancedQuantApi.getFundamentalDuPont(symbolRead);await api.advancedQuantApi.getFundamentalPiotroski(symbolRead);
  expect(fetch.mock.calls.map(c=>String(c[0]).split('/api/v1/quant/')[1].split('?')[0])).toEqual(['screener','fundamental/valuation-matrix','fundamental/dupont/AAA','fundamental/piotroski/AAA']);
  expect(fetch.mock.calls.every(c=>!c[1].body && (!c[1].method || c[1].method==='GET'))).toBe(true);
  fetch.mockResolvedValue({ok:false,status:429,json:async()=>({detail:'https://user:SECRET@host'})});await expect(api.advancedQuantApi.getFundamentalValuation(read)).rejects.not.toThrow('SECRET');expect(fetch).toHaveBeenCalledTimes(5);
  fetch.mockResolvedValue({ok:true,json:async()=>{throw Error('SECRET')}});await expect(api.advancedQuantApi.getFundamentalValuation(read)).rejects.not.toThrow('SECRET');
  fetch.mockRejectedValue(Error('https://user:SECRET@host'));await expect(api.advancedQuantApi.getFundamentalDuPont(symbolRead)).rejects.not.toThrow('SECRET');
  const c=new AbortController();c.abort();await expect(api.advancedQuantApi.getFundamentalValuation(read,c.signal)).rejects.toMatchObject({name:'AbortError'});
  vi.useFakeTimers();fetch.mockImplementation((_url,init)=>new Promise((_,reject)=>init.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))));
  const pending=api.advancedQuantApi.getFundamentalValuation(read),reject=expect(pending).rejects.toThrow('Fundamental analytics unavailable');await vi.advanceTimersByTimeAsync(10001);await reject;vi.useRealTimers();
 });
 it('lifecycle cancels symbol edits stale responses invalid inputs refresh and unmount independently',async()=>{
  let params=symbolRead,handle;const requests=[];
  vi.spyOn(api.advancedQuantApi,'getFundamentalDuPont').mockImplementation((r,signal)=>{const d=deferred();requests.push({r,signal,d});return d.promise;});
  function Probe(){handle=useFundamentalDuPont(params);return <output>{handle.data?.symbol??handle.errorMessage??'Loading'}</output>;}
  const render=()=>root.render(<QueryClientProvider client={client}><Probe/></QueryClientProvider>);
  await mount(<Probe/>,true);const first=requests[0];
  params={...symbolRead,symbol:'BBB'};await flush(render);expect(first.signal.aborted).toBe(true);expect(handle.data).toBeUndefined();
  await flush(()=>first.d.resolve(dupont));expect(handle.data).toBeUndefined();
  const second=requests.at(-1);await flush(()=>second.d.resolve({...dupont,symbol:'BBB'}));expect(handle.data.symbol).toBe('BBB');
  params={...params,as_of:''};await flush(render);expect(handle.data).toBeUndefined();expect(handle.errorMessage).toContain('Invalid');expect(requests).toHaveLength(2);
  params=symbolRead;await flush(render);const third=requests.at(-1);await flush(()=>third.d.resolve(dupont));expect(handle.data.symbol).toBe('AAA');
  await flush(()=>handle.refresh());expect(handle.data).toBeUndefined();await flush(()=>requests.at(-1).d.reject(Error('SECRET')));expect(handle.errorMessage).not.toContain('SECRET');expect(handle.data).toBeUndefined();
  await flush(()=>handle.refresh());const last=requests.at(-1);await flush(()=>root.unmount());root=null;expect(last.signal.aborted).toBe(true);await flush(()=>last.d.resolve(dupont));
 });
 it('lifecycle transport validators reject corrupt data and isolate independent panels',async()=>{
  const fetch=routeFetch();vi.stubGlobal('fetch',fetch);let handle;
  function Probe(){handle={s:useQuantScreener({page:1,pageSize:25},cutoff),v:useFundamentalValuation(read),p:useFundamentalPiotroski(symbolRead)};return null;}
  await mount(<Probe/>,true);await flush();expect(handle.s.data.total).toBe(2);expect(handle.p.data.score).toBe(9);
  fetch.mockImplementation(async url=>({ok:true,json:async()=>String(url).includes('valuation')?{...valuation,roe_unit:'ratio'}:String(url).includes('piotroski')?piotroski:screener}));
  await flush(()=>handle.v.refresh());await flush();expect(handle.v.data).toBeUndefined();expect(handle.v.errorMessage).toBeTruthy();expect(handle.p.data.score).toBe(9);
 });
 it('view quadrants finite axes singleton empty sector medians keyboard and XSS escaping',async()=>{
  expect(valuationQuadrant(10,20,15,15)).toBe('Lower P/E · Higher ROE');expect(valuationQuadrant(20,10,15,15)).toBe('Higher P/E · Lower ROE');
  expect(valuationQuadrant(10,10,15,15)).toBe('Lower P/E · Lower ROE');expect(valuationQuadrant(20,20,15,15)).toBe('Higher P/E · Higher ROE');expect(valuationQuadrant(15,20,15,15)).toBe('On sector benchmark');expect(valuationQuadrant(NaN,0,1,0)).toBe('Unavailable');
  const select=vi.fn();await mount(<ValuationScatterMatrix data={valuation} onSelect={select}/>);
  const point=container.querySelector('g[role=button]');await flush(()=>point.focus());expect(container.textContent).toContain('AAA · P/E 10.00×');await flush(()=>point.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})));expect(select).toHaveBeenCalledWith('AAA');
  const injected={...valuation,data:rows.map(r=>({...r,sector:'<img src=x onerror=alert(1)>'}))};await flush(()=>root.render(<ValuationScatterMatrix data={injected} onSelect={select}/>));expect(container.querySelector('img')).toBeNull();expect(container.textContent).toContain('<img');
  await flush(()=>root.render(<ValuationScatterMatrix data={{...valuation,total:1,data:[{...rows[0],roe:0}]}} onSelect={select}/>));expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
  await flush(()=>root.render(<ValuationScatterMatrix data={{...valuation,total:0,data:[]}} onSelect={select}/>));expect(container.textContent).toContain('No meaningful valuation pairs');
 });
 it('view three factors unavailable NaN null equity and all nine tri-state indicators',async()=>{
  const unknown=copy(piotroski);unknown.criteria[0].status='fail';unknown.criteria[1]={...unknown.criteria[1],status:'unknown',reason:'MISSING_OR_INVALID_FILING_INPUTS',filing_dates:[]};unknown.score=null;unknown.known_passes=7;unknown.unknown_count=1;
  await mount(<><DuPontFactorAnalysis data={dupont}/><PiotroskiFScoreBreakdown data={unknown}/></>);
  expect(container.textContent).toContain('0.1000 × 1.0000 × 2.0000 = 0.2000');expect(container.textContent).toContain('ROE 20.00%');expect(container.querySelector('button[disabled]').title).toContain('Coming in v2');
  expect(container.querySelectorAll('li')).toHaveLength(9);expect(container.textContent).toContain('Score --');expect(container.textContent).toContain('✕ Fail');expect(container.textContent).toContain('? Unknown');expect(container.textContent).toContain('Known passes 7');
  for(const value of [null,NaN,Infinity]){await flush(()=>root.render(<DuPontFactorAnalysis data={{...dupont,net_margin:value}}/>));expect(container.textContent).toContain('ROE --');expect(container.innerHTML).not.toMatch(/NaN|Infinity/);}
  await flush(()=>root.render(<DuPontFactorAnalysis data={{...dupont,status:'not_meaningful',reason:'NONPOSITIVE_EQUITY',roe:null,roe_percent:null}}/>));expect(container.textContent).toContain('Nonpositive equity');
 });
 it('view bounded screener inputs errors pagination and existing navigation stay wired',async()=>{
  useUiStore.setState({selectedTicker:'AAA',screenerFilters:{page:1,pageSize:25},activeFeatureId:null});vi.stubGlobal('fetch',routeFetch());
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date(cutoff));await mount(<FundamentalMatrixView/>,true);await flush();vi.useRealTimers();
  expect(container.textContent).toContain('Quant Screener · 2 matches');expect(container.textContent).toContain('Historical PIT verification: false');expect(container.textContent).toContain('Corporate Ownership');
  expect(container.querySelector('input[max="9"]')).not.toBeNull();expect(container.querySelector('input[max="703"]')).not.toBeNull();expect([...container.querySelectorAll('button')].find(b=>b.textContent==='Next page').disabled).toBe(true);
  await flush(()=>useUiStore.setState({screenerFilters:{page:0,pageSize:704}}));expect(container.querySelector('[role=alert]')).not.toBeNull();expect(container.textContent).not.toContain('Quant Screener · 2 matches');
  expect(container.innerHTML).not.toContain('SECRET');
 });
 it.skipIf(!process.env.FUNDAMENTAL_BACKEND_PAYLOADS)('backend actual route JSON satisfies UI contracts without normalization',()=>{
  const v=JSON.parse(fs.readFileSync(process.env.FUNDAMENTAL_BACKEND_PAYLOADS!,'utf8')),request={as_of:v.cutoff},symbol={symbol:'AAA',...request};
  api.validateFundamentalScreener(v.screener,request);api.validateFundamentalValuation(v.valuation,request);api.validateFundamentalDuPont(v.dupont,symbol);api.validateFundamentalPiotroski(v.piotroski,symbol);
 });
});
'''
