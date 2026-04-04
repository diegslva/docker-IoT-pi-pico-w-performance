"""Renderizador de frames para o Pico W DVI framebuffer.

Gera imagens 320x240 com Pillow e converte para RGB332 (8-bit),
formato nativo do framebuffer picodvi do CircuitPython.

RGB332: 3 bits red (bits 7-5) + 3 bits green (bits 4-2) + 2 bits blue (bits 1-0)
"""

import logging
import math

from PIL import Image, ImageDraw, ImageFont

logger: logging.Logger = logging.getLogger("renderer")

FRAME_WIDTH: int = 320
FRAME_HEIGHT: int = 240
FRAME_SIZE: int = FRAME_WIDTH * FRAME_HEIGHT  # 76800 bytes


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
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return _get_font(size)


# --- Cached sunset background ---
_sunset_base: Image.Image | None = None


def _render_sunset_base() -> Image.Image:
    """Renderiza o background do por do sol (cacheado — nao muda)."""
    global _sunset_base
    if _sunset_base is not None:
        return _sunset_base.copy()

    img: Image.Image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), color=(0, 0, 0))
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

    # Sky gradient
    for y in range(140):
        r: int = int(20 + (235 * y / 140))
        g: int = int(10 + (100 * (1 - y / 140)))
        b: int = int(80 * (1 - y / 140))
        draw.line([(0, y), (319, y)], fill=(min(255, r), max(0, g), max(0, b)))

    # Sun
    cx: int = 160
    cy: int = 70
    radius: int = 30
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            dist: float = math.sqrt(dx * dx + dy * dy)
            if dist <= radius:
                intensity: float = 1.0 - (dist / radius) * 0.3
                sr: int = min(255, int(255 * intensity))
                sg: int = min(255, int(220 * intensity))
                sb: int = min(255, int(50 * intensity))
                px: int = cx + dx
                py: int = cy + dy
                if 0 <= px < 320 and 0 <= py < 240:
                    img.putpixel((px, py), (sr, sg, sb))

    # Ocean
    for y in range(140, 240):
        depth: float = (y - 140) / 100
        or_: int = int(10 * (1 - depth))
        og: int = int(40 + 30 * (1 - depth))
        ob: int = int(100 + 50 * (1 - depth))
        for x in range(320):
            wave: float = math.sin(x * 0.05 + y * 0.1) * 10
            img.putpixel(
                (x, y),
                (
                    max(0, min(255, or_ + int(wave))),
                    max(0, min(255, og + int(wave))),
                    max(0, min(255, ob + int(wave))),
                ),
            )

    # Sun reflection
    for y in range(145, 200):
        spread: float = (y - 140) * 0.8
        for dx in range(int(-spread), int(spread) + 1):
            x = 160 + dx
            if 0 <= x < 320:
                ref_intensity: float = 0.6 * (1 - abs(dx) / max(1, spread)) * (1 - (y - 145) / 55)
                pr, pg, pb = img.getpixel((x, y))
                img.putpixel(
                    (x, y),
                    (
                        min(255, int(pr + 200 * ref_intensity)),
                        min(255, int(pg + 150 * ref_intensity)),
                        min(255, int(pb + 30 * ref_intensity)),
                    ),
                )

    # Palm tree
    trunk_x: int = 60
    for y in range(80, 145):
        lean: int = int((145 - y) * 0.15)
        for dx in range(-2, 3):
            px = trunk_x + lean + dx
            if 0 <= px < 320:
                img.putpixel((px, y), (15, 10, 5))

    leaf_base_x: int = trunk_x + int(65 * 0.15)
    leaf_base_y: int = 80
    for angle_deg in [-30, -10, 15, 40, 60, -50]:
        angle: float = math.radians(angle_deg)
        for t in range(40):
            droop: float = t * t * 0.008
            lx: int = int(leaf_base_x + t * math.cos(angle))
            ly: int = int(leaf_base_y - t * math.sin(angle) + droop)
            for w in range(-1, 2):
                if 0 <= lx < 320 and 0 <= ly + w < 240:
                    img.putpixel((lx, ly + w), (10, 8, 3))

    _sunset_base = img.copy()
    logger.info("Sunset base rendered and cached")
    return img


