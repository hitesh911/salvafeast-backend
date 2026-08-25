import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Table(Base, TimestampMixin):
    __tablename__ = "tables"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    outlet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outlets.id"), nullable=False, index=True
    )
    table_number: Mapped[str] = mapped_column(String(50), nullable=False)
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    qr_code_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    active_status: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    outlet: Mapped["Outlet"] = relationship("Outlet", back_populates="tables")
