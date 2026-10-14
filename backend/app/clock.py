"""Single source of 'now' so tests can move time forward."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

PNG_TZ = ZoneInfo("Pacific/Port_Moresby")


def now() -> datetime:
    return datetime.now(UTC)


def start_of_png_month(at: datetime) -> datetime:
    """First instant of the calendar month in Port Moresby time, returned in UTC."""
    local = at.astimezone(PNG_TZ)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
