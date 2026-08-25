import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import DietaryType


class MenuItem(Base, TimestampMixin):
    __tablename__ = "menu_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    outlet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outlets.id"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    dietary_type: Mapped[DietaryType | None] = mapped_column(
        Enum(DietaryType, name="dietary_type", native_enum=False),
        nullable=True,
    )
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    category: Mapped["MenuCategory"] = relationship("MenuCategory", back_populates="items")
    images: Mapped[list["MenuItemImage"]] = relationship(
        "MenuItemImage", back_populates="menu_item", cascade="all, delete-orphan"
    )
    variants: Mapped[list["MenuItemVariant"]] = relationship(
        "MenuItemVariant", back_populates="menu_item", cascade="all, delete-orphan"
    )
    addons: Mapped[list["MenuItemAddon"]] = relationship(
        "MenuItemAddon", back_populates="menu_item", cascade="all, delete-orphan"
    )
