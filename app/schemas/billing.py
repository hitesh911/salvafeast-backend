from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PaymentMethod
from app.schemas.order import OrderDetailResponse


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outlet_id: UUID
    order_id: UUID
    invoice_number: str
    subtotal_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    total_amount: Decimal
    pdf_url: str | None
    generated_at: datetime
    created_by: UUID


class ReconciliationBreakdownItem(BaseModel):
    payment_method: PaymentMethod | None
    total_amount: Decimal
    order_count: int


class ReconciliationResponse(BaseModel):
    breakdown: list[ReconciliationBreakdownItem]
    grand_total: Decimal
    pending_collection: Decimal


class ExpenseCreate(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    description: str | None = None
    amount: Decimal = Field(gt=0)
    expense_date: date


class ExpenseUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    expense_date: date | None = None


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outlet_id: UUID
    category: str
    description: str | None
    amount: Decimal
    expense_date: date
    created_by: UUID
    created_at: datetime


class ExpenseCategoryBreakdown(BaseModel):
    category: str
    amount: Decimal


class ProfitLossResponse(BaseModel):
    revenue: Decimal
    total_expenses: Decimal
    net: Decimal
    expense_breakdown: list[ExpenseCategoryBreakdown]


class OrderSettleRequest(BaseModel):
    payment_method: PaymentMethod


class OrderSettleResponse(BaseModel):
    order: OrderDetailResponse
    invoice: InvoiceResponse
