from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EmbedPlatform, VerificationStatus


class ContentPostCreateRequest(BaseModel):
    outlet_id: UUID
    menu_item_id: UUID | None = None
    embed_url: str = Field(min_length=1, max_length=512)
    caption: str | None = None


class ContentPostReportRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=512)


class ContentPostOutletSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    logo_url: str | None
    verification_status: VerificationStatus


class ContentPostMenuItemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    base_price: Decimal


class ContentPostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by_user_id: UUID
    outlet_id: UUID
    menu_item_id: UUID | None
    embed_url: str
    embed_platform: EmbedPlatform
    caption: str | None
    like_count: int
    report_count: int
    is_hidden: bool
    created_at: datetime
    outlet_verification_status: VerificationStatus


class ContentPostFeedItem(BaseModel):
    id: UUID
    created_by_user_id: UUID
    embed_url: str
    embed_platform: EmbedPlatform
    caption: str | None
    like_count: int
    created_at: datetime
    outlet: ContentPostOutletSummary
    menu_item: ContentPostMenuItemSummary | None = None
    distance_km: float | None = None
    has_current_user_liked: bool


class PaginatedContentPostFeed(BaseModel):
    items: list[ContentPostFeedItem]
    total: int
    page: int
    page_size: int


class ContentPostLikeResponse(BaseModel):
    liked: bool
    like_count: int


class PlatformContentPostListItem(BaseModel):
    id: UUID
    embed_url: str
    embed_platform: EmbedPlatform
    caption: str | None
    like_count: int
    report_count: int
    is_hidden: bool
    created_at: datetime
    outlet_id: UUID
    outlet_name: str
    created_by_user_id: UUID


class PaginatedPlatformContentPosts(BaseModel):
    items: list[PlatformContentPostListItem]
    total: int
    page: int
    page_size: int


PlatformContentPostSort = Literal["most_reported"]
