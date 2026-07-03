from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any
from .types import PipelineFrame, MarketState
from .temporal import TemporalFirewall
from .risk import RiskEngine
from .portfolio import PortfolioOptimizer
from .layer_03_execution_engine import ExecutionEngine
from .state import StateEngine
from .orderbook import OrderBookLevel
from .backtest_liquidation import apply_delisted_liquidations
from omega.core.vn_market_rules import VnMarketRules


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: list[float]
    returns: list[float]
    trades: list[dict]
    metrics: dict[str, float]
    state: MarketState


@dataclass
class BacktestEngine:
    temporal: TemporalFirewall = field(default_factory=TemporalFirewall)
    risk: RiskEngine = field(default_factory=RiskEngine)
    portfolio: PortfolioOptimizer = field(default_factory=PortfolioOptimizer)
    execution: ExecutionEngine = field(default_factory=ExecutionEngine)
    state: StateEngine = field(default_factory=StateEngine)
    data_module: Any = None

    def _row(self, frame: PipelineFrame, i: int) -> dict[str, float]:
        return {k: (v[i] if i < len(v) else 0.0) for k, v in frame.values.items()}

    def _check_and_liquidate_delisted(
        self,
        state: MarketState,
        current_date: str,
        trades: list[dict],
    ) -> MarketState:
        return apply_delisted_liquidations(
            state=state,
            current_date=current_date,
            trades=trades,
            data_module=self.data_module,
        )

    def run(
        self,
        features: PipelineFrame,
        targets: PipelineFrame,
        prices_by_asset: dict[str, list[float]],
        signal_frame: PipelineFrame,
        book_levels_by_asset: dict[str, list[OrderBookLevel]] | None = None,
        *,
        initial_cash: float = 1_000_000.0,
    ) -> BacktestResult:
        if not features.timestamps:
            return BacktestResult([], [], [], {"sharpe": 0.0, "max_drawdown": 0.0}, MarketState(0, initial_cash))
        if not self.temporal.validate(features, targets).ok:
            raise ValueError("temporal validation failed")

        book_levels_by_asset = book_levels_by_asset or {}
        state = MarketState(timestamp=features.timestamps[0], cash=initial_cash)
        equity_curve: list[float] = [initial_cash]
        pnl_returns: list[float] = []
        trades: list[dict] = []
        prev_equity = initial_cash

        asset_names = list(prices_by_asset.keys())
        if not asset_names:
            asset_names = ["DEFAULT"]
            prices_by_asset = {"DEFAULT": [1.0 for _ in features.timestamps]}

        for i, ts in enumerate(features.timestamps):
            state = self._check_and_liquidate_delisted(state, str(ts), trades)
            state = self.state.settle(state, ts)
            row_scores = self._row(signal_frame, i)
            expected = {a: mean(v) if v else 0.0 for a, v in prices_by_asset.items()}
            returns_by_asset = {a: [((b - a_) / a_) if abs(a_) > 1e-12 else 0.0 for a_, b in zip(series, series[1:])] for a, series in prices_by_asset.items()}
            weights, _, _ = self.portfolio.optimize_portfolio(returns_by_asset, expected)
            gross = sum(abs(v) for v in weights.values())
            risk_report = self.risk.approve([r for series in returns_by_asset.values() for r in series], equity_curve, abs(sum(row_scores.values())), gross, weights)
            if risk_report["approved"]:
                for sym in asset_names:
                    signal = row_scores.get(f"{sym}:score", row_scores.get("score", 0.0))
                    side = "BUY" if signal > 0 else "SELL" if signal < 0 else "HOLD"
                    if side == "HOLD":
                        continue
                    price = prices_by_asset[sym][min(i, len(prices_by_asset[sym]) - 1)]
                    ref_idx = max(i - 1, 0)
                    ref_price = prices_by_asset[sym][ref_idx]
                    target_p = {sym: float(signal)}
                    current_p = {sym: float(state.positions.get(sym, 0.0))}

                    filled = False
                    fill_qty = 0.0
                    fill_price = price
                    executed_side = side

                    if hasattr(self.execution, "generate_execution_plan"):
                        plan_full = self.execution.generate_execution_plan(
                            target_portfolio=target_p,
                            current_portfolio=current_p,
                            portfolio_value=state.cash,
                            prices={sym: price},
                            adv_data={sym: 1_000_000},
                            volatility_data={sym: 0.02},
                        )
                        orders_dict = plan_full.get("orders", {})
                        if not isinstance(orders_dict, dict) or sym not in orders_dict:
                            continue

                        fill_results = self.execution.execute(
                            target_portfolio=target_p,
                            current_portfolio=current_p,
                            portfolio_value=state.cash,
                            prices={sym: price},
                            adv_data={sym: 1_000_000},
                            volatility_data={sym: 0.02},
                        )

                        orders_dict = fill_results.get("orders", {})
                        if sym not in orders_dict:
                            continue

                        order_planned = orders_dict[sym]
                        filled = True
                        fill_qty = float(order_planned.get("total_quantity", 0.0))
                        fill_price = price
                        executed_side = order_planned.get("side", side)

                    if filled and fill_qty > 0.0:
                        floor_price, ceiling_price = VnMarketRules.calculate_price_limits(ref_price)
                        if executed_side == "BUY" and price >= ceiling_price:
                            trades.append({"timestamp": ts, "symbol": sym, "side": executed_side, "qty": 0.0, "price": price, "warning": "price_limit_buy_block"})
                            continue
                        if executed_side == "SELL" and price <= floor_price:
                            trades.append({"timestamp": ts, "symbol": sym, "side": executed_side, "qty": 0.0, "price": price, "warning": "price_limit_sell_block"})
                            continue
                        state = self.state.apply_fill(
                            state,
                            sym,
                            fill_qty,
                            fill_price,
                            executed_side,
                        )
                        trades.append(
                            {
                                "timestamp": ts,
                                "symbol": sym,
                                "side": executed_side,
                                "qty": fill_qty,
                                "price": fill_price,
                            }
                        )

            mtm_prices = {sym: prices_by_asset[sym][min(i, len(prices_by_asset[sym]) - 1)] for sym in asset_names}
            equity = self.state.mark_to_market(state, mtm_prices)
            equity_curve.append(equity)
            pnl_returns.append((equity - prev_equity) / prev_equity if abs(prev_equity) > 1e-12 else 0.0)
            prev_equity = equity

        metrics = self._metrics(equity_curve, pnl_returns)
        return BacktestResult(equity_curve, pnl_returns, trades, metrics, state)

    def _metrics(self, equity_curve: list[float], returns: list[float]) -> dict[str, float]:
        risk = RiskEngine()
        avg = mean(returns) if returns else 0.0
        vol = (sum((r - avg) ** 2 for r in returns) / max(1, len(returns) - 1)) ** 0.5 if returns else 0.0
        sharpe = avg / vol if vol > 1e-12 else 0.0
        return {
            "sharpe": sharpe,
            "max_drawdown": risk.max_drawdown(equity_curve),
            "var_95": risk.var_95(returns),
            "cvar_95": risk.cvar_95(returns),
            "final_equity": equity_curve[-1] if equity_curve else 0.0,
        }
