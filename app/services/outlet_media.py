from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.gcs import upload_bytes_to_gcs

ALLOWED_LOGO_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
MAX_LOGO_BYTES = 5 * 1024 * 1024


async def store_outlet_logo(outlet_id: UUID, file: UploadFile) -> str:
    return await _store_outlet_image(outlet_id, file, folder="logo", label="Logo")


async def store_outlet_cover(outlet_id: UUID, file: UploadFile) -> str:
    return await _store_outlet_image(outlet_id, file, folder="cover", label="Cover")


async def store_user_avatar(user_id: UUID, file: UploadFile) -> str:
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image is empty",
        )
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Avatar must be 5 MB or smaller",
        )
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Avatar must be a JPEG, PNG, WebP, or GIF image",
        )
    original = Path(file.filename or "avatar").name
    safe_name = original.replace("\\", "_").replace("/", "_") or "avatar"
    stem = Path(safe_name).stem[:80] or "avatar"
    suffix = Path(safe_name).suffix[:10]
    blob_name = f"users/{user_id}/avatar/{uuid4()}-{stem}{suffix}"
    return upload_bytes_to_gcs(blob_name, data, content_type)


async def _store_outlet_image(
    outlet_id: UUID, file: UploadFile, *, folder: str, label: str
) -> str:
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image is empty",
        )
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} must be 5 MB or smaller",
        )
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} must be a JPEG, PNG, WebP, or GIF image",
        )
    original = Path(file.filename or folder).name
    safe_name = original.replace("\\", "_").replace("/", "_") or folder
    stem = Path(safe_name).stem[:80] or folder
    suffix = Path(safe_name).suffix[:10]
    blob_name = f"outlets/{outlet_id}/{folder}/{uuid4()}-{stem}{suffix}"
    return upload_bytes_to_gcs(blob_name, data, content_type)
