from pydantic import BaseModel, Field


class UpiPaymentSettingsUpdate(BaseModel):
    upi_vpa: str = Field(min_length=1, max_length=255)
    upi_payee_name: str | None = Field(default=None, max_length=255)


class UpiPaymentSettingsResponse(BaseModel):
    upi_vpa: str | None = None
    upi_payee_name: str | None
    upi_qr_image_url: str | None = None
