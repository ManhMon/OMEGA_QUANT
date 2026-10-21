"""Offline W7 coordinator. SQLite owns transactions; local simulation has no broker capability."""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from datetime import datetime, time as day_time, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from threading import Lock
import time

import numpy as np
import pandas as pd

from features.pit_guard import validate_shadow_data_guard
from omega.core.llm_config import DOMAIN_REGISTRY, _validate_jev_envelope
from omega.core.vn_market_rules import VnMarketRules
from omega.data.calendar import ICT, VNTradingCalendar
from omega.execution.vn_transaction_cost_model import VNTransactionCostModel
from omega.pipeline.telemetry import Telemetry, process_tree_rss
from omega.quant.alpha.forensic_filter import ForensicFilter
from omega.quant.drift_detector import attach_decay_attribution
from omega.quant.execution.smart_execution import build_randomized_twap_schedule, build_vwap_schedule
from omega.quant.portfolio.black_litterman_overlay import apply_calibrated_black_litterman_overlay
from omega.quant.portfolio.portfolio_optimizer import PortfolioOptimizer
from omega.quant.portfolio.regime_overlay import map_four_state_regime
from omega.quant.strategy.unified_alpha_evaluator import annotate_execution_costs, blend_features
from omega.risk.contagion_risk_validator import event_concentration_advisory
from omega.risk.validators import AssetLimitValidator, DrawdownValidator, ExposureValidator, SectorLimitValidator

GATE = "GATE_JEV_DEEP_INTEGRATION_W7_20260930"
ROOT = Path(__file__).resolve().parents[3]
MAX_BYTES = 1_048_576
MAX_ASSETS = 64
MAX_RECORDS = 4096
CACHE_LIMIT = 500_000_000
RSS_LIMIT = 4_000_000_000
DEADLINE_SECONDS = 2.0
RESERVE_SECONDS = .1
MODES = ("disabled", "replay", "shadow", "paper")
ARMS = ("B0", "B1", "B2", "B3", "B4")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CREDENTIAL = re.compile(r"(?i)(?:\b(?:bearer\s+|sk-[\w-]+|gh[pousr]_[\w]+)|https?://[^/@\s]+@|\b(?:api[\s_-]*key|client[\s_-]*secret|(?:access|refresh)[\s_-]*token|private[\s_-]*key|password|secret|token|authorization|cookie|credentials)\s*[:=])")
_CREDENTIAL_KEYS = {"apikey", "clientsecret", "accesstoken", "refreshtoken", "password", "secret", "token", "authorization", "cookie", "credentials", "privatekey"}
REQUEST_FIELDS = {"schema_version", "gate_id", "run_id", "decision_id", "arm", "cutoff", "source_revision",
                  "policy_version", "calendar_digest", "universe", "market", "signal", "initial_cash_vnd",
                  "risk_halt", "actions", "advisory"}
MARKET_FIELDS = {"symbol", "exchange", "sector", "status", "as_of", "available_at", "open", "high", "low",
                 "close", "volume", "reference_price", "bid", "ask", "bid_quantity", "ask_quantity"}
ADVISORY_FIELDS = {"classification", "events", "regime_state", "bl", "concentration", "decay", "tactic", "lambda_r"}
DECISION_FIELDS = {"schema_version", "gate_id", "run_id", "arm", "decision_id", "request_sha", "cutoff", "cutoff_provenance",
                   "mode", "advisory_only", "applied", "live_lambda", "simulation_applied", "outcome", "reason", "baseline_digest",
                   "parent_digest", "annotations", "weights", "risk_safe", "orders", "fills", "nav_vnd", "cost_vnd", "nav_residual_vnd",
                   "ledger", "metrics", "source_revision", "policy_version", "calendar_digest", "universe"}


def get_pipeline_version() -> str:
    return "w7/v1"


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def canonical(value: object) -> bytes:
    def check(item):
        if type(item) is dict:
            for key, child in item.items():
                if (type(key) is not str or re.sub(r"[\s_-]+", "", key).casefold() in _CREDENTIAL_KEYS or
                        _CREDENTIAL.search(key)):
                    raise ValueError("credential field rejected")
                check(child)
        elif type(item) in (list, tuple):
            for child in item:
                check(child)
        elif type(item) is str and _CREDENTIAL.search(item):
            raise ValueError("credential-bearing content rejected")
    _bound_tree(value)
    check(value)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("payload exceeds bound")
    return raw


def _decision_digest(value: dict) -> str:
    bound = deepcopy(value)
    bound["ledger"].pop("parent")
    return digest(bound)


def _bound_tree(value: object, depth: int = 0, budget: list[int] | None = None) -> None:
    budget = [0] if budget is None else budget
    budget[0] += len(value) * 6 if type(value) is str else 32
    if budget[0] > MAX_BYTES:
        raise ValueError("payload exceeds bound")
    if depth > 12:
        raise ValueError("nested payload exceeds bound")
    if type(value) in (dict, list):
        if len(value) > 4096:
            raise ValueError("collection exceeds bound")
        if type(value) is dict:
            for key in value:
                if type(key) is not str or len(key) > 128:
                    raise ValueError("field name exceeds bound")
                budget[0] += len(key) * 6
            if budget[0] > MAX_BYTES:
                raise ValueError("payload exceeds bound")
        for item in value.values() if type(value) is dict else value:
            _bound_tree(item, depth + 1, budget)
    elif type(value) is str and len(value) > 65536:
        raise ValueError("string exceeds bound")
    elif type(value) is int and abs(value) > 10**18:
        raise ValueError("integer exceeds bound")


