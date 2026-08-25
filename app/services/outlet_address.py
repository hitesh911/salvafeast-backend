"""Compose and apply outlet display address from structured parts."""

from __future__ import annotations

from typing import Any

from app.models.outlet import Outlet

DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def compose_display_address(
    *,
    address_line1: str | None = None,
    address_line2: str | None = None,
    landmark: str | None = None,
    area: str | None = None,
    city: str | None = None,
    state: str | None = None,
    pincode: str | None = None,
) -> str | None:
    parts: list[str] = []
    for value in (
        address_line1,
        address_line2,
        landmark,
        area,
        city,
        state,
        pincode,
    ):
        cleaned = (value or "").strip()
        if cleaned:
            parts.append(cleaned)
    if not parts:
        return None
    return ", ".join(parts)[:512]


def apply_structured_address(outlet: Outlet, updates: dict[str, Any]) -> None:
    """Apply address-related updates and refresh denormalized `address` when structured fields change."""
    structured_keys = {
        "address_line1",
        "address_line2",
        "landmark",
        "area",
        "city",
        "state",
        "pincode",
    }
    for key, value in updates.items():
        setattr(outlet, key, value)

    if structured_keys & updates.keys():
        composed = compose_display_address(
            address_line1=outlet.address_line1,
            address_line2=outlet.address_line2,
            landmark=outlet.landmark,
            area=outlet.area,
            city=outlet.city,
            state=outlet.state,
            pincode=outlet.pincode,
        )
        if composed:
            outlet.address = composed
        elif "address" not in updates:
            # Structured cleared — leave freeform address unless explicitly set
            pass


def validate_opening_hours(value: dict | None) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("opening_hours must be an object")
    cleaned: dict[str, dict] = {}
    for day in DAY_KEYS:
        if day not in value:
            continue
        entry = value[day]
        if not isinstance(entry, dict):
            raise ValueError(f"opening_hours.{day} must be an object")
        closed = bool(entry.get("closed", False))
        open_t = entry.get("open")
        close_t = entry.get("close")
        if closed:
            cleaned[day] = {"open": None, "close": None, "closed": True}
            continue
        if not isinstance(open_t, str) or not isinstance(close_t, str):
            raise ValueError(f"opening_hours.{day} requires open and close times")
        cleaned[day] = {"open": open_t, "close": close_t, "closed": False}
    return cleaned or None
