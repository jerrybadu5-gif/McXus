"""PNG working days for the mediator deadline.

National public holidays (Public Holidays Act): New Year's Day, Good Friday, Easter Saturday, Easter Monday,
King's Birthday (second Monday in June), National Remembrance Day (23 July), National Repentance Day
(26 August), Independence Day (16 September), Christmas Day and Boxing Day. Declared or moved holidays can be
added with MCXUS_EXTRA_HOLIDAYS (list of ISO dates). Check the list each year against the gazette.
"""

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

from app.clock import PNG_TZ
from app.config import get_settings


def easter(year: int) -> date:
    """Western Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    day = (h + m - 7 * n + 114) % 31 + 1
    return date(year, month, day)


@lru_cache(maxsize=32)
def holidays(year: int) -> frozenset[date]:
    sunday = easter(year)
    june = date(year, 6, 1)
    first_monday = june + timedelta(days=(7 - june.weekday()) % 7)
    days = {
        date(year, 1, 1),
        sunday - timedelta(days=2),
        sunday - timedelta(days=1),
        sunday + timedelta(days=1),
        first_monday + timedelta(days=7),
        date(year, 7, 23),
        date(year, 8, 26),
        date(year, 9, 16),
        date(year, 12, 25),
        date(year, 12, 26),
    }
    return frozenset(days)


def is_working_day(day: date) -> bool:
    extra = {date.fromisoformat(d) for d in get_settings().extra_holidays}
    return day.weekday() < 5 and day not in holidays(day.year) and day not in extra


def add_working_days(start: datetime, days: int) -> datetime:
    """The end (17:00 Port Moresby time) of the Nth working day after `start`."""
    day = start.astimezone(PNG_TZ).date()
    counted = 0
    while counted < days:
        day += timedelta(days=1)
        if is_working_day(day):
            counted += 1
    return datetime(day.year, day.month, day.day, 17, 0, tzinfo=PNG_TZ).astimezone(UTC)
