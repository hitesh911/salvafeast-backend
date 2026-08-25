import secrets
import time
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.gcs import upload_bytes_to_gcs
from app.models.outlet import Outlet
from app.models.table import Table
from app.services.qr_branding import render_for_outlet


def generate_qr_token() -> str:
    return secrets.token_urlsafe(16)


def build_consumer_table_url(outlet_slug: str, qr_token: str) -> str:
    base = settings.CONSUMER_WEB_BASE_URL.rstrip("/")
    return f"{base}/{outlet_slug}?t={qr_token}"


def _cache_busted_url(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}v={int(time.time())}"


def upload_table_qr_image(outlet_id: uuid.UUID, table_id: uuid.UUID, png_bytes: bytes) -> str:
    blob_path = f"outlets/{outlet_id}/tables/{table_id}.png"
    return _cache_busted_url(upload_bytes_to_gcs(blob_path, png_bytes, "image/png"))


def assign_table_qr(
    db: Session, table: Table, outlet: Outlet, qr_token: str | None = None
) -> None:
    if qr_token is None:
        qr_token = generate_qr_token()
    table.qr_token = qr_token
    consumer_url = build_consumer_table_url(outlet.slug, qr_token)
    png_bytes = render_for_outlet(
        db,
        outlet,
        kind="table",
        url=consumer_url,
        table_number=table.table_number,
    )
    table.qr_code_image_url = upload_table_qr_image(outlet.id, table.id, png_bytes)
