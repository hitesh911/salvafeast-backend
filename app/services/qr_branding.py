from __future__ import annotations

import io
import re
from uuid import UUID

from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy.orm import Session

from app.core.gcs import fetch_stored_bytes
from app.core.qr import generate_qr_image, generate_qr_png, load_font
from app.models.outlet import Outlet
from app.models.outlet_qr_design import OutletQrDesign
from app.services.qr_templates import (
    DEFAULT_TEMPLATE_ID,
    QrKind,
    default_config,
    get_template,
)

CANVAS_W = 1080
CANVAS_H = 1350
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _hex_to_rgb(value: str, fallback: str = "#111827") -> tuple[int, int, int]:
    raw = value if HEX_COLOR.fullmatch(value or "") else fallback
    raw = raw.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _resolve_color(token: str, primary: str, accent: str) -> str:
    if token == "primary":
        return primary
    if token == "accent":
        return accent
    return token


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines[:4]


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    y: int,
    fill: tuple[int, int, int],
    max_width: int,
    canvas_w: int = CANVAS_W,
) -> int:
    lines = _wrap_text(draw, text, font, max_width)
    line_h = int(getattr(font, "size", 36) * 1.2)
    for index, line in enumerate(lines):
        width = draw.textlength(line, font=font)
        x = int((canvas_w - width) / 2)
        draw.text((x, y + index * line_h), line, font=font, fill=fill)
    return y + len(lines) * line_h


def _rounded_rect(size: tuple[int, int], radius: int, color: tuple[int, int, int, int]) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=color)
    return image


