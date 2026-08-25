from decimal import Decimal
from uuid import UUID
import logging

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.gcs import upload_bytes_to_gcs
from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_status_log import OrderStatusLog
from app.models.outlet import Outlet
from app.services.invoice_pdf import render_invoice_pdf

logger = logging.getLogger(__name__)

SETTLEABLE_STATUSES = {
    OrderStatus.placed,
    OrderStatus.accepted,
    OrderStatus.preparing,
    OrderStatus.ready,
    OrderStatus.served,
}


def compute_gst_amounts(
    taxable_amount: Decimal, gst_rate_percent: Decimal | None
) -> tuple[Decimal, Decimal, Decimal]:
    if gst_rate_percent is None:
        return Decimal("0"), Decimal("0"), taxable_amount

    total_gst = (taxable_amount * gst_rate_percent / Decimal("100")).quantize(Decimal("0.01"))
    cgst = (total_gst / 2).quantize(Decimal("0.01"))
    sgst = total_gst - cgst
    invoice_total = taxable_amount + cgst + sgst
    return cgst, sgst, invoice_total


def allocate_invoice_number(db: Session, outlet_id: UUID) -> int:
    db.execute(
        text(
            "INSERT INTO outlet_invoice_sequences (outlet_id, next_number) "
            "VALUES (:outlet_id, 1) ON CONFLICT (outlet_id) DO NOTHING"
        ),
        {"outlet_id": outlet_id},
    )
    allocated = db.execute(
        text(
            "UPDATE outlet_invoice_sequences "
            "SET next_number = next_number + 1 "
            "WHERE outlet_id = :outlet_id "
            "RETURNING next_number - 1 AS allocated_number"
        ),
        {"outlet_id": outlet_id},
    ).scalar_one()
    return int(allocated)


def format_invoice_number(outlet: Outlet, sequence_number: int) -> str:
    prefix = outlet.invoice_prefix or "INV"
    return f"{prefix}-{sequence_number:04d}"


def _load_order_for_invoice(db: Session, outlet_id: UUID, order_id: UUID) -> Order:
    order = (
        db.query(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.addons),
            selectinload(Order.items).selectinload(OrderItem.menu_item),
            selectinload(Order.items).selectinload(OrderItem.variant),
        )
        .filter(Order.id == order_id, Order.outlet_id == outlet_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def get_or_create_invoice(
    db: Session,
    outlet_id: UUID,
    order_id: UUID,
    created_by: UUID,
) -> Invoice:
    existing = (
        db.query(Invoice)
        .filter(Invoice.order_id == order_id, Invoice.outlet_id == outlet_id)
        .first()
    )
    if existing is not None:
        return existing

    order = _load_order_for_invoice(db, outlet_id, order_id)
    outlet = db.query(Outlet).filter(Outlet.id == outlet_id).first()
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")

    subtotal_amount = order.subtotal_amount
    discount_amount = order.discount_amount
    taxable_amount = subtotal_amount - discount_amount
    cgst_amount, sgst_amount, total_amount = compute_gst_amounts(
        taxable_amount, outlet.gst_rate_percent
    )

    sequence_number = allocate_invoice_number(db, outlet_id)
    invoice_number = format_invoice_number(outlet, sequence_number)

    invoice = Invoice(
        outlet_id=outlet_id,
        order_id=order_id,
        invoice_number=invoice_number,
        subtotal_amount=subtotal_amount,
        discount_amount=discount_amount,
        taxable_amount=taxable_amount,
        cgst_amount=cgst_amount,
        sgst_amount=sgst_amount,
        total_amount=total_amount,
        created_by=created_by,
    )
    db.add(invoice)
    db.flush()

    try:
        pdf_bytes = render_invoice_pdf(outlet, order, invoice)
        blob_name = f"outlets/{outlet_id}/invoices/{invoice_number}.pdf"
        invoice.pdf_url = upload_bytes_to_gcs(blob_name, pdf_bytes, "application/pdf")
    except Exception:
        logger.exception("Invoice PDF generation failed for order %s", order_id)

    return invoice


def create_invoice_for_order(
    db: Session,
    outlet_id: UUID,
    order_id: UUID,
    created_by: UUID,
) -> Invoice:
    invoice = get_or_create_invoice(db, outlet_id, order_id, created_by)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Invoice)
            .filter(Invoice.order_id == order_id, Invoice.outlet_id == outlet_id)
            .first()
        )
        if existing is None:
            raise
        return existing

    db.refresh(invoice)
    return invoice


def settle_order(
    db: Session,
    outlet_id: UUID,
    order_id: UUID,
    payment_method: PaymentMethod,
    changed_by: UUID,
) -> tuple[Order, Invoice]:
    order = _load_order_for_invoice(db, outlet_id, order_id)

    if order.payment_status == PaymentStatus.paid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="already settled",
        )
    if order.status not in SETTLEABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must be open before it can be settled",
        )

    order.payment_status = PaymentStatus.paid
    order.payment_method = payment_method
    order.status = OrderStatus.completed
    db.add(
        OrderStatusLog(
            order_id=order.id,
            status=OrderStatus.completed,
            changed_by=changed_by,
        )
    )

    invoice = get_or_create_invoice(db, outlet_id, order_id, changed_by)
    db.commit()
    db.refresh(order)
    db.refresh(invoice)
    return order, invoice
