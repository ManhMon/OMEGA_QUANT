"""Portfolio read contracts and actual React lifecycle; no order execution."""
import hashlib
import importlib.util
import json
import re
from copy import deepcopy
from pathlib import Path
import subprocess

import pytest

from scripts import validate_l2_report as report_validator

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("portfolio_contract_fixtures", ROOT / "tests/api/test_portfolio_contracts.py")
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)
artifacts = contracts.artifacts


@pytest.fixture(scope="module")
def portfolio_ui_runtime(tmp_path_factory):
    runner = tmp_path_factory.mktemp("portfolio_ui_runtime") / "check.cjs"
    runner.write_text(r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), Module = require('node:module');
const root = process.argv[2], mode = process.argv[3], ts = require(path.join(root, 'omega-ui/node_modules/typescript'));
const load = file => {
  if (require.cache[file]) return require.cache[file].exports;
  const m = new Module(file, module); m.filename = file; m.paths = Module._nodeModulePaths(path.dirname(file)); require.cache[file] = m;
  m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
  return m.exports;
};
require.extensions['.ts'] = require.extensions['.tsx'] = (m,file) => { delete require.cache[file]; m.exports = load(file); };
const api = load(path.join(root,'omega-ui/src/api/advancedQuant.ts'));
const cutoff = '2026-01-30T08:30:00Z';
const proof = dataset => ({source:'target_portfolio_parquet',dataset_id:dataset,dataset_version:'portfolio.v1',as_of:cutoff,computed_at:cutoff,requested_pit_cutoff:null,effective_cutoff:cutoff,input_timezone:'UTC+7',normalized_timezone:'UTC',cutoff_resolution:'AS_OF_DEFAULT',max_included_available_at:cutoff,excluded_future_rows:0,content_hash:'a'.repeat(64),artifact_uri:null,is_synthetic:false});
const dates = Array.from({length:30},(_,i)=>new Date(Date.UTC(2026,0,i+1,8,30)).toISOString()).filter(t=>![0,6].includes(new Date(t).getUTCDay()));
const state = {status:'success',account_model:'target_institutional_allocation',weighting_method:'hrp',timestamp:cutoff,price_scale:'VND_FULL',nav_method:'fixed_weight_daily_basket_estimate_not_realized_performance',aum_method:'candidate_market_cap_reference_not_broker_assets',total_aum_vnd:1e7,totalAumBillionVnd:.01,unallocated_cash_vnd:0,cash_balance_vnd:0,hrp_weights:{AAA:1},holdings:[{symbol:'AAA',weight:1,marketValueBillionVnd:.01,adv20BillionVnd:25,alphaScore:.8,sector:'Technology',barraMomentum:null,barraValue:null,barraSize:null,turnoverContribution:null,unrealizedPnlPercent:null}],nav_history:dates.map((timestamp,i)=>({timestamp,nav_vnd:i===10?9e6:1e7})),drawdown_series:dates.map((timestamp,i)=>({timestamp,drawdown_percent:i===10?-10:0})),maxDrawdownEstimatePercent:10,expectedIrAnnualized:null,portfolioBeta:null,dailyTurnoverEstimatePercent:null,icMean:null,icTStat:null,cvar99Percent:null,provenance:proof('target_portfolio_state')};
const universe = {status:'success',timestamp:cutoff,selector_model:'hybrid_rank_sector_capped',symbols:['AAA'],scores:{AAA:.8},sector_weights:{Technology:1},selected_symbols:['AAA'],selected_details:[{symbol:'AAA',sector:'Technology',score:.8,adv_billion_vnd:25,status:'ACTIVE'}],total_evaluated:1,total_selected:1,excluded_summary:{},units:{adv:'billion_vnd',weight:'fraction'},provenance:proof('dynamic_universe')};
const req = {sector_cap:1};
const bad = [null,undefined,true,'1',[],NaN,Infinity,-Infinity,-1,1e13];
const copy = value => structuredClone(value);
const rejectsState = change => {const s=copy(state);change(s);assert.throws(()=>api.validateTargetPortfolio(s));};
async function main() {
  api.validateTargetPortfolio(state); api.validatePortfolioUniverse(universe,req);
  if (mode === 'css') {
    const {compile}=Module.createRequire(path.join(root,'omega-ui/package.json'))('@tailwindcss/node');
    const c=await compile('@import "tailwindcss";', {base:path.join(root,'omega-ui'),onDependency:()=>{}});
    const s=fs.readFileSync(path.join(root,'omega-ui/src/modules/alpha_portfolio/AlphaPortfolioStationView.tsx'),'utf8');
    const classes=[...s.matchAll(/(?:className=|const \w+Class = )['"]([^'"]+)['"]/g)].flatMap(m=>m[1].split(/\s+/));
    fs.writeFileSync(process.argv[4],c.build(classes));return;
  }
  if (mode === 'browser') {
    const esbuild=require(path.join(root,'omega-ui/node_modules/esbuild'));
    const script=`import React from 'react'; import {createRoot} from 'react-dom/client'; import {QueryClient,QueryClientProvider} from '@tanstack/react-query'; import {advancedQuantApi} from './src/api/advancedQuant'; import {AlphaPortfolioStationView} from './src/modules/alpha_portfolio/AlphaPortfolioStationView'; advancedQuantApi.getTargetPortfolioState=async()=>(${JSON.stringify(state)}); advancedQuantApi.getPortfolioDynamicUniverse=async()=>(${JSON.stringify({...universe,symbols:[],scores:{},sector_weights:{},selected_symbols:[],selected_details:[],total_selected:0,excluded_summary:{AAA:'not_selected_by_liquidity_score_lifecycle_or_sector_cap'}})}); createRoot(document.getElementById('root')).render(<React.StrictMode><QueryClientProvider client={new QueryClient()}><AlphaPortfolioStationView /></QueryClientProvider></React.StrictMode>);`;
    esbuild.buildSync({stdin:{contents:script,loader:'tsx',resolveDir:path.join(root,'omega-ui')},bundle:true,format:'iife',outfile:process.argv[4]});return;
  }
  if (mode === 'backend') {
    const data=JSON.parse(fs.readFileSync(process.argv[4],'utf8'));
    api.validateTargetPortfolio(data.state,{as_of:cutoff}); api.validatePortfolioUniverse(data.universe,{as_of:cutoff,top_n:5,sector_cap:.3}); return;
  }
  if (mode === 'numeric') {
    for(const v of bad) {
      assert.throws(()=>api.validateTargetPortfolio({...state,total_aum_vnd:v}));
      assert.throws(()=>api.validatePortfolioUniverse({...universe,total_evaluated:v},req));
      for(const key of ['weight','marketValueBillionVnd','adv20BillionVnd','alphaScore']) rejectsState(s=>s.holdings[0][key]=v);
      rejectsState(s=>s.nav_history[0].nav_vnd=v);
      if(v!==-1) rejectsState(s=>s.drawdown_series[0].drawdown_percent=v);
    }
    for(const v of [null,true,'1',[],NaN,Infinity,-Infinity,1e13]) assert.equal(api.formatAlphaMetric(v),'--');
    assert.equal(api.formatAlphaMetric(0),'0.00');
    rejectsState(s=>{s.hrp_weights.AAA=0;s.holdings[0].weight=0;});
    rejectsState(s=>s.drawdown_series[10].drawdown_percent=-9);
    rejectsState(s=>s.maxDrawdownEstimatePercent=0);
    rejectsState(s=>s.cash_balance_vnd=1);
  }
  if (mode === 'schema') {
    for(const v of [null,[],{},true,'success']) assert.throws(()=>api.validateTargetPortfolio(v));
    for(const key of Object.keys(state)) {const s=copy(state);delete s[key];assert.throws(()=>api.validateTargetPortfolio(s),key);}
    rejectsState(s=>s.legacy=true); rejectsState(s=>s.holdings.push(copy(s.holdings[0])));
    rejectsState(s=>s.holdings[0].symbol='aaa'); rejectsState(s=>s.holdings[0].symbol='../AAA --flag');
    rejectsState(s=>s.holdings[0].barraValue=1);
    rejectsState(s=>s.price_scale='VND_THOUSAND'); rejectsState(s=>s.totalAumBillionVnd=10000);
    for(const key of ['symbols','selected_symbols','selected_details']) assert.throws(()=>api.validatePortfolioUniverse({...universe,[key]:[]},req));
    for(const status of ['DELISTED','FROZEN','SUSPENDED','DISTRESS','UNKNOWN']) assert.throws(()=>api.validatePortfolioUniverse({...universe,selected_details:[{...universe.selected_details[0],status}]},req));
    assert.throws(()=>api.validatePortfolioUniverse(universe));
    assert.throws(()=>api.validatePortfolioUniverse({...universe,scores:{BBB:.8}},req));
    assert.throws(()=>api.validatePortfolioUniverse({...universe,units:{adv:'VND_FULL',weight:'percent'}},req));
    const empty={...universe,symbols:[],scores:{},sector_weights:{},selected_symbols:[],selected_details:[],total_selected:0,excluded_summary:{AAA:'not_selected_by_liquidity_score_lifecycle_or_sector_cap'}};
    api.validatePortfolioUniverse(empty); assert.throws(()=>api.validatePortfolioUniverse({...empty,excluded_summary:{AAA:'secret'}},req));
  }
  if (mode === 'pit') {
    for(const key of ['as_of','computed_at','effective_cutoff','max_included_available_at']) for(const v of [null,'','2026-01-30T08:30:00','2026-02-30T08:30:00Z','2026-01-30T24:30:00Z']) rejectsState(s=>s.provenance[key]=v);
    rejectsState(s=>s.provenance.max_included_available_at='2026-01-30T08:30:01Z');
    rejectsState(s=>s.provenance.effective_cutoff='2026-01-31T08:30:00Z');
    rejectsState(s=>s.provenance.effective_cutoff='2026-01-30T08:29:59Z');
    rejectsState(s=>s.provenance.source='caller_sample'); rejectsState(s=>s.provenance.is_synthetic=true);
    rejectsState(s=>s.provenance.pit_verified=true); rejectsState(s=>s.provenance.content_hash='wrong');
    rejectsState(s=>s.provenance.dataset_id='dynamic_universe');
    rejectsState(s=>s.nav_history[1].timestamp=s.nav_history[0].timestamp);
    const requested=copy(state);requested.timestamp='2026-01-30T15:30:00+07:00';requested.provenance.as_of=requested.timestamp;requested.provenance.requested_pit_cutoff=requested.timestamp;requested.provenance.cutoff_resolution='REQUESTED';
    api.validateTargetPortfolio(requested,{as_of:cutoff});
    const next=copy(requested);next.timestamp='2026-02-02T08:29:59Z';next.provenance.as_of=next.timestamp;next.provenance.computed_at=next.timestamp;next.provenance.requested_pit_cutoff=next.timestamp;
    api.validateTargetPortfolio(next,{as_of:next.timestamp});
    assert.throws(()=>api.validateTargetPortfolio(next,{as_of:cutoff}));
    assert.throws(()=>api.validatePortfolioRequest({as_of:'2099-01-01T00:00:00Z'}));
    assert.throws(()=>api.validatePortfolioRequest({as_of:null}));
  }
  if(mode==='bounds') {
    for(const [key,values] of Object.entries({min_adv_billion:[0,501],top_n:[4,101,5.1],sector_cap:[0,.049,1.1],min_score:[-.1,1.1]})) for(const v of [...values,...bad]) assert.throws(()=>api.validatePortfolioRequest({[key]:v},true));
    for(const field of ['role_id','risk','model','gate','token','output_path']) assert.throws(()=>api.validatePortfolioRequest({[field]:'SECRET'},true));
    rejectsState(s=>s.nav_history=Array(254).fill(s.nav_history[0]));
    rejectsState(s=>s.holdings=Array(11).fill(s.holdings[0]));
    assert.throws(()=>api.validatePortfolioUniverse({...universe,total_evaluated:100001},req));
  }
  if(mode==='network') {
    let calls=[];
    global.fetch=async(url,init)=>{calls.push([url,init]);return {ok:true,json:async()=>url.includes('dynamic-universe')?universe:state};};
    const request={as_of:cutoff};const bound=copy(state);bound.provenance.requested_pit_cutoff=cutoff;bound.provenance.cutoff_resolution='REQUESTED';
    global.fetch=async(url,init)=>{calls.push([url,init]);return {ok:true,json:async()=>bound};};
    const promise=api.advancedQuantApi.getTargetPortfolioState(request);request.as_of='2099-01-01T00:00:00Z';await promise;
    assert(calls[0][0].includes('as_of=2026-01-30')); assert(!calls[0][1].method);
    for(const code of ['DATASET_PIT_INVALID','DATA_DEPENDENCY_UNAVAILABLE','DATA_SCHEMA_INVALID']) {
      let count=0;global.fetch=async()=>{count++;return {ok:false,status:424,json:async()=>({detail:code,message:'https://user:SECRET@host/token'})};};
      await assert.rejects(api.advancedQuantApi.getTargetPortfolioState(),new RegExp(code));assert.equal(count,1);
    }
    for(const status of [429,500]) {let count=0;global.fetch=async()=>{count++;return {ok:false,status,json:async()=>({detail:'https://user:SECRET@host'})};};await assert.rejects(api.advancedQuantApi.getPortfolioDynamicUniverse(req),e=>!e.message.includes('SECRET'));assert.equal(count,1);}
    const controller=new AbortController();controller.abort();await assert.rejects(api.advancedQuantApi.getTargetPortfolioState({},controller.signal),e=>e.name==='AbortError');
    global.fetch=async(_url,init)=>new Promise((_,reject)=>init.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));
    await assert.rejects(api.resilientApiRequest('/api/v1/portfolio/state',{timeoutMs:1,maxRetries:0}),/timed out/);
  }
  if(mode==='lifecycle' || mode==='view') {
    const {JSDOM}=require(path.join(root,'omega-ui/node_modules/jsdom'));const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost:3000'});
    global.window=dom.window;global.document=dom.window.document;global.IS_REACT_ACT_ENVIRONMENT=true;
    const React=require(path.join(root,'omega-ui/node_modules/react')), {createRoot}=require(path.join(root,'omega-ui/node_modules/react-dom/client'));
    const uiRequire=Module.createRequire(path.join(root,'omega-ui/package.json'));const {QueryClient,QueryClientProvider}=uiRequire('@tanstack/react-query');
    const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}}), mount=createRoot(document.getElementById('root'));
    const flush=async fn=>React.act(async()=>{await fn();await new Promise(r=>setTimeout(r,20));});
    const deferred=()=>{let resolve,reject;return {promise:new Promise((a,b)=>{resolve=a;reject=b}),get resolve(){return resolve},get reject(){return reject}};};
    const hooks=load(path.join(root,'omega-ui/src/hooks/usePortfolioState.ts'));
    let requests=[],handle,signal;
    api.advancedQuantApi.getTargetPortfolioState=async(params,s)=>{signal=s;return state;};
    api.advancedQuantApi.getPortfolioDynamicUniverse=async(params,s)=>{const d=deferred();requests.push({d,params,s});return d.promise;};
    let request=req;
    function Probe(){handle=hooks.usePortfolioDynamicUniverse(request);return React.createElement('output',null,handle.data?handle.data.symbols.join(','):handle.errorMessage||'Loading');}
    const render=Component=>mount.render(React.createElement(QueryClientProvider,{client},React.createElement(Component)));
    if(mode==='lifecycle') {
      await flush(()=>render(Probe));assert.equal(requests.length,1);await flush(()=>requests[0].d.resolve(universe));assert.equal(document.querySelector('output').textContent,'AAA');
      request={sector_cap:1,min_score:.9};await flush(()=>render(Probe));assert.equal(handle.data,undefined);
      request={sector_cap:1,min_score:.7};await flush(()=>render(Probe));assert(requests[1].s.aborted);
      await flush(()=>requests[1].d.resolve(universe));assert.equal(handle.data,undefined);
      await flush(()=>requests[2].d.resolve({...universe,symbols:['BBB']}));assert.equal(document.querySelector('output').textContent,'BBB');
      await flush(()=>handle.refresh());assert.equal(handle.data,undefined);await flush(()=>requests[3].d.reject(new Error('SECRET https://user:SECRET@host')));assert.equal(handle.data,undefined);assert(!handle.errorMessage.includes('SECRET'));
      request=null;await flush(()=>render(Probe));assert.equal(handle.data,undefined);assert.equal(handle.errorMessage,'Invalid portfolio inputs.');
      request=req;await flush(()=>render(Probe));const latest=requests.at(-1);await flush(()=>mount.unmount());assert(latest.s.aborted);await flush(()=>latest.d.resolve(universe));
    } else {
      api.advancedQuantApi.getPortfolioDynamicUniverse=async()=>({...universe,symbols:[],scores:{},sector_weights:{},selected_symbols:[],selected_details:[],total_selected:0,excluded_summary:{AAA:'not_selected_by_liquidity_score_lifecycle_or_sector_cap'}});
      api.advancedQuantApi.executePortfolioRebalance=()=>{throw new Error('MUTATION FORBIDDEN');};
      const {AlphaPortfolioStationView}=load(path.join(root,'omega-ui/src/modules/alpha_portfolio/AlphaPortfolioStationView.tsx'));
      await flush(()=>render(AlphaPortfolioStationView));await flush(()=>{});
      const text=document.body.textContent;
      for(const expected of ['Alpha Portfolio Station','UNAVAILABLE','linkage topology contract','Reference capital','Underwater Drawdown','Estimated NAV','No eligible candidates','caller inputs are filters']) assert(text.includes(expected),expected);
      assert(document.querySelector('button[disabled]').textContent.includes('Execution disengaged'));assert.equal(document.querySelectorAll('svg').length,2);
      assert(document.querySelectorAll('table').length>=4);assert.equal(document.querySelectorAll('input').length,7);
      const input=document.querySelector('#portfolio-min_score');const setter=Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set;
      await flush(()=>{setter.call(input,'2');input.dispatchEvent(new dom.window.Event('input',{bubbles:true}));});
      assert(!document.body.textContent.includes('10000000.00'));assert.equal(document.querySelectorAll('svg').length,0);
      await flush(()=>mount.unmount());
    }
    client.clear();dom.window.close();
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
''', encoding="utf-8", newline="\n")
    return runner


def run_runtime(runner, mode, payload=None):
    result = subprocess.run(["node", str(runner), str(ROOT), mode, *([str(payload)] if payload else [])], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["numeric", "schema", "pit", "bounds", "network", "lifecycle", "view"])
def test_portfolio_ui_runtime(portfolio_ui_runtime, mode):
    run_runtime(portfolio_ui_runtime, mode)


def test_portfolio_backend_payloads_pass_ui_validators(artifacts, portfolio_ui_runtime, tmp_path):
    state = contracts.get()
    universe = contracts.get("dynamic-universe", top_n=5, sector_cap=.3)
    assert state.status_code == universe.status_code == 200
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"state": state.json(), "universe": universe.json()}), encoding="utf-8")
    run_runtime(portfolio_ui_runtime, "backend", payload)


@pytest.mark.parametrize("endpoint", ["state", "dynamic-universe"])
@pytest.mark.parametrize("fault,code", [("missing", "DATA_DEPENDENCY_UNAVAILABLE"), ("pit", "DATASET_PIT_INVALID"), ("schema", "DATA_SCHEMA_INVALID")])
def test_portfolio_424_boundary(artifacts, endpoint, fault, code):
    path, _, frame, _ = artifacts
    if fault == "missing":
        path.unlink()
    elif fault == "pit":
        frame.loc[0, "available_at"] = "2026-01-30T08:30:01Z"
        frame.to_parquet(path, index=False)
    else:
        frame.drop(columns="sector").to_parquet(path, index=False)
    response = contracts.get(endpoint)
    assert response.status_code == 424
    assert response.json() == {"detail": code}


def test_portfolio_app_mount_and_read_only_scope():
    app = (ROOT / "omega-ui/src/App.tsx").read_text(encoding="utf-8")
    assert "case 'alpha_portfolio':\n        return <AlphaPortfolioStationView />;" in app
    for relative in ["omega-ui/src/hooks/usePortfolioState.ts", "omega-ui/src/modules/alpha_portfolio/AlphaPortfolioStationView.tsx"]:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "executePortfolioRebalance" not in source
        assert "useMutation" not in source
        assert "localStorage" not in source
        assert "sessionStorage" not in source


def test_portfolio_browser_responsive_and_keyboard(portfolio_ui_runtime, tmp_path):
    from playwright.sync_api import sync_playwright

    script = tmp_path / "station.js"
    run_runtime(portfolio_ui_runtime, "browser", script)
    css = tmp_path / "station.css"
    run_runtime(portfolio_ui_runtime, "css", css)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content('<html><head><style>' + css.read_text(encoding="utf-8") + '</style></head><body style="background:#09090b;padding:16px"><div id="root"></div></body></html>')
        page.add_script_tag(path=str(script))
        page.get_by_role("heading", name="Underwater Drawdown profile").wait_for()
        for width in [320, 768, 1440]:
            page.set_viewport_size({"width": width, "height": 1100})
            overflow = page.evaluate("[...document.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > innerWidth && !e.closest('.overflow-x-auto')).map(e => ({tag:e.tagName,cls:e.className,right:e.getBoundingClientRect().right})).slice(0,12)")
            assert not overflow, str(overflow)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert page.get_by_label("Decision time", exact=False).is_visible()
            assert page.get_by_role("button", name="Execution disengaged", exact=False).is_disabled()
            page.screenshot(path=str(ROOT / f".ly_state/session/role13_portfolio_{width}.png"), full_page=True)
        slider = page.get_by_role("slider", name="Underwater Drawdown profile observation")
        slider.focus()
        slider.press("ArrowLeft")
        assert slider.evaluate("el => document.activeElement === el")
        assert not errors
        browser.close()


@pytest.mark.parametrize("dimension", [2, 3, 5, 12, 17, 18, 19, 20, 21, 22, 24])
def test_portfolio_excluded_side_effect_surfaces(dimension):
    """Scope invariance only: no persistence/CLI/JEV implementation in this read UI."""
    sources = "\n".join((ROOT / p).read_text(encoding="utf-8") for p in ["omega-ui/src/hooks/usePortfolioState.ts", "omega-ui/src/modules/alpha_portfolio/AlphaPortfolioStationView.tsx"])
    for forbidden in ["dispatch_token", "child_process", "writeFile", "phase_gates", "publish_decision", "localStorage", "useMutation"]:
        assert forbidden not in sources, (dimension, forbidden)


SCOPE_FILES = [
    "omega-ui/src/api/advancedQuant.ts",
    "omega-ui/src/hooks/usePortfolioState.ts",
    "omega-ui/src/modules/alpha_portfolio/AlphaPortfolioStationView.tsx",
    "omega-ui/src/App.tsx",
    "tests/test_ui_alpha_portfolio.py",
    "omega-ui/src/layout/TopNavBar.tsx",
    "omega-ui/src/test/app_remediation.test.tsx",
]
SESSION = "l4_role13_slice3_portfolio_ui_rem1_20261008"
CONTRACT_SHA256 = "f137ea1403a4d1dc5a8afa740c97f4963991023d9a2d8d1132a0be79ca282072"
GRAPH_SHA256 = "a3ac96ccac94a5b8776dce3f3e20669e037e14779a1a12abec06ad612e21ca00"


def read_scope_binding():
    directory = ROOT / ".ly_state/session"
    contract_bytes = (directory / f"anti_drip_contract_{SESSION}.json").read_bytes()
    graph_bytes = (directory / f"graph_evidence_{SESSION}.json").read_bytes()
    assert hashlib.sha256(contract_bytes).hexdigest() == CONTRACT_SHA256
    assert hashlib.sha256(graph_bytes).hexdigest() == GRAPH_SHA256
    report_bytes = (directory / f"{SESSION}.md").read_bytes()
    assert not report_bytes.startswith(b"\xef\xbb\xbf") and b"\r" not in report_bytes
    report = report_bytes.decode("utf-8", errors="strict")
    assert "- **Date**: `2026-10-08`" in report
    objects = re.findall(r"```json\n(.*?)\n```", report, re.S)
    assert len(objects) == 1
    binding, errors = report_validator._extract_root_cause_sweep(report)
    assert not errors
    assert binding == json.loads(objects[0])
    manifest = re.findall(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \| `([0-9a-f]{64})` \|$", report, re.M)
    assert f"Graph SHA-256: `{GRAPH_SHA256}`" in report
    return json.loads(objects[0]), json.loads(contract_bytes), json.loads(graph_bytes), manifest


def validate_scope_binding(binding, contract, graph, manifest):
    assert not report_validator._schema_errors(binding, report_validator.ROOT_CAUSE_SWEEP_SCHEMA, "sweep")
    assert binding["session_id"] == contract["session_id"] == graph["session_id"] == SESSION
    assert binding["gate_name"] == contract["gate_name"] == "GATE_L4_MODULAR_QUANT_SLICE3_PORTFOLIO_UI_20261008"
    assert binding["mode"] == contract["mode"] == "remediation"
    assert binding["contract_path"] == f".ly_state/session/anti_drip_contract_{SESSION}.json"
    assert binding["contract_sha256"] == CONTRACT_SHA256
    assert binding["source_audit_path"] == contract["source_audit"]["path"]
    assert binding["source_audit_sha256"] == contract["source_audit"]["sha256"]
    assert not report_validator._validate_finding_sweep_coverage(contract, binding, ROOT)
    assert graph["scope_files"] == SCOPE_FILES
    for key in ["scope_content_hashes", "affected_files", "dependencies"]:
        assert set(graph[key]) == set(SCOPE_FILES)
    assert graph["detail_files"] == SCOPE_FILES
    assert graph["repo_commit"] == graph["graph_commit"] == "fe8c6dcc7b1a3d2831cc044b85c43c4376805a5e"
    assert [row[0] for row in manifest] == SCOPE_FILES
    assert {path: original for path, original, current in manifest} == graph["scope_content_hashes"]
    assert {path: current for path, original, current in manifest} == {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SCOPE_FILES
    }
    assert any(search["scanned_paths"] == SCOPE_FILES
               for finding in binding["finding_sweeps"] for search in finding["searches"])
    assert binding["fault_injection_test_node_ids"]
    assert all(report_validator._validate_pytest_node_id(node, ROOT) is None
               for node in binding["pytest_node_ids"])


def test_portfolio_seven_file_scope_binding():
    validate_scope_binding(*read_scope_binding())


def test_standing_sparse_config_and_snapshot_restore():
    """Exercise the actual config endpoint and existing isolation fixture, offline."""
    spec = importlib.util.spec_from_file_location("standing_config", ROOT / "tests/test_ui_llm_config.py")
    config_tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_tests)
    snapshot = deepcopy(config_tests.copilot._IN_MEMORY_LLM_CONFIG)
    restore = config_tests.restore_llm_config.__wrapped__()
    next(restore)
    try:
        with config_tests.TestClient(config_tests.app) as client:
            config_tests.test_dim7_sparse_calendar_and_profile_isolation(client)
    finally:
        next(restore, None)
    assert config_tests.copilot._IN_MEMORY_LLM_CONFIG == snapshot


@pytest.mark.parametrize("fault", [
    "none", "empty", "wrong_schema", "extra_property", "five_file_scope", "duplicate_path",
    "extra_path", "outside_path", "wrong_session", "wrong_gate", "wrong_mode", "contract_path",
    "contract_digest", "source_path", "source_digest", "missing_finding", "extra_probe",
    "stale_hash", "missing_extension_hash", "unresolved", "finding_unresolved", "search_unresolved",
    "accounting", "justification", "invalid_regex", "missing_search", "missing_tests",
    "missing_faults", "node_union", "unsafe_node", "graph_scope", "graph_hash", "graph_details",
    "graph_dependencies", "graph_commit",
])
def test_portfolio_scope_binding_rejects_faults(fault):
    binding, contract, graph, manifest = deepcopy(read_scope_binding())
    finding = binding["finding_sweeps"][0]
    search = finding["searches"][0]
    if fault == "none":
        binding = None
    elif fault == "empty":
        binding = {}
    elif fault == "wrong_schema":
        binding["schema_version"] = "custom/v1"
    elif fault == "extra_property":
        binding["role_id"] = 13
    elif fault in ["five_file_scope", "duplicate_path", "extra_path", "outside_path"]:
        for scoped_search in finding["searches"][1:]:
            scoped_search["scanned_paths"] = {
                "five_file_scope": SCOPE_FILES[:5], "duplicate_path": SCOPE_FILES + [SCOPE_FILES[-1]],
                "extra_path": SCOPE_FILES + ["omega-ui/src/unbound.ts"], "outside_path": ["../TopNavBar.tsx", *SCOPE_FILES[1:]],
            }[fault]
    elif fault.startswith("wrong_"):
        binding[{"wrong_session": "session_id", "wrong_gate": "gate_name", "wrong_mode": "mode"}[fault]] = "wrong"
    elif fault in ["contract_path", "source_path"]:
        binding["contract_path" if fault == "contract_path" else "source_audit_path"] = "../unbound.json"
    elif fault in ["contract_digest", "source_digest"]:
        binding["contract_sha256" if fault == "contract_digest" else "source_audit_sha256"] = "0" * 64
    elif fault == "missing_finding":
        binding["finding_sweeps"] = []
    elif fault == "extra_probe":
        finding["probe_strings"] = ["unbound"]
    elif fault == "stale_hash":
        manifest[-2] = (manifest[-2][0], manifest[-2][1], "0" * 64)
    elif fault == "missing_extension_hash":
        manifest.pop()
    elif fault in ["unresolved", "finding_unresolved", "search_unresolved"]:
        {"unresolved": binding, "finding_unresolved": finding, "search_unresolved": search}[fault]["unresolved_matches"] = 1
    elif fault == "accounting":
        search["total_matches"] += 1
    elif fault == "justification":
        search["non_actionable_justifications"] = []
    elif fault == "invalid_regex":
        search["search_regex"] = "["
    elif fault == "missing_search":
        finding["searches"] = []
    elif fault == "missing_tests":
        finding["test_node_ids"] = []
    elif fault == "missing_faults":
        binding["fault_injection_test_node_ids"] = []
        finding["fault_injection_test_node_ids"] = []
    elif fault == "node_union":
        binding["pytest_node_ids"] = []
    elif fault == "unsafe_node":
        finding["test_node_ids"].append("tests/../escape.py::test_escape")
        binding["pytest_node_ids"].append("tests/../escape.py::test_escape")
    elif fault == "graph_scope":
        graph["scope_files"] = SCOPE_FILES[:5]
    elif fault == "graph_hash":
        del graph["scope_content_hashes"][SCOPE_FILES[-2]]
    elif fault == "graph_details":
        graph["detail_files"] = SCOPE_FILES[:5]
    elif fault == "graph_dependencies":
        del graph["dependencies"][SCOPE_FILES[-1]]
    elif fault == "graph_commit":
        graph["graph_commit"] = "0" * 40
    with pytest.raises((AssertionError, KeyError, TypeError)):
        validate_scope_binding(binding, contract, graph, manifest)
