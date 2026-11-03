from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime(UTC_FMT)


def parse_utc(value: str) -> datetime:
    return datetime.strptime(value, UTC_FMT).replace(tzinfo=timezone.utc)


def to_local(utc_iso: str, tz_name: str) -> tuple[str, str]:
    """Return (tenant-local calendar date 'YYYY-MM-DD', display 'YYYY-MM-DD HH:MM')."""
    local = parse_utc(utc_iso).astimezone(ZoneInfo(tz_name))
    return local.strftime("%Y-%m-%d"), local.strftime("%Y-%m-%d %H:%M")