def strict_json(raw: bytes | str) -> object:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate JSON field")
            out[key] = value
        return out
    if not isinstance(raw, (bytes, str)) or len(raw) > MAX_BYTES:
        raise ValueError("JSON exceeds bound")
    try:
        value = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")))
        _bound_tree(value)
        canonical(value)
        return value
    except (UnicodeError, RecursionError, TypeError, ValueError):
        raise ValueError("invalid strict JSON") from None


def sandbox_path(value: str | Path, *, existing: bool = False) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError("invalid sandbox path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts or any(":" in p for p in path.parts):
        raise ValueError("path must be repo-relative")
    allowed = (ROOT / ".ly_state/session/jev_deep_integration_20260926/W7", ROOT / ".omega_test_tmp",
               ROOT / ".ly_state/session/pytest_tmp_paths")
    target = ROOT / path
    if not any(target.is_relative_to(p) and target.resolve().is_relative_to(p.resolve()) for p in allowed):
        raise ValueError("path outside shadow sandbox")
    if any(p.is_symlink() or p.is_junction() for p in (target, *target.parents) if p != ROOT):
        raise ValueError("linked sandbox path")
    if target.exists() and not target.is_file() or existing and not target.is_file():
        raise ValueError("path must be a regular file")
    if not target.parent.is_dir():
        raise ValueError("sandbox parent missing")
    return target


def _fields(value: object, fields: set[str]) -> None:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("invalid schema")


def _identifier(value: object) -> None:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("invalid identifier")


def _number(value: object, low: float, high: float, *, integer: bool = False) -> None:
    if type(value) not in ((int,) if integer else (int, float)) or not low <= value <= high or not math.isfinite(value):
        raise ValueError("invalid bounded number")


def _timestamp(value: object) -> datetime:
    if type(value) is not str or len(value) > 40:
        raise ValueError("invalid timestamp")
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError("timestamp must be timezone-aware") from None


def _pit(record: dict, cutoff: datetime) -> None:
    if not _timestamp(record["as_of"]) <= _timestamp(record["available_at"]) <= cutoff:
        raise ValueError("ineligible source availability")


def _settlement(cutoff: datetime) -> str:
    day = cutoff.astimezone(ICT).date()
    for _ in range(2):
        day = VNTradingCalendar.next_trading_day(day)
    return datetime.combine(day, day_time(13), ICT).astimezone(timezone.utc).isoformat()


def _money(amount: Decimal) -> int:
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _validate_request(request: dict) -> tuple[dict, datetime]:
    # Reject the complete input at ingress, including otherwise-inert advisory fields.
    canonical(request)
    _fields(request, REQUEST_FIELDS)
    if (request["schema_version"] != "w7/v1" or request["gate_id"] != GATE or
            request["policy_version"] != "w7-v1" or request["arm"] not in ARMS or type(request["risk_halt"]) is not bool):
        raise ValueError("invalid W7 context")
    for name in ("run_id", "decision_id", "source_revision"):
        _identifier(request[name])
    cutoff = _timestamp(request["cutoff"])
    calendar = hashlib.sha256((ROOT / "config/vn_holidays.json").read_bytes()).hexdigest()
    if request["calendar_digest"] != calendar:
        raise ValueError("calendar revision mismatch")
    _number(request["initial_cash_vnd"], 1, 10**15, integer=True)
    assets, market = request["universe"], request["market"]
    if type(assets) is not list or len(assets) > MAX_ASSETS or type(market) is not list or len(market) != len(assets):
        raise ValueError("universe exceeds bound")
    for symbol in assets:
        _identifier(symbol)
    if len(set(assets)) != len(assets) or "CASH" in assets:
        raise ValueError("invalid ordered universe")
    for symbol, row in zip(assets, market):
        _fields(row, MARKET_FIELDS)
        _identifier(row["sector"])
        if row["symbol"] != symbol or row["exchange"] != "HOSE" or row["status"] not in ("active", "suspended", "delisted"):
            raise ValueError("unsupported venue or lifecycle")
        _pit(row, cutoff)
        for key in ("open", "high", "low", "close", "reference_price", "bid", "ask"):
            # ponytail: profile admits >=1000 VND prices; cheaper instruments need an explicit verified unit profile.
            _number(row[key], 1000, 10**9, integer=True)
        for key in ("volume", "bid_quantity", "ask_quantity"):
            _number(row[key], 0, 10**12, integer=True)
        if row["bid"] > row["ask"]:
            raise ValueError("crossed book")
    signal = request["signal"]
    _fields(signal, {"as_of", "available_at", "values", "covariance"})
    _pit(signal, cutoff)
    if _timestamp(signal["as_of"]).astimezone(ICT).date() >= cutoff.astimezone(ICT).date():
        raise ValueError("signals require prior session observations")
    n = len(assets)
    if type(signal["values"]) is not list or len(signal["values"]) != n or type(signal["covariance"]) is not list or len(signal["covariance"]) != n:
        raise ValueError("signal shape mismatch")
    for value in signal["values"]:
        _number(value, -1, 1)
    for row in signal["covariance"]:
        if type(row) is not list or len(row) != n:
            raise ValueError("covariance shape mismatch")
        for value in row:
            _number(value, -1, 1)
    if type(request["actions"]) is not list or len(request["actions"]) > MAX_ASSETS:
        raise ValueError("actions exceed bound")
    for action in request["actions"]:
        _fields(action, {"action_id", "symbol", "kind", "value", "as_of", "available_at"})
        _identifier(action["action_id"])
        if action["symbol"] not in assets or action["kind"] not in ("split", "dividend"):
            raise ValueError("unsupported corporate action")
        _number(action["value"], 1, 10 if action["kind"] == "split" else 10**9, integer=True)
        _pit(action, cutoff)
    if len({a["action_id"] for a in request["actions"]}) != len(request["actions"]):
        raise ValueError("duplicate corporate action")
    if request["advisory"] is not None and (type(request["advisory"]) is not dict or len(request["advisory"]) > 16):
        raise ValueError("invalid advisory")
    return deepcopy(request), cutoff


class IntegrityStop(ValueError):
    pass


class ShadowPipeline:
    def __init__(self, state_path: str | Path, mode: str = "disabled"):
        if type(mode) is not str or mode not in MODES:
            raise ValueError("unsupported shadow mode")
        self.path = sandbox_path(state_path)
        if self.path.suffix != ".db":
            raise ValueError("state requires a dedicated SQLite .db file")
        self.mode = mode
        self.telemetry = Telemetry()
        self._rss_peak = 0
        self._advisory_cache_bytes = 0
        self._run_lock = Lock()

    def _connect(self):
        sandbox_path(self.path.relative_to(ROOT))
        conn = sqlite3.connect(self.path, timeout=0, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA max_page_count=60000")
        except BaseException:
            conn.close()
            raise
        return conn

    def cache_bytes(self) -> int:
        return self._advisory_cache_bytes + self._sqlite_bytes(self.path)

    @staticmethod
    def _sqlite_bytes(path):
        total = 0
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(str(path) + suffix)
            sandbox_path(candidate.relative_to(ROOT))
            if candidate.is_file():
                total += candidate.stat().st_size
        return total

    def _resources(self):
        self._rss_peak = max(self._rss_peak, process_tree_rss())
        if self._rss_peak > RSS_LIMIT or self.cache_bytes() > CACHE_LIMIT:
            raise ValueError("resource ceiling")

    def _schema(self, db):
        schemas = {
            "states": "CREATE TABLE states (run TEXT NOT NULL, arm TEXT NOT NULL, payload TEXT NOT NULL, sha TEXT NOT NULL, PRIMARY KEY(run,arm))",
            "decisions": "CREATE TABLE decisions (run TEXT NOT NULL, arm TEXT NOT NULL, id TEXT NOT NULL, request_sha TEXT NOT NULL, payload TEXT NOT NULL, sha TEXT NOT NULL, PRIMARY KEY(run,arm,id))",
            "actions": "CREATE TABLE actions (run TEXT NOT NULL, arm TEXT NOT NULL, id TEXT NOT NULL, sha TEXT NOT NULL, PRIMARY KEY(run,arm,id))",
        }
        existing = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        if existing and existing != schemas:
            raise IntegrityStop("state schema mismatch")
        if not existing:
            for sql in schemas.values():
                db.execute(sql)
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise IntegrityStop("corrupt state database")

    def _state(self, db, req):
        oversized = db.execute("SELECT 1 FROM states WHERE run=? AND arm=? AND length(payload)>?",
                               (req["run_id"], req["arm"], MAX_BYTES)).fetchone()
        if oversized:
            raise IntegrityStop("prior state exceeds bound")
        row = db.execute("SELECT payload,sha FROM states WHERE run=? AND arm=?", (req["run_id"], req["arm"])).fetchone()
        if row is None:
            if db.execute("SELECT 1 FROM decisions WHERE run=? AND arm=? LIMIT 1", (req["run_id"], req["arm"])).fetchone():
                raise IntegrityStop("missing prior generation")
            return {"cash": req["initial_cash_vnd"], "positions": {}, "receivables": [], "peak": req["initial_cash_vnd"],
                    "cutoff": None, "parent": None, "universe": req["universe"], "initial_cash": req["initial_cash_vnd"]}
        try:
            state = strict_json(row[0])
            _fields(state, {"cash", "positions", "receivables", "peak", "cutoff", "parent", "universe", "initial_cash"})
            if digest(state) != row[1] or state["universe"] != req["universe"] or state["initial_cash"] != req["initial_cash_vnd"]:
                raise ValueError
            for key in ("cash", "peak", "initial_cash"):
                _number(state[key], 0, 10**18, integer=True)
            if type(state["positions"]) is not dict or not set(state["positions"]) <= set(req["universe"]):
                raise ValueError
            for holding in state["positions"].values():
                _fields(holding, {"settled", "pending"})
                _number(holding["settled"], 0, 10**12, integer=True)
                self._validate_pending(holding["pending"])
            self._validate_pending(state["receivables"])
            _timestamp(state["cutoff"])
            previous = db.execute("SELECT payload,sha FROM decisions WHERE run=? AND arm=? AND sha=? LIMIT 2",
                                  (req["run_id"], req["arm"], state["parent"])).fetchall()
            if len(previous) != 1:
                raise ValueError
            prior = strict_json(previous[0][0])
            self._verify_decision(prior, previous[0][1], req)
            if prior["ledger"] != state:
                raise ValueError
            return state
        except (TypeError, ValueError, KeyError):
            raise IntegrityStop("invalid prior generation") from None

    @staticmethod
    def _verify_decision(decision, sha, req):
        _fields(decision, DECISION_FIELDS)
        if (decision["schema_version"] != "w7/v1" or decision["gate_id"] != GATE or
                decision["run_id"] != req["run_id"] or decision["arm"] != req["arm"] or
                decision["universe"] != req["universe"] or decision["policy_version"] != "w7-v1" or
                decision["live_lambda"] != 0 or type(decision["live_lambda"]) is not float or
                decision["advisory_only"] is not True or decision["applied"] is not False or
                decision["ledger"]["cutoff"] != decision["cutoff"] or decision["ledger"]["parent"] != sha or
                type(sha) is not str or not _SHA.fullmatch(sha) or _decision_digest(decision) != sha):
            raise IntegrityStop("decision contract mismatch")

    @staticmethod
    def _validate_pending(values):
        if type(values) is not list or len(values) > 128:
            raise ValueError("pending state exceeds bound")
        for item in values:
            if type(item) is not list or len(item) != 2:
                raise ValueError("invalid pending item")
            _number(item[0], 0, 10**18, integer=True)
            _timestamp(item[1])

    def _prepare_ledger(self, db, req, state, cutoff):
        for holding in state["positions"].values():
            holding["settled"] += sum(q for q, dt in holding["pending"] if _timestamp(dt) <= cutoff)
            holding["pending"] = [[q, dt] for q, dt in holding["pending"] if _timestamp(dt) > cutoff]
        state["cash"] += sum(q for q, dt in state["receivables"] if _timestamp(dt) <= cutoff)
        state["receivables"] = [[q, dt] for q, dt in state["receivables"] if _timestamp(dt) > cutoff]
        for action in req["actions"]:
            key = (req["run_id"], req["arm"], action["action_id"])
            old = db.execute("SELECT sha FROM actions WHERE run=? AND arm=? AND id=?", key).fetchone()
            if old:
                if old[0] != digest(action):
                    raise IntegrityStop("conflicting corporate action")
                continue
            if _timestamp(action["as_of"]) != cutoff:
                raise ValueError("late corporate action requires entitlement history")
            holding = state["positions"].get(action["symbol"])
            if holding:
                if action["kind"] == "split":
                    holding["settled"] *= action["value"]
                    holding["pending"] = [[q * action["value"], dt] for q, dt in holding["pending"]]
                else:
                    qty = holding["settled"] + sum(q for q, _ in holding["pending"])
                    state["receivables"].append([qty * action["value"], _settlement(cutoff)])
            db.execute("INSERT INTO actions VALUES (?,?,?,?)", (*key, digest(action)))
        return state

    @staticmethod
    def _nav(state, market):
        qty = lambda h: h["settled"] + sum(q for q, _ in h["pending"])
        nav = state["cash"] + sum(q for q, _ in state["receivables"]) + sum(
            qty(state["positions"].get(r["symbol"], {"settled": 0, "pending": []})) * r["close"] for r in market)
        _number(nav, 1, 10**18, integer=True)
        return nav

    @staticmethod
    def _risk(weights, req, nav, peak):
        sectors = {}
        for row, weight in zip(req["market"], weights):
            sectors[row["sector"]] = sectors.get(row["sector"], 0.) + weight
        args = (dict(zip(req["universe"], weights)), sectors, {}, {}, {}, [peak, nav])
        if req["risk_halt"] or any(not gate.validate(*args)[0] for gate in (
                AssetLimitValidator(.1), SectorLimitValidator(.25), ExposureValidator(1.), DrawdownValidator(.1))):
            return False
        return True

    def _baseline(self, req, state, cutoff):
        market = req["market"]
        if market:
            frame = pd.DataFrame([{k: row[k] for k in ("symbol", "as_of", "available_at", "open", "high", "low", "close", "volume")} for row in market])
            for key in ("as_of", "available_at"):
                frame[key] = pd.to_datetime(frame[key], utc=True)
            if validate_shadow_data_guard(frame, cutoff=cutoff)["status"] != "valid":
                raise ValueError("mandatory data quarantined")
        cov = np.array(req["signal"]["covariance"], dtype=float)
        if market and (not np.allclose(cov, cov.T, atol=1e-12, rtol=0) or np.linalg.eigvalsh(cov).min() < -1e-12):
            raise ValueError("invalid mandatory covariance")
        nav = self._nav(state, market)
        if not market:
            return [], False, nav
        series = pd.Series(req["signal"]["values"], index=req["universe"], dtype=float)
        weights = PortfolioOptimizer(max_concentration=.1).optimize_weights(
            series, covariance_matrix=pd.DataFrame(cov, index=series.index, columns=series.index))
        values = [float(v) for v in weights]
        if any(not math.isfinite(v) or v < 0 or v > .1 + 1e-9 for v in values) or math.fsum(values) > 1 + 1e-9:
            raise ValueError("unsafe baseline allocation")
        return values, self._risk(values, req, nav, state["peak"]), nav

    def _classification(self, req, cutoff):
        spec = req["advisory"]["classification"]
        _fields(spec, {"cache_path", "domain", "facts", "available_at", "expires_at", "model"})
        if spec["domain"] != "regime_arbitration" or spec["model"] != "jev-hybrid" or type(spec["facts"]) is not dict:
            raise ValueError("unsupported classification")
        available = _timestamp(spec["available_at"])
        if not available <= cutoff < _timestamp(spec["expires_at"]):
            raise ValueError("expired classification")
        path = sandbox_path(spec["cache_path"], existing=True)
        size = self._sqlite_bytes(path)
        if path == self.path:
            raise ValueError("classification/state isolation required")
        self._advisory_cache_bytes = size
        if self.cache_bytes() > CACHE_LIMIT:
            raise ValueError("classification cache exceeds bound")
        payload = {"schema_version": 2, "domain": spec["domain"], "facts": spec["facts"], "choices": DOMAIN_REGISTRY[spec["domain"]],
                   "decision_cutoff": cutoff.isoformat(), "available_at": available.isoformat(), "entity_ids": tuple(req["universe"]),
                   "source_revisions": (req["source_revision"],), "gate_id": GATE, "model": spec["model"],
                   "prompt_version": "w7-v1", "policy_version": "w7-v1", "profile_version": "w7-v1", "feature_version": "w7-v1",
                   "dataset_manifest": req["calendar_digest"], "code_revision": req["source_revision"]}
        fingerprint = digest(payload)
        if any(Path(str(path) + s).exists() for s in ("-wal", "-shm", "-journal")):
            raise ValueError("cache must be checkpointed and sealed")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0)) as cache:
            cache.set_progress_handler(lambda: int(time.monotonic() >= self._deadline - RESERVE_SECONDS), 1000)
            rows = cache.execute("SELECT envelope FROM decisions WHERE fingerprint=? AND length(envelope)<=? LIMIT 2",
                                 (fingerprint, MAX_BYTES)).fetchall()
        if len(rows) != 1:
            raise ValueError("sealed cache miss")
        envelope = strict_json(rows[0][0])
        _validate_jev_envelope(envelope, fingerprint, spec["domain"], DOMAIN_REGISTRY[spec["domain"]], cutoff, available,
                               spec["model"], cached=True, gate_id=GATE, mode="replay", payload=payload,
                               facts_hash=digest(spec["facts"]), schema_version=2)
        return envelope["selected"]["regime"]

    def _p6_proposal(self, req, baseline, cutoff):
        advisory = req["advisory"]
        _fields(advisory, {"schema_version", "features", "weights", "macro_multiplier"})
        if self.mode not in ("shadow", "replay"):
            raise ValueError("P6 requires shadow or replay mode")
        rows = advisory["features"]
        columns = {"symbol", "direct_news", "spillover", "pead", "feature_as_of", "feature_available_at", "lineage"}
        if type(rows) is not list or len(rows) != len(req["universe"]):
            raise ValueError("P6 feature shape mismatch")
        for symbol, row in zip(req["universe"], rows):
            _fields(row, columns)
            if row["symbol"] != symbol or _timestamp(row["feature_as_of"]).astimezone(ICT).date() >= cutoff.astimezone(ICT).date():
                raise ValueError("P6 requires ordered prior-session features")
        streams = ("direct_news", "spillover", "pead")
        features = pd.DataFrame(rows, columns=["symbol", *streams, "feature_as_of", "feature_available_at", "lineage"]).set_index("symbol")
        quant = pd.Series(req["signal"]["values"], index=req["universe"], dtype=float)
        blend = blend_features(quant, features, weights=advisory["weights"], decision_time=cutoff,
                               macro_multiplier=advisory["macro_multiplier"])
        influence = math.fsum(advisory["weights"].values())
        proposed = list(baseline)
        if influence and baseline:
            candidate = PortfolioOptimizer(max_concentration=.1).optimize_weights(
                blend["score_before_macro"],
                covariance_matrix=pd.DataFrame(req["signal"]["covariance"], index=quant.index, columns=quant.index))
            if not isinstance(candidate, pd.Series) or not candidate.index.equals(quant.index):
                raise ValueError("P6 portfolio shape mismatch")
            for value in candidate:
                _number(value, 0, .1 + 1e-9)
            if math.fsum(candidate) > 1 + 1e-9:
                raise ValueError("unsafe P6 allocation")
            proposed = [base + influence * (float(value) - base) for base, value in zip(baseline, candidate)]
        if math.fsum(abs(value - base) for value, base in zip(proposed, baseline)) > .1 + 1e-9:
            raise ValueError("aggregate P6 influence exceeded")
        proposed = [value * advisory["macro_multiplier"] for value in proposed]
        for value in proposed:
            _number(value, 0, .1 + 1e-9)
        annotations = {"p6": {
            "provenance": "caller_supplied_unverified", "historical_eligible": False, "deployment_evidence": False,
            "macro_multiplier": advisory["macro_multiplier"],
            "stream_validity": {key: blend[f"{key}_valid"].tolist() for key in streams},
            "excluded_streams": [key for key in streams if not blend[f"{key}_valid"].any()],
        }}
        return proposed, annotations, "p6"

    @staticmethod
    def _p6_costs(selected, nav):
        _number(nav, 1, 10**18, integer=True)
        rows = [{"fill_id": row["id"], "side": row["side"], "quantity": row["quantity"],
                 "price_vnd": row["price_vnd"], "nav_vnd": nav} for row in selected["fills"]]
        ledger = annotate_execution_costs(pd.DataFrame(rows, columns=["fill_id", "side", "quantity", "price_vnd", "nav_vnd"]))
        return {"scenario": "p6_17_27_bps", "booked_in_w7_cash": False, "units": "VND_FULL",
                "fills": ledger.to_dict(orient="records")}

    def _proposal(self, req, baseline, cutoff, deadline, stages):
        advisory = req["advisory"]
        if advisory.get("schema_version") == "p6/v1":
            self._resources()
            if time.monotonic() >= deadline - RESERVE_SECONDS:
                raise TimeoutError
            start = time.monotonic()
            result = self._p6_proposal(req, baseline, cutoff)
            stages["p6"] = time.monotonic() - start
            self._resources()
            if time.monotonic() >= deadline - RESERVE_SECONDS:
                raise TimeoutError
            return result
        _fields(advisory, ADVISORY_FIELDS)
        _number(advisory["lambda_r"], 0, .1)
        # No zero-influence call to a solver, cache or provider.
        if advisory["lambda_r"] == 0:
            return baseline, {}, "disabled"
        annotations = {}
        def stage(name, fn):
            self._resources()
            if time.monotonic() >= deadline - RESERVE_SECONDS:
                raise TimeoutError
            start = time.monotonic()
            result = fn()
            stages[name] = time.monotonic() - start
            self._resources()
            if time.monotonic() >= deadline - RESERVE_SECONDS:
                raise TimeoutError
            return result
        events = advisory["events"]
        if type(events) is not list or len(events) > MAX_ASSETS:
            raise ValueError("event bound")
        converted = []
        for event in events:
            _fields(event, {"event_id", "novelty", "as_of", "available_at"})
            _identifier(event["event_id"])
            _pit(event, cutoff)
            converted.append({**event, "available_at": _timestamp(event["available_at"])})
        annotations["forensics"] = stage("forensics", lambda: ForensicFilter().evaluate_counterfactual(converted, cutoff))
        regime = stage("regime", lambda: self._classification(req, cutoff))
        if type(advisory["regime_state"]) is not int or not 0 <= advisory["regime_state"] <= 3:
            raise ValueError("invalid regime state")
        annotations["regime"] = {"label": regime, "state": map_four_state_regime(advisory["regime_state"])}
        bl = advisory["bl"]
        _fields(bl, {"as_of", "available_at", "view_ids", "P", "Q", "errors", "return_units", "return_horizon"})
        _pit(bl, cutoff)
        n, k = len(baseline), len(bl["view_ids"]) if type(bl["view_ids"]) is list else -1
        if not 0 <= k <= 64 or n == 0:
            raise ValueError("invalid BL dimensions")
        for key, rows, columns in (("P", k, n), ("errors", k, 20)):
            value = bl[key]
            if type(value) is not list or len(value) != rows or any(type(row) is not list or len(row) != columns for row in value):
                raise ValueError("invalid BL shape")
            for row in value:
                for v in row:
                    _number(v, -1, 1)
        if type(bl["Q"]) is not list or len(bl["Q"]) != k:
            raise ValueError("invalid BL shape")
        for v in bl["Q"]:
            _number(v, -1, 1)
        base = pd.Series(baseline, index=req["universe"], dtype=float)
        _, meta = stage("black_litterman", lambda: apply_calibrated_black_litterman_overlay(
            base, req["universe"], cutoff, _timestamp(bl["available_at"]), np.array(req["signal"]["covariance"], dtype=float),
            bl["view_ids"], np.array(bl["P"], dtype=float), np.array(bl["Q"], dtype=float), np.array(bl["errors"], dtype=float),
            return_units=bl["return_units"], return_horizon=bl["return_horizon"]))
        if meta["status"] == "k0_bypass":
            return baseline, {}, "disabled"
        if meta["status"] != "proposal_ready":
            raise ValueError("invalid calibrated proposal")
        candidate = PortfolioOptimizer(max_concentration=.1).optimize_weights(
            pd.Series(meta["posterior_proposal"]["mu_BL"], index=base.index),
            covariance_matrix=pd.DataFrame(req["signal"]["covariance"], index=base.index, columns=base.index))
        tilt = (base + advisory["lambda_r"] * (candidate - base)).tolist()
        if any(not math.isfinite(v) or v < 0 for v in tilt) or math.fsum(abs(a-b) for a, b in zip(tilt, baseline)) > .1:
            raise ValueError("aggregate influence exceeded")
        annotations["bl_digest"] = meta["decision_digest"]
        tactic = advisory["tactic"]
        if tactic not in ("TWAP", "VWAP"):
            raise ValueError("unsupported tactic")
        schedule = stage("execution", lambda: build_vwap_schedule() if tactic == "VWAP" else build_randomized_twap_schedule(seed=42))
        annotations["execution"] = {"tactic": tactic, "weights": [s.weight for s in schedule], "simulation_applied": False}
        event = deepcopy(advisory["concentration"])
        if type(event) is not dict or type(event.get("entities")) is not list or not set(event["entities"]) <= set(req["universe"]):
            raise ValueError("event/universe context mismatch")
        for key in ("available_at", "expires_at"):
            event[key] = _timestamp(event[key])
        annotations["concentration"] = stage("concentration", lambda: event_concentration_advisory(event, dict(zip(req["universe"], tilt)), cutoff))
        decay = deepcopy(advisory["decay"])
        _fields(decay, {"gross_before", "gross_after", "cost_before", "cost_after", "maturity", "trigger_detected"})
        decay["maturity"] = _timestamp(decay["maturity"])
        annotations["decay"] = stage("decay", lambda: attach_decay_attribution(**decay, cutoff=cutoff, synthetic=True))
        return [float(v) for v in tilt], annotations, "success"

    def _simulate(self, req, state, weights, safe, cutoff):
        ledger = deepcopy(state)
        nav = self._nav(ledger, req["market"])
        orders, fills = [], []
        reference_nav = nav
        local = cutoff.astimezone(ICT)
        open_session = VNTradingCalendar.is_trading_day(local) and (day_time(9, 15) <= local.time() < day_time(11, 30) or day_time(13) <= local.time() < day_time(14, 30))
        for row, weight in zip(req["market"], weights):
            symbol = row["symbol"]
            holding = ledger["positions"].setdefault(symbol, {"settled": 0, "pending": []})
            current = holding["settled"] + sum(q for q, _ in holding["pending"])
            target = int(Decimal(str(weight)) * nav / row["close"]) // 100 * 100
            delta = target - current
            qty = abs(delta) // 100 * 100
            if not qty or not safe:
                continue
            side = "BUY" if delta > 0 else "SELL"
            price = row["ask"] if side == "BUY" else row["bid"]
            order_id = digest([req["run_id"], req["arm"], req["decision_id"], symbol, side])
            permitted = (open_session and row["status"] == "active" and _timestamp(row["as_of"]) == cutoff and
                         VnMarketRules.is_valid_price(price) and not VNTransactionCostModel().is_price_band_blocked(
                             symbol, row["reference_price"], price, exchange_label=row["exchange"]))
            filled = min(qty, row["ask_quantity"] if side == "BUY" else row["bid_quantity"], row["volume"] // 10) // 100 * 100 if permitted else 0
            if side == "SELL":
                filled = min(filled, holding["settled"] // 100 * 100)
            else:
                filled = min(filled, int(Decimal(ledger["cash"]) / (Decimal(price) * Decimal("1.0015"))) // 100 * 100)
            fee = _money(Decimal(filled * price) * Decimal(".0015"))
            tax = _money(Decimal(filled * price) * Decimal(".001")) if side == "SELL" else 0
            if filled:
                signed = filled if side == "BUY" else -filled
                if side == "BUY":
                    ledger["cash"] -= filled * price + fee
                    holding["pending"].append([filled, _settlement(cutoff)])
                else:
                    holding["settled"] -= filled
                    ledger["receivables"].append([filled * price - fee - tax, _settlement(cutoff)])
                reference_nav += signed * (row["close"] - price) - fee - tax
                fills.append({"id": digest([order_id, "fill"]), "order_id": order_id, "symbol": symbol, "side": side,
                              "quantity": filled, "price_vnd": price, "fee_vnd": fee, "tax_vnd": tax, "clock": cutoff.isoformat()})
            orders.append({"id": order_id, "symbol": symbol, "side": side, "quantity": qty, "price_vnd": price,
                           "submit_clock": cutoff.isoformat(), "remainder_cancelled": qty-filled})
        # Validate the complete post-action/post-fill ledger before it can become a generation.
        self._validate_pending(ledger["receivables"])
        for holding in ledger["positions"].values():
            self._validate_pending(holding["pending"])
        final_nav = self._nav(ledger, req["market"])
        if final_nav != reference_nav or ledger["cash"] < 0:
            raise IntegrityStop("accounting residual")
        ledger["peak"] = max(ledger["peak"], final_nav)
        return {"weights": weights, "risk_safe": safe, "orders": orders, "fills": fills, "nav_vnd": final_nav,
                "cost_vnd": sum(f["fee_vnd"] + f["tax_vnd"] for f in fills), "nav_residual_vnd": final_nav-reference_nav,
                "ledger": ledger}

    def run(self, request: dict) -> dict:
        if not self._run_lock.acquire(blocking=False):
            raise ValueError("shadow worker already active")
        try:
            return self._run(request)
        finally:
            self._run_lock.release()

    def _run(self, request: dict) -> dict:
        start = time.monotonic()
        req, cutoff = _validate_request(request)
        request_sha = digest({"mode": self.mode, "request": req})
        self._rss_peak = 0
        self._advisory_cache_bytes = 0
        deadline, stages = start + DEADLINE_SECONDS, {}
        self._deadline = deadline
        self._resources()
        with closing(self._connect()) as db:
            db.set_progress_handler(lambda: int(time.monotonic() >= deadline - RESERVE_SECONDS), 1000)
            try:
                db.execute("BEGIN IMMEDIATE")
                self._schema(db)
                # Freeze one run-wide configuration across independent arm ledgers.
                sibling = db.execute("SELECT arm FROM states WHERE run=? LIMIT 1", (req["run_id"],)).fetchone()
                if sibling:
                    pinned = self._state(db, {**req, "arm": sibling[0]})
                    if pinned["universe"] != req["universe"] or pinned["initial_cash"] != req["initial_cash_vnd"]:
                        raise IntegrityStop("cross-arm initial conditions mismatch")
                state = self._state(db, req)
                if db.execute("SELECT 1 FROM decisions WHERE run=? AND arm=? AND id=? AND length(payload)>?",
                              (req["run_id"], req["arm"], req["decision_id"], MAX_BYTES)).fetchone():
                    raise IntegrityStop("decision exceeds bound")
                old = db.execute("SELECT request_sha,payload,sha FROM decisions WHERE run=? AND arm=? AND id=?",
                                 (req["run_id"], req["arm"], req["decision_id"])).fetchone()
                if old:
                    result = strict_json(old[1])
                    self._verify_decision(result, old[2], req)
                    if old[0] != request_sha or _decision_digest(result) != old[2] or result["ledger"]["parent"] != old[2]:
                        raise IntegrityStop("conflicting or corrupt decision")
                    db.rollback()
                    return self._finish(result, start, stages, outcome="replay", reason="duplicate")
                if state["cutoff"] is not None and cutoff <= _timestamp(state["cutoff"]):
                    raise IntegrityStop("nonmonotonic decision cutoff")
                if db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] >= MAX_RECORDS or db.execute("SELECT COUNT(*) FROM actions").fetchone()[0] >= MAX_RECORDS:
                    raise ValueError("durable record ceiling")
                self._resources()
                state = self._prepare_ledger(db, req, state, cutoff)
                t0 = time.monotonic()
                weights, safe, nav = self._baseline(req, state, cutoff)
                baseline = self._simulate(req, state, weights, safe, cutoff)
                self._resources()
                baseline_sha = digest(baseline)
                stages["baseline"] = time.monotonic() - t0
                selected, annotations, outcome, reason = baseline, {}, "baseline", "disabled"
                if safe and self.mode != "disabled" and req["arm"] == "B3":
                    if req["advisory"] is None:
                        outcome, reason = "fallback", "missing"
                    else:
                        try:
                            proposed, annotations, reason = self._proposal(req, weights, cutoff, deadline, stages)
                            if not self._risk(proposed, req, nav, state["peak"]):
                                raise ValueError("proposal infeasible")
                            selected = baseline if reason == "disabled" else self._simulate(req, state, proposed, safe, cutoff)
                            if "p6" in annotations:
                                annotations["p6"]["execution_costs"] = self._p6_costs(selected, nav)
                                self._resources()
                                if time.monotonic() >= deadline - RESERVE_SECONDS:
                                    raise TimeoutError
                            outcome = "baseline" if reason == "disabled" else "proposal"
                        except (Exception, MemoryError) as error:
                            selected, annotations = baseline, {}
                            outcome, reason = "fallback", "deadline" if isinstance(error, TimeoutError) else "advisory_error"
                elif req["arm"] not in ("B0", "B3"):
                    # ponytail: missing sealed B1/B2/B4 estimands stay disabled; enable only with preregistered evidence.
                    outcome, reason = "baseline", "missing"
                if not safe:
                    outcome, reason = "rejected", "risk"
                selected = deepcopy(selected)
                selected["ledger"]["cutoff"] = cutoff.isoformat()
                result = {"schema_version": "w7/v1", "gate_id": GATE, "run_id": req["run_id"], "arm": req["arm"],
                          "decision_id": req["decision_id"], "request_sha": request_sha, "cutoff": cutoff.isoformat(),
                          "cutoff_provenance": req["cutoff"], "mode": self.mode, "advisory_only": True, "applied": False,
                          "live_lambda": 0., "simulation_applied": outcome == "proposal", "outcome": outcome, "reason": reason,
                          "baseline_digest": baseline_sha, "parent_digest": state["parent"], "annotations": annotations,
                          "source_revision": req["source_revision"], "policy_version": req["policy_version"],
                          "calendar_digest": req["calendar_digest"], "universe": req["universe"], **selected}
                result["metrics"] = self._metrics(selected, baseline, state, req, nav)
                # State points to a digest excluding its own parent pointer; no self-referential hash.
                generation = _decision_digest(result)
                result["ledger"]["parent"] = generation
                pub = time.monotonic()
                self._resources()
                if pub >= deadline - RESERVE_SECONDS or self.cache_bytes() > CACHE_LIMIT:
                    db.rollback()
                    result.update(deepcopy(baseline), annotations={}, simulation_applied=False)
                    result["metrics"] = self._metrics(baseline, baseline, state, req, nav)
                    return self._finish(result, start, stages, outcome="uncommitted", reason="deadline", committed=False)
                try:
                    payload, state_payload = canonical(result).decode("utf-8"), canonical(result["ledger"]).decode("utf-8")
                    db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?)", (req["run_id"], req["arm"], req["decision_id"], request_sha, payload, generation))
                    db.execute("INSERT OR REPLACE INTO states VALUES (?,?,?,?)", (req["run_id"], req["arm"], state_payload, digest(result["ledger"])))
                    if self.cache_bytes() > CACHE_LIMIT:
                        raise OSError("cache ceiling")
                    self._commit(db)
                except (sqlite3.Error, OSError, MemoryError, ValueError, TypeError):
                    if not db.in_transaction:
                        # A commit can be acknowledged ambiguously: reconcile the complete native transaction.
                        published = db.execute("SELECT request_sha,payload,sha FROM decisions WHERE run=? AND arm=? AND id=?",
                                               (req["run_id"], req["arm"], req["decision_id"])).fetchone()
                        if published != (request_sha, payload, generation):
                            raise IntegrityStop("publication acknowledgment uncertain") from None
                        self._state(db, req)
                        return self._finish(result, start, stages)
                    db.rollback()
                    result.update(deepcopy(baseline), annotations={}, simulation_applied=False)
                    result["metrics"] = self._metrics(baseline, baseline, state, req, nav)
                    return self._finish(result, start, stages, outcome="uncommitted", reason="storage", committed=False)
                stages["publication"] = time.monotonic() - pub
                return self._finish(result, start, stages)
            except BaseException:
                db.set_progress_handler(None, 0)
                if db.in_transaction:
                    db.rollback()
                raise

    @staticmethod
    def _commit(db):
        db.commit()

    @staticmethod
    def _metrics(selected, baseline, state, req, nav):
        requested = sum(o["quantity"] for o in selected["orders"])
        filled = sum(f["quantity"] for f in selected["fills"])
        marks = {r["symbol"]: r["close"] for r in req["market"]}
        before = [((h := state["positions"].get(s, {"settled": 0, "pending": []}))["settled"] +
                   sum(q for q, _ in h["pending"])) * marks[s] / nav for s in req["universe"]]
        return {"allocation_l1_deviation": math.fsum(abs(a-b) for a, b in zip(selected["weights"], baseline["weights"])),
                "turnover": .5 * math.fsum(abs(a-b) for a, b in zip(selected["weights"], before)),
                "fill_ratio": filled / requested if requested else 0., "net_execution_return": selected["nav_vnd"] / nav - 1.,
                "drawdown": 1. - selected["nav_vnd"] / max(state["peak"], selected["nav_vnd"]),
                "implementation_shortfall_vnd": sum((1 if f["side"] == "BUY" else -1) * f["quantity"] * (f["price_vnd"]-marks[f["symbol"]]) +
                                                    f["fee_vnd"] + f["tax_vnd"] for f in selected["fills"]),
                "baseline_parent_orders_digest": digest(baseline["orders"]), "simulated_parent_orders_digest": digest(selected["orders"])}

    def _finish(self, result, start, stages, *, outcome=None, reason=None, committed=True):
        out = deepcopy(result)
        measurement_failed = False
        try:
            rss, cache = max(self._rss_peak, process_tree_rss()), self.cache_bytes()
        except Exception:
            rss, cache = RSS_LIMIT + 1, CACHE_LIMIT + 1
            measurement_failed = True
        elapsed = time.monotonic() - start
        out["committed"] = committed
        out["resource_usage"] = {"rss_bytes": rss, "cache_bytes": cache, "measurement_failed": measurement_failed,
                                 "limits": {"cycle_seconds": DEADLINE_SECONDS, "rss_bytes": RSS_LIMIT, "cache_bytes": CACHE_LIMIT}}
        if outcome:
            out["outcome"], out["reason"] = outcome, reason
        out["decision_digest"] = _decision_digest(result)
        try:
            self.telemetry.record(outcome=out["outcome"], reason=out["reason"], seconds=elapsed,
                                  rss_bytes=rss, cache_bytes=cache, stages=stages)
        except Exception:
            pass
        out["cycle_seconds"] = time.monotonic() - start
        out["readiness_within_limits"] = out["cycle_seconds"] <= DEADLINE_SECONDS and rss <= RSS_LIMIT and cache <= CACHE_LIMIT
        return out
