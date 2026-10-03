"""Minute-precision wall times; missing and ambiguous civil times fail explicitly."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .errors import DomainError, require


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise DomainError("Choose a valid IANA timezone.") from None


def local_datetime(value: str) -> datetime:
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value) is not None,
            "Use a local time in YYYY-MM-DDTHH:MM format, without an offset.")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise DomainError("The local date or time is invalid.") from None


def local_epoch(value: str, timezone_name: str, fold: int | None = None) -> int:
    require(fold is None or (type(fold) is int and fold in (0, 1)), "fold must be 0 or 1.")
    naive = local_datetime(value)
    tz = zone(timezone_name)
    valid = {}
    for option in (0, 1):
        aware = naive.replace(tzinfo=tz, fold=option)
        restored = aware.astimezone(timezone.utc).astimezone(tz)
        if restored.replace(tzinfo=None) == naive:
            valid[option] = int(aware.timestamp())
    require(bool(valid), "This local time does not exist because the clock changes.")
    if len(set(valid.values())) > 1:
        require(fold is not None, "This local time is ambiguous; choose the first or second occurrence.")
    return valid[fold if fold is not None else min(valid)]


def shifted(value: str, days: int) -> str:
    try:
        return (local_datetime(value) + timedelta(days=days)).isoformat(timespec="minutes")
    except OverflowError:
        raise DomainError("The recurring dates extend outside the supported calendar.") from None


def local_label(epoch: int, timezone_name: str) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).astimezone(zone(timezone_name)).strftime("%d %b %Y · %H:%M")


def utc_stamp(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