MESSAGES: list[str] = [
    "Bem-vindo!",
    "Bora treinar!",
    "Supere seus limites",
    "Foco e disciplina",
    "Seu corpo agradece",
    "Mais forte a cada dia",
]


def render_vitoria_sports_frame(timestamp: str, frame_index: int = 0) -> bytes:
    """Renderiza frame dinamico da Vitoria Sports com horario e mensagem rotativa."""
    img: Image.Image = _render_sunset_base()
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

    font_title: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(24)
    font_sub: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font(14)
    font_clock: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(18)
    font_msg: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(16)

    # Title with shadow
    draw.text((162, 12), "Vitoria Sports", fill=(30, 10, 0), font=font_title, anchor="mt")
    draw.text((160, 10), "Vitoria Sports", fill=(255, 220, 100), font=font_title, anchor="mt")

    # Subtitle
    draw.text((162, 38), "- ES -", fill=(30, 10, 0), font=font_sub, anchor="mt")
    draw.text((160, 36), "- ES -", fill=(200, 180, 120), font=font_sub, anchor="mt")

    # Clock (bottom area, over ocean)
    draw.text((162, 198), timestamp, fill=(20, 5, 0), font=font_clock, anchor="mt")
    draw.text((160, 196), timestamp, fill=(255, 255, 200), font=font_clock, anchor="mt")

    # Rotating message
    msg: str = MESSAGES[frame_index % len(MESSAGES)]
    draw.text((162, 220), msg, fill=(20, 5, 0), font=font_msg, anchor="mt")
    draw.text((160, 218), msg, fill=(0, 255, 150), font=font_msg, anchor="mt")

    return image_to_rgb332_direct(img)


def render_crypto_frame(
    btc_price: float,
    eth_price: float,
    timestamp: str,
) -> bytes:
    """Renderiza frame com cotacoes crypto — cores puras RGB332, sem dithering."""
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

    img: Image.Image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), color=BLACK)
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

    margin_x: int = 20
    margin_y: int = 16
    content_w: int = FRAME_WIDTH - 2 * margin_x
    content_h: int = FRAME_HEIGHT - 2 * margin_y
    cx: int = margin_x
    cy: int = margin_y

    draw.rectangle([(cx, cy), (cx + content_w - 1, cy + content_h - 1)], fill=DARK_BLUE)
    draw.rectangle([(cx, cy), (cx + content_w - 1, cy + content_h - 1)], outline=DARK_GRAY, width=2)

    font_title = _get_font_bold(20)
    font_label = _get_font_bold(14)
    font_price = _get_font_bold(32)
    font_footer = _get_font(13)

    draw.rectangle([(cx + 2, cy + 2), (cx + content_w - 3, cy + 32)], fill=NAVY)
    draw.text((FRAME_WIDTH // 2, cy + 6), "CRYPTO TICKER", fill=YELLOW, font=font_title, anchor="mt")
    draw.text((cx + 12, cy + 42), "BTC", fill=ORANGE, font=font_label)
    draw.text((cx + 12, cy + 58), f"${btc_price:,.0f}", fill=WHITE, font=font_price)
    draw.text((cx + 12, cy + 102), "ETH", fill=BLUE, font=font_label)
    draw.text((cx + 12, cy + 118), f"${eth_price:,.0f}", fill=WHITE, font=font_price)
    draw.line([(cx + 8, cy + 162), (cx + content_w - 8, cy + 162)], fill=GRAY, width=1)
    draw.text((cx + 12, cy + 170), f"Updated: {timestamp}", fill=GREEN, font=font_footer)

    TEAL: tuple[int, int, int] = (0, 109, 170)
    draw.text((cx + 12, cy + 188), "Pico W Display Server", fill=TEAL, font=font_footer)

    return image_to_rgb332_direct(img)
