import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models.invoice import Invoice
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outlet import Outlet

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


@dataclass
class InvoiceLineItem:
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


def _format_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _order_item_unit_price(item: OrderItem) -> Decimal:
    addon_total = sum(addon.addon_price_at_order for addon in item.addons)
    return item.item_price_at_order + addon_total


def _order_item_line_total(item: OrderItem) -> Decimal:
    return _order_item_unit_price(item) * item.quantity


def _build_line_items(order: Order) -> list[InvoiceLineItem]:
    lines: list[InvoiceLineItem] = []
    for item in order.items:
        name = item.menu_item.name if item.menu_item else "Item"
        if item.variant:
            name = f"{name} ({item.variant.name})"
        unit_price = _order_item_unit_price(item)
        lines.append(
            InvoiceLineItem(
                name=name,
                quantity=item.quantity,
                unit_price=unit_price,
                line_total=_order_item_line_total(item),
            )
        )
    return lines


def _pdf_safe(text: str | None) -> str:
    """Core PDF fonts are Latin-1; keep readable text when possible."""
    if not text:
        return ""
    return text.encode("latin-1", "replace").decode("latin-1")


def _render_invoice_pdf_fpdf(
    outlet: Outlet,
    order: Order,
    invoice: Invoice,
    line_items: list[InvoiceLineItem],
) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _pdf_safe(outlet.name), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", size=11)
    if outlet.address:
        pdf.multi_cell(0, 6, _pdf_safe(outlet.address))
    if outlet.phone:
        pdf.cell(0, 6, _pdf_safe(f"Phone: {outlet.phone}"), new_x="LMARGIN", new_y="NEXT")
    if outlet.gst_number:
        pdf.cell(
            0,
            6,
            _pdf_safe(f"GSTIN: {outlet.gst_number}"),
            new_x="LMARGIN",
            new_y="NEXT",
        )

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(
        0,
        6,
        _pdf_safe(f"Invoice: {invoice.invoice_number}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_font("Helvetica", size=11)
    pdf.cell(
        0,
        6,
        f"Date: {invoice.generated_at.strftime('%d %b %Y')}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(0, 6, f"Order ID: {order.id}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    col_widths = (80, 20, 40, 40)
    headers = ("Item", "Qty", "Unit Price", "Line Total")
    pdf.set_font("Helvetica", "B", 10)
    for width, header in zip(col_widths, headers, strict=True):
        pdf.cell(width, 8, header, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", size=10)
    for line in line_items:
        pdf.cell(col_widths[0], 8, _pdf_safe(line.name)[:42], border=1)
        pdf.cell(col_widths[1], 8, str(line.quantity), border=1)
        pdf.cell(col_widths[2], 8, _format_money(line.unit_price), border=1)
        pdf.cell(col_widths[3], 8, _format_money(line.line_total), border=1)
        pdf.ln()

    pdf.ln(8)
    pdf.set_font("Helvetica", size=11)
    totals = [
        ("Subtotal", invoice.subtotal_amount),
        ("Discount", invoice.discount_amount),
        ("Taxable Amount", invoice.taxable_amount),
        ("CGST", invoice.cgst_amount),
        ("SGST", invoice.sgst_amount),
        ("Total", invoice.total_amount),
    ]
    for label, amount in totals:
        pdf.cell(120)
        style = "B" if label == "Total" else ""
        pdf.set_font("Helvetica", style, 11)
        pdf.cell(35, 7, label, border=0)
        pdf.cell(25, 7, _format_money(amount), border=0, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def _render_invoice_html(
    outlet: Outlet,
    order: Order,
    invoice: Invoice,
    line_items: list[InvoiceLineItem],
) -> str:
    return _jinja_env.get_template("invoice.html").render(
        outlet_name=outlet.name,
        outlet_address=outlet.address,
        outlet_phone=outlet.phone,
        gst_number=outlet.gst_number,
        invoice_number=invoice.invoice_number,
        generated_date=invoice.generated_at.strftime("%d %b %Y"),
        order_id=str(order.id),
        line_items=[
            {
                "name": line.name,
                "quantity": line.quantity,
                "unit_price": _format_money(line.unit_price),
                "line_total": _format_money(line.line_total),
            }
            for line in line_items
        ],
        subtotal_amount=_format_money(invoice.subtotal_amount),
        discount_amount=_format_money(invoice.discount_amount),
        taxable_amount=_format_money(invoice.taxable_amount),
        cgst_amount=_format_money(invoice.cgst_amount),
        sgst_amount=_format_money(invoice.sgst_amount),
        total_amount=_format_money(invoice.total_amount),
    )


def render_invoice_pdf(
    outlet: Outlet,
    order: Order,
    invoice: Invoice,
) -> bytes:
    line_items = _build_line_items(order)
    html = _render_invoice_html(outlet, order, invoice, line_items)

    try:
        from weasyprint import HTML

        return HTML(string=html).write_pdf()
    except Exception as exc:
        # WeasyPrint needs GTK/Pango on Windows; fall back so settle still works.
        logger.warning(
            "WeasyPrint PDF failed (%s); using FPDF fallback",
            exc,
        )
        return _render_invoice_pdf_fpdf(outlet, order, invoice, line_items)
