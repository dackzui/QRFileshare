from __future__ import annotations

from pathlib import Path
from typing import Optional

import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer, SquareModuleDrawer

from config import QR_ASSETS_DIR, QR_OUTPUT_DIR

# Canva-inspired QR themes
QR_THEMES = {
    "canva-classic": {
        "name": "Canva Classic",
        "front": (17, 24, 39),
        "back": (255, 255, 255),
        "rounded": True,
    },
    "canva-violet": {
        "name": "Canva Violet",
        "front": (124, 58, 237),
        "back": (250, 245, 255),
        "rounded": True,
    },
    "canva-ocean": {
        "name": "Canva Ocean",
        "front": (14, 116, 144),
        "back": (236, 254, 255),
        "rounded": True,
    },
    "canva-coral": {
        "name": "Canva Coral",
        "front": (225, 29, 72),
        "back": (255, 241, 242),
        "rounded": True,
    },
    "canva-midnight": {
        "name": "Canva Midnight",
        "front": (255, 255, 255),
        "back": (15, 23, 42),
        "rounded": False,
    },
}

LOGO_PLACEMENTS = {
    "none": "No logo",
    "center": "Center (on QR)",
    "above": "Above QR",
    "below": "Below QR",
    "top_left": "Top left",
    "top_right": "Top right",
    "bottom_left": "Bottom left",
    "bottom_right": "Bottom right",
}

BORDER_STYLES = {
    "none": "No border",
    "simple": "Simple frame",
    "double": "Double frame",
    "rounded": "Rounded frame",
    "polaroid": "Polaroid",
    "custom": "Custom PNG",
}


class QrAssetError(Exception):
    pass


def build_share_url(base_url: str, link_id: str) -> str:
    return f"{base_url.rstrip('/')}/s/{link_id}"


def default_qr_path(link_id: str, output_dir: Path = QR_OUTPUT_DIR) -> Path:
    return output_dir / f"share_{link_id}.png"


