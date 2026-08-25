from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.v1.deps import require_outlet_permission
from app.core.gcs import upload_bytes_to_gcs
from app.db.database import get_db
from app.models.outlet import Outlet
from app.schemas.payment_settings import UpiPaymentSettingsResponse, UpiPaymentSettingsUpdate
from app.services.upi import decode_qr_from_image, parse_upi_uri, validate_upi_vpa

router = APIRouter(prefix="/outlets/{outlet_id}", tags=["payment-settings"])


def _get_outlet(db: Session, outlet_id: UUID) -> Outlet:
    outlet = db.query(Outlet).filter(Outlet.id == outlet_id).first()
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")
    return outlet


@router.get("/payment-settings/upi", response_model=UpiPaymentSettingsResponse)
def get_upi_payment_settings(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.view")),
):
    outlet = _get_outlet(db, outlet_id)
    return UpiPaymentSettingsResponse(
        upi_vpa=outlet.upi_vpa,
        upi_payee_name=outlet.upi_payee_name,
        upi_qr_image_url=outlet.upi_qr_image_url,
    )


@router.patch("/payment-settings/upi", response_model=UpiPaymentSettingsResponse)
def update_upi_payment_settings(
    outlet_id: UUID,
    payload: UpiPaymentSettingsUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.edit")),
):
    outlet = _get_outlet(db, outlet_id)
    outlet.upi_vpa = validate_upi_vpa(payload.upi_vpa)
    outlet.upi_payee_name = payload.upi_payee_name.strip() if payload.upi_payee_name else None
    db.commit()
    db.refresh(outlet)
    return UpiPaymentSettingsResponse(
        upi_vpa=outlet.upi_vpa,
        upi_payee_name=outlet.upi_payee_name,
        upi_qr_image_url=outlet.upi_qr_image_url,
    )


@router.post(
    "/payment-settings/upi/from-qr-image",
    response_model=UpiPaymentSettingsResponse,
)
async def update_upi_from_qr_image(
    outlet_id: UUID,
    qr_image: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.edit")),
):
    outlet = _get_outlet(db, outlet_id)
    image_bytes = await qr_image.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image is empty",
        )

    upi_uri = decode_qr_from_image(image_bytes)
    upi_vpa, upi_payee_name = parse_upi_uri(upi_uri)

    content_type = qr_image.content_type or "image/jpeg"
    blob_name = f"outlets/{outlet_id}/payment/upi-qr.jpg"
    upi_qr_image_url = upload_bytes_to_gcs(blob_name, image_bytes, content_type)

    outlet.upi_vpa = upi_vpa
    outlet.upi_payee_name = upi_payee_name
    outlet.upi_qr_image_url = upi_qr_image_url
    db.commit()
    db.refresh(outlet)

    return UpiPaymentSettingsResponse(
        upi_vpa=upi_vpa,
        upi_payee_name=upi_payee_name,
        upi_qr_image_url=upi_qr_image_url,
    )
