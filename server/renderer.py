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

            # Distribute error (attenuated Floyd-Steinberg — less noisy)
            strength: float = 0.5  # 0.0 = no dither, 1.0 = full dither
            er *= strength
            eg *= strength
            eb *= strength
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
    """Renderiza frame com cotacoes crypto — area util centralizada com bordas."""
    # Frame inteiro preto (bordas)
    img: Image.Image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), color=(0, 0, 0))
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

    # Area util centralizada
    margin_x: int = 20
    margin_y: int = 16
    content_w: int = FRAME_WIDTH - 2 * margin_x   # 280
    content_h: int = FRAME_HEIGHT - 2 * margin_y   # 208
    cx: int = margin_x  # content x start
    cy: int = margin_y  # content y start

    # Background da area util
    draw.rectangle(
        [(cx, cy), (cx + content_w - 1, cy + content_h - 1)],
        fill=(10, 15, 36),
    )

    # Borda sutil
    draw.rectangle(
        [(cx, cy), (cx + content_w - 1, cy + content_h - 1)],
        outline=(36, 36, 85),
        width=2,
    )

    font_title: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(20)
    font_label: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(14)
    font_price: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(32)
    font_footer: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font(13)

    # Title bar
    draw.rectangle([(cx + 2, cy + 2), (cx + content_w - 3, cy + 32)], fill=(36, 36, 85))
    draw.text(
        (FRAME_WIDTH // 2, cy + 6),
        "CRYPTO TICKER",
        fill=(255, 255, 85),
        font=font_title,
        anchor="mt",
    )

    # BTC
    draw.text((cx + 12, cy + 42), "BTC", fill=(255, 182, 0), font=font_label)
    draw.text((cx + 12, cy + 58), f"${btc_price:,.0f}", fill=(255, 255, 255), font=font_price)

    # ETH
    draw.text((cx + 12, cy + 102), "ETH", fill=(85, 85, 255), font=font_label)
    draw.text((cx + 12, cy + 118), f"${eth_price:,.0f}", fill=(255, 255, 255), font=font_price)

    # Divider
    draw.line([(cx + 8, cy + 162), (cx + content_w - 8, cy + 162)], fill=(85, 85, 85), width=1)

    # Footer
    draw.text((cx + 12, cy + 170), f"Updated: {timestamp}", fill=(0, 219, 0), font=font_footer)
    draw.text((cx + 12, cy + 188), "Pico W Display Server", fill=(73, 73, 73), font=font_footer)

    return image_to_rgb332_dithered(img)
