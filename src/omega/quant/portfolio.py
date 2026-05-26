from __future__ import annotations

from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class PortfolioOptimizer:
    risk_parity_floor: float = 0.0

    def normalize(self, weights: dict[str, float]) -> dict[str, float]:
        total = sum(abs(v) for v in weights.values()) or 1.0
        return {k: v / total for k, v in weights.items()}

    def covariance_matrix(self, returns_by_asset: dict[str, list[float]]) -> dict[str, dict[str, float]]:
        assets = list(returns_by_asset.keys())
        if not assets:
            return {}
        min_len = min((len(v) for v in returns_by_asset.values()), default=0)
        if min_len == 0:
            return {a: {b: 0.0 for b in assets} for a in assets}
        trimmed = {a: v[-min_len:] for a, v in returns_by_asset.items()}
        means = {a: mean(v) for a, v in trimmed.items()}
        cov = {a: {} for a in assets}
        for a in assets:
            for b in assets:
                cov[a][b] = sum((trimmed[a][i] - means[a]) * (trimmed[b][i] - means[b]) for i in range(min_len)) / max(1, min_len - 1)
        return cov

    def _matvec(self, cov: dict[str, dict[str, float]], w: dict[str, float]) -> dict[str, float]:
        return {i: sum(w[j] * cov.get(i, {}).get(j, 0.0) for j in w.keys()) for i in w.keys()}

    def _project_box(self, weights: dict[str, float], single_stock_cap: float) -> dict[str, float]:
        return {k: max(-single_stock_cap, min(single_stock_cap, v)) for k, v in weights.items()}

    def _project_sector_caps(self, weights: dict[str, float], sector_caps: dict[str, float]) -> dict[str, float]:
        out = dict(weights)
        sector_totals: dict[str, float] = {}
        for k, v in out.items():
            sector = k.split(":")[0] if ":" in k else "default"
            sector_totals[sector] = sector_totals.get(sector, 0.0) + abs(v)
        for sector, total in sector_totals.items():
            cap = sector_caps.get(sector, 1.0)
            if total > cap and total > 0:
                factor = cap / total
                for k in list(out.keys()):
                    k_sector = k.split(":")[0] if ":" in k else "default"
                    if k_sector == sector:
                        out[k] *= factor
        return out

    def _project_gross_cap(self, weights: dict[str, float], gross_cap: float = 1.0) -> dict[str, float]:
        gross = sum(abs(v) for v in weights.values())
        if gross <= gross_cap or gross <= 0:
            return weights
        factor = gross_cap / gross
        return {k: v * factor for k, v in weights.items()}

    def apply_constraints(
        self,
        weights: dict[str, float],
        sector_caps: dict[str, float],
        single_stock_cap: float = 0.1,
        gross_cap: float = 1.0,
    ) -> dict[str, float]:
        constrained = self._project_box(weights, single_stock_cap)
        constrained = self._project_sector_caps(constrained, sector_caps)
        constrained = self._project_gross_cap(constrained, gross_cap=gross_cap)
        return constrained

    def objective(
        self,
        w: dict[str, float],
        expected_returns: dict[str, float],
        cov: dict[str, dict[str, float]],
        risk_aversion: float,
        turnover_penalty: float,
        prev_weights: dict[str, float] | None,
        transaction_cost_bps: float,
    ) -> float:
        mu_term = -sum(expected_returns.get(k, 0.0) * v for k, v in w.items())
        cw = self._matvec(cov, w)
        risk_term = 0.5 * risk_aversion * sum(w[k] * cw.get(k, 0.0) for k in w.keys())
        turnover_term = 0.0
        if prev_weights is not None:
            turnover_term = turnover_penalty * sum(abs(w.get(k, 0.0) - prev_weights.get(k, 0.0)) for k in set(w) | set(prev_weights))
        tc_term = transaction_cost_bps / 10000.0 * sum(abs(v) for v in w.values())
        return mu_term + risk_term + turnover_term + tc_term

    def _gradient(
        self,
        w: dict[str, float],
        expected_returns: dict[str, float],
        cov: dict[str, dict[str, float]],
        risk_aversion: float,
        turnover_penalty: float,
        prev_weights: dict[str, float] | None,
        transaction_cost_bps: float,
    ) -> dict[str, float]:
        cw = self._matvec(cov, w)
        grad = {}
        for k in w.keys():
            g = risk_aversion * cw.get(k, 0.0) - expected_returns.get(k, 0.0)
            if prev_weights is not None:
                diff = w[k] - prev_weights.get(k, 0.0)
                g += turnover_penalty * (1.0 if diff >= 0 else -1.0)
            g += transaction_cost_bps / 10000.0 * (1.0 if w[k] >= 0 else -1.0)
            grad[k] = g
        return grad

    def optimize_portfolio(
        self,
        returns_by_asset: dict[str, list[float]],
        expected_returns: dict[str, float],
        sector_caps: dict[str, float] | None = None,
        single_stock_cap: float = 0.1,
        risk_aversion: float = 1.0,
        turnover_penalty: float = 0.0,
        transaction_cost_bps: float = 0.0,
        prev_weights: dict[str, float] | None = None,
        gross_cap: float = 1.0,
        max_iter: int = 300,
        lr: float = 0.05,
        tol: float = 1e-8,
    ) -> tuple[dict[str, float], dict[str, dict[str, float]], str]:
        cov = self.covariance_matrix(returns_by_asset)
        sector_caps = sector_caps or {"default": 1.0}

        assets = list(expected_returns.keys()) or list(returns_by_asset.keys())
        if not assets:
            return {}, cov, "empty"

        w = dict(prev_weights) if prev_weights else {a: 1.0 / len(assets) for a in assets}
        w = {a: w.get(a, 0.0) for a in assets}
        w = self.apply_constraints(w, sector_caps, single_stock_cap=single_stock_cap, gross_cap=gross_cap)

        last_obj = self.objective(w, expected_returns, cov, risk_aversion, turnover_penalty, prev_weights, transaction_cost_bps)
        status = "max_iter"

        for _ in range(max_iter):
            grad = self._gradient(w, expected_returns, cov, risk_aversion, turnover_penalty, prev_weights, transaction_cost_bps)
            candidate = dict(w)
            for a in assets:
                candidate[a] = candidate[a] - lr * grad[a]
            candidate = self.apply_constraints(candidate, sector_caps, single_stock_cap=single_stock_cap, gross_cap=gross_cap)
            obj = self.objective(candidate, expected_returns, cov, risk_aversion, turnover_penalty, prev_weights, transaction_cost_bps)

            if abs(last_obj - obj) < tol:
                w = candidate
                status = "converged"
                break

            if obj <= last_obj:
                w = candidate
                last_obj = obj
            else:
                lr *= 0.5

        return self.normalize(w), cov, status

    def optimize_risk_parity(self, vols: dict[str, float]) -> dict[str, float]:
        inv = {k: (1.0 / max(v, 1e-9)) for k, v in vols.items()}
        return self.normalize(inv)
