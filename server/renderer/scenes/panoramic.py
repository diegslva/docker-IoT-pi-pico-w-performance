"""Cena panoramica — multi-display com ciclo dia/noite, sol/lua, scrolling text."""

import logging
import math
import random

import numpy as np
from PIL import Image, ImageDraw

from server.renderer.fonts import get_font_bold
from server.renderer.rgb332 import FRAME_HEIGHT, FRAME_WIDTH, image_to_rgb332
from server.renderer.scenes.base import RenderContext, SceneRenderer
from server.renderer.text import draw_scrolling_text

logger: logging.Logger = logging.getLogger("scene.panoramic")

MESSAGES: list[str] = [
    "Bem-vindo!",
    "Bora treinar!",
    "Supere seus limites",
    "Foco e disciplina",
    "Seu corpo agradece",
    "Mais forte a cada dia",
]

_panoramic_cache: Image.Image | None = None
_panoramic_cache_key: str = ""


def _sky_colors(hour: int, minute: int) -> tuple[tuple[int, int, int], tuple[int, int, int], bool]:
    """Retorna (sky_top, sky_bottom, is_night) baseado no horario."""
    h: float = hour + minute / 60

    if h < 5 or h >= 20:
        return (5, 5, 20), (10, 10, 40), True
    elif h < 6:
        t: float = h - 5
        return (
            (int(5 + 15 * t), int(5 + 5 * t), int(20 + 30 * t)),
            (int(10 + 80 * t), int(10 + 30 * t), int(40 + 20 * t)),
            False,
        )
    elif h < 7.5:
        return (20, 10, 50), (255, 100, 30), False
    elif h < 9:
        return (20, 20, 80), (240, 140, 40), False
    elif h < 15:
        return (15, 30, 100), (200, 160, 60), False
    elif h < 17:
        return (20, 20, 80), (240, 140, 40), False
    elif h < 18.5:
        return (15, 5, 40), (255, 100, 30), False
    elif h < 20:
        t = (h - 18.5) / 1.5
        return (
            (int(15 - 10 * t), 5, int(40 - 20 * t)),
            (int(100 - 90 * t), int(40 - 30 * t), 30),
            False,
        )
    return (5, 5, 20), (10, 10, 40), True


