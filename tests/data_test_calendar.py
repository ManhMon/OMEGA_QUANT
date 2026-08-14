"""
Tests for OMEGA_QUANT VN Trading Calendar.

Tests JSON loading, fallback behavior, sample dates, and public API.
"""

import json
import pytest
from datetime import datetime, date
from pathlib import Path
from unittest.mock import patch, mock_open
from omega.data.calendar import VNTradingCalendar, _load_holidays, _get_json_holidays, get_futures_expiry_date


class TestJSONLoading:
    """Test JSON holiday loading functionality."""
    
    def test_json_file_exists(self):
        """Verify vn_holidays.json exists in expected location."""
        # tests/data_test_calendar.py -> parent = tests/ -> parent = repo root
        config_path = Path(__file__).parent.parent / "config" / "vn_holidays.json"
        assert config_path.exists(), f"Holiday JSON not found at {config_path}"
    
    def test_json_structure(self):
        """Verify JSON has correct structure with metadata and holidays."""
        config_path = Path(__file__).parent.parent / "config" / "vn_holidays.json"
        
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check metadata
        assert 'metadata' in data
        metadata = data['metadata']
        assert 'source' in metadata
        assert 'provenance_urls' in metadata
        assert 'generated_at' in metadata
        assert 'coverage_start' in metadata
        assert 'coverage_end' in metadata
        
        # Check version exists and is semver
        assert 'version' in metadata, "metadata must contain 'version' field"
        version = metadata['version']
        assert isinstance(version, str), "version must be a string"
        # Validate semver format (major.minor.patch)
        parts = version.split('.')
        assert len(parts) == 3, f"version must be semver format (major.minor.patch), got: {version}"
        assert all(part.isdigit() for part in parts), f"version parts must be numeric, got: {version}"
        
        # Check holidays structure
        assert 'holidays' in data
        holidays = data['holidays']
        assert isinstance(holidays, dict)
        
        # Verify coverage years
        assert '2015' in holidays
        assert '2024' in holidays
        assert '2027' in holidays
    
    def test_json_cache_loading(self):
        """Test that _get_json_holidays returns cached data."""
        holidays1 = _get_json_holidays()
        holidays2 = _get_json_holidays()
        
        # Should return same object (cached)
        assert holidays1 is holidays2
        assert isinstance(holidays1, dict)


class TestSampleDates:
    """Test specific holiday dates across different years."""
    
    def test_year_2015_holidays(self):
        """Test 2015 holiday dates."""
        holidays = _load_holidays(2015)
        
        # New Year
        assert date(2015, 1, 1) in holidays
        
        # Tet 2015 (Feb 18-23)
        assert date(2015, 2, 18) in holidays
        assert date(2015, 2, 19) in holidays
        assert date(2015, 2, 20) in holidays
        assert date(2015, 2, 21) in holidays
        assert date(2015, 2, 22) in holidays
        assert date(2015, 2, 23) in holidays
        
        # Fixed holidays
        assert date(2015, 4, 30) in holidays  # Reunification Day
        assert date(2015, 5, 1) in holidays   # Labor Day
        assert date(2015, 9, 2) in holidays   # National Day
    
    def test_year_2024_holidays(self):
        """Test 2024 holiday dates including Hung Kings."""
        holidays = _load_holidays(2024)
        
        # Tet 2024 (Feb 8-14)
        assert date(2024, 2, 8) in holidays
        assert date(2024, 2, 9) in holidays
        assert date(2024, 2, 10) in holidays
        assert date(2024, 2, 11) in holidays
        assert date(2024, 2, 12) in holidays
        assert date(2024, 2, 13) in holidays
        assert date(2024, 2, 14) in holidays
        
        # Hung Kings 2024 (April 18)
        assert date(2024, 4, 18) in holidays
        
        # Fixed holidays
        assert date(2024, 1, 1) in holidays
        assert date(2024, 4, 30) in holidays
        assert date(2024, 5, 1) in holidays
        assert date(2024, 9, 2) in holidays
    
    def test_year_2027_holidays(self):
        """Test 2027 holiday dates."""
        holidays = _load_holidays(2027)
        
        # Tet 2027 (Feb 5-11)
        assert date(2027, 2, 5) in holidays
        assert date(2027, 2, 6) in holidays
        assert date(2027, 2, 7) in holidays
        assert date(2027, 2, 8) in holidays
        assert date(2027, 2, 9) in holidays
        assert date(2027, 2, 10) in holidays
        assert date(2027, 2, 11) in holidays
        
        # Fixed holidays
        assert date(2027, 1, 1) in holidays
        assert date(2027, 4, 30) in holidays
        assert date(2027, 5, 1) in holidays
        assert date(2027, 9, 2) in holidays
    
    def test_compensatory_dates(self):
        """Test compensatory holiday dates when holidays fall on weekends."""
        # 2023: Jan 1 is Sunday -> compensatory Jan 2
        holidays_2023 = _load_holidays(2023)
        assert date(2023, 1, 2) in holidays_2023
        
        # 2017: Jan 1 is Sunday -> compensatory Jan 2
        holidays_2017 = _load_holidays(2017)
        assert date(2017, 1, 2) in holidays_2017
        
        # 2023: Sep 2 is Saturday -> compensatory Sep 4
        assert date(2023, 9, 4) in holidays_2023


