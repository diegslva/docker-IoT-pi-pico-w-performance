"""Renderizador de frames para o Pico W DVI framebuffer.

Gera imagens 320x240 com Pillow e converte para RGB332 (8-bit),
formato nativo do framebuffer picodvi do CircuitPython.

RGB332: 3 bits red (bits 7-5) + 3 bits green (bits 4-2) + 2 bits blue (bits 1-0)
"""

import logging

from PIL import Image, ImageDraw, ImageFont

logger: logging.Logger = logging.getLogger("renderer")

FRAME_WIDTH: int = 320
FRAME_HEIGHT: int = 240
FRAME_SIZE: int = FRAME_WIDTH * FRAME_HEIGHT  # 76800 bytes

# RGB332 quantization levels
_R_LEVELS: list[int] = [0, 36, 73, 109, 146, 182, 219, 255]
_G_LEVELS: list[int] = [0, 36, 73, 109, 146, 182, 219, 255]
_B_LEVELS: list[int] = [0, 85, 170, 255]


def _nearest_rgb332(r: int, g: int, b: int) -> tuple[int, int, int, int]:
    """Encontra cor RGB332 mais proxima e retorna (encoded, r_quant, g_quant, b_quant)."""
    ri: int = min(7, r >> 5)
    gi: int = min(7, g >> 5)
    bi: int = min(3, b >> 6)
    return (
        (ri << 5) | (gi << 2) | bi,
        _R_LEVELS[ri],
        _G_LEVELS[gi],
        _B_LEVELS[bi],
    )


def image_to_rgb332_dithered(img: Image.Image) -> bytes:
    """Converte imagem Pillow para RGB332 com Floyd-Steinberg dithering."""
    img = img.convert("RGB")
    if img.size != (FRAME_WIDTH, FRAME_HEIGHT):
        img = img.resize((FRAME_WIDTH, FRAME_HEIGHT))

    # Work with float errors for dithering
    pixels = list(img.getdata())
    errors: list[list[float]] = [[0.0, 0.0, 0.0] for _ in range(FRAME_WIDTH * FRAME_HEIGHT)]
    buf: bytearray = bytearray(FRAME_SIZE)

    for y in range(FRAME_HEIGHT):
        for x in range(FRAME_WIDTH):
            idx: int = y * FRAME_WIDTH + x
            r_raw, g_raw, b_raw = pixels[idx]

            # Add accumulated error
            r: int = max(0, min(255, int(r_raw + errors[idx][0])))
            g: int = max(0, min(255, int(g_raw + errors[idx][1])))
            b: int = max(0, min(255, int(b_raw + errors[idx][2])))

            encoded, rq, gq, bq = _nearest_rgb332(r, g, b)
            buf[idx] = encoded

            # Quantization error
            er: float = r - rq
            eg: float = g - gq
            eb: float = b - bq

            # Distribute error (Floyd-Steinberg)
            if x + 1 < FRAME_WIDTH:
                n = idx + 1
                errors[n][0] += er * 7 / 16
                errors[n][1] += eg * 7 / 16
                errors[n][2] += eb * 7 / 16
            if y + 1 < FRAME_HEIGHT:
                if x - 1 >= 0:
                    n = idx + FRAME_WIDTH - 1
                    errors[n][0] += er * 3 / 16
                    errors[n][1] += eg * 3 / 16
                    errors[n][2] += eb * 3 / 16
                n = idx + FRAME_WIDTH
                errors[n][0] += er * 5 / 16
                errors[n][1] += eg * 5 / 16
                errors[n][2] += eb * 5 / 16
                if x + 1 < FRAME_WIDTH:
                    n = idx + FRAME_WIDTH + 1
                    errors[n][0] += er * 1 / 16
                    errors[n][1] += eg * 1 / 16
                    errors[n][2] += eb * 1 / 16

    return bytes(buf)


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carrega fonte TrueType com fallback."""
    font_paths: list[str] = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _get_font_bold(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carrega fonte bold com fallback."""
    font_paths: list[str] = [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return _get_font(size)


def render_crypto_frame(
    btc_price: float,
    eth_price: float,
    timestamp: str,
) -> bytes:
    """Renderiza frame com cotacoes crypto — cores otimizadas pra RGB332."""
    img: Image.Image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), color=(10, 15, 36))
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

    font_title: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(22)
    font_label: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(16)
    font_price: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(36)
    font_footer: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font(16)

    # Title bar background
    draw.rectangle([(0, 0), (319, 38)], fill=(36, 36, 85))
    draw.text(
        (FRAME_WIDTH // 2, 8),
        "CRYPTO TICKER v2",
        fill=(255, 255, 85),
        font=font_title,
        anchor="mt",
    )

    # BTC section
    draw.text((15, 50), "BTC", fill=(255, 182, 0), font=font_label)
    draw.text((15, 70), f"${btc_price:,.0f}", fill=(255, 255, 255), font=font_price)

    # ETH section
    draw.text((15, 125), "ETH", fill=(85, 85, 255), font=font_label)
    draw.text((15, 145), f"${eth_price:,.0f}", fill=(255, 255, 255), font=font_price)

    # Divider
    draw.line([(10, 195), (310, 195)], fill=(85, 85, 85), width=2)

    # Footer — bright colors that RGB332 renders well
    draw.text((15, 205), f"Updated: {timestamp} UTC", fill=(0, 255, 0), font=font_footer)
    draw.text((15, 223), "Pico W Display Server v0.1.0", fill=(85, 85, 85), font=font_footer)

    return image_to_rgb332_dithered(img)