def _render_base(total_positions: int, hour: int, minute: int) -> Image.Image:
    """Renderiza panorama base via NumPy. Cacheado por minuto."""
    global _panoramic_cache, _panoramic_cache_key

    cache_key: str = f"{total_positions}_{hour}_{minute}"
    if _panoramic_cache is not None and _panoramic_cache_key == cache_key:
        return _panoramic_cache.copy()

    W: int = FRAME_WIDTH * total_positions
    H: int = FRAME_HEIGHT
    h: float = hour + minute / 60

    sky_top, sky_bottom, is_night = _sky_colors(hour, minute)
    arr: np.ndarray = np.zeros((H, W, 3), dtype=np.float32)

    # Sky gradient
    sky_t: np.ndarray = np.linspace(0, 1, 150).reshape(150, 1)
    for c in range(3):
        arr[:150, :, c] = sky_top[c] + (sky_bottom[c] - sky_top[c]) * sky_t

    if is_night:
        # Moon
        moon_x: int = int(W * 0.6)
        moon_y: int = 50
        moon_r: int = 25
        my, mx = np.ogrid[
            moon_y - moon_r : moon_y + moon_r + 1, moon_x - moon_r : moon_x + moon_r + 1
        ]
        dist: np.ndarray = np.sqrt((mx - moon_x) ** 2 + (my - moon_y) ** 2)
        mask: np.ndarray = dist <= moon_r
        intensity: np.ndarray = np.where(mask, 1.0 - (dist / moon_r) * 0.2, 0)

        y_s: int = max(0, moon_y - moon_r)
        y_e: int = min(H, moon_y + moon_r + 1)
        x_s: int = max(0, moon_x - moon_r)
        x_e: int = min(W, moon_x + moon_r + 1)
        sl_y: slice = slice(y_s - (moon_y - moon_r), y_e - (moon_y - moon_r))
        sl_x: slice = slice(x_s - (moon_x - moon_r), x_e - (moon_x - moon_r))
        moon_i: np.ndarray = intensity[sl_y, sl_x]
        moon_mask: np.ndarray = mask[sl_y, sl_x]

        arr[y_s:y_e, x_s:x_e, 0] = np.where(moon_mask, 220 * moon_i, arr[y_s:y_e, x_s:x_e, 0])
        arr[y_s:y_e, x_s:x_e, 1] = np.where(moon_mask, 220 * moon_i, arr[y_s:y_e, x_s:x_e, 1])
        arr[y_s:y_e, x_s:x_e, 2] = np.where(moon_mask, 240 * moon_i, arr[y_s:y_e, x_s:x_e, 2])

        rng: random.Random = random.Random(42)
        for _ in range(80 * total_positions):
            sx: int = rng.randint(0, W - 1)
            sy: int = rng.randint(0, 130)
            brightness: int = rng.randint(120, 255)
            if arr[sy, sx, 0] < 30:
                arr[sy, sx] = [brightness, brightness, brightness]
    else:
        sun_frac: float = max(0.0, min(1.0, (h - 5) / 14))
        sun_x: int = int(W * 0.1 + (W * 0.8) * sun_frac)
        sun_y: int = int(130 - 80 * math.sin(sun_frac * math.pi))
        radius: int = 40

        sy_s: int = max(0, sun_y - radius)
        sy_e: int = min(150, sun_y + radius + 1)
        sx_s: int = max(0, sun_x - radius)
        sx_e: int = min(W, sun_x + radius + 1)

        yy, xx = np.ogrid[sy_s:sy_e, sx_s:sx_e]
        sun_dist: np.ndarray = np.sqrt((xx - sun_x) ** 2 + (yy - sun_y) ** 2)
        sun_mask: np.ndarray = sun_dist <= radius
        sun_i: np.ndarray = np.where(sun_mask, 1.0 - (sun_dist / radius) * 0.3, 0)

        arr[sy_s:sy_e, sx_s:sx_e, 0] = np.where(
            sun_mask, np.minimum(255, 255 * sun_i), arr[sy_s:sy_e, sx_s:sx_e, 0]
        )
        arr[sy_s:sy_e, sx_s:sx_e, 1] = np.where(
            sun_mask, np.minimum(255, 230 * sun_i), arr[sy_s:sy_e, sx_s:sx_e, 1]
        )
        arr[sy_s:sy_e, sx_s:sx_e, 2] = np.where(
            sun_mask, np.minimum(255, 60 * sun_i), arr[sy_s:sy_e, sx_s:sx_e, 2]
        )

    # Ocean
    ocean_brightness: float = 0.2 if is_night else 1.0
    ocean_y: np.ndarray = np.arange(150, H).reshape(-1, 1).astype(np.float32)
    ocean_x: np.ndarray = np.arange(W).reshape(1, -1).astype(np.float32)
    depth: np.ndarray = (ocean_y - 150) / (H - 150)
    wave: np.ndarray = (
        np.sin(ocean_x * 0.03 + ocean_y * 0.08) * 12 + np.sin(ocean_x * 0.07 - ocean_y * 0.05) * 6
    )

    arr[150:, :, 0] = np.clip((10 * (1 - depth) + wave * 0.3) * ocean_brightness, 0, 255)
    arr[150:, :, 1] = np.clip((50 + 30 * (1 - depth) + wave * 0.5) * ocean_brightness, 0, 255)
    arr[150:, :, 2] = np.clip((120 + 40 * (1 - depth) + wave) * ocean_brightness, 0, 255)

    # Reflection
    ref_cx: int = int(W * 0.6) if is_night else sun_x
    ref_y: np.ndarray = np.arange(155, 220).reshape(-1, 1).astype(np.float32)
    ref_x: np.ndarray = np.arange(W).reshape(1, -1).astype(np.float32)
    spread: np.ndarray = (ref_y - 150) * 1.5
    dx_abs: np.ndarray = np.abs(ref_x - ref_cx)
    ref_i: np.ndarray = (
        0.4 * np.maximum(0, 1 - dx_abs / np.maximum(1, spread)) * (1 - (ref_y - 155) / 65)
    )
    ref_i *= 0.5 + 0.5 * np.sin(ref_x * 0.1 + ref_y * 0.2)

    if is_night:
        arr[155:220, :, 0] = np.clip(arr[155:220, :, 0] + 100 * ref_i, 0, 255)
        arr[155:220, :, 1] = np.clip(arr[155:220, :, 1] + 100 * ref_i, 0, 255)
        arr[155:220, :, 2] = np.clip(arr[155:220, :, 2] + 120 * ref_i, 0, 255)
    else:
        arr[155:220, :, 0] = np.clip(arr[155:220, :, 0] + 220 * ref_i, 0, 255)
        arr[155:220, :, 1] = np.clip(arr[155:220, :, 1] + 170 * ref_i, 0, 255)
        arr[155:220, :, 2] = np.clip(arr[155:220, :, 2] + 40 * ref_i, 0, 255)

    img: Image.Image = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    # Palm trees
    palm_positions: list[int] = [80]
    if total_positions >= 2:
        palm_positions.append(W - 100)
    if total_positions >= 4:
        palm_positions.extend([W // 3, 2 * W // 3])

    tree_color: tuple[int, int, int] = (5, 3, 2) if is_night else (15, 10, 5)
    leaf_color: tuple[int, int, int] = (3, 2, 1) if is_night else (8, 6, 3)

    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
    for trunk_x in palm_positions:
        for y in range(75, 155):
            lean: int = int((155 - y) * 0.12)
            draw.line([(trunk_x + lean - 3, y), (trunk_x + lean + 3, y)], fill=tree_color)
        leaf_bx: int = trunk_x + int(80 * 0.12)
        leaf_by: int = 75
        for a in [-40, -20, 0, 25, 50, 70, -55]:
            angle: float = math.radians(a)
            points: list[tuple[int, int]] = []
            for t in range(45):
                lx: int = int(leaf_bx + t * math.cos(angle))
                ly: int = int(leaf_by - t * math.sin(angle) + t * t * 0.007)
                points.append((lx, ly))
            if len(points) >= 2:
                draw.line(points, fill=leaf_color, width=4)

    _panoramic_cache = img.copy()
    _panoramic_cache_key = cache_key
    logger.info(
        "Panoramic rendered (NumPy): %dx%d %d:%02d %s",
        W,
        H,
        hour,
        minute,
        "night" if is_night else "day",
    )
    return img


class PanoramicScene(SceneRenderer):
    """Cena panoramica multi-display com ciclo dia/noite e textos scrolling."""

    SCROLL_SPEED: float = 15.0

    def render(self, ctx: RenderContext) -> bytes:
        img: Image.Image = _render_base(ctx.total_devices, ctx.hour, ctx.minute)
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
        W: int = img.width

        font_title = get_font_bold(28)
        font_info = get_font_bold(18)
        font_motiv = get_font_bold(14)

        tick: float = ctx.hour * 3600 + ctx.minute * 60 + ctx.second
        offset_px: int = int(tick * self.SCROLL_SPEED)

        # Todos os textos com mesmo comprimento pra mesmo cycle visual.
        # Pad com espacos pra igualar largura percebida.
        title_str: str = "Vitoria Sports - ES"
        clock_str: str = f"Vitoria Sports  -  {ctx.timestamp}  -  ES"
        motiv_str: str = "Vitoria Sports  -  Bora treinar!  -  ES"

        draw_scrolling_text(
            draw, title_str, y=10,
            fill=(255, 220, 100), shadow=(20, 5, 0),
            font=font_title, canvas_width=W, offset_px=offset_px,
        )

        draw_scrolling_text(
            draw, clock_str, y=193,
            fill=(255, 255, 200), shadow=(20, 5, 0),
            font=font_info, canvas_width=W, offset_px=offset_px,
        )

        draw_scrolling_text(
            draw, motiv_str, y=220,
            fill=(0, 255, 150), shadow=(20, 5, 0),
            font=font_motiv, canvas_width=W, offset_px=offset_px,
        )

        x_start: int = ctx.position * FRAME_WIDTH
        x_end: int = x_start + FRAME_WIDTH
        return image_to_rgb332(img.crop((x_start, 0, x_end, FRAME_HEIGHT)))
