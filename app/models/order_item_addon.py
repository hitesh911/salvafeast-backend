import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrderItemAddon(Base):
    __tablename__ = "order_item_addons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False
    )
    addon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_item_addons.id"), nullable=False
    )
    addon_price_at_order: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    order_item: Mapped["OrderItem"] = relationship("OrderItem", back_populates="addons")
    addon: Mapped["MenuItemAddon"] = relationship("MenuItemAddon")
