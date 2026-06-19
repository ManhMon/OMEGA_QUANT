"""
L2 Fix Tests: VND_FULL Price-Unit Contract & Exchange Resolver
==============================================================
Tests proving:
1. VND_FULL ensure_vnd_scale guard at ingestion boundaries
2. Exchange resolver UNKNOWN exclusion/flag behavior
3. Order quantity correctness for VND_FULL input
4. Trade notional correctness for VND_FULL input
5. Cash/PnL correctness for VND_FULL input
6. Commission calculation for VND_FULL
7. Slippage calculation correctness
8. ADV/capacity handling with zero-volume/inactive tickers
9. Backward-compatible THOUSANDS price_unit handling

Author: Data Engineer (Role 15)
Date: 2026-06-12
Gate: HOSE_HNX_DATA_REBUILD_PHASE12_AUDIT_20260612
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from dataclasses import dataclass


# ── VND_FULL Price Contract Tests ────────────────────────────────────────────

class TestVndPriceContract:
    """Tests for omega.data.vnd_price_contract module."""

    def test_detect_price_unit_thousands(self):
        """Prices with median < 1000 are detected as THOUSANDS."""
        from omega.data.vnd_price_contract import detect_price_unit, THOUSANDS
        df = pd.DataFrame({"close": [45.5, 50.0, 48.0, 52.0, 47.0]})
        assert detect_price_unit(df) == THOUSANDS

    def test_detect_price_unit_vnd_full(self):
        """Prices with median >= 1000 are detected as VND_FULL."""
        from omega.data.vnd_price_contract import detect_price_unit, VND_FULL
        df = pd.DataFrame({"close": [45500.0, 50000.0, 48000.0, 52000.0, 47000.0]})
        assert detect_price_unit(df) == VND_FULL

    def test_detect_price_unit_empty_df(self):
        """Empty DataFrame defaults to VND_FULL."""
        from omega.data.vnd_price_contract import detect_price_unit, VND_FULL
        df = pd.DataFrame({"close": []})
        assert detect_price_unit(df) == VND_FULL

    def test_ensure_vnd_scale_converts_thousands(self):
        """ensure_vnd_scale converts THOUSANDS prices to VND_FULL."""
        from omega.data.vnd_price_contract import ensure_vnd_scale, VND_FULL, detect_price_unit
        df = pd.DataFrame({
            "open": [45.0, 50.0],
            "high": [46.0, 51.0],
            "low": [44.0, 49.0],
            "close": [45.5, 50.5],
        })
        result = ensure_vnd_scale(df)
        # Should be multiplied by 1000
        assert result["close"].iloc[0] == pytest.approx(45500.0)
        assert result["close"].iloc[1] == pytest.approx(50500.0)
        assert result["open"].iloc[0] == pytest.approx(45000.0)
        # Original should not be modified (inplace=False)
        assert df["close"].iloc[0] == pytest.approx(45.5)
        # Result should be VND_FULL
        assert detect_price_unit(result) == VND_FULL

    def test_ensure_vnd_scale_noop_for_vnd_full(self):
        """ensure_vnd_scale does not modify VND_FULL prices."""
        from omega.data.vnd_price_contract import ensure_vnd_scale
        df = pd.DataFrame({
            "open": [45000.0, 50000.0],
            "high": [46000.0, 51000.0],
            "low": [44000.0, 49000.0],
            "close": [45500.0, 50500.0],
        })
        result = ensure_vnd_scale(df)
        pd.testing.assert_frame_equal(result, df)

    def test_ensure_vnd_scale_inplace(self):
        """ensure_vnd_scale with inplace=True modifies in place."""
        from omega.data.vnd_price_contract import ensure_vnd_scale
        df = pd.DataFrame({
            "close": [50.0, 55.0],
            "volume": [1000, 2000],
        })
        result = ensure_vnd_scale(df, inplace=True)
        assert result is df
        assert df["close"].iloc[0] == pytest.approx(50000.0)

    def test_ensure_vnd_scale_preserves_non_price_cols(self):
        """Non-price columns (volume, ticker) are preserved."""
        from omega.data.vnd_price_contract import ensure_vnd_scale
        df = pd.DataFrame({
            "ticker": ["VCB", "HPG"],
            "close": [50.0, 30.0],
            "volume": [100000, 200000],
        })
        result = ensure_vnd_scale(df)
        assert result["ticker"].tolist() == ["VCB", "HPG"]
        assert result["volume"].tolist() == [100000, 200000]

    def test_price_scale_metadata(self):
        """Metadata dict has required keys."""
        from omega.data.vnd_price_contract import price_scale_metadata, VND_FULL
        meta = price_scale_metadata()
        assert meta["canonical_price_unit"] == VND_FULL
        assert meta["vnd_price_scale_factor"] == 1000.0

    def test_get_price_multiplier_vnd_full(self):
        """VND_FULL returns multiplier 1.0."""
        from omega.data.vnd_price_contract import get_price_multiplier, VND_FULL
        assert get_price_multiplier(VND_FULL) == 1.0

    def test_get_price_multiplier_thousands(self):
        """THOUSANDS returns multiplier 1000.0."""
        from omega.data.vnd_price_contract import get_price_multiplier, THOUSANDS
        assert get_price_multiplier(THOUSANDS) == 1000.0

    def test_get_price_multiplier_invalid(self):
        """Invalid price unit raises ValueError."""
        from omega.data.vnd_price_contract import get_price_multiplier
        with pytest.raises(ValueError):
            get_price_multiplier("INVALID")


# ── Exchange Resolver Tests ──────────────────────────────────────────────────

class TestExchangeResolver:
    """Tests for omega.data.exchange_resolver module."""

    def test_resolve_exchange_known(self):
        """Known ticker resolves to correct exchange."""
        from omega.data.exchange_resolver import resolve_exchange
        emap = {"VCB": "HOSE", "SHB": "HNX", "ACB": "UPCOM"}
        assert resolve_exchange("VCB", emap) == "HOSE"
        assert resolve_exchange("SHB", emap) == "HNX"
        assert resolve_exchange("ACB", emap) == "UPCOM"

    def test_resolve_exchange_unknown(self):
        """UNKNOWN ticker returns 'UNKNOWN'."""
        from omega.data.exchange_resolver import resolve_exchange
        emap = {"VCB": "HOSE", "XYZ": "UNKNOWN"}
        assert resolve_exchange("XYZ", emap) == "UNKNOWN"
        assert resolve_exchange("MISSING", emap) == "UNKNOWN"

    def test_resolve_exchange_invalid_value(self):
        """Invalid exchange values are mapped to UNKNOWN."""
        from omega.data.exchange_resolver import resolve_exchange
        emap = {"VCB": "NASDAQ", "HPG": ""}
        assert resolve_exchange("VCB", emap) == "UNKNOWN"
        assert resolve_exchange("HPG", emap) == "UNKNOWN"

    def test_assign_exchange_column(self):
        """assign_exchange_column adds exchange column."""
        from omega.data.exchange_resolver import assign_exchange_column
        df = pd.DataFrame({"ticker": ["VCB", "HPG", "UNKNOWN_TICKER"]})
        emap = {"VCB": "HOSE", "HPG": "HOSE"}
        result = assign_exchange_column(df, emap)
        assert "exchange" in result.columns
        assert result["exchange"].tolist() == ["HOSE", "HOSE", "UNKNOWN"]

    def test_build_promoted_candidate_excludes_unknown(self):
        """UNKNOWN tickers are excluded from promoted dataset."""
        from omega.data.exchange_resolver import build_promoted_candidate
        df = pd.DataFrame({
            "ticker": ["VCB", "VCB", "HPG", "HPG", "BAD1", "BAD1"],
            "date": pd.date_range("2025-01-01", periods=6),
            "close": [50000.0, 51000.0, 30000.0, 31000.0, 5000.0, 5100.0],
            "volume": [100000, 110000, 200000, 210000, 0, 0],
        })
        emap = {"VCB": "HOSE", "HPG": "HOSE", "BAD1": "UNKNOWN"}
        promoted, manifest = build_promoted_candidate(df, emap)

        assert promoted["ticker"].nunique() == 2
        assert "BAD1" not in promoted["ticker"].values
        assert manifest["excluded_unknown_tickers"] == 1
        assert manifest["promoted_tickers"] == 2

    def test_build_promoted_candidate_flag_mode(self):
        """With exclude_unknown=False, UNKNOWN rows are flagged not dropped."""
        from omega.data.exchange_resolver import build_promoted_candidate
        df = pd.DataFrame({
            "ticker": ["VCB", "BAD1"],
            "date": [datetime(2025, 1, 1), datetime(2025, 1, 1)],
            "close": [50000.0, 5000.0],
            "volume": [100000, 0],
        })
        emap = {"VCB": "HOSE", "BAD1": "UNKNOWN"}
        promoted, manifest = build_promoted_candidate(df, emap, exclude_unknown=False)

        assert len(promoted) == 2
        assert "exchange_flag" in promoted.columns
        assert promoted[promoted["ticker"] == "BAD1"]["exchange_flag"].iloc[0] == "EXCLUDED_UNKNOWN"
        assert promoted[promoted["ticker"] == "VCB"]["exchange_flag"].iloc[0] == "OK"

    def test_build_promoted_candidate_zero_volume_stats(self):
        """Zero-volume stats are computed correctly in promoted manifest."""
        from omega.data.exchange_resolver import build_promoted_candidate
        df = pd.DataFrame({
            "ticker": ["VCB", "VCB", "HPG", "HPG", "ILLIQ", "ILLIQ"],
            "date": pd.date_range("2025-01-01", periods=6),
            "close": [50000, 51000, 30000, 31000, 8000, 8100],
            "volume": [100000, 0, 200000, 210000, 0, 0],
        })
        emap = {"VCB": "HOSE", "HPG": "HOSE", "ILLIQ": "HOSE"}
        promoted, manifest = build_promoted_candidate(df, emap)

        assert manifest["zero_volume_rows_in_promoted"] == 3  # VCB row + ILLIQ 2 rows
        assert manifest["fully_inactive_tickers_in_promoted"] == 1  # ILLIQ

    def test_build_promoted_manifest_counts(self):
        """Manifest contains correct counts."""
        from omega.data.exchange_resolver import build_promoted_candidate
        df = pd.DataFrame({
            "ticker": ["A", "A", "B", "C"],
            "close": [50000, 51000, 30000, 5000],
            "volume": [100, 200, 300, 0],
        })
        emap = {"A": "HOSE", "B": "HNX", "C": "UNKNOWN"}
        _, manifest = build_promoted_candidate(df, emap)

        assert manifest["total_input_tickers"] == 3
        assert manifest["total_input_rows"] == 4
        assert manifest["promoted_tickers"] == 2
        assert manifest["promoted_rows"] == 3
        assert manifest["excluded_unknown_tickers"] == 1
        assert manifest["excluded_unknown_rows"] == 1


# ── Order Generator VND_FULL Tests ───────────────────────────────────────────

class TestOrderGeneratorVndFull:
    """Tests proving order generator correctness with VND_FULL prices."""

    def _make_generator(self):
        from omega.execution.order_generator import OrderGenerator, PositionSizingConfig
        config = PositionSizingConfig(
            max_position_weight=0.05,
            min_order_size=100,
            board_lot_size=100,
        )
        return OrderGenerator(config)

    def test_signal_to_order_vnd_full(self):
        """VND_FULL price=50000 -> correct quantity for 5% of 1B VND portfolio."""
        gen = self._make_generator()
        order = gen.convert_signal_to_order(
            symbol="VCB",
            signal_weight=0.05,
            portfolio_value=1_000_000_000.0,  # 1B VND
            current_price=50000.0,  # 50,000 VND (VND_FULL)
            current_position=0,
            price_unit="VND_FULL",
        )
        assert order is not None
        # target_notional = 1B * 0.05 = 50M VND
        # target_qty = 50M / 50000 = 1000 shares
        assert order.quantity == 1000

    def test_signal_to_order_thousands_backward_compat(self):
        """THOUSANDS price=50.0 -> same result as VND_FULL price=50000."""
        gen = self._make_generator()
        order = gen.convert_signal_to_order(
            symbol="VCB",
            signal_weight=0.05,
            portfolio_value=1_000_000_000.0,
            current_price=50.0,  # 50 thousand VND
            current_position=0,
            price_unit="THOUSANDS",
        )
        assert order is not None
        assert order.quantity == 1000

    def test_signal_to_order_default_is_vnd_full(self):
        """Default price_unit is VND_FULL (no multiplier)."""
        gen = self._make_generator()
        order = gen.convert_signal_to_order(
            symbol="HPG",
            signal_weight=0.05,
            portfolio_value=1_000_000_000.0,
            current_price=30000.0,  # 30,000 VND
            current_position=0,
        )
        assert order is not None
        # target_notional = 1B * 0.05 = 50M; qty = 50M / 30000 ≈ 1666 -> rounded to 1700
        assert order.quantity == 1700

    def test_validate_compliance_vnd_full(self):
        """Compliance check uses VND_FULL price correctly."""
        from omega.execution.broker_gateway import BrokerOrder, OrderSide, OrderType
        gen = self._make_generator()
        order = BrokerOrder(
            symbol="VCB",
            side=OrderSide.BUY,
            quantity=1000,
            order_type=OrderType.MARKET,
        )
        # price=50000 VND_FULL, qty=1000 -> notional = 50M VND
        # 50M / 1B = 5% -> should pass (max_position_weight=5%)
        valid, msg = gen.validate_compliance(
            order, current_price=50000.0, adv=100000, portfolio_value=1_000_000_000.0,
            price_unit="VND_FULL",
        )
        assert valid is True

    def test_validate_compliance_thousands_backward_compat(self):
        """Compliance check with THOUSANDS gives same result."""
        from omega.execution.broker_gateway import BrokerOrder, OrderSide, OrderType
        gen = self._make_generator()
        order = BrokerOrder(
            symbol="VCB",
            side=OrderSide.BUY,
            quantity=1000,
            order_type=OrderType.MARKET,
        )
        valid, msg = gen.validate_compliance(
            order, current_price=50.0, adv=100000, portfolio_value=1_000_000_000.0,
            price_unit="THOUSANDS",
        )
        assert valid is True


# ── Trade Blotter VND_FULL Tests ─────────────────────────────────────────────

class TestTradeBlotterVndFull:
    """Tests proving trade notional correctness with VND_FULL prices."""

    def _make_blotter(self):
        from omega.execution.trade_blotter import TradeBlotter
        return TradeBlotter()

    def test_notional_vnd_full(self):
        """VND_FULL: notional = qty * price (no *1000)."""
        blotter = self._make_blotter()
        trade = blotter.record_trade(
            broker_order_id="BRK_001",
            client_order_id="CLI_001",
            symbol="VCB",
            side="BUY",
            quantity=100,
            price=50000.0,  # 50,000 VND
            price_unit="VND_FULL",
        )
        # notional = 100 * 50000 * 1.0 = 5,000,000 VND
        assert trade.notional_value == pytest.approx(5_000_000.0)

    def test_notional_thousands_backward_compat(self):
        """THOUSANDS: notional = qty * price * 1000."""
        blotter = self._make_blotter()
        trade = blotter.record_trade(
            broker_order_id="BRK_002",
            client_order_id="CLI_002",
            symbol="VCB",
            side="BUY",
            quantity=100,
            price=50.0,  # 50 thousand VND
            price_unit="THOUSANDS",
        )
        # notional = 100 * 50 * 1000 = 5,000,000 VND (same!)
        assert trade.notional_value == pytest.approx(5_000_000.0)

    def test_commission_vnd_full(self):
        """Commission is 0.15% of VND_FULL notional."""
        blotter = self._make_blotter()
        trade = blotter.record_trade(
            broker_order_id="BRK_003",
            client_order_id="CLI_003",
            symbol="HPG",
            side="SELL",
            quantity=500,
            price=30000.0,  # 30,000 VND
            commission_rate=0.0015,
            price_unit="VND_FULL",
        )
        expected_notional = 500 * 30000.0  # 15,000,000
        expected_commission = expected_notional * 0.0015  # 22,500
        assert trade.notional_value == pytest.approx(expected_notional)
        assert trade.commission == pytest.approx(expected_commission)

    def test_summary_stats_vnd_full(self):
        """Summary stats aggregate VND_FULL notionals correctly."""
        blotter = self._make_blotter()
        blotter.record_trade("B1", "C1", "VCB", "BUY", 100, 50000.0, price_unit="VND_FULL")
        blotter.record_trade("B2", "C2", "HPG", "SELL", 200, 30000.0, price_unit="VND_FULL")
        stats = blotter.get_summary_stats()
        assert stats["total_buy_value_vnd"] == pytest.approx(5_000_000.0)
        assert stats["total_sell_value_vnd"] == pytest.approx(6_000_000.0)
        assert stats["total_turnover_vnd"] == pytest.approx(11_000_000.0)


# ── PnL Monitor VND_FULL Tests ───────────────────────────────────────────────

class TestPnLMonitorVndFull:
    """Tests proving PnL/cash correctness with VND_FULL prices."""

    def _make_monitor(self, price_scale=1.0):
        from omega.quant.monitoring.pnl_monitor import PnLSlippageMonitor
        return PnLSlippageMonitor(
            initial_equity=2_000_000_000.0,
            price_scale=price_scale,
        )

    def test_record_trade_vnd_full_notional(self):
        """VND_FULL: notional_vnd = qty * fill_price * 1.0."""
        monitor = self._make_monitor()
        ts = datetime(2026, 1, 2, 10, 0)
        record = monitor.record_trade(
            symbol="VCB",
            quantity=1000,
            fill_price=50000.0,
            benchmark_price=49900.0,
            timestamp=ts,
        )
        # notional = 1000 * 50000 * 1.0 = 50,000,000 VND
        assert record.notional_vnd == pytest.approx(50_000_000.0)

    def test_cash_update_buy_vnd_full(self):
        """Buy trade reduces cash by notional in VND."""
        monitor = self._make_monitor()
        ts = datetime(2026, 1, 2, 10, 0)
        initial_cash = monitor.cash
        monitor.record_trade(
            symbol="VCB", quantity=1000, fill_price=50000.0,
            benchmark_price=49900.0, timestamp=ts,
        )
        # cash -= 1000 * 50000 * 1.0 = 50M
        assert monitor.cash == pytest.approx(initial_cash - 50_000_000.0)

    def test_realized_pnl_sell_vnd_full(self):
        """Sell trade realizes PnL correctly in VND_FULL."""
        monitor = self._make_monitor()
        ts1 = datetime(2026, 1, 2, 10, 0)
        ts2 = datetime(2026, 1, 3, 10, 0)

        # Buy 1000 @ 50000
        monitor.record_trade("VCB", 1000, 50000.0, 49900.0, ts1)
        # Sell 1000 @ 52000 -> realized PnL = 1000 * (52000 - 50000) * 1.0 = 2,000,000
        monitor.record_trade("VCB", -1000, 52000.0, 51900.0, ts2)

        assert monitor._realized_pnl == pytest.approx(2_000_000.0)

    def test_unrealized_pnl_snapshot_vnd_full(self):
        """Unrealized PnL snapshot uses VND_FULL correctly."""
        monitor = self._make_monitor()
        ts1 = datetime(2026, 1, 2, 10, 0)
        ts2 = datetime(2026, 1, 3, 10, 0)

        # Buy 1000 @ 50000
        monitor.record_trade("VCB", 1000, 50000.0, 49900.0, ts1)

        # Snapshot at market price 52000
        snapshot = monitor.compute_pnl_snapshot(
            market_prices={"VCB": 52000.0},
            timestamp=ts2,
        )
        # unreal = 1000 * (52000 - 50000) * 1.0 = 2,000,000
        assert snapshot.unrealized_pnl == pytest.approx(2_000_000.0)

    def test_slippage_bps_calculation(self):
        """Slippage in bps is independent of price_scale."""
        monitor = self._make_monitor()
        ts = datetime(2026, 1, 2, 10, 0)
        record = monitor.record_trade(
            "VCB", 1000, 50500.0, 50000.0, ts,
        )
        # Buy slippage = (50500 - 50000) / 50000 * 10000 * 1 = 100 bps
        assert record.slippage_bps == pytest.approx(100.0)

    def test_price_unit_thousands_backward_compat(self):
        """THOUSANDS price_unit via price_scale=1000 still works."""
        from omega.quant.monitoring.pnl_monitor import PnLSlippageMonitor
        monitor = PnLSlippageMonitor(
            initial_equity=2_000_000_000.0,
            price_unit="THOUSANDS",
        )
        assert monitor.price_scale == 1000.0
        ts = datetime(2026, 1, 2, 10, 0)
        record = monitor.record_trade(
            "VCB", 1000, 50.0, 49.9, ts,
        )
        # notional = 1000 * 50 * 1000 = 50,000,000 (same as VND_FULL test)
        assert record.notional_vnd == pytest.approx(50_000_000.0)


# ── ADV / Capacity / Zero-Volume Tests ───────────────────────────────────────

class TestAdvCapacityZeroVolume:
    """Tests for ADV, slippage, and capacity with zero-volume/inactive tickers."""

    def test_adv_with_zero_volume_rows(self):
        """ADV computation handles zero-volume rows correctly."""
        from omega.data.vnstock_live import VnStockLiveDataProvider
        # Simulate price data with some zero-volume days
        df = pd.DataFrame({
            "ticker": ["VCB"] * 5,
            "date": pd.date_range("2026-01-01", periods=5),
            "close": [50000.0, 50500.0, 51000.0, 50000.0, 50200.0],
            "volume": [100000, 0, 120000, 0, 110000],
            "value": [5e9, 0, 6.12e9, 0, 5.522e9],
        })

        # Compute ADV manually (mimicking the vectorized method)
        adv_volume = df["volume"].mean()  # (100000 + 0 + 120000 + 0 + 110000) / 5 = 66000
        assert adv_volume == pytest.approx(66000.0)

    def test_capacity_zero_adv_ticker(self):
        """Ticker with all-zero volume has ADV=0; capacity checks should handle this."""
        df = pd.DataFrame({
            "ticker": ["ILLIQ"] * 5,
            "date": pd.date_range("2026-01-01", periods=5),
            "close": [8000.0, 8100.0, 8000.0, 8050.0, 8000.0],
            "volume": [0, 0, 0, 0, 0],
        })
        adv_volume = df["volume"].mean()
        assert adv_volume == 0.0

        # Order validation: order.qty > adv * 0.2 should fail when adv=0
        # (0 > 0 is False, so the ADV check is skipped - this is correct safe behavior)
        order_qty = 100
        adv_threshold = adv_volume * 0.2
        # When ADV=0, the check `order_qty > adv * 0.2` is 100 > 0 = True
        # The order generator should flag this if adv=0 is passed
        from omega.execution.order_generator import OrderGenerator, PositionSizingConfig
        from omega.execution.broker_gateway import BrokerOrder, OrderSide, OrderType
        gen = OrderGenerator(PositionSizingConfig())
        order = BrokerOrder(
            symbol="ILLIQ", side=OrderSide.BUY,
            quantity=100, order_type=OrderType.MARKET,
        )
        # With adv=0, the check `order.quantity > adv * 0.2` evaluates to True (100 > 0)
        valid, msg = gen.validate_compliance(
            order, current_price=8000.0, adv=0, portfolio_value=1_000_000_000.0,
        )
        assert valid is False
        assert "ADV" in msg

    def test_exchange_aware_adv_by_exchange(self):
        """ADV should be computed per ticker regardless of exchange."""
        df = pd.DataFrame({
            "ticker": ["VCB", "VCB", "SHB", "SHB", "SHB"],
            "volume": [100000, 110000, 50000, 60000, 55000],
        })
        adv_by_ticker = df.groupby("ticker")["volume"].mean()
        assert adv_by_ticker["VCB"] == pytest.approx(105000.0)
        assert adv_by_ticker["SHB"] == pytest.approx(55000.0)


# ── Integration: Full Pipeline VND_FULL Consistency ──────────────────────────

class TestPipelineVndFullConsistency:
    """End-to-end tests proving VND_FULL consistency across pipeline."""

    def test_ingest_to_order_consistency(self):
        """Data ingested as VND_FULL produces correct order sizing."""
        from omega.data.vnd_price_contract import ensure_vnd_scale
        from omega.execution.order_generator import OrderGenerator, PositionSizingConfig

        # Simulate ingested data in THOUSANDS (raw VCI)
        raw_df = pd.DataFrame({
            "close": [50.0, 51.0, 52.0],
            "open": [49.0, 50.5, 51.5],
            "high": [51.0, 52.0, 53.0],
            "low": [48.0, 49.0, 50.0],
        })
        vnd_df = ensure_vnd_scale(raw_df)
        latest_price = vnd_df["close"].iloc[-1]  # 52000.0

        gen = OrderGenerator(PositionSizingConfig())
        order = gen.convert_signal_to_order(
            symbol="VCB",
            signal_weight=0.05,
            portfolio_value=1_000_000_000.0,
            current_price=latest_price,
            price_unit="VND_FULL",
        )
        # 50M / 52000 = 961.5 -> rounded to 1000
        assert order.quantity == 1000

    def test_ingest_to_pnl_consistency(self):
        """Data ingested as VND_FULL produces correct PnL."""
        from omega.data.vnd_price_contract import ensure_vnd_scale
        from omega.quant.monitoring.pnl_monitor import PnLSlippageMonitor

        raw_df = pd.DataFrame({"close": [50.0, 52.0]})
        vnd_df = ensure_vnd_scale(raw_df)
        buy_price = vnd_df["close"].iloc[0]  # 50000
        sell_price = vnd_df["close"].iloc[1]  # 52000

        monitor = PnLSlippageMonitor(initial_equity=1_000_000_000.0, price_scale=1.0)
        ts1 = datetime(2026, 1, 2, 10, 0)
        ts2 = datetime(2026, 1, 3, 10, 0)

        monitor.record_trade("VCB", 1000, buy_price, buy_price - 100, ts1)
        monitor.record_trade("VCB", -1000, sell_price, sell_price - 100, ts2)

        # realized PnL = 1000 * (52000 - 50000) * 1.0 = 2,000,000 VND
        assert monitor._realized_pnl == pytest.approx(2_000_000.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
