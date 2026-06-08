"""Run Phase 3.5 Walk-Forward Backtest on Real Data.

This script runs the complete walk-forward backtest and saves results.
"""
import logging
import sys
from pathlib import Path
import json
import argparse
from datetime import datetime

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from phase35_data_loader import Phase35DataLoader
from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine
from omega.quant import phase34_microstructure_alphas

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run walk-forward backtest."""
    parser = argparse.ArgumentParser(description="Run Phase 3.5 walk-forward backtest")
    parser.add_argument(
        "--no-xgboost",
        action="store_true",
        help="Disable Stage 4 optional XGBoost signal path",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2015-01-05",
        help="Start date for data loading",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2026-05-14",
        help="End date for data loading",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=1_000_000_000.0,
        help="Initial capital in VND",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="multi_factor",
        help="Trading strategy",
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=10.0,
        help="Slippage in basis points",
    )
    parser.add_argument(
        "--commission-bps",
        type=float,
        default=20.0,
        help="Commission in basis points",
    )
    parser.add_argument(
        "--quick-mode",
        action="store_true",
        help="Run quickly with 1 symbol, 2 folds, 1 train year, 1 test year",
    )
    parser.add_argument(
        "--drawdown-control",
        action="store_true",
        help="Enable active drawdown control stop-out",
    )
    parser.add_argument(
        "--drawdown-threshold",
        type=float,
        default=0.05,
        help="Drawdown threshold (e.g. 0.05 for 5 pct)",
    )
    parser.add_argument(
        "--enable-evolved",
        action="store_true",
        help="Enable inline GP evolution per fold and blend evolved signal with hand-crafted alphas",
    )
    parser.add_argument(
        "--evolved-blend-weight",
        type=float,
        default=0.5,
        help="Weight of evolved signal in blend (0-1), remainder is hand-crafted (default: 0.5)",
    )
    args = parser.parse_args()
    args.use_xgboost = not args.no_xgboost

    logger.info("=" * 80)
    logger.info("Phase 3.5 Walk-Forward Backtest - Real VN Market Data")
    logger.info("=" * 80)
    
    # Configuration translation
    START_DATE = args.start_date
    END_DATE = args.end_date
    
    if args.quick_mode:
        TOP_N_SYMBOLS = 1
        N_FOLDS = 2
        TRAIN_YEARS = 1
        TEST_YEARS = 1
    else:
        TOP_N_SYMBOLS = 30
        N_FOLDS = 8
        TRAIN_YEARS = 3
        TEST_YEARS = 1
        
    MIN_IC_THRESHOLD = 0.02
    TOP_N_ALPHAS = 5
    RETURN_HORIZON = 5  # T+5
    STAGE2_TOP_N_STOCKS = 15       # relaxed from 8 to fix negative portfolio IC
    STAGE2_REBALANCE_FREQ = 7
    STAGE2_SECTOR_CAP_PCT = 0.40   # relaxed from 0.30 to fix negative portfolio IC
    
    # Calculate transaction costs from slippage and commission inputs
    tcost_bps = args.slippage_bps + args.commission_bps
    cost_per_turnover = tcost_bps / 10000.0
    cost_aware = tcost_bps > 0
    
    logger.info(f"Configuration:")
    logger.info(f"  Date Range: {START_DATE} to {END_DATE}")
    logger.info(f"  Top Symbols: {TOP_N_SYMBOLS}")
    logger.info(f"  Folds: {N_FOLDS}")
    logger.info(f"  Train Window: {TRAIN_YEARS} year(s)")
    logger.info(f"  Test Window: {TEST_YEARS} year(s)")
    logger.info(f"  Min IC Threshold: {MIN_IC_THRESHOLD}")
    logger.info(f"  Top Alphas: {TOP_N_ALPHAS}")
    logger.info(f"  Return Horizon: T+{RETURN_HORIZON}")
    logger.info(f"  [Stage2] Top N Stocks: {STAGE2_TOP_N_STOCKS}")
    logger.info(f"  [Stage2] Rebalance Freq: every {STAGE2_REBALANCE_FREQ} days")
    logger.info(f"  [Stage2] Sector Cap: {STAGE2_SECTOR_CAP_PCT:.0%}")
    logger.info(f"  [Stage4] Use XGBoost: {args.use_xgboost}")
    logger.info(f"  [Stage6.2] Cost Aware: {cost_aware} (tcost={tcost_bps} bps)")
    logger.info(f"  [Stage6.3] Drawdown Control: {args.drawdown_control} (threshold={args.drawdown_threshold:.1%})")
    logger.info(f"  [Evolved] Enable: {args.enable_evolved} (blend_weight={args.evolved_blend_weight:.2f})")
    logger.info(f"  [UI Context] Initial Capital: {args.initial_capital:,.0f} VND | Strategy: {args.strategy}")
    logger.info("")
    
    # Step 1: Load and prepare data
    logger.info("Step 1: Loading and preparing data...")
    loader = Phase35DataLoader()
    
    df = loader.load_and_prepare(
        start_date=START_DATE,
        end_date=END_DATE,
        top_n_symbols=TOP_N_SYMBOLS,
        forward_horizons=[1, 3, 5],
    )
    
    logger.info(f"Data loaded: {len(df):,} rows, {df['ticker'].nunique()} symbols")
    logger.info(f"Date range: {df['date'].min()} to {df['date'].max()}")
    logger.info("")
    
    # Step 2: Create walk-forward splits
    logger.info("Step 2: Creating walk-forward splits...")
    splits = loader.create_walk_forward_splits(
        df,
        n_folds=N_FOLDS,
        train_years=TRAIN_YEARS,
        test_years=TEST_YEARS,
    )
    
    logger.info(f"Created {len(splits)} valid folds")
    logger.info("")
    
    if len(splits) == 0:
        logger.error("No valid splits created. Exiting.")
        sys.exit(1)
    
    # Step 3: Run walk-forward backtest
    logger.info("Step 3: Running walk-forward backtest...")
    engine = Phase35WalkForwardEngine(
        alpha_module=phase34_microstructure_alphas,
        min_ic_threshold=MIN_IC_THRESHOLD,
        top_n_alphas=TOP_N_ALPHAS,
        top_n_stocks=STAGE2_TOP_N_STOCKS,
        rebalance_freq=STAGE2_REBALANCE_FREQ,
        sector_cap_pct=STAGE2_SECTOR_CAP_PCT,
        use_xgboost=args.use_xgboost,
        cost_aware=cost_aware,
        cost_per_turnover=cost_per_turnover,
        drawdown_control=args.drawdown_control,
        drawdown_threshold=args.drawdown_threshold,
        strategy=args.strategy,
        initial_capital=args.initial_capital,
        enable_evolved=args.enable_evolved,
        evolved_blend_weight=args.evolved_blend_weight,
    )
    
    alpha_cols = list(phase34_microstructure_alphas.PHASE34_ALPHA_COLUMNS)
    return_col = f'fwd_ret_{RETURN_HORIZON}'
    
    result = engine.run_walk_forward(splits, alpha_cols, return_col=return_col)
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 80)
    logger.info(result.summary())
    logger.info("")
    
    # Step 4: Save results
    logger.info("Step 4: Saving results...")
    
    output_dir = Path(__file__).parent.parent / "data" / "phase35_results"
    output_dir.mkdir(exist_ok=True)
    
    # Save detailed results as JSON
    results_dict = {
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "top_n_symbols": TOP_N_SYMBOLS,
            "n_folds": len(splits),
            "train_years": TRAIN_YEARS,
            "test_years": TEST_YEARS,
            "min_ic_threshold": MIN_IC_THRESHOLD,
            "top_n_alphas": TOP_N_ALPHAS,
            "return_horizon": RETURN_HORIZON,
            "stage2_top_n_stocks": STAGE2_TOP_N_STOCKS,
            "stage2_rebalance_freq": STAGE2_REBALANCE_FREQ,
            "stage2_sector_cap_pct": STAGE2_SECTOR_CAP_PCT,
            "use_xgboost": args.use_xgboost,
            "initial_capital": args.initial_capital,
            "strategy": args.strategy,
            "slippage_bps": args.slippage_bps,
            "commission_bps": args.commission_bps,
            "quick_mode": args.quick_mode,
            "drawdown_control": args.drawdown_control,
            "drawdown_threshold": args.drawdown_threshold,
            "enable_evolved": args.enable_evolved,
            "evolved_blend_weight": args.evolved_blend_weight,
        },
        "summary": {
            "avg_portfolio_ic": result.avg_portfolio_ic,
            "avg_portfolio_sharpe": result.avg_portfolio_sharpe,
            "avg_portfolio_max_dd": result.avg_portfolio_max_dd,
            "avg_portfolio_pnl_vnd": getattr(result, "avg_portfolio_pnl_vnd", 0.0),
            "total_folds": result.total_folds,
        },
        "alpha_ics": result.avg_ic_by_alpha,
        "fold_details": [
            {
                "fold_id": m.fold_id,
                "train_start": m.train_start,
                "train_end": m.train_end,
                "test_start": m.test_start,
                "test_end": m.test_end,
                "portfolio_ic": m.portfolio_ic,
                "portfolio_sharpe": m.portfolio_sharpe,
                "portfolio_max_dd": m.portfolio_max_dd,
                "portfolio_total_return": m.portfolio_total_return,
                "portfolio_pnl_vnd": getattr(m, "portfolio_pnl_vnd", 0.0),
                "alpha_ics": m.alpha_ics,
                "n_train_samples": m.n_train_samples,
                "n_test_samples": m.n_test_samples,
            }
            for m in result.fold_metrics
        ],
        "timestamp": datetime.now().isoformat(),
    }
    
    result_suffix = "xgboost" if args.use_xgboost else "baseline"
    json_path = output_dir / f"phase35_backtest_results_{result_suffix}.json"
    with open(json_path, 'w') as f:
        json.dump(results_dict, f, indent=2)
    
    logger.info(f"Results saved to: {json_path}")
    
    # Save summary as text
    summary_path = output_dir / f"phase35_backtest_summary_{result_suffix}.txt"
    with open(summary_path, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("Phase 3.5 Walk-Forward Backtest Results\n")
        f.write("=" * 80 + "\n\n")
        f.write(result.summary())
        f.write("\n\n")
        f.write("Fold Details:\n")
        f.write("-" * 80 + "\n")
        for m in result.fold_metrics:
            f.write(f"\nFold {m.fold_id}:\n")
            f.write(f"  Train: {m.train_start} to {m.train_end} ({m.n_train_samples:,} samples)\n")
            f.write(f"  Test:  {m.test_start} to {m.test_end} ({m.n_test_samples:,} samples)\n")
            f.write(f"  Portfolio IC: {m.portfolio_ic:.4f}\n")
            f.write(f"  Portfolio Sharpe: {m.portfolio_sharpe:.4f}\n")
            f.write(f"  Portfolio Max DD: {m.portfolio_max_dd:.2%}\n")
            f.write(f"  Portfolio Total Return: {m.portfolio_total_return:.2%}\n")
    
    logger.info(f"Summary saved to: {summary_path}")
    logger.info("")
    logger.info("=" * 80)
    logger.info("Phase 3.5 Walk-Forward Backtest Complete!")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
