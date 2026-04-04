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


# --- Panoramic day/night cycle (cached per minute) ---
_panoramic_cache: Image.Image | None = None
_panoramic_cache_key: str = ""


def _sky_colors(hour: int, minute: int) -> tuple[tuple[int, int, int], tuple[int, int, int], bool]:
    """Retorna (sky_top, sky_bottom, is_night) baseado no horario."""
    h: float = hour + minute / 60

    if h < 5 or h >= 20:
        # Night
        return (5, 5, 20), (10, 10, 40), True
    elif h < 6:
        # Pre-dawn
        t: float = h - 5
        return (int(5 + 15 * t), int(5 + 5 * t), int(20 + 30 * t)), (int(10 + 80 * t), int(10 + 30 * t), int(40 + 20 * t)), False
    elif h < 7.5:
        # Dawn
        return (20, 10, 50), (255, 100, 30), False
    elif h < 9:
        # Morning golden
        return (20, 20, 80), (240, 140, 40), False
    elif h < 15:
        # Midday
        return (15, 30, 100), (200, 160, 60), False
    elif h < 17:
        # Afternoon golden
        return (20, 20, 80), (240, 140, 40), False
    elif h < 18.5:
        # Sunset
        return (15, 5, 40), (255, 100, 30), False
    elif h < 20:
        # Dusk
        t = (h - 18.5) / 1.5
        return (int(15 - 10 * t), int(5 - 0 * t), int(40 - 20 * t)), (int(100 - 90 * t), int(40 - 30 * t), int(30 - 0 * t)), False
    return (5, 5, 20), (10, 10, 40), True