class TestFallbackBehavior:
    """Test fallback to minimal holidays when JSON is missing."""
    
    def test_fallback_for_unknown_year(self):
        """Test that unknown years fall back to minimal fixed holidays."""
        # Year 2030 is not in JSON
        holidays = _load_holidays(2030)
        
        # Should have minimal fixed holidays
        assert date(2030, 1, 1) in holidays   # New Year
        assert date(2030, 4, 30) in holidays  # Reunification Day
        assert date(2030, 5, 1) in holidays   # Labor Day
        assert date(2030, 9, 2) in holidays   # National Day
        
        # Should NOT have Tet or Hung Kings (not in fallback)
        # Fallback only includes fixed holidays
        assert len(holidays) >= 4  # At least the 4 fixed holidays
    
    def test_fallback_includes_compensatory(self):
        """Test that fallback includes compensatory days for weekends."""
        # 2028: Jan 1 is Saturday -> should have compensatory Jan 3
        holidays = _load_holidays(2028)
        assert date(2028, 1, 1) in holidays
        assert date(2028, 1, 3) in holidays  # Compensatory Monday
    
    def test_missing_json_file_fallback(self):
        """Test that missing JSON file triggers fallback to fixed holidays."""
        # Mock Path.exists to return False (simulate missing file)
        with patch('omega.data.calendar.Path.exists', return_value=False):
            # Clear the JSON cache to force reload
            import omega.data.calendar as cal_module
            cal_module._JSON_HOLIDAYS_CACHE = None
            
            # Load holidays for 2024 (should fallback)
            holidays = _load_holidays(2024)
            
            # Should have deterministic fixed holidays
            assert date(2024, 1, 1) in holidays   # New Year
            assert date(2024, 4, 30) in holidays  # Reunification Day
            assert date(2024, 5, 1) in holidays   # Labor Day
            assert date(2024, 9, 2) in holidays   # National Day
            
            # Should have at least these 4 fixed holidays
            assert len(holidays) >= 4
    
    def test_corrupted_json_file_fallback(self):
        """Test that corrupted JSON file triggers fallback to fixed holidays."""
        # Mock open to return invalid JSON
        with patch('builtins.open', mock_open(read_data='{"invalid json')):
            # Clear the JSON cache to force reload
            import omega.data.calendar as cal_module
            cal_module._JSON_HOLIDAYS_CACHE = None
            
            # Load holidays for 2024 (should fallback)
            holidays = _load_holidays(2024)
            
            # Should have deterministic fixed holidays
            assert date(2024, 1, 1) in holidays   # New Year
            assert date(2024, 4, 30) in holidays  # Reunification Day
            assert date(2024, 5, 1) in holidays   # Labor Day
            assert date(2024, 9, 2) in holidays   # National Day
            
            # Should have at least these 4 fixed holidays
            assert len(holidays) >= 4


class TestPublicAPI:
    """Test public API methods remain unchanged."""
    
    def test_is_trading_day_weekday(self):
        """Test is_trading_day for regular weekday."""
        # Monday, not a holiday
        dt = datetime(2024, 3, 4, 10, 0)  # March 4, 2024 is Monday
        assert VNTradingCalendar.is_trading_day(dt) is True


