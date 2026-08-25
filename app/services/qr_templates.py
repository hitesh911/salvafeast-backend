from __future__ import annotations

from typing import Any, Literal

QrKind = Literal["table", "counter"]

TEMPLATES: dict[str, dict[str, Any]] = {
    "classic": {
        "id": "classic",
        "name": "Classic",
        "description": "Ivory card with a charcoal QR and serif-style heading.",
        "layout": "card",
        "defaults": {
            "primary": "#1C1917",
            "accent": "#F4EEE3",
            "headline": "",
            "tagline": "",
            "show_logo": True,
        },
        "qr_fill": "primary",
        "qr_back": "#FFFFFF",
        "bg": "accent",
        "text": "primary",
        "panel": "#FFFFFF",
    },
    "midnight": {
        "id": "midnight",
        "name": "Midnight",
        "description": "Dark navy poster with gold QR modules.",
        "layout": "dark",
        "defaults": {
            "primary": "#0B1220",
            "accent": "#E8C872",
            "headline": "",
            "tagline": "",
            "show_logo": True,
        },
        "qr_fill": "accent",
        "qr_back": "primary",
        "bg": "primary",
        "text": "accent",
        "panel": "#111827",
    },
    "saffron": {
        "id": "saffron",
        "name": "Saffron",
        "description": "Warm spice banner over a cream body.",
        "layout": "banner",
        "defaults": {
            "primary": "#C45C26",
            "accent": "#FFF7ED",
            "headline": "",
            "tagline": "",
            "show_logo": True,
        },
        "qr_fill": "#1C1917",
        "qr_back": "#FFFFFF",
        "bg": "accent",
        "text": "#1C1917",
        "banner_text": "#FFF7ED",
        "panel": "#FFFFFF",
    },
    "leaf": {
        "id": "leaf",
        "name": "Leaf",
        "description": "Sage cafe palette with a deep forest QR.",
        "layout": "banner",
        "defaults": {
            "primary": "#3F6F5B",
            "accent": "#F3F7F1",
            "headline": "",
            "tagline": "",
            "show_logo": True,
        },
        "qr_fill": "#1F3D32",
        "qr_back": "#FFFFFF",
        "bg": "accent",
        "text": "#1F3D32",
        "banner_text": "#F3F7F1",
        "panel": "#FFFFFF",
    },
    "banner": {
        "id": "banner",
        "name": "Banner",
        "description": "Bold color bar up top, quiet card below.",
        "layout": "banner",
        "defaults": {
            "primary": "#1D4ED8",
            "accent": "#F8FAFC",
            "headline": "",
            "tagline": "",
            "show_logo": True,
        },
        "qr_fill": "#0F172A",
        "qr_back": "#FFFFFF",
        "bg": "accent",
        "text": "#0F172A",
        "banner_text": "#FFFFFF",
        "panel": "#FFFFFF",
    },
    "stamp": {
        "id": "stamp",
        "name": "Stamp",
        "description": "Thick rounded frame like a restaurant stamp.",
        "layout": "stamp",
        "defaults": {
            "primary": "#7F1D1D",
            "accent": "#FFFBEB",
            "headline": "",
            "tagline": "",
            "show_logo": True,
        },
        "qr_fill": "#7F1D1D",
        "qr_back": "#FFFFFF",
        "bg": "accent",
        "text": "primary",
        "panel": "#FFFFFF",
    },
}

DEFAULT_TEMPLATE_ID = "classic"


def template_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "description": item["description"],
            "defaults": dict(item["defaults"]),
        }
        for item in TEMPLATES.values()
    ]


def get_template(template_id: str) -> dict[str, Any]:
    return TEMPLATES.get(template_id) or TEMPLATES[DEFAULT_TEMPLATE_ID]


def default_tagline(kind: QrKind) -> str:
    if kind == "table":
        return "Table {table}"
    return "Scan to order · Counter"


def default_config(kind: QrKind, outlet_name: str, template_id: str = DEFAULT_TEMPLATE_ID) -> dict[str, Any]:
    template = get_template(template_id)
    config = dict(template["defaults"])
    config["headline"] = outlet_name
    config["tagline"] = default_tagline(kind)
    return config
