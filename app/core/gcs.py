import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, status
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.cloud import storage
from google.oauth2 import service_account
from jose import JWTError, jwt

from app.core.config import settings

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_UPLOAD_PURPOSE = "menu_image_upload"


def gcs_configured() -> bool:
    """True when a bucket is set. Auth is ADC (Cloud Run) or optional JSON key."""
    return bool(settings.GCS_BUCKET_NAME.strip())


def use_object_storage() -> bool:
    """Local disk when SALVA_ENV=local; GCS when dev/production."""
    env = settings.SALVA_ENV.strip().lower()
    if env == "local":
        return False
    if env not in ("dev", "production"):
        raise ValueError(
            f"Unknown SALVA_ENV: {settings.SALVA_ENV!r} (expected local|dev|production)"
        )
    if not gcs_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GCS_BUCKET_NAME is required when SALVA_ENV is dev or production",
        )
    return True


def local_media_root() -> Path:
    root = Path(settings.LOCAL_MEDIA_DIR)
    if not root.is_absolute():
        root = _BACKEND_ROOT / root
    root.mkdir(parents=True, exist_ok=True)
    return root


@lru_cache(maxsize=1)
def _json_key_path() -> Path | None:
    raw = settings.GCS_SERVICE_ACCOUNT_JSON_PATH.strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = _BACKEND_ROOT / path
    return path if path.is_file() else None


def _get_gcs_client_and_bucket():
    """
    Prefer optional JSON key (local/dev override). Otherwise Application Default
    Credentials — on Cloud Run that is the runtime service account via the
    metadata server (no key file in env).
    """
    key_path = _json_key_path()
    if key_path is not None:
        credentials = service_account.Credentials.from_service_account_file(
            str(key_path)
        )
        client = storage.Client(
            credentials=credentials, project=credentials.project_id
        )
        return client, client.bucket(settings.GCS_BUCKET_NAME)

    credentials, project = google_auth_default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    project_id = settings.GCS_PROJECT_ID.strip() or project
    client = storage.Client(credentials=credentials, project=project_id)
    return client, client.bucket(settings.GCS_BUCKET_NAME)


def _signed_url_kwargs(client: storage.Client) -> dict:
    """
    V4 signing with a private key works from a JSON SA file.
    On Cloud Run / GCE, ADC has no private key — use IAMCredentials signBlob
    via service_account_email + access_token (SA needs iam.serviceAccounts.signBlob).
    """
    credentials = getattr(client, "_credentials", None)
    if credentials is None:
        return {}

    # Service-account JSON credentials can sign locally.
    if isinstance(credentials, service_account.Credentials):
        return {}

    if not getattr(credentials, "valid", False) or not getattr(
        credentials, "token", None
    ):
        credentials.refresh(GoogleAuthRequest())

    email = settings.GCS_SIGNING_SERVICE_ACCOUNT.strip() or None
    if not email:
        email = getattr(credentials, "service_account_email", None)
        if email == "default":
            # Force metadata refresh so "default" resolves to the real SA email.
            credentials.refresh(GoogleAuthRequest())
            email = getattr(credentials, "service_account_email", None)
            if email == "default":
                email = None

    if not email or not credentials.token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Cannot sign GCS URLs with ADC: set GCS_SIGNING_SERVICE_ACCOUNT "
                "to the Cloud Run runtime SA email, and ensure that SA can signBlob"
            ),
        )

    return {
        "service_account_email": email,
        "access_token": credentials.token,
    }


def _public_gcs_url(blob_name: str) -> str:
    return f"https://storage.googleapis.com/{settings.GCS_BUCKET_NAME}/{blob_name}"


def gcs_public_url_prefix() -> str:
    bucket = settings.GCS_BUCKET_NAME.strip()
    if not bucket:
        return ""
    return f"https://storage.googleapis.com/{bucket}/"


def blob_name_from_media_url(url: str | None) -> str | None:
    """Extract object path from a GCS public URL or our /public/media proxy URL."""
    if not url:
        return None
    clean = url.split("?", 1)[0].strip()
    prefix = gcs_public_url_prefix()
    if prefix and clean.startswith(prefix):
        return clean[len(prefix) :].lstrip("/")

    marker = "/api/v1/public/media/"
    idx = clean.find(marker)
    if idx != -1:
        return clean[idx + len(marker) :].lstrip("/")
    return None


def rewrite_gcs_url_for_client(url: str, api_base: str) -> str:
    """
    Org policy blocks public bucket ACLs, so browsers cannot load storage.googleapis.com
    URLs. Rewrite them to the authenticated-backend media proxy (still unauthenticated
    HTTP GET — access is via unguessable object paths).
    """
    blob_name = blob_name_from_media_url(url)
    if not blob_name:
        return url
    # Already a proxy URL pointing at this API — leave as-is (preserve query string).
    if "/api/v1/public/media/" in url.split("?", 1)[0] and api_base and url.startswith(
        api_base.rstrip("/")
    ):
        return url

    base = api_base.rstrip("/")
    path = quote(blob_name, safe="/")
    suffix = ""
    if "?" in url:
        suffix = "?" + url.split("?", 1)[1]
    return f"{base}/api/v1/public/media/{path}{suffix}"