def test_futures_expiry_rolls_back_on_holiday():
    with patch.object(VNTradingCalendar, "is_trading_day", side_effect=lambda dt: dt.date() != date(2024, 9, 19)):
        assert get_futures_expiry_date(2024, 9) == date(2024, 9, 18)
    
    def test_is_trading_day_weekend(self):
        """Test is_trading_day for weekend."""
        # Saturday
        dt = datetime(2024, 3, 2, 10, 0)  # March 2, 2024 is Saturday
        assert VNTradingCalendar.is_trading_day(dt) is False
        
        # Sunday
        dt = datetime(2024, 3, 3, 10, 0)  # March 3, 2024 is Sunday
        assert VNTradingCalendar.is_trading_day(dt) is False
    
    def test_is_trading_day_holiday(self):
        """Test is_trading_day for holiday."""
        # Tet 2024 (Feb 10)
        dt = datetime(2024, 2, 10, 10, 0)
        assert VNTradingCalendar.is_trading_day(dt) is False
        
        # Labor Day
        dt = datetime(2024, 5, 1, 10, 0)
        assert VNTradingCalendar.is_trading_day(dt) is False
    
    def test_is_valid_trading_timestamp_morning(self):
        """Test is_valid_trading_timestamp for morning session."""
        # 9:30 AM on trading day
        dt = datetime(2024, 3, 4, 9, 30)
        assert VNTradingCalendar.is_valid_trading_timestamp(dt) is True
        
        # 11:00 AM on trading day
        dt = datetime(2024, 3, 4, 11, 0)
        assert VNTradingCalendar.is_valid_trading_timestamp(dt) is True
    
    def test_is_valid_trading_timestamp_afternoon(self):
        """Test is_valid_trading_timestamp for afternoon session."""
        # 1:30 PM on trading day
        dt = datetime(2024, 3, 4, 13, 30)
        assert VNTradingCalendar.is_valid_trading_timestamp(dt) is True
        
        # 2:30 PM on trading day (ATC)
        dt = datetime(2024, 3, 4, 14, 30)
        assert VNTradingCalendar.is_valid_trading_timestamp(dt) is True
    
    def test_is_valid_trading_timestamp_outside_hours(self):
        """Test is_valid_trading_timestamp outside trading hours."""
        # 8:00 AM (before market open)
        dt = datetime(2024, 3, 4, 8, 0)
        assert VNTradingCalendar.is_valid_trading_timestamp(dt) is False
        
        # 12:00 PM (lunch break)
        dt = datetime(2024, 3, 4, 12, 0)
        assert VNTradingCalendar.is_valid_trading_timestamp(dt) is False
        
        # 3:00 PM (after market close)
        dt = datetime(2024, 3, 4, 15, 0)
        assert VNTradingCalendar.is_valid_trading_timestamp(dt) is False
    
    def test_validate_timestamps_list(self):
        """Test validate_timestamps with list of timestamps."""
        # All trading days
        timestamps = [
            datetime(2024, 3, 4, 10, 0),  # Monday
            datetime(2024, 3, 5, 10, 0),  # Tuesday
            datetime(2024, 3, 6, 10, 0),  # Wednesday
        ]
        assert VNTradingCalendar.validate_timestamps(timestamps, strict=False) is True
        
        # Contains weekend
        timestamps_with_weekend = [
            datetime(2024, 3, 4, 10, 0),  # Monday
            datetime(2024, 3, 2, 10, 0),  # Saturday
        ]
        assert VNTradingCalendar.validate_timestamps(timestamps_with_weekend, strict=False) is False
    
    def test_validate_timestamps_strict_mode(self):
        """Test validate_timestamps in strict mode (checks trading hours)."""
        # Valid trading hours
        timestamps = [
            datetime(2024, 3, 4, 9, 30),   # Morning session
            datetime(2024, 3, 4, 13, 30),  # Afternoon session
        ]
        assert VNTradingCalendar.validate_timestamps(timestamps, strict=True) is True
        
        # Outside trading hours
        timestamps_outside = [
            datetime(2024, 3, 4, 9, 30),   # Valid
            datetime(2024, 3, 4, 12, 0),   # Lunch break - invalid
        ]
        assert VNTradingCalendar.validate_timestamps(timestamps_outside, strict=True) is False


class TestCaching:
    """Test holiday caching behavior."""
    
    def test_holiday_cache_per_year(self):
        """Test that holidays are cached per year."""
        # Clear cache
        VNTradingCalendar._holiday_cache.clear()
        
        # Load 2024
        holidays_2024_1 = VNTradingCalendar._get_holidays(2024)
        holidays_2024_2 = VNTradingCalendar._get_holidays(2024)
        
        # Should return same object (cached)
        assert holidays_2024_1 is holidays_2024_2
        
        # Load 2025
        holidays_2025 = VNTradingCalendar._get_holidays(2025)
        
        # Should be different object
        assert holidays_2024_1 is not holidays_2025
        
        # Cache should have both years
        assert 2024 in VNTradingCalendar._holiday_cache
        assert 2025 in VNTradingCalendar._holiday_cache
