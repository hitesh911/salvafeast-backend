import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Enum, Float, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import OutletType, VerificationStatus


class Outlet(Base, TimestampMixin):
    __tablename__ = "outlets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    landmark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    area: Mapped[str | None] = mapped_column(String(128), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    whatsapp_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cuisine_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    opening_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fssai_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cost_for_two: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_pure_veg: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    outlet_type: Mapped[OutletType | None] = mapped_column(
        Enum(OutletType, name="outlet_type", native_enum=False),
        nullable=True,
    )
    gst_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    active_status: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status", native_enum=False),
        default=VerificationStatus.pending,
        nullable=False,
    )
    require_customer_login: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_prepaid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    upi_vpa: Mapped[str | None] = mapped_column(String(255), nullable=True)
    upi_payee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    upi_qr_image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    counter_qr_image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    gst_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    invoice_prefix: Mapped[str | None] = mapped_column(String(20), nullable=True)

    memberships: Mapped[list["OutletMembership"]] = relationship(
        "OutletMembership", back_populates="outlet"
    )
    roles: Mapped[list["Role"]] = relationship("Role", back_populates="outlet")
    tables: Mapped[list["Table"]] = relationship("Table", back_populates="outlet")
    qr_designs: Mapped[list["OutletQrDesign"]] = relationship(
        "OutletQrDesign", back_populates="outlet"
    )
