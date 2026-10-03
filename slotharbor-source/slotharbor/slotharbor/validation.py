"""Small, explicit input boundaries shared by CLI and HTTP callers."""
import re
from .errors import require


def text(value, field: str, minimum: int = 1, maximum: int = 120) -> str:
    require(isinstance(value, str), f"{field} must be text.")
    value = value.strip()
    require(minimum <= len(value) <= maximum, f"{field} must be {minimum}–{maximum} characters.")
    require(not any(ord(c) < 32 or ord(c) == 127 for c in value), f"{field} contains control characters.")
    return value


def integer(value, field: str, minimum: int, maximum: int) -> int:
    require(type(value) is int or (isinstance(value, str) and re.fullmatch(r"-?\d{1,12}", value) is not None),
            f"{field} must be a whole number.")
    value = int(value)
    require(minimum <= value <= maximum, f"{field} must be between {minimum} and {maximum}.")
    return value


def boolean(value, field: str) -> bool:
    require(type(value) is bool, f"{field} must be true or false.")
    return value
