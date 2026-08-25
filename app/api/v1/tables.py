from uuid import UUID
import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.v1.deps import require_outlet_permission
from app.db.database import get_db
from app.models.outlet import Outlet
from app.models.table import Table
from app.schemas.table import CounterQrResponse, TableCreate, TableResponse, TableUpdate
from app.services.outlet_qr import assign_counter_qr, build_consumer_counter_url
from app.services.qr_branding import get_design, png_bytes_for_stored_or_render, render_for_outlet
from app.services.table_qr import assign_table_qr, build_consumer_table_url, generate_qr_token

router = APIRouter(prefix="/outlets/{outlet_id}", tags=["tables"])


def _versioned_media_url(url: str | None, version: int | None) -> str | None:
    """Force clients to refetch when the design/asset changes (same storage path)."""
    if not url:
        return None
    if version is None:
        return url
    return f"{url.split('?', 1)[0]}?v={version}"


def _safe_filename(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in name)
    return cleaned.strip("-") or "qr"


def _png_download(png_bytes: bytes, filename: str) -> Response:
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def _get_table(db: Session, outlet_id: UUID, table_id: UUID) -> Table:
    table = db.query(Table).filter(Table.id == table_id, Table.outlet_id == outlet_id).first()
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


def _get_outlet(db: Session, outlet_id: UUID) -> Outlet:
    outlet = db.query(Outlet).filter(Outlet.id == outlet_id).first()
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")
    return outlet


@router.get("/tables", response_model=list[TableResponse])
def list_tables(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("tables.view")),
):
    tables = (
        db.query(Table)
        .filter(Table.outlet_id == outlet_id)
        .order_by(Table.table_number)
        .all()
    )
    return tables


@router.get("/counter-qr", response_model=CounterQrResponse)
def get_counter_qr(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("tables.view")),
):
    outlet = _get_outlet(db, outlet_id)
    design = get_design(db, outlet_id, "counter")
    version = int(design.updated_at.timestamp()) if design and design.updated_at else None
    return CounterQrResponse(
        counter_qr_image_url=_versioned_media_url(outlet.counter_qr_image_url, version),
        counter_order_url=build_consumer_counter_url(outlet.slug),
    )


@router.get("/counter-qr/image")
def download_counter_qr(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("tables.view")),
):
    outlet = _get_outlet(db, outlet_id)
    png_bytes = png_bytes_for_stored_or_render(
        outlet.counter_qr_image_url,
        render_for_outlet(
            db,
            outlet,
            kind="counter",
            url=build_consumer_counter_url(outlet.slug),
        ),
    )
    return _png_download(png_bytes, "counter-order-qr.png")


@router.post("/counter-qr/regenerate", response_model=CounterQrResponse)
def regenerate_counter_qr(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("tables.edit")),
):
    outlet = _get_outlet(db, outlet_id)
    assign_counter_qr(db, outlet)
    db.commit()
    db.refresh(outlet)
    return CounterQrResponse(
        counter_qr_image_url=_versioned_media_url(
            outlet.counter_qr_image_url,
            int(time.time()),
        ),
        counter_order_url=build_consumer_counter_url(outlet.slug),
    )


@router.post("/tables", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
def create_table(
    outlet_id: UUID,
    payload: TableCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("tables.edit")),
):
    outlet = _get_outlet(db, outlet_id)
    table = Table(
        outlet_id=outlet_id,
        table_number=payload.table_number,
        qr_token=generate_qr_token(),
    )
    db.add(table)
    db.flush()
    assign_table_qr(db, table, outlet, qr_token=table.qr_token)
    db.commit()
    db.refresh(table)
    return table


@router.patch("/tables/{table_id}", response_model=TableResponse)
def update_table(
    outlet_id: UUID,
    table_id: UUID,
    payload: TableUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("tables.edit")),
):
    table = _get_table(db, outlet_id, table_id)
    if payload.table_number is not None:
        table.table_number = payload.table_number
    if payload.active_status is not None:
        table.active_status = payload.active_status
    db.commit()
    db.refresh(table)
    return table


@router.delete("/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_table(
    outlet_id: UUID,
    table_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("tables.edit")),
):
    table = _get_table(db, outlet_id, table_id)
    db.delete(table)
    db.commit()


@router.get("/tables/{table_id}/qr.png")
def download_table_qr(
    outlet_id: UUID,
    table_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("tables.view")),
):
    outlet = _get_outlet(db, outlet_id)
    table = _get_table(db, outlet_id, table_id)
    png_bytes = png_bytes_for_stored_or_render(
        table.qr_code_image_url,
        render_for_outlet(
            db,
            outlet,
            kind="table",
            url=build_consumer_table_url(outlet.slug, table.qr_token),
            table_number=table.table_number,
        ),
    )
    return _png_download(png_bytes, f"table-{_safe_filename(table.table_number)}.png")


@router.post("/tables/{table_id}/regenerate-qr", response_model=TableResponse)
def regenerate_table_qr(
    outlet_id: UUID,
    table_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("tables.edit")),
):
    outlet = _get_outlet(db, outlet_id)
    table = _get_table(db, outlet_id, table_id)
    assign_table_qr(db, table, outlet, qr_token=generate_qr_token())
    db.commit()
    db.refresh(table)
    return table
