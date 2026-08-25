from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.enums import UserGender
from app.schemas.auth import MembershipSummaryResponse


class UserProfileResponse(BaseModel):
    id: UUID
    phone: str
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    date_of_birth: date | None = None
    gender: UserGender | None = None
    dietary_preferences: list[str] = []
    profile_completed_at: datetime | None = None
    memberships: list[MembershipSummaryResponse] = []


class UserProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    date_of_birth: date | None = None
    gender: UserGender | None = None
    dietary_preferences: list[str] | None = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("dietary_preferences")
    @classmethod
    def _normalize_dietary(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        allowed = {"veg", "vegan", "non_veg", "jain", "eggetarian"}
        cleaned = []
        for item in value:
            key = item.strip().lower().replace(" ", "_")
            if key in allowed and key not in cleaned:
                cleaned.append(key)
        return cleaned
