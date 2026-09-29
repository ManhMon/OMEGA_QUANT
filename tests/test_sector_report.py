from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from scripts.generate_sector_report import generate_sector_report, OUTPUT_DIR


class _DB:
    def __init__(self, sectors=None, news=None, macro=None):
        self._sectors = sectors or []
        self._news = news or []
        self._macro = macro or []

    def get_ticker_sector(self):
        return self._sectors

    def get_news_articles(self, **kwargs):
        return self._news

    def get_macro_data(self):
        return self._macro


def test_score_delta_null_without_prior(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.generate_sector_report.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("scripts.generate_sector_report.Database", lambda: _DB())
    monkeypatch.setattr("scripts.generate_sector_report.DataLoader.load_market_data", lambda *args, **kwargs: _market_panel())
    payload = generate_sector_report(datetime(2026, 6, 30).date())
    assert "no_prior_report" in payload["quality_flags"]
    assert payload["executive_table"][0]["score_delta_1d"] is None


def test_score_delta_computed_with_prior(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.generate_sector_report.OUTPUT_DIR", tmp_path)
    prior_path = tmp_path / "sector_report_2026-06-29.json"
    prior_path.write_text(json.dumps({"executive_table": [{"sector": "Sector-0", "composite_score": 0.2}]}), encoding="utf-8")
    monkeypatch.setattr("scripts.generate_sector_report.Database", lambda: _DB())
    monkeypatch.setattr("scripts.generate_sector_report.DataLoader.load_market_data", lambda *args, **kwargs: _market_panel())
    payload = generate_sector_report(datetime(2026, 6, 30).date())
    assert any(row["score_delta_1d"] is not None for row in payload["executive_table"])


def test_sector_mapping_not_pit_flag(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.generate_sector_report.OUTPUT_DIR", tmp_path)
    sectors = [{"ticker": "HPG", "sector": "Steel", "effective_date": None}]
    monkeypatch.setattr("scripts.generate_sector_report.Database", lambda: _DB(sectors=sectors))
    monkeypatch.setattr("scripts.generate_sector_report.DataLoader.load_market_data", lambda *args, **kwargs: _market_panel())
    payload = generate_sector_report(datetime(2026, 6, 30).date())
    assert "sector_mapping_not_pit" in payload["quality_flags"]


def test_json_and_md_tables_match(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.generate_sector_report.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("scripts.generate_sector_report.Database", lambda: _DB())
    monkeypatch.setattr("scripts.generate_sector_report.DataLoader.load_market_data", lambda *args, **kwargs: _market_panel())
    payload = generate_sector_report(datetime(2026, 6, 30).date())
    md_text = (tmp_path / "sector_report_2026-06-30.md").read_text(encoding="utf-8")
    assert payload["executive_table"][0]["sector"] in md_text


def test_degrades_without_macro_or_news(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.generate_sector_report.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("scripts.generate_sector_report.Database", lambda: _DB())
    monkeypatch.setattr("scripts.generate_sector_report.DataLoader.load_market_data", lambda *args, **kwargs: _market_panel())
    payload = generate_sector_report(datetime(2026, 6, 30).date())
    assert isinstance(payload["macro_backdrop"], list)


def test_f001_sector_report_assert_pit_rejects_future_available_at(monkeypatch, tmp_path):
    """F-001: assert_pit fails closed on market data available_at exceeding cutoff."""
    monkeypatch.setattr("scripts.generate_sector_report.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("scripts.generate_sector_report.Database", lambda: _DB())
    cutoff = datetime(2026, 6, 30, 8, 30, tzinfo=timezone.utc)
    def _future_market_panel():
        panel = _market_panel()
        panel["available_at"] = cutoff + timedelta(days=1)
        return panel
    monkeypatch.setattr("scripts.generate_sector_report.DataLoader.load_market_data", lambda *args, **kwargs: _future_market_panel())
    with pytest.raises(AssertionError):
        generate_sector_report(datetime(2026, 6, 30).date(), assert_pit=True)


def test_f001_sector_mapping_future_effective_date_rejected_for_pit(monkeypatch, tmp_path):
    """F-001: sector records with future effective dates cannot satisfy PIT mapping."""
    monkeypatch.setattr("scripts.generate_sector_report.OUTPUT_DIR", tmp_path)
    sectors = [{"ticker": "HPG", "sector": "Steel", "effective_date": "2026-07-01"}]
    monkeypatch.setattr("scripts.generate_sector_report.Database", lambda: _DB(sectors=sectors))
    monkeypatch.setattr("scripts.generate_sector_report.DataLoader.load_market_data", lambda *args, **kwargs: _market_panel())
    payload = generate_sector_report(datetime(2026, 6, 30).date())
    assert "sector_mapping_not_pit" in payload["quality_flags"]


def test_f005_sector_report_partial_symbol_mapping_audit_flag(monkeypatch, tmp_path):
    """F-005: partial symbol mapping falls back and flags non-pit when records invalid."""
    monkeypatch.setattr("scripts.generate_sector_report.OUTPUT_DIR", tmp_path)
    sectors = [{"ticker": "HPG", "sector": "Steel", "effective_date": None}]
    monkeypatch.setattr("scripts.generate_sector_report.Database", lambda: _DB(sectors=sectors))
    monkeypatch.setattr("scripts.generate_sector_report.DataLoader.load_market_data", lambda *args, **kwargs: _market_panel())
    payload = generate_sector_report(datetime(2026, 6, 30).date())
    assert payload["audit"]["sector_mapping_not_pit"] is True


def _market_panel():
    dates = pd.date_range("2026-03-01", periods=80, freq="B")
    rows = []
    tickers = ["HPG", "FPT", "VCB", "SSI", "PVD", "VNM"]
    for t_idx, ticker in enumerate(tickers):
        for d_idx, dt in enumerate(dates):
            close = 20_000 + t_idx * 1_000 + d_idx * 10
            rows.append({"date": dt, "ticker": ticker, "close": close, "volume": 1000 + t_idx * 10, "value": close * (1000 + t_idx * 10), "available_at": dt.tz_localize("UTC") + pd.Timedelta(days=1)})
    frame = pd.DataFrame(rows).set_index(["date", "ticker"])
    return frame
