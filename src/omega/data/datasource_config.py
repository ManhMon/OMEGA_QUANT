# OMEGA_QUANT Data Source Configuration
# P4.1: Strict VnStock PIT Compliance (100% Embargo/Lag Differentiation)

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
from datetime import datetime, date, timedelta

class DataType(Enum):
    """Data type classification for PIT compliance."""
    PRICE = "price"           # T-1 lag (daily prices)
    FUNDAMENTAL = "fundamental"  # T+90 embargo (financial reports)
    MICROSTRUCTURE = "microstructure"  # T-1 lag (order book, flows)
    CORPORATE_ACTION = "corporate_action"  # T+0 (announcement date)

@dataclass
class DataSourceConfig:
    """Configuration for a single data source with PIT rules."""
    source_name: str
    data_type: DataType
    lag_days: int = 1  # Minimum lag (T-1 for prices)
    embargo_days: int = 0  # Additional embargo for fundamental data
    
    def validate_release_date(self, report_date: date, current_date: date) -> bool:
        """Validate if data can be used based on embargo rules."""
        if self.data_type == DataType.FUNDAMENTAL:
            embargo_end = report_date + timedelta(days=self.embargo_days)
            return current_date >= embargo_end
        else:
            return True  # Prices don't have embargo, only lag
    
    def get_valid_as_of(self, data_date: date) -> date:
        """Get the earliest valid date for data usage."""
        return data_date + timedelta(days=self.lag_days)

@dataclass
class EmbargoConfig:
    """T+90 Embargo configuration for VN market financial reports."""
    quarterly_embargo_days: int = 90  # T+90 for quarterly reports
    annual_embargo_days: int = 90     # T+90 for annual reports
    earnings_embargo_days: int = 90   # T+90 for earnings announcements
    
class VnStockDataSource:
    """
    Strict VnStock integration with PIT compliance.
    NO FALLBACKS to VNDirect/FiinPro for production.
    """
    
    def __init__(self):
        self.configs = {
            DataType.PRICE: DataSourceConfig(
                source_name="vnstock",
                data_type=DataType.PRICE,
                lag_days=1,  # T-1 minimum
                embargo_days=0
            ),
            DataType.FUNDAMENTAL: DataSourceConfig(
                source_name="vnstock",
                data_type=DataType.FUNDAMENTAL,
                lag_days=1,  # T-1 minimum
                embargo_days=90  # T+90 embargo for financial reports
            ),
            DataType.MICROSTRUCTURE: DataSourceConfig(
                source_name="vnstock",
                data_type=DataType.MICROSTRUCTURE,
                lag_days=1,
                embargo_days=0
            ),
            DataType.CORPORATE_ACTION: DataSourceConfig(
                source_name="vnstock",
                data_type=DataType.CORPORATE_ACTION,
                lag_days=0,  # Use announcement date (T+0)
                embargo_days=0
            )
        }
        self.embargo = EmbargoConfig()
    
    def validate_pit_compliance(self, data_type: DataType, data_date: date, current_date: date) -> bool:
        """
        PIT validation: Ensure data is not used before embargo period.
        
        Args:
            data_type: Type of data (PRICE, FUNDAMENTAL, etc.)
            data_date: Date of the data (report date for financials)
            current_date: Current date for validation
            
        Returns:
            True if PIT compliant, False if violation
        """
        config = self.configs.get(data_type)
        if config is None:
            return False
        
        return config.validate_release_date(data_date, current_date)
    
    def get_valid_date(self, data_type: DataType, data_date: date) -> date:
        """Get the earliest valid date for data usage."""
        config = self.configs.get(data_type)
        if config is None:
            return data_date
        return config.get_valid_as_of(data_date)
    
    def validate_no_lookahead(self, feature_ts: date, decision_ts: date) -> bool:
        """
        Validate no look-ahead bias: feature timestamp must be < decision timestamp.
        
        Args:
            feature_ts: Timestamp of feature calculation
            decision_ts: Timestamp of trading decision
            
        Returns:
            True if no look-ahead (valid), False if look-ahead detected
        """
        return feature_ts < decision_ts
    
    def validate_timestamps(self, feature_ts: Optional[date], decision_ts: date, 
                           execution_ts: Optional[date] = None) -> dict:
        """
        Comprehensive PIT timestamp validation.
        
        Returns:
            Dict with validation results for each timestamp
        """
        results = {
            "feature_before_decision": True,
            "decision_before_execution": True,
            "settlement_delay_valid": True,
            "all_valid": True
        }
        
        if feature_ts is not None:
            results["feature_before_decision"] = self.validate_no_lookahead(feature_ts, decision_ts)
        
        if execution_ts is not None:
            # T+2.5 settlement delay (VN market)
            # Simplification for datetime/date handling. 
            # In actual implementation, we might need more robust timestamp tracking, but this is a stub.
            # Using simple day addition for now (execution must be at least 3 days after decision to be safe).
            min_execution = decision_ts + timedelta(days=3)
            results["decision_before_execution"] = execution_ts >= min_execution
            results["settlement_delay_valid"] = results["decision_before_execution"]
        
        results["all_valid"] = all([
            results["feature_before_decision"],
            results["decision_before_execution"],
            results["settlement_delay_valid"]
        ])
        
        return results

# PIT Guardian integration
def validate_data_source_pit(data_source: VnStockDataSource, 
                             data_type: DataType,
                             data_date: date,
                             current_date: date) -> bool:
    """Validate PIT compliance for data source usage."""
    return data_source.validate_pit_compliance(data_type, data_date, current_date)