def rewrite_gcs_urls_in_text(text: str, api_base: str) -> str:
    prefix = gcs_public_url_prefix()
    if not prefix or prefix not in text or not api_base.strip():
        return text
    # Replace bare GCS prefix; blob paths stay as stored (may include %20 etc.).
    media_base = api_base.rstrip("/") + "/api/v1/public/media/"
    return text.replace(prefix, media_base)


def open_gcs_blob(blob_name: str):
    """Return (blob, content_type) after existence check."""
    if ".." in blob_name or blob_name.startswith(("/", "\\")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path")
    normalized = blob_name.lstrip("/")
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path")

    if not use_object_storage():
        path = local_media_root() / normalized
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return path, None

    _, bucket = _get_gcs_client_and_bucket()
    blob = bucket.blob(normalized)
    if not blob.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    blob.reload()
    return blob, (blob.content_type or "application/octet-stream")


def _public_api_base_url() -> str:
    base = settings.LOCAL_MEDIA_BASE_URL.rstrip("/")
    suffix = "/local-media"
    if base.endswith(suffix):
        return base[: -len(suffix)]
    return base


def _local_public_url(blob_name: str) -> str:
    base = settings.LOCAL_MEDIA_BASE_URL.rstrip("/")
    return f"{base}/{blob_name.replace(chr(92), '/')}"


def create_local_menu_upload_token(
    outlet_id: uuid.UUID, blob_name: str, content_type: str
) -> str:
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.GCS_SIGNED_URL_EXPIRE_MINUTES
    )
    payload = {
        "purpose": _LOCAL_UPLOAD_PURPOSE,
        "outlet_id": str(outlet_id),
        "blob_name": blob_name,
        "content_type": content_type,
        "exp": expires,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_local_menu_upload_token(outlet_id: uuid.UUID, token: str) -> tuple[str, str]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired upload token",
        ) from exc

    if payload.get("purpose") != _LOCAL_UPLOAD_PURPOSE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid upload token",
        )
    if payload.get("outlet_id") != str(outlet_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Upload token does not match outlet",
        )

    blob_name = payload.get("blob_name")
    content_type = payload.get("content_type")
    if not isinstance(blob_name, str) or not isinstance(content_type, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid upload token",
        )
    return blob_name, content_type


def _upload_bytes_locally(blob_name: str, data: bytes) -> str:
    target = local_media_root() / blob_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return _local_public_url(blob_name)


def upload_bytes_to_gcs(blob_name: str, data: bytes, content_type: str) -> str:
    if not use_object_storage():
        return _upload_bytes_locally(blob_name, data)

    _, bucket = _get_gcs_client_and_bucket()
    blob = bucket.blob(blob_name)
    blob.upload_from_string(data, content_type=content_type)
    return _public_gcs_url(blob_name)


def generate_menu_image_upload_url(
    outlet_id: uuid.UUID, filename: str, content_type: str
) -> tuple[str, str]:
    blob_name = f"outlets/{outlet_id}/menu/{uuid.uuid4()}-{filename}"

    if not use_object_storage():
        token = create_local_menu_upload_token(outlet_id, blob_name, content_type)
        api_base = _public_api_base_url()
        upload_url = (
            f"{api_base}/api/v1/outlets/{outlet_id}/menu-images/local-upload"
            f"?token={quote(token, safe='')}"
        )
        return upload_url, _local_public_url(blob_name)

    client, bucket = _get_gcs_client_and_bucket()
    blob = bucket.blob(blob_name)

    upload_url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=settings.GCS_SIGNED_URL_EXPIRE_MINUTES),
        method="PUT",
        content_type=content_type,
        **_signed_url_kwargs(client),
    )
    return upload_url, _public_gcs_url(blob_name)


def fetch_stored_bytes(url: str | None) -> bytes | None:
    if not url:
        return None
    # Cache-bust query params (?v=...) must not affect storage path lookup.
    clean = url.split("?", 1)[0]
    local_base = settings.LOCAL_MEDIA_BASE_URL.rstrip("/")
    if clean.startswith(local_base + "/"):
        relative = clean[len(local_base) + 1 :].lstrip("/")
        path = local_media_root() / relative
        if path.is_file():
            return path.read_bytes()
        return None

    blob_name = blob_name_from_media_url(clean)
    if blob_name:
        try:
            if use_object_storage():
                _, gcs_bucket = _get_gcs_client_and_bucket()
                return gcs_bucket.blob(blob_name).download_as_bytes()
            path = local_media_root() / blob_name
            if path.is_file():
                return path.read_bytes()
            return None
        except HTTPException:
            pass
        except Exception:
            return None

    try:
        import httpx

        response = httpx.get(url, timeout=8.0, follow_redirects=True)
        if response.status_code >= 400:
            return None
        return response.content
    except Exception:
        return None
