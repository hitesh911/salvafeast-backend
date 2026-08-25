from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.gcs import local_media_root, use_object_storage
from app.core.sms import init_sms_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_sms_provider(settings)
    yield


app = FastAPI(title="Salva Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
