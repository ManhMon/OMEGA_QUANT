#!/usr/bin/env python3
"""
Performance Profiling Script for OMEGA_QUANT Pipeline
Backend Engineer (Role 9) - Phase 10

Profiles pipeline performance with 100+ tickers to identify bottlenecks.
Generates detailed performance report with recommendations.

Usage:
    python scripts/profile_performance.py --tickers 100 --days 252
    python scripts/profile_performance.py --profile-memory
"""

from __future__ import annotations

import argparse
import cProfile
import io
import logging
import pstats
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

import numpy as np
import pandas as pd

# Add packages to path
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

from omega.core.pipeline import OmegaPipeline, PipelineConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("PerformanceProfiler")


class PerformanceProfiler:
    """
    Performance profiler for OMEGA_QUANT pipeline.
    
    Measures:
    - Total execution time
    - Per-component timing (data, features, alpha, risk, execution)
    - Memory usage
    - Bottleneck identification
    """
    
    def __init__(self, num_tickers: int = 100, num_days: int = 252):
        self.num_tickers = num_tickers
        self.num_days = num_days
        self.results: Dict[str, Any] = {}
        
    def generate_test_universe(self) -> List[str]:
        """Generate test universe of tickers."""
        # Generate synthetic ticker names
        tickers = [f"TICK{i:04d}" for i in range(self.num_tickers)]
        logger.info(f"Generated test universe: {len(tickers)} tickers")
        return tickers
    
    def profile_pipeline(self, enable_cprofile: bool = False) -> Dict[str, Any]:
        """
        Profile the full pipeline execution.
        
        Args:
            enable_cprofile: Enable cProfile for detailed profiling
            
        Returns:
            Performance metrics dictionary
        """
        logger.info(f"Starting performance profiling: {self.num_tickers} tickers, {self.num_days} days")
        
        # Generate test universe
        universe = self.generate_test_universe()
        
        # Configure pipeline
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.num_days)
        
        config = PipelineConfig(
            universe=universe,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            as_of_time=end_date,
            rebalance_frequency="daily"
        )
        
        # Profile execution
        if enable_cprofile:
            profiler = cProfile.Profile()
            profiler.enable()
        
        start_time = time.time()
        
        try:
            pipeline = OmegaPipeline(config)
            result = pipeline.run()
            
            end_time = time.time()
            total_time = end_time - start_time
            
            if enable_cprofile:
                profiler.disable()
                
                # Get profiling stats
                s = io.StringIO()
                ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
                ps.print_stats(30)  # Top 30 functions
                profile_output = s.getvalue()
            else:
                profile_output = None
            
            # Collect metrics
            metrics = {
                "success": result.success,
                "total_time_seconds": total_time,
                "num_tickers": self.num_tickers,
                "num_days": self.num_days,
                "throughput_tickers_per_second": self.num_tickers / total_time if total_time > 0 else 0,
                "time_per_ticker_ms": (total_time * 1000) / self.num_tickers if self.num_tickers > 0 else 0,
                "profile_output": profile_output,
                "timestamp": datetime.now().isoformat()
            }
            
            # Add pipeline-specific metrics if available
            if result.metrics:
                metrics["pipeline_metrics"] = result.metrics
            
            # Performance assessment
            if total_time < 10:
                metrics["performance_grade"] = "EXCELLENT"
                metrics["recommendation"] = "Pipeline meets production requirements (<10s for 100 tickers)"
            elif total_time < 30:
                metrics["performance_grade"] = "GOOD"
                metrics["recommendation"] = "Pipeline acceptable but could be optimized"
            elif total_time < 60:
                metrics["performance_grade"] = "FAIR"
                metrics["recommendation"] = "Pipeline needs optimization for production use"
            else:
                metrics["performance_grade"] = "POOR"
                metrics["recommendation"] = "Pipeline requires significant optimization"
            
            logger.info(f"Profiling complete: {total_time:.2f}s total, Grade: {metrics['performance_grade']}")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Profiling failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "total_time_seconds": time.time() - start_time,
                "timestamp": datetime.now().isoformat()
            }
    
    def profile_component(self, component_name: str, component_func, *args, **kwargs) -> Dict[str, Any]:
        """
        Profile a single pipeline component.
        
        Args:
            component_name: Name of the component
            component_func: Function to profile
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            Component performance metrics
        """
        logger.info(f"Profiling component: {component_name}")
        
        start_time = time.time()
        
        try:
            result = component_func(*args, **kwargs)
            end_time = time.time()
            
            metrics = {
                "component": component_name,
                "success": True,
                "time_seconds": end_time - start_time,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Component {component_name}: {metrics['time_seconds']:.2f}s")
            return metrics
            
        except Exception as e:
            logger.error(f"Component {component_name} failed: {e}", exc_info=True)
            return {
                "component": component_name,
                "success": False,
                "error": str(e),
                "time_seconds": time.time() - start_time,
                "timestamp": datetime.now().isoformat()
            }
    
    def generate_report(self, metrics: Dict[str, Any], output_path: Path) -> None:
        """
        Generate performance report.
        
        Args:
            metrics: Performance metrics
            output_path: Path to save report
        """
        logger.info(f"Generating performance report: {output_path}")
        
        report_lines = [
            "=" * 80,
            "OMEGA_QUANT PERFORMANCE PROFILING REPORT",
            "=" * 80,
            "",
            f"Timestamp: {metrics.get('timestamp', 'N/A')}",
            f"Configuration: {metrics.get('num_tickers', 'N/A')} tickers, {metrics.get('num_days', 'N/A')} days",
            "",
            "=" * 80,
            "PERFORMANCE METRICS",
            "=" * 80,
            "",
            f"Total Execution Time: {metrics.get('total_time_seconds', 0):.2f} seconds",
            f"Throughput: {metrics.get('throughput_tickers_per_second', 0):.2f} tickers/second",
            f"Time per Ticker: {metrics.get('time_per_ticker_ms', 0):.2f} ms",
            "",
            f"Performance Grade: {metrics.get('performance_grade', 'N/A')}",
            f"Recommendation: {metrics.get('recommendation', 'N/A')}",
            "",
        ]
        
        # Add pipeline metrics if available
        if "pipeline_metrics" in metrics:
            report_lines.extend([
                "=" * 80,
                "PIPELINE METRICS",
                "=" * 80,
                ""
            ])
            for key, value in metrics["pipeline_metrics"].items():
                report_lines.append(f"{key}: {value}")
            report_lines.append("")
        
        # Add profiling output if available
        if metrics.get("profile_output"):
            report_lines.extend([
                "=" * 80,
                "DETAILED PROFILING (Top 30 Functions)",
                "=" * 80,
                "",
                metrics["profile_output"],
                ""
            ])
        
        # Add bottleneck analysis
        report_lines.extend([
            "=" * 80,
            "BOTTLENECK ANALYSIS",
            "=" * 80,
            "",
            "Common bottlenecks to check:",
            "1. Data Loading: Check if data loader is vectorized",
            "2. Feature Computation: Ensure no iterrows() or loops over tickers",
            "3. Alpha Generation: Verify cross-sectional operations are vectorized",
            "4. Risk Controls: Check if position limits use vectorized operations",
            "5. Execution Simulation: Ensure batch processing, not row-by-row",
            "",
            "Optimization recommendations:",
            "- Use pandas groupby().transform() for per-ticker operations",
            "- Use pandas merge() instead of iterative lookups",
            "- Cache intermediate results when possible",
            "- Use numpy vectorized operations instead of apply()",
            "- Profile with cProfile to identify specific slow functions",
            "",
        ])
        
        report_lines.append("=" * 80)
        
        # Write report
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write("\n".join(report_lines))
        
        logger.info(f"Report saved to: {output_path}")


def main():
    """Main entry point for performance profiling."""
    parser = argparse.ArgumentParser(
        description="OMEGA_QUANT Performance Profiler"
    )
    parser.add_argument(
        "--tickers",
        type=int,
        default=100,
        help="Number of tickers to test (default: 100)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=252,
        help="Number of days to test (default: 252)"
    )
    parser.add_argument(
        "--profile-detailed",
        action="store_true",
        help="Enable detailed cProfile profiling"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="artifacts/performance_report.txt",
        help="Output path for performance report"
    )
    
    args = parser.parse_args()
    
    # Create profiler
    profiler = PerformanceProfiler(
        num_tickers=args.tickers,
        num_days=args.days
    )
    
    # Run profiling
    metrics = profiler.profile_pipeline(enable_cprofile=args.profile_detailed)
    
    # Generate report
    output_path = Path(args.output)
    profiler.generate_report(metrics, output_path)
    
    # Print summary
    print("\n" + "=" * 80)
    print("PERFORMANCE PROFILING SUMMARY")
    print("=" * 80)
    print(f"Total Time: {metrics.get('total_time_seconds', 0):.2f}s")
    print(f"Grade: {metrics.get('performance_grade', 'N/A')}")
    print(f"Report: {output_path}")
    print("=" * 80)
    
    # Exit with appropriate code
    if metrics.get("success", False):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
