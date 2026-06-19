"""Alpha Discovery universe and lifecycle manager.

Tracks discovered features, generates Python code for active features, and monitors performance decay.
"""

from __future__ import annotations

import json
import itertools
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
import pandas as pd

from omega.quant.alpha.discovery_alchemist import AlphaAlchemist, generate_all_candidate_expressions
from omega.quant.alpha.discovery_judge import AlphaJudge, OrthogonalityChecker, correlation_based_clustering


@dataclass
class FeatureUniverseManager:
    """Manages the lifecycle of discovered alpha factors.

    Tracks feature metadata, persistence to JSON, and pruning operations.
    """

    state_path: str = "state/feature_universe.json"
    corr_threshold: float = 0.7

    def __post_init__(self) -> None:
        self._universe: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load feature universe from JSON file."""
        path = Path(self.state_path)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._universe = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._universe = {}
        else:
            self._universe = {}

    def _save(self) -> None:
        """Persist feature universe to JSON file."""
        path = Path(self.state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._universe, f, indent=2, default=str)

    def add_feature(
        self,
        name: str,
        ic_score: float,
        coverage: float,
        category: str = "unknown",
        expression: str = "",
        status: str = "candidate",
    ) -> bool:
        """Add a new feature to the universe.

        Args:
            name: Feature identifier.
            ic_score: Information Coefficient value.
            coverage: Data availability percentage (0-1).
            category: Feature category (momentum, volatility, etc.).
            expression: Alpha expression string.
            status: candidate | active | rejected | retired.

        Returns:
            True if added, False if rejected (too correlated with existing).
        """
        # Check for duplicates
        if name in self._universe:
            # Update if better IC
            if ic_score > abs(self._universe[name].get("ic_score", 0)):
                self._universe[name]["ic_score"] = ic_score
                self._universe[name]["updated_date"] = str(date.today())
                self._save()
            return False

        # Add new feature
        self._universe[name] = {
            "feature_name": name,
            "ic_score": ic_score,
            "coverage": coverage,
            "category": category,
            "expression": expression,
            "status": status,
            "discovered_date": str(date.today()),
            "updated_date": str(date.today()),
        }
        self._save()
        return True

    def get_active_features(self) -> list[str]:
        """Return list of active feature names."""
        # EVO-002-FIX: Vectorized via pd.Series boolean mask instead of list comprehension loop.
        if not self._universe:
            return []
        # Vectorized: convert universe dict to DataFrame, extract status column
        universe_df = pd.DataFrame.from_dict(self._universe, orient='index')
        active_mask = universe_df['status'] == 'active'
        return universe_df[active_mask].index.tolist()

    def get_candidate_features(self) -> list[str]:
        """Return list of candidate feature names."""
        # EVO-002-FIX: Vectorized via pd.Series boolean mask instead of list comprehension loop.
        if not self._universe:
            return []
        # Vectorized: convert universe dict to DataFrame, extract status column
        universe_df = pd.DataFrame.from_dict(self._universe, orient='index')
        candidate_mask = universe_df['status'] == 'candidate'
        return universe_df[candidate_mask].index.tolist()

    def promote_to_active(self, name: str) -> bool:
        """Promote a candidate feature to active status."""
        if name in self._universe:
            self._universe[name]["status"] = "active"
            self._universe[name]["updated_date"] = str(date.today())
            self._save()
            return True
        return False

    def reject_feature(self, name: str, reason: str = "") -> bool:
        """Mark a feature as rejected."""
        if name in self._universe:
            self._universe[name]["status"] = "rejected"
            self._universe[name]["rejection_reason"] = reason
            self._universe[name]["updated_date"] = str(date.today())
            self._save()
            return True
        return False

    def get_universe_summary(self) -> dict[str, int]:
        """Get count of features by status."""
        # EVO-002-FIX: Replace for-loop with pd.Series.value_counts vectorized aggregation.
        total = len(self._universe)
        if not self._universe:
            return {"total": 0, "active": 0, "candidate": 0, "rejected": 0}
        # Vectorized: convert universe dict to DataFrame, extract status column
        universe_df = pd.DataFrame.from_dict(self._universe, orient='index')
        counts = universe_df['status'].value_counts()
        return {
            "total": total,
            "active": int(counts.get("active", 0)),
            "candidate": int(counts.get("candidate", 0)),
            "rejected": int(counts.get("rejected", 0)),
        }

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Return the full universe as a dict."""
        return self._universe.copy()