def assets_dir_for(link_id: str) -> Path:
    path = QR_ASSETS_DIR / link_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_png_upload(file_storage, destination: Path, *, kind: str = "image") -> Path:
    """Validate and save an uploaded PNG. Raises QrAssetError on failure."""
    if file_storage is None or not getattr(file_storage, "filename", None):
        raise QrAssetError(f"Choose a PNG file for the {kind}.")

    filename = Path(file_storage.filename).name
    if not filename.lower().endswith(".png"):
        raise QrAssetError(f"{kind.capitalize()} must be a PNG file.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(destination)

    try:
        with Image.open(destination) as img:
            if img.format != "PNG":
                raise QrAssetError(f"{kind.capitalize()} must be a valid PNG file.")
            img.load()
    except QrAssetError:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise QrAssetError(f"Could not read {kind} PNG: {exc}") from exc

    return destination


def _load_png(path: Path | str | None) -> Optional[Image.Image]:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        return Image.open(file_path).convert("RGBA")
    except Exception:
        return None


def _fit_logo(logo: Image.Image, max_size: int) -> Image.Image:
    fitted = logo.copy()
    fitted.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return fitted


def _paste_rgba(base: Image.Image, overlay: Image.Image, xy: tuple[int, int]) -> Image.Image:
    canvas = base.convert("RGBA")
    if overlay.mode != "RGBA":
        overlay = overlay.convert("RGBA")
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(overlay, xy, overlay)
    return Image.alpha_composite(canvas, layer)


def _apply_logo(
    canvas: Image.Image,
    logo: Image.Image,
    placement: str,
    *,
    qr_box: tuple[int, int, int, int],
    back_color: tuple[int, int, int],
) -> Image.Image:
    placement = placement if placement in LOGO_PLACEMENTS else "none"
    if placement == "none":
        return canvas.convert("RGB")

    left, top, right, bottom = qr_box
    qr_w = right - left
    qr_h = bottom - top

    if placement == "center":
        logo_img = _fit_logo(logo, max(24, int(min(qr_w, qr_h) * 0.22)))
        pad = max(4, logo_img.width // 10)
        badge = Image.new(
            "RGBA",
            (logo_img.width + pad * 2, logo_img.height + pad * 2),
            (*back_color, 255),
        )
        badge.paste(logo_img, (pad, pad), logo_img if logo_img.mode == "RGBA" else None)
        x = left + (qr_w - badge.width) // 2
        y = top + (qr_h - badge.height) // 2
        return _paste_rgba(canvas, badge, (x, y)).convert("RGB")

    logo_img = _fit_logo(logo, max(32, int(min(canvas.width, canvas.height) * 0.18)))
    margin = 12

    if placement == "above":
        extra = logo_img.height + margin * 2
        expanded = Image.new("RGB", (canvas.width, canvas.height + extra), back_color)
        expanded.paste(canvas.convert("RGB"), (0, extra))
        x = (expanded.width - logo_img.width) // 2
        return _paste_rgba(expanded, logo_img, (x, margin)).convert("RGB")

    if placement == "below":
        extra = logo_img.height + margin * 2
        expanded = Image.new("RGB", (canvas.width, canvas.height + extra), back_color)
        expanded.paste(canvas.convert("RGB"), (0, 0))
        x = (expanded.width - logo_img.width) // 2
        y = canvas.height + margin
        return _paste_rgba(expanded, logo_img, (x, y)).convert("RGB")

    positions = {
        "top_left": (margin, margin),
        "top_right": (canvas.width - logo_img.width - margin, margin),
        "bottom_left": (margin, canvas.height - logo_img.height - margin),
        "bottom_right": (
            canvas.width - logo_img.width - margin,
            canvas.height - logo_img.height - margin,
        ),
    }
    xy = positions.get(placement, (margin, margin))
    return _paste_rgba(canvas, logo_img, xy).convert("RGB")


def _draw_builtin_border(
    qr_img: Image.Image,
    style: str,
    *,
    back_color: tuple[int, int, int],
    front_color: tuple[int, int, int],
) -> Image.Image:
    style = style if style in BORDER_STYLES else "none"
    if style in ("none", "custom"):
        return qr_img.convert("RGB")

    qr = qr_img.convert("RGB")
    pad = 28 if style != "polaroid" else 36
    bottom_extra = 56 if style == "polaroid" else 0
    width = qr.width + pad * 2
    height = qr.height + pad * 2 + bottom_extra
    canvas = Image.new("RGB", (width, height), (255, 255, 255) if style == "polaroid" else back_color)
    canvas.paste(qr, (pad, pad))
    draw = ImageDraw.Draw(canvas)
    inset = 8

    if style == "simple":
        draw.rectangle(
            [inset, inset, width - inset - 1, height - inset - 1],
            outline=front_color,
            width=4,
        )
    elif style == "double":
        draw.rectangle(
            [inset, inset, width - inset - 1, height - inset - 1],
            outline=front_color,
            width=3,
        )
        draw.rectangle(
            [inset + 8, inset + 8, width - inset - 9, height - inset - 9],
            outline=front_color,
            width=2,
        )
    elif style == "rounded":
        draw.rounded_rectangle(
            [inset, inset, width - inset - 1, height - inset - 1],
            radius=24,
            outline=front_color,
            width=5,
        )
    elif style == "polaroid":
        draw.rectangle([0, 0, width - 1, height - 1], outline=(226, 232, 240), width=1)

    return canvas


def _apply_custom_border(qr_img: Image.Image, border: Image.Image) -> Image.Image:
    """Place the QR in the center of a custom PNG frame."""
    frame = border.convert("RGBA")
    # Reasonable output size based on frame
    max_side = max(frame.width, frame.height, 640)
    scale = max_side / max(frame.width, frame.height)
    if scale != 1:
        frame = frame.resize(
            (max(1, int(frame.width * scale)), max(1, int(frame.height * scale))),
            Image.Resampling.LANCZOS,
        )

    inset = int(min(frame.width, frame.height) * 0.14)
    inner_w = max(64, frame.width - inset * 2)
    inner_h = max(64, frame.height - inset * 2)
    qr = ImageOps.contain(qr_img.convert("RGBA"), (inner_w, inner_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", frame.size, (255, 255, 255, 255))
    x = (frame.width - qr.width) // 2
    y = (frame.height - qr.height) // 2
    canvas.paste(qr, (x, y), qr)
    canvas = Image.alpha_composite(canvas, frame)
    return canvas.convert("RGB")


def _add_label(
    base: Image.Image,
    label: str,
    *,
    back_color: tuple[int, int, int],
    front_color: tuple[int, int, int],
) -> Image.Image:
    width, height = base.size
    footer = 48
    canvas = Image.new("RGB", (width, height + footer), back_color)
    canvas.paste(base.convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    text = label[:40] + ("..." if len(label) > 40 else "")
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_color = front_color if sum(back_color) > 380 else (203, 213, 225)
    draw.text(((width - text_w) // 2, height + 12), text, fill=text_color, font=font)
    return canvas


def apply_branding(
    image: Image.Image,
    *,
    logo_path: str | Path | None = None,
    logo_placement: str = "none",
    border_style: str = "none",
    border_path: str | Path | None = None,
    back_color: tuple[int, int, int] = (255, 255, 255),
    front_color: tuple[int, int, int] = (17, 24, 39),
) -> Image.Image:
    """Apply logo + border branding to any image (QR or uploaded photo)."""
    canvas = image.convert("RGB")
    qr_box = (0, 0, canvas.width, canvas.height)

    logo = _load_png(logo_path)
    placement = (logo_placement or "none").strip().lower()
    if logo is not None and placement in LOGO_PLACEMENTS and placement != "none":
        canvas = _apply_logo(
            canvas,
            logo,
            placement,
            qr_box=qr_box,
            back_color=back_color,
        )

    style = (border_style or "none").strip().lower()
    custom_border = _load_png(border_path)
    if style == "custom" and custom_border is not None:
        canvas = _apply_custom_border(canvas, custom_border)
    elif style not in ("none", "custom"):
        canvas = _draw_builtin_border(
            canvas,
            style,
            back_color=back_color,
            front_color=front_color,
        )
    return canvas.convert("RGB")


IMAGE_UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def is_brandable_image(filename: str, mime_type: str = "") -> bool:
    suffix = Path(filename or "").suffix.lower()
    if suffix in IMAGE_UPLOAD_EXTENSIONS:
        return True
    return (mime_type or "").lower().startswith("image/") and "svg" not in (mime_type or "").lower()


def brand_image_bytes(
    content: bytes,
    filename: str,
    *,
    logo_path: str | Path | None = None,
    logo_placement: str = "none",
    border_style: str = "none",
    border_path: str | Path | None = None,
) -> tuple[bytes, str]:
    """
    Brand an uploaded image. Returns (bytes, mime_type).
    Non-image content is returned unchanged.
    """
    placement = (logo_placement or "none").strip().lower()
    style = (border_style or "none").strip().lower()
    has_logo = bool(logo_path) and placement != "none"
    has_border = style not in ("", "none") and (
        style != "custom" or bool(border_path)
    )
    if not has_logo and not has_border:
        return content, ""

    if not is_brandable_image(filename):
        return content, ""

    from io import BytesIO

    try:
        with Image.open(BytesIO(content)) as src:
            src.load()
            branded = apply_branding(
                src,
                logo_path=logo_path,
                logo_placement=placement,
                border_style=style,
                border_path=border_path,
            )
    except Exception:
        return content, ""

    buffer = BytesIO()
    # Always save branded uploads as PNG so transparency/frames stay clean.
    branded.save(buffer, format="PNG")
    return buffer.getvalue(), "image/png"


def default_branding_dir() -> Path:
    path = QR_ASSETS_DIR / "default"
    path.mkdir(parents=True, exist_ok=True)
    return path


def generate_qr_image(
    share_url: str,
    output_path: Path,
    label: str = "",
    theme: str = "canva-classic",
    *,
    logo_path: str | Path | None = None,
    logo_placement: str = "none",
    border_style: str = "none",
    border_path: str | Path | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    palette = QR_THEMES.get(theme, QR_THEMES["canva-classic"])
    drawer = RoundedModuleDrawer() if palette["rounded"] else SquareModuleDrawer()

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4,
    )
    qr.add_data(share_url)
    qr.make(fit=True)

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer,
        color_mask=SolidFillColorMask(
            back_color=palette["back"],
            front_color=palette["front"],
        ),
    )
    canvas = apply_branding(
        img.get_image().convert("RGB"),
        logo_path=logo_path,
        logo_placement=logo_placement,
        border_style=border_style,
        border_path=border_path,
        back_color=palette["back"],
        front_color=palette["front"],
    )

    if label:
        canvas = _add_label(
            canvas,
            label,
            back_color=palette["back"],
            front_color=palette["front"],
        )

    canvas.save(output_path)
    return output_path


def ensure_qr_image(
    link_id: str,
    *,
    target_url: str,
    label: str = "",
    theme: str = "canva-classic",
    logo_path: str | Path | None = None,
    logo_placement: str = "none",
    border_style: str = "none",
    border_path: str | Path | None = None,
) -> Path:
    path = default_qr_path(link_id)
    if not path.exists():
        generate_qr_image(
            target_url,
            path,
            label=label,
            theme=theme,
            logo_path=logo_path,
            logo_placement=logo_placement,
            border_style=border_style,
            border_path=border_path,
        )
    return path
