#!/usr/bin/env python
"""run_signal_sanitizer.py - Clean and sanitize signals before portfolio construction.

Wires SignalSanitizer + ConstraintSolver from omega.quant packages.
PIT-safe: No look-ahead bias. All operations are cross-sectional at time T.
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime, date

# Wire packages/quant/src into path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'packages', 'quant', 'src'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Import SignalSanitizer ---
SignalSanitizer = None
try:
    from omega.quant.signal_sanitizer import SignalSanitizer
    logger.info('SignalSanitizer imported successfully')
except ImportError as e:
    logger.warning(f'SignalSanitizer not available: {e}. Using manual sanitization.')

# --- Import ConstraintSolver ---
ConstraintSolver = None
try:
    from omega.quant.constraint_solver import ConstraintSolver
    logger.info('ConstraintSolver imported successfully')
except ImportError as e:
    logger.warning(f'ConstraintSolver not available: {e}. Using manual constraints.')


def winsorize_signals(signals: dict, lower_pct: float = 0.01, upper_pct: float = 0.99) -> dict:
    """Winsorize signal values at lower/upper percentiles cross-sectionally."""
    values = [v for v in signals.values() if v is not None and not (isinstance(v, float) and v != v)]
    if not values:
        return signals

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    lower_bound = sorted_vals[max(0, int(n * lower_pct))]
    upper_bound = sorted_vals[min(n - 1, int(n * upper_pct))]

    result = {}
    for ticker, val in signals.items():
        if val is None or (isinstance(val, float) and val != val):
            result[ticker] = 0.0
        else:
            result[ticker] = max(lower_bound, min(upper_bound, val))
    return result


def zscore_normalize(signals: dict) -> dict:
    """Z-score normalize signals cross-sectionally."""
    values = [v for v in signals.values() if v is not None]
    if len(values) < 2:
        return signals

    mean_val = sum(values) / len(values)
    variance = sum((v - mean_val) ** 2 for v in values) / len(values)
    std_val = variance ** 0.5

    if std_val < 1e-10:
        return {k: 0.0 for k in signals}

    return {k: (v - mean_val) / std_val if v is not None else 0.0 for k, v in signals.items()}


def fill_nan(signals: dict) -> dict:
    """Replace NaN/None values with 0."""
    result = {}
    for ticker, val in signals.items():
        if val is None or (isinstance(val, float) and val != val):
            result[ticker] = 0.0
        else:
            result[ticker] = val
    return result


def apply_vn_constraints(signals: dict, adv_data: dict = None) -> dict:
    """Apply VN market constraints manually.

    Constraints:
      Board lot: 100 shares minimum (filter signals too weak to trade)
      Max concentration: 25% per stock
      ADV constraint: max 40% daily volume
    """
    if not signals:
        return signals

    # Max concentration: cap any single signal at 25% of total absolute signal
    total_abs = sum(abs(v) for v in signals.values())
    max_concentration = 0.25

    constrained = {}
    for ticker, val in signals.items():
        if total_abs > 0:
            weight = abs(val) / total_abs
            if weight > max_concentration:
                # Scale down to max concentration
                if abs(val) > 0:
                    val = val * (max_concentration * total_abs / abs(val))
        constrained[ticker] = val

    # ADV constraint: if adv_data available, cap at 40% daily volume
    if adv_data:
        max_adv_pct = 0.40
        for ticker in list(constrained.keys()):
            if ticker in adv_data:
                adv = adv_data[ticker]
                if adv > 0 and abs(constrained[ticker]) > adv * max_adv_pct:
                    sign = 1 if constrained[ticker] >= 0 else -1
                    constrained[ticker] = sign * adv * max_adv_pct
                    logger.info(f'{ticker}: ADV-capped to {constrained[ticker]:.4f}')

    # Board lot filter: remove signals with absolute value too small
    # (proxy: if normalized signal < 0.01, unlikely to fill a board lot)
    min_signal_threshold = 0.01
    constrained = {k: v for k, v in constrained.items() if abs(v) >= min_signal_threshold}

    return constrained


def run_sanitizer(date_str: str, signals_file: str) -> int:
    """Main sanitization pipeline."""
    logger.info(f'=== Signal Sanitizer Started for {date_str} ===')

    # Load signals
    if not os.path.exists(signals_file):
        logger.error(f'Signals file not found: {signals_file}')
        return 1

    with open(signals_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    # Extract signals dict (handle nested formats)
    if isinstance(raw_data, dict) and 'signals' in raw_data:
        signals = raw_data['signals']
    elif isinstance(raw_data, dict):
        signals = raw_data
    else:
        logger.error('Invalid signals format: expected dict or {signals: dict}')
        return 1

    num_before = len(signals)
    logger.info(f'Loaded {num_before} raw signals')

    # --- Step 1: Signal Sanitization ---
    logger.info('Step 1: Signal Sanitization')

    if SignalSanitizer is not None and hasattr(SignalSanitizer, 'sanitize'):
        logger.info('Using SignalSanitizer module')
        sanitizer = SignalSanitizer()
        signals = sanitizer.sanitize(signals)
    else:
        # Manual sanitization pipeline
        logger.info('Using manual sanitization (winsorize -> zscore -> fill_nan)')
        signals = winsorize_signals(signals, lower_pct=0.01, upper_pct=0.99)
        signals = zscore_normalize(signals)
        signals = fill_nan(signals)

    logger.info(f'After sanitization: {len(signals)} signals')

    # --- Step 2: VN Constraint Solving ---
    logger.info('Step 2: VN Constraint Solving')

    # Load ADV data if available
    adv_file = os.path.join(os.path.dirname(signals_file), f'{date_str}_adv.json')
    adv_data = None
    if os.path.exists(adv_file):
        with open(adv_file, 'r', encoding='utf-8') as f:
            adv_data = json.load(f)
        logger.info(f'Loaded ADV data from {adv_file}')

    constraints_applied = []

    if ConstraintSolver is not None and hasattr(ConstraintSolver, 'solve'):
        logger.info('Using ConstraintSolver module')
        solver = ConstraintSolver()
        constraints_config = {
            'board_lot': 100,
            'max_concentration': 0.25,
            'max_adv_pct': 0.40,
        }
        signals = solver.solve(signals, constraints=constraints_config, adv_data=adv_data)
        constraints_applied = ['board_lot=100', 'max_concentration=25%', 'max_adv_pct=40%']
    else:
        logger.info('Using manual constraint application')
        signals = apply_vn_constraints(signals, adv_data=adv_data)
        constraints_applied = ['board_lot=100 (filter)', 'max_concentration=25%', 'max_adv_pct=40%']

    num_after = len(signals)
    logger.info(f'After constraints: {num_after} signals')

    # --- Save sanitized output ---
    output_dir = os.path.dirname(signals_file)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f'{date_str}_sanitized.json')

    output_payload = {
        'date': date_str,
        'sanitized_at': datetime.utcnow().isoformat() + 'Z',
        'num_signals_before': num_before,
        'num_signals_after': num_after,
        'constraints_applied': constraints_applied,
        'signals': signals,
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_payload, f, indent=2, ensure_ascii=False)

    logger.info(f'Sanitized signals saved to: {output_file}')

    # --- Summary ---
    print()
    print('=' * 50)
    print(f'  Signal Sanitizer Summary ({date_str})')
    print('=' * 50)
    print(f'  Signals before:      {num_before}')
    print(f'  Signals after:       {num_after}')
    print(f'  Removed:             {num_before - num_after}')
    print(f'  Constraints applied: {", ".join(constraints_applied)}')
    print(f'  Output:              {output_file}')
    print('=' * 50)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Clean and sanitize signals before portfolio construction.'
    )
    parser.add_argument(
        '--date',
        type=str,
        default=date.today().strftime('%Y-%m-%d'),
        help='Target date (YYYY-MM-DD). Default: today.'
    )
    parser.add_argument(
        '--signals-file',
        type=str,
        default=None,
        help='Path to signals JSON. Default: .ly_state/shadow_live/{date}.json'
    )
    args = parser.parse_args()

    if args.signals_file is None:
        workspace_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
        args.signals_file = os.path.join(
            workspace_root, '.ly_state', 'shadow_live', f'{args.date}.json'
        )

    sys.exit(run_sanitizer(args.date, args.signals_file))


if __name__ == '__main__':
    main()
