"""
V21 VN Trading Calendar - Holiday and session validation for Vietnamese stock market.
"""

from datetime import datetime, date
from typing import Set, Optional


# Dynamic holiday loading - hỗ trợ nhiều năm
def _load_holidays(year: int) -> Set[date]:
    """Load VN holidays for a given year. Expand as needed."""
    holidays = {
        date(year, 1, 1),   # New Year
        date(year, 4, 30),  # Reunification Day
        date(year, 5, 1),   # Labor Day
        date(year, 9, 2),   # National Day
    }
    
    # Hung Kings' Festival (Lunar March 10)
    if year == 2025:
        holidays.add(date(2025, 4, 7))
    elif year == 2026:
        # Falls on Sunday April 26 -> Compensatory holiday on Monday April 27
        holidays.update([date(2026, 4, 26), date(2026, 4, 27)])
    elif year == 2027:
        holidays.add(date(2027, 4, 16))
    
    # Tet holiday approximation (Lunar Jan 1-5)
    if year == 2026:
        holidays.update([date(2026, 1, 28), date(2026, 1, 29), date(2026, 1, 30), date(2026, 1, 31), date(2026, 2, 1), date(2026, 2, 2)])
    elif year == 2027:
        holidays.update([date(2027, 2, 16), date(2027, 2, 17), date(2027, 2, 18), date(2027, 2, 19), date(2027, 2, 20)])
    elif year == 2025:
        holidays.update([date(2025, 1, 29), date(2025, 1, 30), date(2025, 1, 31), date(2025, 2, 1), date(2025, 2, 2), date(2025, 2, 3)])
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
