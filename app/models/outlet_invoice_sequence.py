import uuid

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OutletInvoiceSequence(Base):
    __tablename__ = "outlet_invoice_sequences"

    outlet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outlets.id"), primary_key=True
    )
    next_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    outlet: Mapped["Outlet"] = relationship("Outlet")
