from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.v1.deps import require_outlet_permission
from app.db.database import get_db
from app.models.outlet import Outlet
from app.models.outlet_qr_design import OutletQrDesign
from app.models.table import Table
from app.schemas.qr_studio import (
    QrDesignConfig,
    QrDesignResponse,
    QrDesignsResponse,
    QrDesignUpdate,
    QrTemplateItem,
)
from app.services.outlet_qr import assign_counter_qr, build_consumer_counter_url
from app.services.qr_branding import HEX_COLOR, render_for_outlet
from app.services.qr_templates import (
    DEFAULT_TEMPLATE_ID,
    TEMPLATES,
    default_config,
    template_catalog,
)
from app.services.table_qr import assign_table_qr, build_consumer_table_url

router = APIRouter(prefix="/outlets/{outlet_id}/qr-studio", tags=["qr-studio"])

QrKind = Literal["table", "counter"]


def _get_outlet(db: Session, outlet_id: UUID) -> Outlet:
    outlet = db.query(Outlet).filter(Outlet.id == outlet_id).first()
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")
    return outlet


def _validate_config(config: QrDesignConfig) -> None:
    if not HEX_COLOR.fullmatch(config.primary) or not HEX_COLOR.fullmatch(config.accent):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Colors must be hex values like #1C1917",
        )


def _design_response(
    outlet: Outlet, kind: QrKind, row: OutletQrDesign | None
) -> QrDesignResponse:
    if row is None:
        return QrDesignResponse(
            kind=kind,
            template_id=DEFAULT_TEMPLATE_ID,
            config=QrDesignConfig.model_validate(default_config(kind, outlet.name)),
            saved=False,
        )
    merged = default_config(kind, outlet.name, row.template_id)
    merged.update(row.config or {})
    return QrDesignResponse(
        kind=kind,
        template_id=row.template_id if row.template_id in TEMPLATES else DEFAULT_TEMPLATE_ID,
        config=QrDesignConfig.model_validate(merged),
        saved=True,
    )


@router.get("/templates", response_model=list[QrTemplateItem])
def list_qr_templates(
    outlet_id: UUID,
    _user=Depends(require_outlet_permission("qr_studio.view")),
):
    del outlet_id
    return template_catalog()


@router.get("/designs", response_model=QrDesignsResponse)
def get_qr_designs(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("qr_studio.view")),
):
    outlet = _get_outlet(db, outlet_id)
    rows = {
        row.kind: row
        for row in db.query(OutletQrDesign).filter(OutletQrDesign.outlet_id == outlet_id).all()
    }
    return QrDesignsResponse(
        table=_design_response(outlet, "table", rows.get("table")),
        counter=_design_response(outlet, "counter", rows.get("counter")),
        logo_url=outlet.logo_url,
    )


@router.put("/designs/{kind}", response_model=QrDesignsResponse)
def save_qr_design(
    outlet_id: UUID,
    kind: QrKind,
    payload: QrDesignUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("qr_studio.edit")),
):
    if payload.template_id not in TEMPLATES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown template")
    _validate_config(payload.config)
    outlet = _get_outlet(db, outlet_id)
    row = (
        db.query(OutletQrDesign)
        .filter(OutletQrDesign.outlet_id == outlet_id, OutletQrDesign.kind == kind)
        .first()
    )
    config = payload.config.model_dump()
    if row is None:
        row = OutletQrDesign(
            outlet_id=outlet_id,
            kind=kind,
            template_id=payload.template_id,
            config=config,
        )
        db.add(row)
    else:
        row.template_id = payload.template_id
        row.config = config
    db.flush()

    if kind == "counter":
        assign_counter_qr(db, outlet)
    else:
        tables = (
            db.query(Table)
            .filter(Table.outlet_id == outlet_id)
            .order_by(Table.table_number)
            .all()
        )
        for table in tables:
            assign_table_qr(db, table, outlet, qr_token=table.qr_token)

    db.commit()
    rows = {
        item.kind: item
        for item in db.query(OutletQrDesign).filter(OutletQrDesign.outlet_id == outlet_id).all()
    }
    return QrDesignsResponse(
        table=_design_response(outlet, "table", rows.get("table")),
        counter=_design_response(outlet, "counter", rows.get("counter")),
        logo_url=outlet.logo_url,
    )


@router.get("/preview/{kind}")
def preview_qr_design(
    outlet_id: UUID,
    kind: QrKind,
    template_id: str = Query(default=DEFAULT_TEMPLATE_ID),
    primary: str = Query(default="#1C1917"),
    accent: str = Query(default="#F4EEE3"),
    headline: str = Query(default=""),
    tagline: str = Query(default=""),
    show_logo: bool = Query(default=True),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("qr_studio.view")),
):
    if template_id not in TEMPLATES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown template")
    config = QrDesignConfig(
        primary=primary,
        accent=accent,
        headline=headline,
        tagline=tagline,
        show_logo=show_logo,
    )
    _validate_config(config)
    outlet = _get_outlet(db, outlet_id)
    if kind == "table":
        url = build_consumer_table_url(outlet.slug, "preview")
        table_number = "12"
    else:
        url = build_consumer_counter_url(outlet.slug)
        table_number = None
    png_bytes = render_for_outlet(
        db,
        outlet,
        kind=kind,
        url=url,
        table_number=table_number,
        template_id=template_id,
        config=config.model_dump(),
    )
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
