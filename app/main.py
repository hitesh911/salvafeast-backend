from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.gcs import gcs_public_url_prefix, local_media_root, rewrite_gcs_urls_in_text, use_object_storage
from app.core.sms import init_sms_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_sms_provider(settings)
    yield


class RewritePrivateGcsUrlsMiddleware(BaseHTTPMiddleware):
    """Rewrite private storage.googleapis.com URLs in JSON to /api/v1/public/media/..."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        prefix = gcs_public_url_prefix()
        if not prefix:
            return response

        api_base = settings.API_PUBLIC_BASE_URL.strip() or str(request.base_url).rstrip("/")
        body = b""
        async for chunk in response.body_iterator:
            body += chunk if isinstance(chunk, (bytes, bytearray)) else chunk.encode("utf-8")

        text = body.decode("utf-8")
        if prefix not in text:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
                background=response.background,
            )

        rewritten = rewrite_gcs_urls_in_text(text, api_base)
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-length", "content-encoding")
        }
        return Response(
            content=rewritten.encode("utf-8"),
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
            background=response.background,
        )


app = FastAPI(title="Salva Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# After CORS so rewritten JSON still gets CORS headers.
app.add_middleware(RewritePrivateGcsUrlsMiddleware)

app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def local_media_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/local-media/"):
        # QR/logo files are overwritten in place; avoid sticky browser caches.
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


if not use_object_storage():
    media_dir = local_media_root()
    app.mount(
        "/local-media",
        StaticFiles(directory=str(media_dir)),
        name="local-media",
    )
