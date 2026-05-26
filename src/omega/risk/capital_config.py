from dataclasses import dataclass

@dataclass(frozen=True)
class CapitalConfig:
    """
    Cấu hình vốn và giới hạn an toàn cho V21_QUANT
    
    Phase 3.2.1: Individual Scale (2B-5B) Configuration
    - max_notional_per_asset_pct: 0.25 (High-Alpha Concentration for 10-15 stocks)
    - liquidity_max_participation_pct: 0.40 (Micro-Scale for Individual Investors)
    - max_drawdown_limit_pct: 0.10 (10% drawdown alert threshold)
    """
    initial_capital: float = 2_000_000_000.0  # 2 tỷ VNĐ
    max_notional_per_asset_pct: float = 0.25  # Phase 3.2.1: 25% vốn cho 1 cổ phiếu (500M)
    max_notional_per_sector_pct: float = 0.35  # Tối đa 35% vốn cho 1 nhóm ngành (700M)
    
    # Risk Limits
    max_drawdown_limit_pct: float = 0.10  # Phase 3.2.1: Cắt lỗ toàn danh mục ở 10% (200M)
    daily_var_limit_pct: float = 0.02     # VaR 95% không quá 2% vốn (40M/ngày)
    liquidity_max_participation_pct: float = 0.40  # Phase 3.2.1: Micro-Scale (40% ADV)

CAPITAL_SETTING = CapitalConfig()
