"""Indian phone numbers: 10 digits only (no country code)."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BeforeValidator, Field

INDIAN_PHONE_PATTERN = re.compile(r"^[6-9]\d{9}$")
INDIAN_PHONE_ERROR = "Enter a valid 10-digit Indian mobile number"


def normalize_indian_phone(value: object) -> str:
    if value is None:
        raise ValueError(INDIAN_PHONE_ERROR)
    digits = re.sub(r"\D", "", str(value).strip())
    # Accept pasted +91 / 91 prefixes, store as 10 digits only
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not INDIAN_PHONE_PATTERN.fullmatch(digits):
        raise ValueError(INDIAN_PHONE_ERROR)
    return digits


def normalize_optional_indian_phone(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return normalize_indian_phone(value)


IndianPhone = Annotated[
    str,
    BeforeValidator(normalize_indian_phone),
    Field(min_length=10, max_length=10, examples=["9876543210"]),
]

OptionalIndianPhone = Annotated[
    str | None,
    BeforeValidator(normalize_optional_indian_phone),
]
