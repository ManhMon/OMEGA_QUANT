#!/usr/bin/env python3
"""Generate Markdown report from hybrid regime CPCV comparison JSON."""

from __future__ import annotations

import json
from pathlib import Path


RESULTS_PATH = Path("data/phase35_results/hybrid_regime_cpcv_comparison.json")
REPORT_PATH = Path("data/phase35_results/backtest_report.md")


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _num(value: float) -> str:
    return f"{value:.4f}"


def _summary_row(name: str, stats: dict) -> str:
    return (
        f"| {name} | {_num(stats['mean_sharpe'])} | {_pct(stats['mean_return'])} | "
        f"{_pct(stats['mean_max_dd'])} | {stats['n_folds_completed']} | {stats['n_folds_errored']} |"
    )


def _regime_rows(regimes: dict[str, dict]) -> list[str]:
    rows = []
    for regime_name in ("bull", "sideways", "bear"):
        regime = regimes.get(regime_name, {})
        rows.append(
            f"| {regime_name.title()} | {_num(regime.get('mean_ic', 0.0))} | "
            f"{_num(regime.get('std_ic', 0.0))} | {regime.get('n_folds', 0)} |"
        )
    return rows


def build_report(payload: dict) -> str:
    config = payload["config"]
    aggregated = payload["aggregated"]
    baseline = aggregated["Baseline"]
    hybrid = aggregated["Hybrid"]
    hybrid_diag = hybrid.get("profitability_diag", {})
    hybrid_regimes = hybrid_diag.get("alpha_ic_per_regime", {})
    perf = payload.get("perf", {})

    lines = [
        "# Backtest Report",
        "",
        "## Metadata",
        f"- Gate: `{payload.get('gate', 'n/a')}`",
        f"- Perf gate: `{payload.get('perf_gate', 'n/a')}`",
        f"- Diagnostic gate: `{payload.get('diag_gate', 'n/a')}`",
        "",
        "## Configuration",
        f"- Date range: {config['start_date']} -> {config['end_date']}",
        f"- Capital: {config['capital']:,.0f} VND",
        f"- CPCV: {config['folds']} folds, {config['n_test_folds']} test folds, embargo {config['embargo_pct']:.2%}",
        f"- Label horizon: {config['label_horizon']} days",
        f"- Dynamic universe: {config['dynamic_universe']}",
        f"- Symbols: {config['symbol_count']}",
        f"- Quick mode: {config['quick_mode']}",
        f"- Workers: {config['workers']}",
        "",
        "## Aggregate Comparison",
        "| Strategy | Mean Sharpe | Mean Return | Mean Max DD | Folds Done | Folds Error |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        _summary_row("Baseline", baseline),
        _summary_row("Hybrid", hybrid),
        "",
        "## Hybrid Profitability",
        f"- Mean gross return: {_pct(hybrid_diag.get('mean_gross_return', 0.0))}",
        f"- Median gross return: {_pct(hybrid_diag.get('median_gross_return', 0.0))}",
        f"- Mean total transaction cost: {_pct(hybrid_diag.get('mean_total_tc_pct', 0.0))}",
        f"- Median total transaction cost: {_pct(hybrid_diag.get('median_total_tc_pct', 0.0))}",
        f"- Min/Max gross return: {_pct(hybrid_diag.get('min_gross_return', 0.0))} / {_pct(hybrid_diag.get('max_gross_return', 0.0))}",
        "",
        "## Hybrid Alpha IC By Regime",
        "| Regime | Mean IC | Std IC | Folds |",
        "| --- | ---: | ---: | ---: |",
        *_regime_rows(hybrid_regimes),
        "",
        "## Runtime",
        f"- Total elapsed: {perf.get('total_elapsed_sec', 0.0):.2f} sec ({perf.get('total_elapsed_min', 0.0):.2f} min)",
        "",
        "ponytail: report is summary-only from current JSON schema; add charts/per-fold appendix when consumers need deeper diagnostics.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    payload = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    REPORT_PATH.write_text(build_report(payload), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
