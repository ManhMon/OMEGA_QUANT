"""
VCI Data Integration Module - Mock Implementation
Layer 01: Core Intelligence
Task 2.1.3: VCI Data Integration (Mock Data)

Wires mock VCI real-time feed into the feature pruning pipeline.
Ensures data validation (missing data < 5%) and latency monitoring (< 100ms).

Version: v21.0
Date: 2026-05-04
"""

import time
import hashlib
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')


@dataclass
class VCIDataQualityMetrics:
    """Data quality metrics for VCI feed"""
    total_records: int = 0
    missing_records: int = 0
    missing_rate: float = 0.0
    latency_ms: float = 0.0
    max_missing_rate: float = 0.05
    max_latency_ms: float = 100.0
    timestamp: datetime = field(default_factory=datetime.now)
    validation_passed: bool = False
    
    def __post_init__(self):
        self.total_records = int(self.total_records)
        self.missing_records = int(self.missing_records)
        if self.total_records > 0:
            self.missing_rate = float(self.missing_records / self.total_records)
            self.validation_passed = bool(
                self.missing_rate < self.max_missing_rate and
                self.latency_ms < self.max_latency_ms
            )


@dataclass
class VCIIntegrationConfig:
    """Configuration for VCI integration"""
    max_missing_rate: float = 0.05  # 5% threshold
    max_latency_ms: float = 100.0  # 100ms threshold
    mock_symbols: List[str] = field(default_factory=lambda: [
        'VCB', 'HPG', 'FPT', 'VHM', 'VIC', 'GAS', 'MSN', 'MWG', 'TCB', 'VNM'
    ])
    mock_features_count: int = 50  # Number of mock features to generate
    mock_lookback_days: int = 252  # 1 year of mock data
    as_of_date: Optional[datetime] = None  # Fixed end date for reproducible tests
    enable_latency_monitoring: bool = True
    enable_data_validation: bool = True


