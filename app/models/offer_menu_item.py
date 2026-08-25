import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OfferMenuItem(Base):
    __tablename__ = "offer_menu_items"
    __table_args__ = (UniqueConstraint("offer_id", "menu_item_id", name="uq_offer_menu_item"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offers.id", ondelete="CASCADE"), nullable=False
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_items.id"), nullable=False
    )

    offer: Mapped["Offer"] = relationship("Offer", back_populates="menu_items")
    menu_item: Mapped["MenuItem"] = relationship("MenuItem")