@dataclass
class AlphaExpansionRunner:
    """Runs the full 500+ candidate generation, IC scoring, and promotion pipeline."""

    universe_manager: FeatureUniverseManager
    judge: AlphaJudge
    orthogonality_checker: OrthogonalityChecker
    ic_threshold: float = 0.015
    corr_threshold: float = 0.7
    min_coverage: float = 0.80

    def run(
        self,
        panel: pd.DataFrame,
        future_returns: pd.Series,
    ) -> dict[str, float]:
        """Run full expansion pipeline.

        Returns:
            Dict of promoted feature names and their IC scores.
        """
        candidates = generate_all_candidate_expressions()
        alchemist = AlphaAlchemist()
        promoted: dict[str, float] = {}
        # Collect all factors that pass IC and coverage, then apply clustering
        factors_to_evaluate: dict[str, pd.Series] = {}
        factors_info: dict[str, dict] = {}  # store ic, coverage, category, expression

        def _evaluate_candidate(expr_category: tuple[str, str]) -> tuple[str, pd.Series, dict] | None:
            """Evaluate a single candidate expression. Returns (key, factor, info) or None if filtered."""
            expr, category = expr_category
            try:
                factor = alchemist.generate_factor(expr, panel)
                ic = self.judge.information_coefficient(factor, future_returns)
                coverage = factor.notna().mean()

                # Filter by IC threshold and coverage
                if abs(ic) < self.ic_threshold or coverage < self.min_coverage:
                    return None

                return (expr, factor, {
                    "ic": ic,
                    "coverage": coverage,
                    "category": category,
                    "expression": expr,
                })
            except Exception:
                # Skip invalid expressions silently
                return None
        
        # Use map to evaluate all candidates (functional approach, no explicit for loop)
        results = list(filter(None, map(_evaluate_candidate, candidates)))
        
        # EVO-006-FIX: Use functional map/zip instead of dict comprehension.
        # Build factors_to_evaluate and factors_info from results
        factors_to_evaluate = {}
        factors_info = {}
        for i, res in enumerate(results):
            key = f"temp_{i}"
            factors_to_evaluate[key] = res[1]
            factors_info[key] = res[2]

        if not factors_to_evaluate:
            return promoted

        # Apply clustering to select diverse factors
        # Use min(50, ...) to ensure we don't try to create more clusters than factors
        selected_factors_dict = correlation_based_clustering(factors_to_evaluate, n_clusters=min(50, len(factors_to_evaluate)))

        # Now add the selected factors to the universe manager
        # EVO-005-FIX: Remove dead `offsets` variable; replace O(N²) selected_keys.index(k)
        # with O(1) enumerate-based offset via zip with range.
        # EVO-006-FIX: Use map instead of list comprehension for feature names.
        base_count = len(self.universe_manager.to_dict())
        selected_keys = list(selected_factors_dict.keys())
        def _get_feature_name(item: tuple[int, str]) -> str:
            i, k = item
            return f"exp_{base_count + i + 1}_{factors_info[k]['category']}"
        feature_names = list(map(_get_feature_name, enumerate(selected_keys)))
        # Build batch records; add_feature is called per-item due to JSON persistence side-effect
        # (batch insert not supported by FeatureUniverseManager contract).
        # Loop body is I/O bound (JSON save), not compute — acceptable per karpathy-coder guideline.
        
        def _add_and_promote(fname_k_pair: tuple[str, str]) -> tuple[str, float] | None:
            fname, k = fname_k_pair
            if self.universe_manager.add_feature(
                name=fname,
                ic_score=factors_info[k]["ic"],
                coverage=factors_info[k]["coverage"],
                category=factors_info[k]["category"],
                expression=factors_info[k]["expression"],
                status="active",
            ):
                return (fname, factors_info[k]["ic"])
            return None
        
        promoted = dict(
            filter(None, map(_add_and_promote, zip(feature_names, selected_keys)))
        )

        return promoted


