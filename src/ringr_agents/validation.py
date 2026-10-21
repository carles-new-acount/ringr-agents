"""Validation and normalization of the values returned by the ParserModel.

Each function receives a raw value (never None: missing values are handled by
the caller) and returns it normalized, or raises InvalidFieldError.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any


class InvalidFieldError(ValueError):
    """The parser returned a value that does not satisfy the field contract."""


def parse_iso_date(value: Any) -> date:
    """Parse a strict 'yyyy-mm-dd' string."""
    if not isinstance(value, str):
        raise InvalidFieldError(f"expected a 'yyyy-mm-dd' string, got {type(value).__name__}")
    try:
        # strptime instead of date.fromisoformat: since Python 3.11 the latter
        # also accepts formats like '20261105', which the contract doesn't allow.
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise InvalidFieldError(f"{value!r} is not a valid 'yyyy-mm-dd' date") from exc


def parse_positive_amount(value: Any) -> float:
    """Parse a strictly positive, finite amount rounded to cents."""
    # bool is a subclass of int, so True would otherwise pass as 1.0.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidFieldError(f"expected a number, got {type(value).__name__}")
    amount = float(value)
    if not math.isfinite(amount) or amount <= 0:
        raise InvalidFieldError(f"{value!r} is not a positive finite amount")
    return round(amount, 2)


def parse_text(value: Any) -> str | None:
    """Collapse whitespace (including newlines). Blank text counts as no value."""
    if not isinstance(value, str):
        raise InvalidFieldError(f"expected a string, got {type(value).__name__}")
    text = " ".join(value.split())
    return text or None
