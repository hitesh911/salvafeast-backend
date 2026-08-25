import io
import re
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException, status

VPA_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+$")


def validate_upi_vpa(vpa: str) -> str:
    normalized = vpa.strip()
    if not VPA_PATTERN.match(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UPI VPA format — expected something@something",
        )
    return normalized


def decode_qr_from_image(image_bytes: bytes) -> str:
    try:
        from PIL import Image
        from pyzbar.pyzbar import decode
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="QR decoding is unavailable — install pyzbar and libzbar",
        ) from exc

    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read the uploaded image",
        ) from exc

    try:
        codes = decode(image)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="QR decoding failed — ensure libzbar is installed on the server",
        ) from exc

    if not codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No QR code detected — try a clearer photo or enter your UPI ID manually",
        )

    decoded = codes[0].data.decode("utf-8", errors="replace").strip()
    if not decoded.startswith("upi://"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This doesn't look like a UPI payment QR code",
        )
    return decoded


def parse_upi_uri(upi_uri: str) -> tuple[str, str | None]:
    parsed = urlparse(upi_uri)
    params = parse_qs(parsed.query)
    pa_values = params.get("pa")
    if not pa_values or not pa_values[0].strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="UPI QR code is missing a payee address (pa)",
        )

    payee_name_values = params.get("pn")
    payee_name = payee_name_values[0].strip() if payee_name_values else None
    if payee_name == "":
        payee_name = None

    return validate_upi_vpa(pa_values[0]), payee_name
