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


def image_to_rgb332_direct(img: Image.Image) -> bytes:
    """Converte imagem Pillow para RGB332 sem dithering — cores puras."""
    img = img.convert("RGB")
    if img.size != (FRAME_WIDTH, FRAME_HEIGHT):
        img = img.resize((FRAME_WIDTH, FRAME_HEIGHT))

    pixels: bytes = img.tobytes()
    buf: bytearray = bytearray(FRAME_SIZE)

    for i in range(FRAME_SIZE):
        offset: int = i * 3
        r: int = pixels[offset]
        g: int = pixels[offset + 1]
        b: int = pixels[offset + 2]
        buf[i] = (r & 0xE0) | ((g >> 3) & 0x1C) | ((b >> 6) & 0x03)

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
    """Renderiza frame com cotacoes crypto — cores puras RGB332, sem dithering.

    Todas as cores usadas sao exatamente representaveis em RGB332:
        R: 0, 36, 73, 109, 146, 182, 219, 255
        G: 0, 36, 73, 109, 146, 182, 219, 255
        B: 0, 85, 170, 255
    """
    # Cores exatas RGB332 (zero artefatos)
    BLACK: tuple[int, int, int] = (0, 0, 0)
    DARK_BLUE: tuple[int, int, int] = (0, 0, 85)
    NAVY: tuple[int, int, int] = (0, 36, 85)
    WHITE: tuple[int, int, int] = (255, 255, 255)
    YELLOW: tuple[int, int, int] = (255, 255, 0)
    ORANGE: tuple[int, int, int] = (255, 146, 0)
    BLUE: tuple[int, int, int] = (73, 73, 255)
    GREEN: tuple[int, int, int] = (0, 219, 0)
    GRAY: tuple[int, int, int] = (73, 73, 85)
    DARK_GRAY: tuple[int, int, int] = (36, 36, 85)

    # Frame inteiro preto (bordas)
    img: Image.Image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), color=BLACK)
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

    # Area util centralizada
    margin_x: int = 20
    margin_y: int = 16
    content_w: int = FRAME_WIDTH - 2 * margin_x
    content_h: int = FRAME_HEIGHT - 2 * margin_y
    cx: int = margin_x
    cy: int = margin_y

    # Background da area util
    draw.rectangle([(cx, cy), (cx + content_w - 1, cy + content_h - 1)], fill=DARK_BLUE)

    # Borda
    draw.rectangle([(cx, cy), (cx + content_w - 1, cy + content_h - 1)], outline=DARK_GRAY, width=2)

    font_title: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(20)
    font_label: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(14)
    font_price: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(32)
    font_footer: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font(13)

    # Title bar
    draw.rectangle([(cx + 2, cy + 2), (cx + content_w - 3, cy + 32)], fill=NAVY)
    draw.text(
        (FRAME_WIDTH // 2, cy + 6),
        "CRYPTO TICKER",
        fill=YELLOW,
        font=font_title,
        anchor="mt",
    )

    # BTC
    draw.text((cx + 12, cy + 42), "BTC", fill=ORANGE, font=font_label)
    draw.text((cx + 12, cy + 58), f"${btc_price:,.0f}", fill=WHITE, font=font_price)

    # ETH
    draw.text((cx + 12, cy + 102), "ETH", fill=BLUE, font=font_label)
    draw.text((cx + 12, cy + 118), f"${eth_price:,.0f}", fill=WHITE, font=font_price)

    # Divider
    draw.line([(cx + 8, cy + 162), (cx + content_w - 8, cy + 162)], fill=GRAY, width=1)

    # Footer
    draw.text((cx + 12, cy + 170), f"Updated: {timestamp}", fill=GREEN, font=font_footer)
    TEAL: tuple[int, int, int] = (0, 109, 170)
    draw.text((cx + 12, cy + 188), "Pico W Display Server", fill=TEAL, font=font_footer)

    return image_to_rgb332_direct(img)