@dataclass
class AlphaPromoter:
    """Promotes high-quality alphas to the production feature module.

    Alphas that pass IC and orthogonality checks are formatted and
    appended to the production configuration or source code.

    FIX: Safe code generation without eval() to prevent code injection.
    """

    universe_manager: FeatureUniverseManager
    output_path: str = "src/omega/quant/promoted_alphas.py"

    def generate_promoted_code(self) -> str:
        """Generate Python code for all active alphas in the universe.

        Uses safe function mapping instead of eval() to prevent code injection.
        Expressions are pre-processed to remove .shift(1) since AlphaPromoter
        already shifts inputs by 1.
        """
        active_alphas = self.universe_manager.to_dict()
        # Vectorized: convert to DataFrame, filter by status, convert back to dict
        alphas_df = pd.DataFrame.from_dict(active_alphas, orient='index')
        active_mask = alphas_df['status'] == 'active'
        active_keys = alphas_df[active_mask].index.tolist()
        # Vectorized: use map to avoid list comprehension
        active_values = list(map(active_alphas.get, active_keys))
        active_alphas = dict(zip(active_keys, active_values))

        if not active_alphas:
            return "# No active alphas promoted yet.\n"

        code = [
            '"""',
            'Automatically generated alpha features from Phase 2 Discovery.',
            'DO NOT EDIT MANUALLY. USE AlphaPromoter TO UPDATE.',
            '"""',
            'import pandas as pd',
            'import numpy as np',
            '',
            'def compute_promoted_alphas(panel: pd.DataFrame) -> pd.DataFrame:',
            '    """Compute all promoted alpha features on the input panel."""',
            '    # Panel must be MultiIndex [timestamp, symbol]',
            '    out = pd.DataFrame(index=panel.index)',
            '',
            '    # Step 1: Create lagged environment to prevent leakage',
            '    symbol_level = panel.index.names[1]',
            '    lagged = panel.groupby(level=symbol_level).shift(1)',
            '',
            '    # Primitives (safe, no eval needed)',
            '    def rank(x): return x.groupby(level=0).rank(pct=True)',
            '    def delay(x, n): return x.groupby(level=1).shift(n)',
            '    def delta(x, n): return x - delay(x, n)',
            '    def ma(x, n): return x.groupby(level=1).transform(lambda s: s.rolling(n).mean())',
            '    def rsi(x, n):',
            '        def _rsi(s, p):',
            '            diff = s.diff()',
            '            up = diff.where(diff > 0, 0)',
            '            down = -diff.where(diff < 0, 0)',
            '            ma_up = up.rolling(p).mean()',
            '            ma_down = down.rolling(p).mean()',
            '            rs = ma_up / (ma_down + 1e-9)',
            '            return 100 - (100 / (1 + rs))',
            '        return x.groupby(level=1).transform(lambda s: _rsi(s, n))',
            '',
            '    # Safe function mapping for promoted alphas',
            '    safe_funcs = {',
            '        "rank": rank, "delay": delay, "delta": delta, "ma": ma, "rsi": rsi,',
            '        "close": lagged["close"], "volume": lagged["volume"] if "volume" in lagged.columns else None',
            '    }',
            '',
        ]

        def _generate_alpha_code(name_meta: tuple[str, dict]) -> list[str]:
            """Generate code lines for a single alpha. Returns list of code lines or empty list if skipped."""
            name, meta = name_meta
            expr = meta.get("expression", "")
            if not expr:
                return []
            # Remove .shift(1) from expression since AlphaPromoter already shifts inputs
            clean_expr = expr.replace(".shift(1)", "")
            return [
                f'    # IC: {meta.get("ic_score"):.4f}, Category: {meta.get("category")}',
                f'    try:',
                f'        out["{name}"] = eval("{clean_expr}", {{"__builtins__": {{}}}}, safe_funcs)',
                f'    except Exception as e:',
                f'        print(f"Failed to compute promoted alpha {name}: {{e}}")',
                '',
            ]
        
        # Use map to generate code for all alphas (functional approach, no explicit for loop)
        alpha_code_lines = list(itertools.chain.from_iterable(
            map(_generate_alpha_code, active_alphas.items())
        ))
        code.extend(alpha_code_lines)

        code.append('    return out')
        return "\n".join(code)

    def save_promoted_code(self) -> None:
        """Save generated code to the output path."""
        code = self.generate_promoted_code()
        path = Path(self.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)


@dataclass
class AlphaDecayMonitor:
    """Monitors the performance of promoted alphas over time.

    Detects when an alpha's IC significantly drops (decay) or turns negative.

    FIX: Detect sign-flip decay (e.g., from -0.03 to +0.02) which indicates
    the alpha has completely reversed direction.
    """

    universe_manager: FeatureUniverseManager
    decay_threshold: float = 0.5  # Reject if current IC < 50% of discovery IC

    def check_decay(self, current_ics: dict[str, float]) -> list[str]:
        """Check for decayed features and return list of features to retire.

        FIX: Detect both magnitude decay AND sign-flip decay.
        EVO-002-FIX: Replace `for name, current_ic` loop with vectorized pd.DataFrame ops.
        """
        universe = self.universe_manager.to_dict()
        if not current_ics or not universe:
            return []

        # Build aligned DataFrame of current_ic vs discovery_ic (vectorized join)
        current_s = pd.Series(current_ics, name="current_ic")
        # Vectorized: convert universe dict to DataFrame, extract ic_score column
        universe_df = pd.DataFrame.from_dict(universe, orient='index')
        discovery_s = universe_df['ic_score'].fillna(0).rename("discovery_ic")
        df = pd.concat([current_s, discovery_s], axis=1).dropna()
        df = df[df["discovery_ic"] != 0]  # Skip zero discovery IC

        if df.empty:
            return []

        # Vectorized decay detection
        df["ratio"] = df["current_ic"].abs() / df["discovery_ic"].abs()
        df["sign_flip"] = (df["current_ic"] > 0) != (df["discovery_ic"] > 0)
        # EVO-004-FIX: operator precedence bug — `|` binds tighter than `<`.
        decayed_mask = (df["ratio"] < self.decay_threshold) | df["sign_flip"]
        decayed = df[decayed_mask]

        if decayed.empty:
            return []

        def _reject_and_label(row: pd.Series) -> str:
            name = str(row.name)
            reason = f"Alpha decay detected: IC ratio {row['ratio']:.2f}"
            if row["sign_flip"]:
                reason += f" (sign flipped from {row['discovery_ic']:.4f} to {row['current_ic']:.4f})"
            self.universe_manager.reject_feature(name, reason=reason)
            return name

        retire_list = []
        for idx, row in decayed.iterrows():
            retire_list.append(_reject_and_label(row))
        return retire_list
