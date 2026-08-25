import time
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.gcs import upload_bytes_to_gcs
from app.models.outlet import Outlet
from app.services.qr_branding import render_for_outlet


def build_consumer_counter_url(outlet_slug: str) -> str:
    base = settings.CONSUMER_WEB_BASE_URL.rstrip("/")
    return f"{base}/{outlet_slug}"


def _cache_busted_url(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}v={int(time.time())}"


def upload_counter_qr_image(outlet_id: uuid.UUID, png_bytes: bytes) -> str:
    blob_path = f"outlets/{outlet_id}/counter-qr.png"
    return _cache_busted_url(upload_bytes_to_gcs(blob_path, png_bytes, "image/png"))


def assign_counter_qr(db: Session, outlet: Outlet) -> None:
    consumer_url = build_consumer_counter_url(outlet.slug)
    png_bytes = render_for_outlet(
        db,
        outlet,
        kind="counter",
        url=consumer_url,
    )
    outlet.counter_qr_image_url = upload_counter_qr_image(outlet.id, png_bytes)
