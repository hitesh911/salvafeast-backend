from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse

from app.core.gcs import open_gcs_blob, use_object_storage

router = APIRouter(tags=["public-media"])


@router.get("/media/{object_path:path}")
def get_public_media(object_path: str):
    """
    Stream private GCS (or local) objects for <img src> / downloads.

    Needed because org policy prevents allUsers on the bucket, so direct
    storage.googleapis.com URLs return 403 in the browser.
    """
    handle, content_type = open_gcs_blob(object_path)
    headers = {"Cache-Control": "public, max-age=86400"}

    if not use_object_storage():
        path = Path(handle)
        return FileResponse(
            path,
            media_type=content_type or "application/octet-stream",
            headers=headers,
        )

    blob = handle

    def _iter():
        with blob.open("rb") as f:
            while True:
                chunk = f.read(256 * 1024)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        _iter(),
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )
