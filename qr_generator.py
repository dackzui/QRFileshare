from pathlib import Path

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer, SquareModuleDrawer

from config import QR_OUTPUT_DIR

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


def build_share_url(base_url: str, link_id: str) -> str:
    return f"{base_url.rstrip('/')}/s/{link_id}"


def generate_qr_image(
    share_url: str,
    output_path: Path,
    label: str = "",
    theme: str = "canva-classic",
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

    if label:
        from PIL import Image, ImageDraw, ImageFont

        base = img.get_image().convert("RGB")
        width, height = base.size
        footer = 48
        canvas = Image.new("RGB", (width, height + footer), palette["back"])
        canvas.paste(base, (0, 0))
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except OSError:
            font = ImageFont.load_default()
        text = label[:40] + ("..." if len(label) > 40 else "")
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_color = palette["front"] if sum(palette["back"]) > 380 else (203, 213, 225)
        draw.text(
            ((width - text_w) // 2, height + 12),
            text,
            fill=text_color,
            font=font,
        )
        canvas.save(output_path)
    else:
        img.save(output_path)

    return output_path


def default_qr_path(link_id: str, output_dir: Path = QR_OUTPUT_DIR) -> Path:
    return output_dir / f"share_{link_id}.png"


def ensure_qr_image(
    link_id: str,
    *,
    target_url: str,
    label: str = "",
    theme: str = "canva-classic",
) -> Path:
    path = default_qr_path(link_id)
    if not path.exists():
        generate_qr_image(target_url, path, label=label, theme=theme)
    return path