def _inlay_logo(qr: Image.Image, logo_bytes: bytes | None) -> Image.Image:
    if not logo_bytes:
        return qr
    try:
        logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    except Exception:
        return qr
    qr_size = qr.width
    badge = int(qr_size * 0.28)
    logo.thumbnail((badge - 16, badge - 16), Image.Resampling.LANCZOS)
    plate = Image.new("RGBA", (badge, badge), (0, 0, 0, 0))
    plate_draw = ImageDraw.Draw(plate)
    plate_draw.rounded_rectangle((0, 0, badge - 1, badge - 1), radius=badge // 5, fill=(255, 255, 255, 255))
    ox = (badge - logo.width) // 2
    oy = (badge - logo.height) // 2
    plate.paste(logo, (ox, oy), logo)
    pos = ((qr_size - badge) // 2, (qr_size - badge) // 2)
    composed = qr.convert("RGBA")
    composed.alpha_composite(plate, pos)
    return composed


def _load_logo_bytes(outlet: Outlet, show_logo: bool) -> bytes | None:
    if not show_logo:
        return None
    return fetch_stored_bytes(outlet.logo_url)


def render_branded_qr_png(
    *,
    url: str,
    outlet: Outlet,
    kind: QrKind,
    template_id: str,
    config: dict,
    table_number: str | None = None,
) -> bytes:
    template = get_template(template_id)
    primary = str(config.get("primary") or template["defaults"]["primary"])
    accent = str(config.get("accent") or template["defaults"]["accent"])
    headline = str(config.get("headline") or outlet.name).strip() or outlet.name
    tagline = str(config.get("tagline") or "")
    if table_number:
        tagline = tagline.replace("{table}", table_number)
    tagline = tagline.replace("{outlet}", outlet.name)
    headline = headline.replace("{outlet}", outlet.name)
    if kind == "table" and table_number and "{table}" not in str(config.get("tagline") or ""):
        if not tagline:
            tagline = f"Table {table_number}"
    show_logo = bool(config.get("show_logo", True))

    qr_fill = _resolve_color(str(template["qr_fill"]), primary, accent)
    qr_back = _resolve_color(str(template["qr_back"]), primary, accent)
    bg = _hex_to_rgb(_resolve_color(str(template["bg"]), primary, accent))
    text = _hex_to_rgb(_resolve_color(str(template["text"]), primary, accent))
    panel = _hex_to_rgb(str(template.get("panel") or "#FFFFFF"))
    banner_text = _hex_to_rgb(
        _resolve_color(str(template.get("banner_text") or "#FFFFFF"), primary, accent)
    )
    primary_rgb = _hex_to_rgb(primary)

    logo_bytes = _load_logo_bytes(outlet, show_logo)
    qr = generate_qr_image(
        url,
        fill_color=qr_fill,
        back_color=qr_back,
        box_size=14,
        border=2,
        high_ecc=bool(logo_bytes),
    )
    qr = qr.resize((720, 720), Image.Resampling.NEAREST)
    qr = _inlay_logo(qr, logo_bytes)

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), bg)
    draw = ImageDraw.Draw(canvas)
    layout = template["layout"]
    title_font = load_font(64, bold=True)
    tag_font = load_font(36, bold=False)
    small_font = load_font(22, bold=True)

    if layout == "banner":
        draw.rectangle((0, 0, CANVAS_W, 280), fill=primary_rgb)
        _draw_centered(draw, headline, title_font, 90, banner_text, CANVAS_W - 120)
        card = _rounded_rect((860, 860), 48, (*panel, 255))
        canvas.paste(card, (110, 340), card)
        canvas.paste(qr, ((CANVAS_W - qr.width) // 2, 410), qr)
        _draw_centered(draw, tagline, tag_font, 1180, text, CANVAS_W - 140)
    elif layout == "dark":
        canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), primary_rgb)
        draw = ImageDraw.Draw(canvas)
        _draw_centered(draw, headline, title_font, 80, _hex_to_rgb(accent), CANVAS_W - 120)
        glow = _rounded_rect((800, 800), 40, (*_hex_to_rgb(accent), 40))
        canvas.paste(glow, (140, 300), glow)
        canvas.paste(qr, ((CANVAS_W - qr.width) // 2, 340), qr)
        _draw_centered(draw, tagline, tag_font, 1120, _hex_to_rgb(accent), CANVAS_W - 140)
        _draw_centered(draw, "SCAN TO ORDER", small_font, 1220, _hex_to_rgb(accent), CANVAS_W - 140)
    elif layout == "stamp":
        outer = _rounded_rect((CANVAS_W - 80, CANVAS_H - 80), 56, (*primary_rgb, 255))
        inner = _rounded_rect((CANVAS_W - 160, CANVAS_H - 160), 44, (*_hex_to_rgb(accent), 255))
        canvas.paste(outer, (40, 40), outer)
        canvas.paste(inner, (80, 80), inner)
        draw = ImageDraw.Draw(canvas)
        _draw_centered(draw, "SCAN & ORDER", small_font, 130, primary_rgb, CANVAS_W - 200)
        _draw_centered(draw, headline, title_font, 180, primary_rgb, CANVAS_W - 200)
        plate = _rounded_rect((780, 780), 36, (255, 255, 255, 255))
        canvas.paste(plate, (150, 320), plate)
        canvas.paste(qr, ((CANVAS_W - qr.width) // 2, 350), qr)
        _draw_centered(draw, tagline, tag_font, 1140, primary_rgb, CANVAS_W - 200)
    else:
        card = _rounded_rect((CANVAS_W - 96, CANVAS_H - 96), 48, (*panel, 255))
        shadow = card.filter(ImageFilter.GaussianBlur(12))
        canvas.paste(
            Image.new("RGBA", shadow.size, (0, 0, 0, 40)),
            (58, 62),
            shadow,
        )
        canvas.paste(card, (48, 48), card)
        draw = ImageDraw.Draw(canvas)
        _draw_centered(draw, headline, title_font, 100, text, CANVAS_W - 180)
        canvas.paste(qr, ((CANVAS_W - qr.width) // 2, 280), qr)
        _draw_centered(draw, tagline, tag_font, 1060, text, CANVAS_W - 180)
        _draw_centered(draw, "Scan with any camera", small_font, 1160, text, CANVAS_W - 180)

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def get_design(db: Session, outlet_id: UUID, kind: QrKind) -> OutletQrDesign | None:
    return (
        db.query(OutletQrDesign)
        .filter(OutletQrDesign.outlet_id == outlet_id, OutletQrDesign.kind == kind)
        .first()
    )


def render_for_outlet(
    db: Session,
    outlet: Outlet,
    *,
    kind: QrKind,
    url: str,
    table_number: str | None = None,
    template_id: str | None = None,
    config: dict | None = None,
) -> bytes:
    design = get_design(db, outlet.id, kind)
    if template_id is None and design is None:
        return generate_qr_png(url)
    chosen_template = template_id or (design.template_id if design else DEFAULT_TEMPLATE_ID)
    chosen_config = config or (design.config if design else default_config(kind, outlet.name))
    return render_branded_qr_png(
        url=url,
        outlet=outlet,
        kind=kind,
        template_id=chosen_template,
        config=chosen_config,
        table_number=table_number,
    )


def png_bytes_for_stored_or_render(
    stored_url: str | None,
    render: bytes,
) -> bytes:
    stored = fetch_stored_bytes(stored_url)
    return stored if stored else render