class VCIDataIntegration:
    """
    VCI Data Integration with Mock Implementation
    
    Provides mock VCI real-time feed for feature pruning pipeline.
    Includes data validation and latency monitoring.
    
    Integration Points for Real VCI Feed:
    1. Replace `fetch_mock_vci_data()` with real VCI API call
    2. Replace `generate_mock_features()` with real feature computation
    3. Connect to vnstock_vci_datasource.py for production data
    4. Wire into live_ingestor.py for real-time streaming
    """
    
    def __init__(self, config: Optional[VCIIntegrationConfig] = None):
        self.config = config or VCIIntegrationConfig()
        self.quality_history: List[VCIDataQualityMetrics] = []
        
    def fetch_mock_vci_data(
        self,
        symbols: Optional[List[str]] = None,
        lookback_days: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch mock VCI data (OHLCV format).
        
        INTEGRATION POINT 1: Replace with real VCI API
        Real implementation should call:
            from vnstock_vci_datasource import VnstockVCIDataSource
            datasource = VnstockVCIDataSource()
            data = datasource.get_ohlcv(symbols, days=lookback_days)
        
        Args:
            symbols: List of stock symbols (default: config.mock_symbols)
            lookback_days: Number of days to fetch (default: config.mock_lookback_days)
            
        Returns:
            DataFrame with MultiIndex (date, symbol) and columns [open, high, low, close, volume]
        """
        start_time = time.perf_counter()
        
        symbols = self.config.mock_symbols if symbols is None else symbols
        lookback_days = self.config.mock_lookback_days if lookback_days is None else lookback_days
        
        # Generate mock OHLCV data
        as_of_date = self.config.as_of_date or datetime.now()
        dates = pd.date_range(
            end=as_of_date,
            periods=lookback_days,
            freq='D'
        )
        
        data_records = []
        for symbol in symbols:
            # Generate realistic price series with trend + noise
            seed = int.from_bytes(hashlib.sha256(symbol.encode("utf-8")).digest()[:8], "little")
            rng = np.random.default_rng(seed)
            base_price = rng.uniform(10000, 100000)  # VND prices
            trend = np.linspace(0, 0.2, lookback_days)
            noise = rng.standard_normal(lookback_days) * 0.02
            
            close_prices = base_price * (1 + trend + noise)
            
            for i, date in enumerate(dates):
                close = close_prices[i]
                open_price = close * (1 + rng.uniform(-0.01, 0.01))
                high = max(open_price, close) * (1 + rng.uniform(0, 0.02))
                low = min(open_price, close) * (1 - rng.uniform(0, 0.02))
                volume = rng.uniform(100000, 1000000)
                
                # Randomly inject missing data (< 5%)
                if rng.random() < 0.02:  # 2% missing rate
                    close = np.nan
                
                data_records.append({
                    'date': date,
                    'symbol': symbol,
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'close': close,
                    'volume': volume
                })
        
        df = pd.DataFrame(data_records)
        
        # Handle empty case
        if df.empty:
            return pd.DataFrame()
        
        df = df.set_index(['date', 'symbol']).sort_index()
        
        # Record latency
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        if self.config.enable_latency_monitoring:
            print(f"[VCI Integration] Mock data fetch latency: {latency_ms:.2f}ms")
        
        return df
    
    def generate_mock_features(
        self,
        ohlcv_data: pd.DataFrame,
        n_features: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Generate mock features from OHLCV data.
        
        INTEGRATION POINT 2: Replace with real feature computation
        Real implementation should call:
            from feature_factory import FeatureFactory
            factory = FeatureFactory()
            features = factory.compute_features(ohlcv_data)
        
        Args:
            ohlcv_data: DataFrame with OHLCV data (MultiIndex: date, symbol)
            n_features: Number of features to generate (default: config.mock_features_count)
            
        Returns:
            DataFrame with MultiIndex (date, symbol) and feature columns
        """
        start_time = time.perf_counter()
        
        n_features = self.config.mock_features_count if n_features is None else n_features
        
        # Extract close prices for feature generation
        if 'close' not in ohlcv_data.columns:
            raise ValueError("OHLCV data must contain 'close' column")
        
        # Unstack to get (date, symbol) matrix
        close_prices = ohlcv_data['close'].unstack(level='symbol')
        
        features_dict = {}
        
        # Generate mock features (simple technical indicators)
        for i in range(n_features):
            feature_name = f'feature_{i:03d}'
            
            if i < 10:
                # Momentum features (returns over different periods)
                period = min((i + 1) * 5, 20)  # Cap at 20 to reduce NaNs
                features_dict[feature_name] = close_prices.pct_change(period).fillna(0)
            elif i < 20:
                # Moving average features
                window = min((i - 9) * 10, 50)  # Cap at 50 to reduce NaNs
                ma = close_prices.rolling(window, min_periods=1).mean()
                features_dict[feature_name] = (ma / close_prices - 1).fillna(0)
            elif i < 30:
                # Volatility features
                window = min((i - 19) * 5, 30)  # Cap at 30 to reduce NaNs
                vol = close_prices.pct_change().rolling(window, min_periods=1).std()
                features_dict[feature_name] = vol.fillna(0)
            else:
                # Random noise features (to test pruning)
                features_dict[feature_name] = pd.DataFrame(
                    np.random.randn(*close_prices.shape),
                    index=close_prices.index,
                    columns=close_prices.columns
                )
        
        # Stack back to MultiIndex format
        feature_dfs = []
        for feature_name, feature_data in features_dict.items():
            stacked = feature_data.stack()
            stacked.name = feature_name
            feature_dfs.append(stacked)
        
        features = pd.concat(feature_dfs, axis=1)
        
        # Record latency
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        if self.config.enable_latency_monitoring:
            print(f"[VCI Integration] Feature generation latency: {latency_ms:.2f}ms")
        
        return features
    
    def validate_data_quality(
        self,
        data: pd.DataFrame,
        latency_ms: float
    ) -> VCIDataQualityMetrics:
        """
        Validate data quality (missing rate < 5%, latency < 100ms).
        
        Args:
            data: DataFrame to validate
            latency_ms: Latency in milliseconds
            
        Returns:
            VCIDataQualityMetrics with validation results
        """
        total_records = data.size
        missing_records = data.isna().sum().sum()
        
        metrics = VCIDataQualityMetrics(
            total_records=total_records,
            missing_records=missing_records,
            latency_ms=latency_ms,
            max_missing_rate=self.config.max_missing_rate,
            max_latency_ms=self.config.max_latency_ms,
            timestamp=datetime.now()
        )
        
        # Store in history
        self.quality_history.append(metrics)
        
        # Log validation results
        if self.config.enable_data_validation:
            status = "PASS" if metrics.validation_passed else "FAIL"
            print(f"[VCI Integration] Data Quality Validation: {status}")
            print(f"  - Total records: {metrics.total_records:,}")
            print(f"  - Missing records: {metrics.missing_records:,}")
            print(f"  - Missing rate: {metrics.missing_rate:.2%} (threshold: {self.config.max_missing_rate:.2%})")
            print(f"  - Latency: {metrics.latency_ms:.2f}ms (threshold: {self.config.max_latency_ms:.2f}ms)")
        
        return metrics
    
    def fetch_features_for_pruning(
        self,
        symbols: Optional[List[str]] = None,
        lookback_days: Optional[int] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame, VCIDataQualityMetrics]:
        """
        Fetch VCI data and generate features for pruning pipeline.
        
        INTEGRATION POINT 3: Main entry point for feature pruning pipeline
        This method orchestrates the full data flow:
        1. Fetch VCI data (mock or real)
        2. Generate features
        3. Validate data quality
        4. Return features AND ohlcv_data ready for pruning
        
        Args:
            symbols: List of stock symbols
            lookback_days: Number of days to fetch
            
        Returns:
            Tuple of (features DataFrame, ohlcv_data DataFrame, quality metrics)
        """
        start_time = time.perf_counter()
        
        # Step 1: Fetch VCI data
        print(f"[VCI Integration] Fetching VCI data...")
        ohlcv_data = self.fetch_mock_vci_data(symbols, lookback_days)

        raw_latency_ms = (time.perf_counter() - start_time) * 1000
        metrics = self.validate_data_quality(ohlcv_data, raw_latency_ms)

        if not metrics.validation_passed:
            print(f"[VCI Integration] WARNING: Raw VCI data quality validation failed!")
            return pd.DataFrame(), ohlcv_data, metrics
        
        # Step 2: Generate features
        print(f"[VCI Integration] Generating features...")
        features = self.generate_mock_features(ohlcv_data)
        
        return features, ohlcv_data, metrics
    
    def wire_to_feature_pruning(
        self,
        pruner,
        symbols: Optional[List[str]] = None,
        lookback_days: Optional[int] = None,
        forward_return_period: int = 5
    ) -> Dict:
        """
        Wire VCI data into feature pruning pipeline.
        
        INTEGRATION POINT 4: Connect to feature_pruning.py
        This method demonstrates the full integration:
        1. Fetch features from VCI
        2. Compute forward returns
        3. Run feature pruning
        4. Return pruning results with quality metrics
        
        Args:
            pruner: FeaturePruning instance from feature_pruning.py
            symbols: List of stock symbols
            lookback_days: Number of days to fetch
            forward_return_period: Days ahead for return calculation
            
        Returns:
            Dictionary with pruning results and quality metrics
        """
        print("=" * 80)
        print("VCI DATA INTEGRATION -> FEATURE PRUNING PIPELINE")
        print("=" * 80)
        
        # Step 1: Fetch features from VCI
        features, ohlcv_data, quality_metrics = self.fetch_features_for_pruning(symbols, lookback_days)
        
        if not quality_metrics.validation_passed:
            return {
                'success': False,
                'error': 'Data quality validation failed',
                'quality_metrics': quality_metrics
            }
        
        # Step 2: Compute forward returns using the SAME ohlcv_data
        print(f"[VCI Integration] Computing forward returns (period={forward_return_period})...")
        
        # Get close prices and compute forward returns
        close_prices = ohlcv_data['close'].unstack(level='symbol')
        forward_returns = close_prices.shift(-forward_return_period) / close_prices - 1
        forward_returns_stacked = forward_returns.stack()
        forward_returns_stacked.name = 'forward_return'
        
        # Align features and returns using the same index
        # Both should have MultiIndex (date, symbol)
        common_idx = features.index.intersection(forward_returns_stacked.index)
        
        if len(common_idx) == 0:
            print(f"[VCI Integration] ERROR: No common index between features and returns")
            print(f"  Features index sample: {features.index[:5].tolist()}")
            print(f"  Returns index sample: {forward_returns_stacked.index[:5].tolist()}")
            return {
                'success': False,
                'error': 'No common index between features and returns',
                'quality_metrics': quality_metrics
            }
        
        features_aligned = features.loc[common_idx]
        returns_aligned = forward_returns_stacked.loc[common_idx]
        
        # Remove rows where forward return is NaN (end of series)
        valid_mask = ~returns_aligned.isna()
        features_aligned = features_aligned[valid_mask]
        returns_aligned = returns_aligned[valid_mask]
        
        if len(features_aligned) == 0:
            print(f"[VCI Integration] ERROR: No valid data after removing NaN returns")
            return {
                'success': False,
                'error': 'No valid data after removing NaN returns',
                'quality_metrics': quality_metrics
            }
        
        # Convert to flat format for pruner (single index)
        features_flat = features_aligned.copy()
        features_flat.index = range(len(features_flat))
        returns_flat = returns_aligned.copy()
        returns_flat.index = range(len(returns_flat))
        
        print(f"[VCI Integration] Features shape: {features_flat.shape}")
        print(f"[VCI Integration] Returns shape: {returns_flat.shape}")
        
        # Step 3: Run feature pruning
        print(f"[VCI Integration] Running feature pruning...")
        pruning_result = pruner.prune_features(features_flat, returns_flat, progressive=True)
        
        print(f"[VCI Integration] Pruning complete:")
        print(f"  - Kept features: {len(pruning_result.kept_features)}")
        print(f"  - Removed features: {len(pruning_result.removed_features)}")
        print(f"  - Removal rate: {len(pruning_result.removed_features) / (len(pruning_result.kept_features) + len(pruning_result.removed_features)):.1%}")
        
        # Step 4: Return results
        return {
            'success': True,
            'pruning_result': pruning_result,
            'quality_metrics': quality_metrics,
            'features_shape': features_flat.shape,
            'returns_shape': returns_flat.shape,
            'kept_features': pruning_result.kept_features,
            'removed_features': pruning_result.removed_features
        }
    
    def get_quality_summary(self) -> pd.DataFrame:
        """
        Get summary of data quality metrics over time.
        
        Returns:
            DataFrame with quality metrics history
        """
        if not self.quality_history:
            return pd.DataFrame()
        
        records = []
        for metrics in self.quality_history:
            records.append({
                'timestamp': metrics.timestamp,
                'total_records': metrics.total_records,
                'missing_records': metrics.missing_records,
                'missing_rate': metrics.missing_rate,
                'latency_ms': metrics.latency_ms,
                'validation_passed': metrics.validation_passed
            })
        
        return pd.DataFrame(records)


# ============================================================================
# INTEGRATION DOCUMENTATION
# ============================================================================

"""
INTEGRATION POINTS FOR REAL VCI FEED:

1. Data Source Integration (vnstock_vci_datasource.py)
   - Replace fetch_mock_vci_data() with VnstockVCIDataSource.get_ohlcv()
   - Ensure VNSTOCK_API_KEY is configured
   - Handle rate limiting and API errors

2. Feature Computation (feature_factory.py)
   - Replace generate_mock_features() with FeatureFactory.compute_features()
   - Use real technical indicators and alpha factors
   - Ensure PIT compliance (no lookahead bias)

3. Real-time Streaming (live_ingestor.py)
   - Connect to live_ingestor.py for real-time data streaming
   - Implement incremental feature updates
   - Handle market hours and trading calendar

4. Feature Pruning Pipeline (feature_pruning.py)
   - Current implementation: wire_to_feature_pruning()
   - Supports both in-sample and out-of-sample IC computation
   - Enforces data quality validation before pruning

5. Monitoring and Alerting
   - quality_history tracks all validation metrics
   - get_quality_summary() provides historical view
   - Add alerting for validation failures (missing rate > 5%, latency > 100ms)

EXAMPLE USAGE:

    from vci_integration import VCIDataIntegration, VCIIntegrationConfig
    from feature_pruning import FeaturePruning, FeaturePruningConfig
    
    # Configure VCI integration
    vci_config = VCIIntegrationConfig(
        max_missing_rate=0.05,
        max_latency_ms=100.0,
        mock_symbols=['VCB', 'HPG', 'FPT']
    )
    vci = VCIDataIntegration(vci_config)
    
    # Configure feature pruning
    pruning_config = FeaturePruningConfig(
        min_ic_threshold=0.02,
        stability_threshold=0.5,
        progressive_rate=0.15
    )
    pruner = FeaturePruning(pruning_config)
    
    # Wire VCI data into pruning pipeline
    result = vci.wire_to_feature_pruning(
        pruner=pruner,
        symbols=['VCB', 'HPG', 'FPT'],
        lookback_days=252,
        forward_return_period=5
    )
    
    if result['success']:
        print(f"Kept features: {result['kept_features']}")
        print(f"Quality metrics: {result['quality_metrics']}")
    else:
        print(f"Error: {result['error']}")

PERFORMANCE REQUIREMENTS:

1. Data Validation: < 5% missing data
   - Monitored via VCIDataQualityMetrics.missing_rate
   - Validation fails if missing_rate >= 0.05

2. Latency Monitoring: < 100ms
   - Monitored via VCIDataQualityMetrics.latency_ms
   - Validation fails if latency_ms >= 100.0

3. Quality History: Persistent tracking
   - All metrics stored in quality_history
   - Accessible via get_quality_summary()

CONTRACT COMPLIANCE:

- Input: VCI data feed (OHLCV format)
- Output: Features ready for pruning pipeline
- Guarantees:
  1. Data quality validation (missing rate < 5%)
  2. Latency monitoring (< 100ms)
  3. PIT compliance (no lookahead bias)
  4. Integration with feature_pruning.py
  5. Audit trail via quality_history
"""


if __name__ == '__main__':
    print("=" * 80)
    print("VCI DATA INTEGRATION - DEMO")
    print("=" * 80)
    
    # Import feature pruning
    from feature_pruning import FeaturePruning, FeaturePruningConfig
    
    # Configure VCI integration
    vci_config = VCIIntegrationConfig(
        max_missing_rate=0.05,
        max_latency_ms=100.0,
        mock_symbols=['VCB', 'HPG', 'FPT', 'VHM', 'VIC'],
        mock_features_count=30,
        mock_lookback_days=252
    )
    vci = VCIDataIntegration(vci_config)
    
    # Configure feature pruning
    pruning_config = FeaturePruningConfig(
        min_ic_threshold=0.02,
        stability_threshold=0.5,
        progressive_rate=0.15,
        min_features=10
    )
    pruner = FeaturePruning(pruning_config)
    
    # Wire VCI data into pruning pipeline
    result = vci.wire_to_feature_pruning(
        pruner=pruner,
        symbols=['VCB', 'HPG', 'FPT', 'VHM', 'VIC'],
        lookback_days=252,
        forward_return_period=5
    )
    
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    
    if result['success']:
        print(f"[SUCCESS] Integration successful!")
        print(f"\nFeatures shape: {result['features_shape']}")
        print(f"Returns shape: {result['returns_shape']}")
        print(f"\nKept features: {len(result['kept_features'])}")
        print(f"Removed features: {len(result['removed_features'])}")
        print(f"\nTop 10 kept features by IC:")
        pruning_result = result['pruning_result']
        top_features = sorted(
            pruning_result.feature_ics.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        )[:10]
        for feat, ic in top_features:
            if feat in pruning_result.kept_features:
                print(f"  {feat}: IC={ic:.4f}")
        
        print(f"\nData Quality Metrics:")
        metrics = result['quality_metrics']
        print(f"  - Total records: {metrics.total_records:,}")
        print(f"  - Missing rate: {metrics.missing_rate:.2%}")
        print(f"  - Latency: {metrics.latency_ms:.2f}ms")
        print(f"  - Validation: {'PASS' if metrics.validation_passed else 'FAIL'}")
    else:
        print(f"[FAIL] Integration failed: {result['error']}")
    
    print("\n" + "=" * 80)
    print("Quality History Summary")
    print("=" * 80)
    quality_summary = vci.get_quality_summary()
    print(quality_summary)
    
    print("\n" + "=" * 80)
    print("VCI Data Integration demo complete")
    print("=" * 80)
