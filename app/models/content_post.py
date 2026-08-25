import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EmbedPlatform


class ContentPost(Base):
    __tablename__ = "content_posts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    outlet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outlets.id"), nullable=False, index=True
    )
    menu_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_items.id"), nullable=True
    )
    embed_url: Mapped[str] = mapped_column(String(512), nullable=False)
    embed_platform: Mapped[EmbedPlatform] = mapped_column(
        Enum(EmbedPlatform, name="embed_platform", native_enum=False),
        nullable=False,
    )
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    created_by_user: Mapped["User"] = relationship("User")
    outlet: Mapped["Outlet"] = relationship("Outlet")
    menu_item: Mapped["MenuItem | None"] = relationship("MenuItem")
    likes: Mapped[list["ContentPostLike"]] = relationship(
        "ContentPostLike", back_populates="content_post", cascade="all, delete-orphan"
    )
    reports: Mapped[list["ContentPostReport"]] = relationship(
        "ContentPostReport", back_populates="content_post", cascade="all, delete-orphan"
    )
