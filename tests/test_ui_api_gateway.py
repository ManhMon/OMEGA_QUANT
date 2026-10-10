import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from omega.api.server import app
from omega.api.routes import execution, macro, portfolio, quant
from omega.data.interbank_rate_snapshot import build_snapshot, save_snapshot


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Real, PIT-valid artifacts isolate gateway behavior from workstation datasets.
    for name in ('MACRO_PARQUET_PATH', 'MACRO_DAILY_PARQUET_PATH', 'MARKET_PARQUET_PATH',
                 'INTERBANK_PATH', 'SOVEREIGN_PATH', 'LIMIT_BANDS_PATH'):
        monkeypatch.setattr(macro, name, tmp_path / name)
    monkeypatch.setattr(quant, 'QUANT_PARQUET_PATH', tmp_path / 'universe.parquet')
    monkeypatch.setattr(portfolio, 'HYBRID_EVAL_PATH', tmp_path / 'missing_portfolio.parquet')
    clock = '2026-01-30T08:30:00Z'
    pd.DataFrame([
        dict(indicator=indicator, value=value, observation_date='2026-01-30', as_of=clock,
             available_at=clock, source='fixture', unit=unit)
        for indicator, value, unit in [('usd_vnd', 25000.0, 'VND_PER_USD'), ('cpi', 3.0, 'PERCENT_YOY')]
    ]).to_parquet(macro.MACRO_PARQUET_PATH, index=False)
    pd.DataFrame([
        dict(ticker='VCB', date=day.date().isoformat(), close=50000.0 + index * 100,
             as_of=day.isoformat(), available_at=day.isoformat())
        for index, day in enumerate(pd.date_range('2025-10-01T08:30:00Z', clock))
    ]).to_parquet(macro.MARKET_PARQUET_PATH, index=False)
    save_snapshot(macro.INTERBANK_PATH, [build_snapshot(
        datetime(2026, 1, 30).date(), 'overnight', 'SBV', 4.0,
        vintage_at=datetime.fromisoformat(clock.replace('Z', '+00:00')),
    )])
    pd.DataFrame([dict(
        curve_type='SOVEREIGN', tenor='2Y', tenor_days=730, rate=3.0,
        rate_unit='PERCENT_PER_ANNUM', day_count='ACT/ACT', compounding='SEMI_ANNUAL',
        effective_date='2026-01-30', source='HNX', as_of=clock, available_at=clock,
    )]).to_parquet(macro.SOVEREIGN_PATH, index=False)
    pd.DataFrame([
        dict(symbol='AAA' if index == 0 else f'X{index:03}', sector='Technology', exchange='HOSE',
             status='WATCH', pe=12.0, pb=2.0, roe=15.0, piotroski_f=8.0, altman_z=3.0,
             is_fallback=index % 2 == 0, is_veto=index % 3 == 0, as_of=clock, available_at=clock)
        for index in range(30)
    ]).to_parquet(quant.QUANT_PARQUET_PATH, index=False)
    with TestClient(app) as gateway:
        yield gateway


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "omega-api-bridge"


