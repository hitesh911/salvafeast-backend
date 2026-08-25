"""Detect embed platform from Instagram/YouTube URLs."""

import re
from urllib.parse import urlparse

from app.models.enums import EmbedPlatform

_INSTAGRAM_HOST = re.compile(r"(^|\.)instagram\.com$", re.IGNORECASE)
_INSTAGRAM_PATH = re.compile(r"^/(p|reel)/", re.IGNORECASE)
_YOUTUBE_HOST = re.compile(r"(^|\.)youtube\.com$", re.IGNORECASE)
_YOUTUBE_SHORT_HOST = re.compile(r"(^|\.)youtu\.be$", re.IGNORECASE)
_YOUTUBE_WATCH_PATH = re.compile(r"^/watch/?$", re.IGNORECASE)


class InvalidEmbedUrlError(ValueError):
    """Raised when URL is not a supported Instagram or YouTube embed."""


def detect_embed_platform(url: str) -> EmbedPlatform:
    normalized = url.strip()
    if not normalized:
        raise InvalidEmbedUrlError("Embed URL is required")

    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        raise InvalidEmbedUrlError("Embed URL must use http or https")

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    path = parsed.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"

    if _INSTAGRAM_HOST.search(host) and _INSTAGRAM_PATH.match(path):
        return EmbedPlatform.instagram

    if _YOUTUBE_SHORT_HOST.search(host) and len(path) > 1:
        return EmbedPlatform.youtube

    if _YOUTUBE_HOST.search(host) and _YOUTUBE_WATCH_PATH.match(path):
        return EmbedPlatform.youtube

    raise InvalidEmbedUrlError(
        "Embed URL must be an Instagram post/reel or YouTube watch link"
    )
