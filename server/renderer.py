"""Renderizador de frames para o Pico W DVI framebuffer.

Gera imagens 320x240 com Pillow e converte para RGB332 (8-bit),
formato nativo do framebuffer picodvi do CircuitPython.

RGB332: 3 bits red (bits 7-5) + 3 bits green (bits 4-2) + 2 bits blue (bits 1-0)
"""

import logging
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

logger: logging.Logger = logging.getLogger("renderer")

FRAME_WIDTH: int = 320
FRAME_HEIGHT: int = 240
FRAME_SIZE: int = FRAME_WIDTH * FRAME_HEIGHT  # 76800 bytes


def rgb888_to_rgb332(r: int, g: int, b: int) -> int:
    """Converte RGB888 para RGB332 (8-bit color)."""
    return (r & 0xE0) | ((g >> 3) & 0x1C) | ((b >> 6) & 0x03)


def image_to_rgb332(img: Image.Image) -> bytes:
    """Converte imagem Pillow (RGB) para buffer RGB332."""
    img = img.convert("RGB")
    if img.size != (FRAME_WIDTH, FRAME_HEIGHT):
        img = img.resize((FRAME_WIDTH, FRAME_HEIGHT))

    pixels: bytes = img.tobytes()
    buf: bytearray = bytearray(FRAME_SIZE)

    for i in range(FRAME_SIZE):
        offset: int = i * 3
        buf[i] = rgb888_to_rgb332(pixels[offset], pixels[offset + 1], pixels[offset + 2])

    return bytes(buf)


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carrega fonte — usa DejaVu (disponivel na maioria dos sistemas) ou fallback."""
    font_paths: list[str] = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def render_crypto_frame(
    btc_price: float,
    eth_price: float,
    timestamp: str,
) -> bytes:
    """Renderiza frame com cotacoes crypto e retorna como RGB332."""
    img: Image.Image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), color=(13, 17, 23))
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

    font_title: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font(24)
    font_price: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font(28)
    font_small: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font(14)

    # Title
    draw.text((FRAME_WIDTH // 2, 10), "Crypto Ticker", fill=(255, 215, 0), font=font_title, anchor="mt")

    # BTC
    draw.text((15, 55), "BTC", fill=(255, 153, 0), font=font_small)
    draw.text((15, 75), f"${btc_price:,.0f}", fill=(255, 255, 255), font=font_price)

    # ETH
    draw.text((15, 120), "ETH", fill=(98, 126, 234), font=font_small)
    draw.text((15, 140), f"${eth_price:,.0f}", fill=(255, 255, 255), font=font_price)

    # Divider line
    draw.line([(10, 185), (310, 185)], fill=(50, 50, 50), width=1)

    # Footer
    draw.text((15, 195), f"Updated: {timestamp} UTC", fill=(100, 100, 100), font=font_small)
    draw.text((15, 215), "Pico W Display Server", fill=(60, 60, 60), font=font_small)

    return image_to_rgb332(img)