def test_macro_summary_endpoint(client):
    response = client.get("/api/v1/macro/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "total_records" in data
    assert "indicators" in data
    assert "latest_snapshots" in data
    assert len(data["latest_snapshots"]) > 0
    assert "usd_vnd" in data["indicators"]


def test_macro_yield_curve_gateway(client):
    response = client.get('/api/v1/macro/yield-curve', params={'as_of': '2026-01-30T08:30:00Z'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['status'] == 'success'
    assert data['interbank'][0]['rate'] == 4.0
    assert data['interbank'][0]['rate_unit'] == 'PERCENT_PER_ANNUM'
    assert data['sovereign'][0]['rate'] == 3.0
    assert data['sovereign'][0]['curve_type'] == 'SOVEREIGN'


@pytest.mark.parametrize('route', ['yield-curve', 'regime-metrics', 'limit-bands'])
@pytest.mark.parametrize('cutoff', ['bad', '2026-01-30T08:30:00', '2999-01-30T08:30:00Z'])
def test_macro_gateway_rejects_invalid_cutoff(client, route, cutoff):
    response = client.get(f'/api/v1/macro/{route}', params={'as_of': cutoff})
    assert response.status_code == 422, response.text
    assert 'SECRET' not in response.text


@pytest.mark.parametrize('route', ['regime-metrics', 'limit-bands'])
def test_macro_gateway_missing_dependency(client, route):
    response = client.get(f'/api/v1/macro/{route}', params={'as_of': '2026-01-30T08:30:00Z'})
    assert response.status_code == 424, response.text
    assert response.json() == {'detail': 'MACRO_DATA_UNAVAILABLE'}


@pytest.mark.parametrize('params', [
    [('symbol', 'AAA'), ('symbol', 'ZZZ')], [('limit', '1'), ('limit', '2')],
    {'unknown': 'SECRET'}, {'symbol': '../AAA'}, {'limit': 'NaN'},
])
def test_quant_gateway_rejects_parameter_ambiguity(client, params):
    response = client.get('/api/v1/quant/screener', params=params)
    assert response.status_code == 422, response.text
    assert response.json() == {'detail': 'INVALID_FUNDAMENTAL_REQUEST'}


def test_quant_screener_default(client):
    response = client.get("/api/v1/quant/screener")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total"] > 0
    assert data["page"] == 1
    assert data["limit"] == 25
    assert len(data["data"]) == 25
    assert data["historical_pit_verified"] is False


def test_quant_screener_symbol_filter(client):
    response = client.get("/api/v1/quant/screener?symbol=AAA")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total"] == 1
    assert data["data"][0]["symbol"] == "AAA"


def test_quant_screener_case_insensitivity(client):
    # Canonical identifiers are validated, never silently normalized at admission.
    response = client.get("/api/v1/quant/screener?symbol=aaa")
    assert response.status_code == 422
    assert response.json() == {"detail": "INVALID_FUNDAMENTAL_REQUEST"}


def test_quant_screener_fallback_filter(client):
    response = client.get("/api/v1/quant/screener?is_fallback=true")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    for item in data["data"]:
        assert item["is_fallback"] is True


def test_quant_screener_pagination(client):
    response = client.get("/api/v1/quant/screener?page=2&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["page"] == 2
    assert data["limit"] == 10
    assert len(data["data"]) == 10


def test_portfolio_state_endpoint(client):
    response = client.get("/api/v1/portfolio/state?as_of=2026-01-30T08:30:00Z")
    assert response.status_code == 424
    assert response.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"


def test_websocket_ticks(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/v1/stream/ticks") as websocket:
            websocket.receive_json()
    assert excinfo.value.code == 1013


def test_sse_system_events(client):
    response = client.get("/sse/v1/events/system?limit=2")
    assert response.status_code == 200
    text = response.text
    assert "data:" in text
    assert "omega_api_gateway" in text


# 16-Dimension Adversarial Matrix Tests
def test_quant_screener_invalid_page(client):
    # Dimension 1 & 8: Strict Types & Boundary validation
    response = client.get("/api/v1/quant/screener?page=0")
    assert response.status_code == 422


def test_quant_screener_limit_bounds(client):
    # Dimension 4 & 8: Bounds & Memory Cap protection
    response = client.get("/api/v1/quant/screener?limit=5000")
    assert response.status_code == 422


def test_quant_screener_nonexistent_symbol(client):
    # Dimension 10: Canonical symbol lookups & empty sets
    response = client.get("/api/v1/quant/screener?symbol=ZZZ")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["data"]) == 0


def test_macro_summary_missing_file(monkeypatch, client):
    # Dimension 2 & 11: Fail-closed on missing file
    from omega.api.routes import macro
    monkeypatch.setattr(macro, "MACRO_PARQUET_PATH", macro.Path("nonexistent_path.parquet"))
    response = client.get("/api/v1/macro/summary")
    assert response.status_code == 404
    assert response.json() == {"detail": "Macro indicators dataset not found"}


def test_quant_screener_missing_file(monkeypatch, client):
    # Dimension 2 & 11: Fail-closed on missing dataset
    from omega.api.routes import quant
    monkeypatch.setattr(quant, "QUANT_PARQUET_PATH", quant.Path("nonexistent_path.parquet"))
    response = client.get("/api/v1/quant/screener")
    assert response.status_code == 424
    assert response.json() == {"detail": "FUNDAMENTAL_DATA_UNAVAILABLE"}


def test_quant_screener_veto_filter(client):
    # Dimension 9: Financial business logic & veto flag filtering
    response = client.get("/api/v1/quant/screener?is_veto=false&limit=10")
    assert response.status_code == 200
    data = response.json()
    for item in data["data"]:
        assert item["is_veto"] is False


def test_portfolio_state_structure_and_types(client):
    # Dimension 6 & 9: PIT ISO timestamps, fail-closed contracts
    response = client.get("/api/v1/portfolio/state?as_of=2026-01-30T08:30:00Z")
    assert response.status_code == 424
    assert response.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"


_EXECUTION_CUTOFF = '2026-10-09T08:30:00Z'


def _execution_record(**changes):
    row = dict(order_id='o1', execution_ts='2026-10-05T03:00:00Z',
               recorded_at='2026-10-05T03:00:00Z', feature_ts='2026-10-05T02:00:00Z',
               available_at='2026-10-05T02:00:00Z', decision_ts='2026-10-05T02:30:00Z',
               symbol='VCB', side='BUY', quantity=100.0, intended_price=10000.0,
               executed_price=10100.0, execution_status='FILLED', arrival_price=10000.0,
               fee_vnd=1000.0, venue='HOSE')
    row.update(changes)
    return row


@pytest.fixture
def execution_gateway(monkeypatch):
    class Engine:
        rows = []

        def get_orders(self, limit):
            assert limit == 5000
            return self.rows

    engine = Engine()
    test_app = FastAPI()
    test_app.include_router(execution.router)
    monkeypatch.setattr(execution, '_get_engine', lambda: engine)
    with TestClient(test_app) as gateway:
        yield gateway, engine


@pytest.mark.parametrize('endpoint', ['blotter', 'timeline', 'slippage-distribution', 'settlement-timeline'])
def test_execution_gateway_read_contracts(execution_gateway, endpoint):
    gateway, engine = execution_gateway
    engine.rows = [_execution_record(recorded_at=_EXECUTION_CUTOFF),
                   _execution_record(order_id='future', recorded_at='2026-10-09T08:30:00.000001Z')]
    response = gateway.get(f'/api/v1/execution/{endpoint}', params={'as_of': _EXECUTION_CUTOFF})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['effective_cutoff'] == _EXECUTION_CUTOFF
    assert result['provenance'] == 'RECORDED'
    assert result['price_unit'] == 'VND_FULL'
    assert 'future' not in response.text
    engine.rows[0].pop('recorded_at')
    assert gateway.get(f'/api/v1/execution/{endpoint}', params={'as_of': _EXECUTION_CUTOFF}).status_code == 424


@pytest.mark.parametrize('endpoint', ['blotter', 'timeline', 'slippage-distribution', 'settlement-timeline'])
@pytest.mark.parametrize('params', [
    {'as_of': 'bad'}, {'as_of': '2026-10-09T08:30:00'}, {'as_of': '2999-01-01T00:00:00Z'},
    {'unknown': 'SECRET'}, [('as_of', _EXECUTION_CUTOFF), ('as_of', _EXECUTION_CUTOFF)],
])
def test_execution_gateway_rejects_ambiguous_or_invalid_query(execution_gateway, endpoint, params):
    gateway, _ = execution_gateway
    response = gateway.get(f'/api/v1/execution/{endpoint}', params=params)
    assert response.status_code == 422, response.text
    assert 'SECRET' not in response.text


@pytest.mark.parametrize('endpoint', ['blotter', 'timeline', 'slippage-distribution', 'settlement-timeline'])
@pytest.mark.parametrize('value', [None, '', '100', [], True, float('nan'), float('inf'), float('-inf'), -1, 1e13])
def test_execution_gateway_invalid_rows_fail_closed(execution_gateway, endpoint, value):
    gateway, engine = execution_gateway
    engine.rows = [_execution_record(quantity=value)]
    response = gateway.get(f'/api/v1/execution/{endpoint}')
    assert response.status_code == 424, response.text
    assert response.json() == {'detail': 'EXECUTION_DATA_INVALID'}


def test_execution_gateway_slippage_and_unconfirmed_settlement(execution_gateway):
    gateway, engine = execution_gateway
    engine.rows = [_execution_record(), _execution_record(order_id='sell', side='SELL', executed_price=9900.0, quantity=200.0)]
    result = gateway.get('/api/v1/execution/slippage-distribution').json()
    assert [point['slippage_bps'] for point in result['points']] == pytest.approx([110, 105])
    assert result['venues'][0]['average_slippage_bps'] == pytest.approx(320 / 3)
    engine.rows = [_execution_record(execution_ts='2026-04-29T03:00:00Z', recorded_at='2026-04-29T03:00:00Z',
                                    feature_ts=None, available_at=None, decision_ts=None,
                                    cash_available_vnd=999999.0, shares_available=100.0)]
    settlement = gateway.get('/api/v1/execution/settlement-timeline').json()['settlements'][0]
    assert settlement['confirmed'] is False
    assert settlement['cash_available_vnd'] is None
    assert settlement['shares_available'] is None
    assert settlement['expected_settlement_at'] == '2026-05-05T08:30:00Z'


_MACRO_UI_RUNNER = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const [root, mode, scenario] = process.argv.slice(1);
const uiRequire = Module.createRequire(path.join(root, 'omega-ui/package.json'));
const ts = uiRequire('typescript');
const file = path.join(root, 'omega-ui/src/modules/macro_cockpit/LandingDatabaseHub.tsx');
const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const mod = new Module(file);
mod.filename = file;
mod.require = (name) => {
  if (name === '@tanstack/react-query') return { useQuery: (options) => options };
  if (name === '../../api/client') return { API_BASE: 'https://fixture.invalid' };
  return name.startsWith('react') ? uiRequire(name) : {};
};
mod._compile(compiled + '\nexports.requestMacroData = requestMacroData;', file);
const { requestMacroData, validateMacroData, useMacroData } = mod.exports;
const cap = 1024 * 1024, encoder = new TextEncoder(), cutoff = '2026-01-30T08:30:00Z';
function payload(state = 'expansion') {
  const base = { status: 'success', effective_cutoff: cutoff };
  return [{ ...base, interbank: [], sovereign: [] }, {
    ...base, regime: state, probability_method: 'DETERMINISTIC_RULE_ONE_HOT',
    coordinate_method: 'TANH_NATIVE_UNIT_ZSCORE', coordinates: { unit: 'DIMENSIONLESS', growth: 0, inflation: 0 },
    state_probabilities: { expansion: 1, neutral_chop: 0, high_vol_bear: 0, crisis: 0 },
    indicators: [], omo_net_billion_vnd: 0,
  }, { ...base, bands: [] }];
}
async function responseBoundary() {
  const controller = new AbortController();
  let chunks = [encoder.encode('{}')], header = null, ok = true, body = true;
  let valid = false, expected, reads = 0, cancels = 0, releases = 0, parses = 0;
  switch (scenario) {
    case 'exact-cap': chunks = [encoder.encode('{}' + ' '.repeat(cap - 2))]; valid = true; expected = {}; break;
    case 'cap-plus-one': chunks = [encoder.encode('{}' + ' '.repeat(cap - 1))]; break;
    case 'cumulative-overflow': chunks = [encoder.encode('{}'), new Uint8Array(cap - 2).fill(32), encoder.encode(' ')]; break;
    case 'understated-length': header = '2'; chunks = [new Uint8Array(cap + 1)]; break;
    case 'oversized-length': header = String(cap + 1); break;
    case 'unknown-field': chunks = [encoder.encode('{"unknown":"' + 'x'.repeat(cap) + '"}')]; break;
    case 'oversized-array': chunks = [encoder.encode('[' + '0,'.repeat(cap / 2) + '0]')]; break;
    case 'multibyte-overflow': chunks = [encoder.encode('"' + 'é'.repeat(cap / 2) + '"')]; break;
    case 'split-utf8': chunks = Array.from(encoder.encode('{"value":"đồng"}'), (b) => new Uint8Array([b])); valid = true; expected = { value: 'đồng' }; break;
    case 'invalid-utf8': chunks = [new Uint8Array([0x22, 0xc3, 0x22])]; break;
    case 'malformed-json': chunks = [encoder.encode('{SECRET')]; break;
    case 'empty-body': chunks = []; break;
    case 'missing-stream': body = false; break;
    case 'http-error': ok = false; break;
    case 'already-aborted': controller.abort(); break;
    case 'cancel-error': chunks = [new Uint8Array(cap + 1)]; break;
    case 'read-error': case 'abort-during-read': case 'fetch-error': break;
    case 'native-response': valid = true; expected = {}; break;
    default: assert.fail(scenario);
  }
  const reader = {
    async read() {
      reads++;
      if (scenario === 'read-error' && reads === 2) throw Error('SECRET read error');
      if (scenario === 'abort-during-read') controller.abort();
      const value = chunks.shift();
      return value === undefined ? { done: true } : { done: false, value };
    },
    async cancel() { cancels++; if (scenario === 'cancel-error') throw Error('SECRET cancel error'); },
    releaseLock() { releases++; },
  };
  const headers = new Headers(header === null ? {} : { 'Content-Length': header });
  const nativeResponse = new Response('{}');
  global.fetch = async (url, init) => {
    assert.equal(url, 'https://fixture.invalid/api/v1/macro/yield-curve');
    assert.equal(init.signal, controller.signal); assert.equal(init.headers.Accept, 'application/json');
    if (scenario === 'fetch-error') throw Error('SECRET fetch error');
    if (scenario === 'native-response') return nativeResponse;
    return { ok, headers,
      body: body ? { getReader: () => reader } : null,
      json() { assert.fail('unbounded JSON reader'); }, text() { assert.fail('unbounded text reader'); },
    };
  };
  const originalParse = JSON.parse;
  JSON.parse = (...args) => { parses++; return originalParse(...args); };
  try {
    const call = requestMacroData('/api/v1/macro/yield-curve', controller.signal);
    if (valid) assert.deepEqual(await call, expected);
    else await assert.rejects(call, (error) => scenario !== 'cancel-error' || error.message === 'Invalid macro response');
  } finally { JSON.parse = originalParse; }
  assert.equal(parses, valid || ['malformed-json', 'empty-body'].includes(scenario) ? 1 : 0);
  if (!['native-response', 'fetch-error'].includes(scenario) && body) {
    assert.equal(releases, 1); assert.equal(cancels, valid ? 0 : 1);
  }
  if (['oversized-length', 'http-error', 'already-aborted'].includes(scenario)) assert.equal(reads, 0);
}
function regimeBoundary() {
  const invalid = { array: ['expansion'], empty_array: [], object: {}, boxed: new String('expansion'),
    coercible: { toString() { assert.fail('must not coerce'); } }, number: 1, boolean: true,
    null: null, undefined: undefined, empty: '', unknown: 'unknown', nan: NaN, inf: Infinity, neg_inf: -Infinity };
  if (scenario in invalid) {
    const data = payload(); data[1].regime = invalid[scenario];
    assert.throws(() => validateMacroData(...data, cutoff), /Invalid macro response/); return;
  }
  const data = payload('ExPaNsIoN');
  if (scenario === 'one-hot-mismatch') {
    data[1].state_probabilities = { expansion: 0, neutral_chop: 1, high_vol_bear: 0, crisis: 0 };
    assert.throws(() => validateMacroData(...data, cutoff), /Invalid macro response/);
  } else {
    assert.equal(validateMacroData(...data, cutoff).regime, 'expansion');
    for (const state of ['expansion', 'neutral_chop', 'high_vol_bear', 'crisis']) {
      const values = payload(state.toUpperCase());
      for (const key of Object.keys(values[1].state_probabilities)) values[1].state_probabilities[key] = Number(key === state);
      assert.equal(validateMacroData(...values, cutoff).regime, state);
    }
  }
}
async function queryBoundary() {
  const [routeIndex, fault] = scenario.split(':'), selected = Number(routeIndex);
  const outer = new AbortController(), requests = [], values = payload();
  let removals = 0, cleared = 0, timeout;
  const remove = outer.signal.removeEventListener.bind(outer.signal);
  outer.signal.removeEventListener = (...args) => { removals++; return remove(...args); };
  global.setTimeout = (callback, delay) => { assert.equal(delay, 10000); timeout = callback; return 1; };
  global.clearTimeout = (id) => { assert.equal(id, 1); cleared++; };
  global.fetch = async (url, { signal }) => {
    const index = requests.length; requests.push({ url, signal });
    if (fault === 'success') return new Response(JSON.stringify({ ...values[index], effective_cutoff: new URL(url).searchParams.get('as_of') }));
    if (index === selected && !['timeout', 'external-abort'].includes(fault)) {
      if (fault === 'http') return new Response('SECRET', { status: 500 });
      if (fault === 'parse') return new Response('SECRET');
      if (fault === 'missing-stream') return new Response(null);
      if (fault === 'read') return new Response(new ReadableStream({ start(c) { c.error(Error('SECRET')); } }));
      return new Response(new Uint8Array(cap + 1));
    }
    return new Response(new ReadableStream({ start(c) {
      if (signal.aborted) c.error(Error('SECRET abort'));
      else signal.addEventListener('abort', () => c.error(Error('SECRET abort')), { once: true });
    } }));
  };
  const options = useMacroData();
  assert.equal(options.retry, false); assert.equal(options.retryOnMount, false);
  assert.equal(options.refetchOnWindowFocus, false); assert.equal(options.refetchOnReconnect, false);
  assert.equal(options.enabled({ state: { status: 'error' } }), false);
  const call = options.queryFn({ signal: outer.signal });
  if (fault === 'timeout') timeout();
  if (fault === 'external-abort') outer.abort();
  if (fault === 'success') assert.equal((await call).regime, 'expansion');
  else await assert.rejects(call, (error) => error.message === 'Macro data unavailable');
  assert.equal(requests.length, 3);
  assert.equal(new Set(requests.map(({ url }) => new URL(url).searchParams.get('as_of'))).size, 1);
  assert.deepEqual(requests.map(({ url }) => new URL(url).pathname),
    ['/api/v1/macro/yield-curve', '/api/v1/macro/regime-metrics', '/api/v1/macro/limit-bands']);
  for (const request of requests) assert.equal(request.signal.aborted, fault !== 'success');
  assert.equal(cleared, 1); assert.equal(removals, 1);
}
(async () => {
  if (mode === 'response') await responseBoundary();
  else if (mode === 'regime') regimeBoundary();
  else await queryBoundary();
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""


def _run_macro_ui(mode, scenario):
    node = shutil.which('node')
    assert node is not None, 'Node.js required for actual macro UI boundary checks'
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, '-e', _MACRO_UI_RUNNER, str(root), mode, scenario], cwd=root,
        capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(result.stdout + result.stderr)


@pytest.mark.parametrize('scenario', [
    'exact-cap', 'cap-plus-one', 'cumulative-overflow', 'understated-length', 'oversized-length',
    'unknown-field', 'oversized-array', 'multibyte-overflow', 'split-utf8', 'invalid-utf8',
    'malformed-json', 'empty-body', 'missing-stream', 'http-error', 'read-error', 'cancel-error',
    'already-aborted', 'abort-during-read', 'fetch-error', 'native-response',
])
def test_macro_ui_response_boundary(scenario):
    _run_macro_ui('response', scenario)


@pytest.mark.parametrize('scenario', [
    'array', 'empty_array', 'object', 'boxed', 'coercible', 'number', 'boolean', 'null', 'undefined',
    'empty', 'unknown', 'nan', 'inf', 'neg_inf', 'one-hot-mismatch', 'valid',
])
def test_macro_ui_regime_type_boundary(scenario):
    _run_macro_ui('regime', scenario)


@pytest.mark.parametrize('route', range(3))
@pytest.mark.parametrize('fault', ['overflow', 'http', 'parse', 'read', 'missing-stream', 'timeout', 'external-abort', 'success'])
def test_macro_ui_query_fail_closed(route, fault):
    _run_macro_ui('query', f'{route}:{fault}')