def _render_panoramic_base(total_positions: int, hour: int = 12, minute: int = 0) -> Image.Image:
    """Renderiza panorama com ciclo dia/noite completo. Cacheado por minuto."""
    global _panoramic_cache, _panoramic_cache_key

    cache_key: str = f"{total_positions}_{hour}_{minute}"
    if _panoramic_cache is not None and _panoramic_cache_key == cache_key:
        return _panoramic_cache.copy()

    W: int = FRAME_WIDTH * total_positions
    H: int = FRAME_HEIGHT
    h: float = hour + minute / 60

    sky_top, sky_bottom, is_night = _sky_colors(hour, minute)

    img: Image.Image = Image.new("RGB", (W, H), color=(0, 0, 0))
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

    # Sky gradient
    for y in range(150):
        t: float = y / 150
        r: int = int(sky_top[0] + (sky_bottom[0] - sky_top[0]) * t)
        g: int = int(sky_top[1] + (sky_bottom[1] - sky_top[1]) * t)
        b: int = int(sky_top[2] + (sky_bottom[2] - sky_top[2]) * t)
        draw.line([(0, y), (W - 1, y)], fill=(min(255, r), max(0, g), max(0, b)))

    if is_night:
        # Moon
        moon_x: int = int(W * 0.6)
        moon_y: int = 50
        moon_r: int = 25
        for dy in range(-moon_r, moon_r + 1):
            for dx in range(-moon_r, moon_r + 1):
                dist: float = math.sqrt(dx * dx + dy * dy)
                if dist <= moon_r:
                    intensity: float = 1.0 - (dist / moon_r) * 0.2
                    px: int = moon_x + dx
                    py: int = moon_y + dy
                    if 0 <= px < W and 0 <= py < H:
                        img.putpixel((px, py), (
                            min(255, int(220 * intensity)),
                            min(255, int(220 * intensity)),
                            min(255, int(240 * intensity)),
                        ))

        # Stars
        import random
        rng: random.Random = random.Random(42)  # deterministic stars
        for _ in range(80 * total_positions):
            sx: int = rng.randint(0, W - 1)
            sy: int = rng.randint(0, 130)
            brightness: int = rng.randint(120, 255)
            if img.getpixel((sx, sy))[0] < 30:
                img.putpixel((sx, sy), (brightness, brightness, brightness))
    else:
        # Sun position (5h-19h arc)
        sun_frac: float = max(0.0, min(1.0, (h - 5) / 14))
        sun_x: int = int(W * 0.1 + (W * 0.8) * sun_frac)
        sun_y: int = int(130 - 80 * math.sin(sun_frac * math.pi))

        # Sun
        radius: int = 40
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= radius:
                    intensity = 1.0 - (dist / radius) * 0.3
                    px = sun_x + dx
                    py = sun_y + dy
                    if 0 <= px < W and 0 <= py < 150:
                        img.putpixel((px, py), (
                            min(255, int(255 * intensity)),
                            min(255, int(230 * intensity)),
                            min(255, int(60 * intensity)),
                        ))

    # Ocean — darker at night
    ocean_brightness: float = 0.2 if is_night else 1.0
    for y in range(150, H):
        depth: float = (y - 150) / (H - 150)
        for x in range(W):
            wave: float = math.sin(x * 0.03 + y * 0.08) * 12 + math.sin(x * 0.07 - y * 0.05) * 6
            r = max(0, min(255, int((10 * (1 - depth) + wave * 0.3) * ocean_brightness)))
            g = max(0, min(255, int((50 + 30 * (1 - depth) + wave * 0.5) * ocean_brightness)))
            b = max(0, min(255, int((120 + 40 * (1 - depth) + wave) * ocean_brightness)))
            img.putpixel((x, y), (r, g, b))

    # Reflection (sun or moon)
    if not is_night:
        ref_cx: int = sun_x
    else:
        ref_cx = int(W * 0.6)

    for y in range(155, 220):
        spread: float = (y - 150) * 1.5
        for dx in range(int(-spread), int(spread) + 1):
            x = ref_cx + dx
            if 0 <= x < W:
                ref: float = 0.4 * (1 - abs(dx) / max(1, spread)) * (1 - (y - 155) / 65)
                wave_mod: float = 0.5 + 0.5 * math.sin(x * 0.1 + y * 0.2)
                ref *= wave_mod
                pr, pg, pb = img.getpixel((x, y))
                if is_night:
                    img.putpixel((x, y), (
                        min(255, int(pr + 100 * ref)),
                        min(255, int(pg + 100 * ref)),
                        min(255, int(pb + 120 * ref)),
                    ))
                else:
                    img.putpixel((x, y), (
                        min(255, int(pr + 220 * ref)),
                        min(255, int(pg + 170 * ref)),
                        min(255, int(pb + 40 * ref)),
                    ))

    # Palm trees (silhouette — works day and night)
    palm_positions: list[int] = [80]
    if total_positions >= 2:
        palm_positions.append(W - 100)
    if total_positions >= 4:
        palm_positions.extend([W // 3, 2 * W // 3])

    tree_color: tuple[int, int, int] = (5, 3, 2) if is_night else (15, 10, 5)
    leaf_color: tuple[int, int, int] = (3, 2, 1) if is_night else (8, 6, 3)

    for trunk_x in palm_positions:
        for y in range(75, 155):
            lean: int = int((155 - y) * 0.12)
            for dx in range(-3, 4):
                px = trunk_x + lean + dx
                if 0 <= px < W:
                    img.putpixel((px, y), tree_color)
        leaf_bx: int = trunk_x + int(80 * 0.12)
        leaf_by: int = 75
        for a in [-40, -20, 0, 25, 50, 70, -55]:
            angle: float = math.radians(a)
            for t in range(45):
                lx: int = int(leaf_bx + t * math.cos(angle))
                ly: int = int(leaf_by - t * math.sin(angle) + t * t * 0.007)
                for w in range(-2, 3):
                    if 0 <= lx < W and 0 <= ly + w < H:
                        img.putpixel((lx, ly + w), leaf_color)

    _panoramic_cache = img.copy()
    _panoramic_cache_key = cache_key
    logger.info("Panoramic rendered: %dx%d (%d displays) %d:%02d %s",
                W, H, total_positions, hour, minute, "night" if is_night else "day")
    return img


def _draw_scrolling_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    fill: tuple[int, int, int],
    shadow: tuple[int, int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    canvas_width: int,
    offset_px: int,
) -> None:
    """Desenha texto scrollando da direita pra esquerda com wrap-around.

    offset_px e o deslocamento absoluto em pixels (compartilhado por todos os textos).
    """
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width: int = bbox[2] - bbox[0]
    spacing: int = canvas_width  # gap between repetitions
    cycle: int = text_width + spacing

    # Position within the cycle
    x: int = canvas_width - (offset_px % cycle)

    # Draw main instance + one before and one after for seamless wrap
    for shift in [-cycle, 0, cycle]:
        draw_x: int = x + shift
        if -text_width <= draw_x <= canvas_width:
            draw.text((draw_x + 2, y + 2), text, fill=shadow, font=font, anchor="lt")
            draw.text((draw_x, y), text, fill=fill, font=font, anchor="lt")


def render_panoramic_frame(
    position: int,
    total_positions: int,
    timestamp: str,
    hour: int = 12,
    minute: int = 0,
    second: int = 0,
    frame_index: int = 0,
) -> bytes:
    """Renderiza frame panoramico com textos scrollando, retorna slice da posicao."""
    img: Image.Image = _render_panoramic_base(total_positions, hour=hour, minute=minute)
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
    W: int = img.width

    font_title: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(28)
    font_sub: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font(18)
    font_clock: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(20)
    font_msg: ImageFont.FreeTypeFont | ImageFont.ImageFont = _get_font_bold(20)

    # Time-based tick for smooth scrolling (seconds since midnight)
    tick: float = hour * 3600 + minute * 60 + second

    # Single offset for all text — same speed, same direction, perfectly synchronized
    SCROLL_SPEED: float = 15.0  # px/s — at 0.5s interval = ~8px per frame (smooth)
    offset_px: int = int(tick * SCROLL_SPEED)

    _draw_scrolling_text(
        draw, "Vitoria Sports  -  ES", y=10,
        fill=(255, 220, 100), shadow=(20, 5, 0),
        font=font_title, canvas_width=W, offset_px=offset_px,
    )

    clock_text: str = f"{timestamp}     Vitoria Sports     {timestamp}"
    _draw_scrolling_text(
        draw, clock_text, y=193,
        fill=(255, 255, 200), shadow=(20, 5, 0),
        font=font_clock, canvas_width=W, offset_px=offset_px,
    )

    _draw_scrolling_text(
        draw, "Bora treinar!     Vitoria Sports - ES     Bora treinar!     Vitoria Sports - ES", y=216,
        fill=(0, 255, 150), shadow=(20, 5, 0),
        font=font_clock, canvas_width=W, offset_px=offset_px,
    )

    # Crop slice for this position
    x_start: int = position * FRAME_WIDTH
    x_end: int = x_start + FRAME_WIDTH
    slice_img: Image.Image = img.crop((x_start, 0, x_end, FRAME_HEIGHT))
    return image_to_rgb332_direct(slice_img)


# --- Multi-display effects ---


def render_wave_frame(
    effect_image: Image.Image,
    position: int,
    tick: int,
    total_positions: int,
    timestamp: str,
) -> bytes:
    """Efeito Wave — imagem aparece na TV ativa, outras mostram Vitoria Sports."""
    active_position: int = tick % total_positions
    if position == active_position:
        img: Image.Image = effect_image.copy().resize((FRAME_WIDTH, FRAME_HEIGHT))
        return image_to_rgb332_direct(img)
    return render_vitoria_sports_frame(timestamp=timestamp, frame_index=tick)


def render_wall_frame(
    effect_image: Image.Image,
    position: int,
    total_positions: int,
) -> bytes:
    """Efeito Video Wall — cada TV mostra um pedaco da imagem panoramica."""
    wall_width: int = FRAME_WIDTH * total_positions
    img: Image.Image = effect_image.copy().resize((wall_width, FRAME_HEIGHT))

    # Crop the slice for this position
    x_start: int = position * FRAME_WIDTH
    x_end: int = x_start + FRAME_WIDTH
    slice_img: Image.Image = img.crop((x_start, 0, x_end, FRAME_HEIGHT))
    return image_to_rgb332_direct(slice_img)


def render_scroll_frame(
    effect_image: Image.Image,
    position: int,
    tick: int,
    total_positions: int,
    speed: int,
) -> bytes:
    """Efeito Scroll — imagem larga desloca continuamente por todas as TVs."""
    wall_width: int = FRAME_WIDTH * total_positions
    img: Image.Image = effect_image.copy().resize((wall_width, FRAME_HEIGHT))
    img_width: int = img.width

    # Offset based on tick and speed
    offset: int = (tick * speed) % img_width

    # This device's window
    x_start: int = (offset + position * FRAME_WIDTH) % img_width

    # Create frame by wrapping around
    frame: Image.Image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT))
    if x_start + FRAME_WIDTH <= img_width:
        frame.paste(img.crop((x_start, 0, x_start + FRAME_WIDTH, FRAME_HEIGHT)), (0, 0))
    else:
        # Wrap around
        first_part: int = img_width - x_start
        frame.paste(img.crop((x_start, 0, img_width, FRAME_HEIGHT)), (0, 0))
        frame.paste(img.crop((0, 0, FRAME_WIDTH - first_part, FRAME_HEIGHT)), (first_part, 0))

    return image_to_rgb332_direct(frame)


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
