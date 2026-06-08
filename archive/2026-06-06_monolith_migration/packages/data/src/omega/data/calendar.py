"""
OMEGA_QUANT VN Trading Calendar - Holiday and session validation for Vietnamese stock market.
"""

import json
from datetime import datetime, date
from typing import Set, Optional
from pathlib import Path


# JSON-based holiday loading with fallback
def _load_holidays_from_json() -> dict:
    """Load holidays from JSON config file.
    
    Returns:
        dict: Year -> list of date strings mapping, or empty dict if file not found
    """
    try:
        # Path relative to package root
        config_path = Path(__file__).parent.parent.parent.parent.parent.parent / "config" / "vn_holidays.json"
        
        if not config_path.exists():
            return {}
        
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data.get('holidays', {})
    except Exception:
        # Silently fail and return empty dict for fallback
        return {}


# Cache for loaded JSON holidays
_JSON_HOLIDAYS_CACHE: Optional[dict] = None


def _get_json_holidays() -> dict:
    """Get cached JSON holidays or load them."""
    global _JSON_HOLIDAYS_CACHE
    if _JSON_HOLIDAYS_CACHE is None:
        _JSON_HOLIDAYS_CACHE = _load_holidays_from_json()
    return _JSON_HOLIDAYS_CACHE


def _load_holidays(year: int) -> Set[date]:
    """Load VN holidays for a given year.
    
    First attempts to load from JSON config file (OMEGA_QUANT/config/vn_holidays.json).
    Falls back to minimal fixed holidays if JSON not available.
    
    Includes:
    - New Year (Jan 1)
    - Tet/Lunar New Year (variable dates)
    - Hung Kings Festival (Lunar March 10)
    - Reunification Day (April 30)
    - Labor Day (May 1)
    - National Day (Sep 2)
    - Compensatory holidays (nghỉ bù) when holidays fall on weekends
    
    Coverage: 2015-2027 (from JSON)
    """
    holidays = set()
    
    # Try to load from JSON first
    json_holidays = _get_json_holidays()
    year_str = str(year)
    
    if year_str in json_holidays:
        # Parse ISO date strings from JSON
        for date_str in json_holidays[year_str]:
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d').date()
                holidays.add(dt)
            except ValueError:
                continue
        return holidays
    
    # Fallback: minimal fixed holidays only (no Tet, no Hung Kings)
    # This ensures deterministic behavior when JSON is missing
    holidays.add(date(year, 1, 1))   # New Year
    holidays.add(date(year, 4, 30))  # Reunification Day
    holidays.add(date(year, 5, 1))   # Labor Day
    holidays.add(date(year, 9, 2))   # National Day
    
    # Add compensatory days for fixed holidays falling on weekends
    if date(year, 1, 1).weekday() == 5:  # Saturday
        holidays.add(date(year, 1, 3))
    elif date(year, 1, 1).weekday() == 6:  # Sunday
        holidays.add(date(year, 1, 2))
    
    if date(year, 4, 30).weekday() == 5:  # Saturday
        holidays.add(date(year, 5, 3))
    elif date(year, 4, 30).weekday() == 6:  # Sunday
        holidays.add(date(year, 5, 2))
    
    if date(year, 5, 1).weekday() == 6:  # Sunday
        if date(year, 4, 30).weekday() != 5:
            holidays.add(date(year, 5, 2))
    
    if date(year, 9, 2).weekday() == 5:  # Saturday
        holidays.add(date(year, 9, 4))
    elif date(year, 9, 2).weekday() == 6:  # Sunday
        holidays.add(date(year, 9, 3))
    
    return holidays


class VNTradingCalendar:
    """"Vietnamese stock market trading calendar (HOSE/HNX/UPCOM).
    
    Trading sessions:
    - Morning: 09:00 - 11:30
    - Lunch break: 11:30 - 13:00
    - Afternoon: 13:00 - 14:30
    - ATO (At The Open): 09:00 - 09:15
    - ATC (At The Close): 14:30 - 14:45
    
    Holidays: Dynamic loading by year (supports 2025-2027+)
    """
    
    # Cache holidays per year
    _holiday_cache: dict = {}
    
    @classmethod
    def _get_holidays(cls, year: int) -> Set[date]:
        """Get or create holiday set for a year."""
        if year not in cls._holiday_cache:
            cls._holiday_cache[year] = _load_holidays(year)
        return cls._holiday_cache[year]
    
    @classmethod
    def is_trading_day(cls, dt: datetime) -> bool:
        """Check if date is a trading day (not weekend or holiday)."""
        d = dt.date()
        # Weekend check
        if d.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        # Holiday check - dynamic by year
        year_holidays = cls._get_holidays(d.year)
        if d in year_holidays:
            return False
        return True
    
    @classmethod
    def is_valid_trading_timestamp(cls, dt: datetime) -> bool:
        """Check if timestamp falls within VN trading hours."""
        if not cls.is_trading_day(dt):
            return False
        
        hour = dt.hour
        minute = dt.minute
        
        # Morning session: 09:00 - 11:30
        if (hour == 9 and minute >= 0) or (hour == 10) or (hour == 11 and minute <= 30):
            return True
        
        # Afternoon session: 13:00 - 14:45 (including ATC)
        if (hour == 13) or (hour == 14 and minute <= 45):
            return True
        
        return False
    
    @classmethod
    def validate_timestamps(cls, timestamps: list, strict: bool = False) -> bool:
        """Validate list of timestamps.
        
        Args:
            timestamps: Unix timestamps (seconds) or datetime objects
            strict: If True, require all timestamps to be valid trading times
                   If False, only check they are trading days
        """
        for ts in timestamps:
            if isinstance(ts, int):
                dt = datetime.fromtimestamp(ts)
            else:
                dt = ts
            
            if strict:
                if not cls.is_valid_trading_timestamp(dt):
                    return False
            else:
                if not cls.is_trading_day(dt):
                    return False
        
        return True
