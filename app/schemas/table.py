from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TableCreate(BaseModel):
    table_number: str


class TableUpdate(BaseModel):
    table_number: str | None = None
    active_status: bool | None = None


class TableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outlet_id: UUID
    table_number: str
    qr_token: str
    qr_code_image_url: str | None
    active_status: bool
    created_at: datetime
    updated_at: datetime


class CounterQrResponse(BaseModel):
    counter_qr_image_url: str | None
    counter_order_url: str
