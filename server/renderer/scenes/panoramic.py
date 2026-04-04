"""Cena panoramica — multi-display com ciclo dia/noite, animacoes em tempo real.

Arquitetura de camadas:
- Camada estatica (cacheada por minuto): ceu, sol/lua, palmeiras
- Camada dinamica (por frame): oceano com ondas, reflexo cintilante, estrelas piscando

A 15 FPS via TCP streaming, as animacoes ficam visivelmente fluidas.
"""

import logging
import math
import random
import time

import numpy as np
from PIL import Image, ImageDraw

from server.renderer.config import FRAME_HEIGHT, FRAME_WIDTH, image_to_frame
from server.renderer.fonts import get_font_bold
from server.renderer.scenes.base import RenderContext, SceneRenderer
from server.renderer.text import draw_scrolling_text

logger: logging.Logger = logging.getLogger("scene.panoramic")

# --- Cache da camada estatica (ceu + sol/lua + palmeiras) ---
_sky_cache: np.ndarray | None = None
_sky_cache_key: str = ""
_sky_cache_meta: dict = {}


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


def _render_sky(total_positions: int, hour: int, minute: int) -> tuple[np.ndarray, dict]:
    """Renderiza camada estatica (ceu + astros + palmeiras). Cacheada por minuto."""
    global _sky_cache, _sky_cache_key, _sky_cache_meta

    cache_key: str = f"{total_positions}_{hour}_{minute}"
    if _sky_cache is not None and _sky_cache_key == cache_key:
        return _sky_cache.copy(), _sky_cache_meta

    W: int = FRAME_WIDTH * total_positions
    H: int = FRAME_HEIGHT
    h: float = hour + minute / 60

    sky_top, sky_bottom, is_night = _sky_colors(hour, minute)
    arr: np.ndarray = np.zeros((H, W, 3), dtype=np.float32)

    # Sky gradient
    sky_t: np.ndarray = np.linspace(0, 1, 150).reshape(150, 1)
    for c in range(3):
        arr[:150, :, c] = sky_top[c] + (sky_bottom[c] - sky_top[c]) * sky_t

    sun_x: int = 0
    if is_night:
        # Lua
        moon_x: int = int(W * 0.6)
        moon_y: int = 50
        moon_r: int = 25
        my, mx = np.ogrid[
            moon_y - moon_r : moon_y + moon_r + 1, moon_x - moon_r : moon_x + moon_r + 1
        ]
        dist: np.ndarray = np.sqrt((mx - moon_x) ** 2 + (my - moon_y) ** 2)
        mask: np.ndarray = dist <= moon_r
        intensity: np.ndarray = np.where(mask, 1.0 - (dist / moon_r) * 0.2, 0)

        y_s = max(0, moon_y - moon_r)
        y_e = min(H, moon_y + moon_r + 1)
        x_s = max(0, moon_x - moon_r)
        x_e = min(W, moon_x + moon_r + 1)
        sl_y: slice = slice(y_s - (moon_y - moon_r), y_e - (moon_y - moon_r))
        sl_x: slice = slice(x_s - (moon_x - moon_r), x_e - (moon_x - moon_r))
        moon_i: np.ndarray = intensity[sl_y, sl_x]
        moon_mask: np.ndarray = mask[sl_y, sl_x]

        arr[y_s:y_e, x_s:x_e, 0] = np.where(moon_mask, 220 * moon_i, arr[y_s:y_e, x_s:x_e, 0])
        arr[y_s:y_e, x_s:x_e, 1] = np.where(moon_mask, 220 * moon_i, arr[y_s:y_e, x_s:x_e, 1])
        arr[y_s:y_e, x_s:x_e, 2] = np.where(moon_mask, 240 * moon_i, arr[y_s:y_e, x_s:x_e, 2])

        # Glow lunar (halo suave)
        glow_r: int = 60
        gy, gx = np.ogrid[
            moon_y - glow_r : moon_y + glow_r + 1, moon_x - glow_r : moon_x + glow_r + 1
        ]
        glow_dist: np.ndarray = np.sqrt((gx - moon_x) ** 2 + (gy - moon_y) ** 2)
        glow_mask: np.ndarray = (glow_dist > moon_r) & (glow_dist <= glow_r)
        glow_i: np.ndarray = np.where(glow_mask, 0.15 * (1 - glow_dist / glow_r), 0)

        gy_s: int = max(0, moon_y - glow_r)
        gy_e: int = min(H, moon_y + glow_r + 1)
        gx_s: int = max(0, moon_x - glow_r)
        gx_e: int = min(W, moon_x + glow_r + 1)
        gsl_y: slice = slice(gy_s - (moon_y - glow_r), gy_e - (moon_y - glow_r))
        gsl_x: slice = slice(gx_s - (moon_x - glow_r), gx_e - (moon_x - glow_r))
        g_i: np.ndarray = glow_i[gsl_y, gsl_x]

        arr[gy_s:gy_e, gx_s:gx_e, 0] = np.clip(arr[gy_s:gy_e, gx_s:gx_e, 0] + 180 * g_i, 0, 255)
        arr[gy_s:gy_e, gx_s:gx_e, 1] = np.clip(arr[gy_s:gy_e, gx_s:gx_e, 1] + 180 * g_i, 0, 255)
        arr[gy_s:gy_e, gx_s:gx_e, 2] = np.clip(arr[gy_s:gy_e, gx_s:gx_e, 2] + 200 * g_i, 0, 255)

        sun_x = moon_x
    else:
        # Sol com glow
        sun_frac: float = max(0.0, min(1.0, (h - 5) / 14))
        sun_x = int(W * 0.1 + (W * 0.8) * sun_frac)
        sun_y: int = int(130 - 80 * math.sin(sun_frac * math.pi))
        radius: int = 40

        # Glow solar (halo quente)
        glow_r = 80
        gy2, gx2 = np.ogrid[
            max(0, sun_y - glow_r) : min(150, sun_y + glow_r + 1),
            max(0, sun_x - glow_r) : min(W, sun_x + glow_r + 1),
        ]
        glow_d: np.ndarray = np.sqrt((gx2 - sun_x) ** 2 + (gy2 - sun_y) ** 2)
        glow_mask2: np.ndarray = (glow_d > radius) & (glow_d <= glow_r)
        glow_i2: np.ndarray = np.where(glow_mask2, 0.12 * (1 - glow_d / glow_r), 0)

        gy2_s: int = max(0, sun_y - glow_r)
        gy2_e: int = min(150, sun_y + glow_r + 1)
        gx2_s: int = max(0, sun_x - glow_r)
        gx2_e: int = min(W, sun_x + glow_r + 1)

        arr[gy2_s:gy2_e, gx2_s:gx2_e, 0] = np.clip(
            arr[gy2_s:gy2_e, gx2_s:gx2_e, 0] + 255 * glow_i2, 0, 255
        )
        arr[gy2_s:gy2_e, gx2_s:gx2_e, 1] = np.clip(
            arr[gy2_s:gy2_e, gx2_s:gx2_e, 1] + 200 * glow_i2, 0, 255
        )
        arr[gy2_s:gy2_e, gx2_s:gx2_e, 2] = np.clip(
            arr[gy2_s:gy2_e, gx2_s:gx2_e, 2] + 60 * glow_i2, 0, 255
        )

        # Sol
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

    # Metadata pra camada dinamica
    meta: dict = {
        "is_night": is_night,
        "sun_x": sun_x,
        "W": W,
        "H": H,
        "total_positions": total_positions,
    }

    _sky_cache = np.clip(arr, 0, 255)
    _sky_cache_key = cache_key
    _sky_cache_meta = meta
    logger.info(
        "Sky layer rendered: %dx%d %d:%02d %s",
        W,
        H,
        hour,
        minute,
        "night" if is_night else "day",
    )
    return _sky_cache.copy(), meta


def _render_ocean_animated(arr: np.ndarray, t: float, meta: dict) -> None:
    """Renderiza oceano animado com ondas em movimento. Modifica arr in-place."""
    W: int = meta["W"]
    H: int = meta["H"]
    is_night: bool = meta["is_night"]

    ocean_brightness: float = 0.2 if is_night else 1.0
    ocean_y: np.ndarray = np.arange(150, H).reshape(-1, 1).astype(np.float32)
    ocean_x: np.ndarray = np.arange(W).reshape(1, -1).astype(np.float32)
    depth: np.ndarray = (ocean_y - 150) / (H - 150)

    # Ondas com offset temporal — se movem continuamente
    wave: np.ndarray = (
        np.sin(ocean_x * 0.03 + ocean_y * 0.08 + t * 1.2) * 12
        + np.sin(ocean_x * 0.07 - ocean_y * 0.05 + t * 0.8) * 6
        + np.sin(ocean_x * 0.015 + t * 0.5) * 4
    )

    # Espuma nas cristas (pontos brancos onde a onda e alta)
    foam: np.ndarray = np.where(wave > 14, (wave - 14) * 0.1, 0)

    arr[150:, :, 0] = np.clip(
        (10 * (1 - depth) + wave * 0.3 + foam * 80) * ocean_brightness, 0, 255
    )
    arr[150:, :, 1] = np.clip(
        (50 + 30 * (1 - depth) + wave * 0.5 + foam * 90) * ocean_brightness, 0, 255
    )
    arr[150:, :, 2] = np.clip(
        (120 + 40 * (1 - depth) + wave + foam * 100) * ocean_brightness, 0, 255
    )


def _render_reflection_animated(arr: np.ndarray, t: float, meta: dict) -> None:
    """Renderiza reflexo cintilante do sol/lua na agua. Modifica arr in-place."""
    W: int = meta["W"]
    is_night: bool = meta["is_night"]
    ref_cx: int = meta["sun_x"]

    ref_y: np.ndarray = np.arange(155, 220).reshape(-1, 1).astype(np.float32)
    ref_x: np.ndarray = np.arange(W).reshape(1, -1).astype(np.float32)
    spread: np.ndarray = (ref_y - 150) * 1.5
    dx_abs: np.ndarray = np.abs(ref_x - ref_cx)

    ref_i: np.ndarray = (
        0.4 * np.maximum(0, 1 - dx_abs / np.maximum(1, spread)) * (1 - (ref_y - 155) / 65)
    )

    # Cintilacao — shimmer com multiplas frequencias temporais
    shimmer: np.ndarray = (
        0.3
        + 0.3 * np.sin(ref_x * 0.1 + ref_y * 0.2 + t * 2.5)
        + 0.2 * np.sin(ref_x * 0.25 - t * 1.8)
        + 0.2 * np.sin(ref_y * 0.15 + t * 3.2)
    )
    ref_i *= shimmer

    if is_night:
        arr[155:220, :, 0] = np.clip(arr[155:220, :, 0] + 100 * ref_i, 0, 255)
        arr[155:220, :, 1] = np.clip(arr[155:220, :, 1] + 100 * ref_i, 0, 255)
        arr[155:220, :, 2] = np.clip(arr[155:220, :, 2] + 120 * ref_i, 0, 255)
    else:
        arr[155:220, :, 0] = np.clip(arr[155:220, :, 0] + 220 * ref_i, 0, 255)
        arr[155:220, :, 1] = np.clip(arr[155:220, :, 1] + 170 * ref_i, 0, 255)
        arr[155:220, :, 2] = np.clip(arr[155:220, :, 2] + 40 * ref_i, 0, 255)


def _render_stars_animated(arr: np.ndarray, t: float, meta: dict) -> None:
    """Renderiza estrelas piscando (noite). Modifica arr in-place."""
    if not meta["is_night"]:
        return

    W: int = meta["W"]
    total_positions: int = meta["total_positions"]
    rng: random.Random = random.Random(42)

    for _ in range(80 * total_positions):
        sx: int = rng.randint(0, W - 1)
        sy: int = rng.randint(0, 130)
        base_brightness: int = rng.randint(120, 255)

        if arr[sy, sx, 0] < 30:
            # Cada estrela pisca com frequencia e fase proprias
            freq: float = rng.uniform(0.5, 3.0)
            phase: float = rng.uniform(0, 6.28)
            twinkle: float = 0.5 + 0.5 * math.sin(t * freq + phase)
            brightness: float = base_brightness * twinkle
            arr[sy, sx] = [brightness, brightness, brightness]


def _render_seagulls_animated(img: Image.Image, t: float, meta: dict) -> None:
    """Renderiza silhuetas de gaivotas planando no ceu. Sutil e nostalgico."""
    if meta["is_night"]:
        return

    W: int = meta["W"]
    total_positions: int = meta["total_positions"]
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

    # Poucas gaivotas — 2 por display, nao uma revoada
    rng: random.Random = random.Random(31)
    num_birds: int = 2 * total_positions

    for _ in range(num_birds):
        base_x: int = rng.randint(0, W - 1)
        base_y: int = rng.randint(30, 120)
        size: int = rng.randint(4, 10)
        speed: float = rng.uniform(6.0, 14.0)
        glide_freq: float = rng.uniform(0.3, 0.8)
        glide_amp: float = rng.uniform(2.0, 5.0)
        wing_freq: float = rng.uniform(1.5, 3.0)

        # Posicao com drift horizontal + oscilacao vertical (planar)
        x: int = int(base_x + t * speed) % W
        y: int = int(base_y + glide_amp * math.sin(t * glide_freq))

        # Abertura das asas oscila suavemente (planar, nao bater)
        wing_angle: float = 0.3 + 0.15 * math.sin(t * wing_freq)

        # Silhueta: forma "V" ou "M" simples — apenas sombra
        half_span: int = size
        shadow_color: tuple[int, int, int] = (20, 15, 10)

        # Asa esquerda (curva pra baixo)
        points_left: list[tuple[int, int]] = []
        for i in range(half_span + 1):
            px: int = x - i
            py: int = int(y + i * wing_angle)
            points_left.append((px, py))

        # Asa direita (curva pra baixo)
        points_right: list[tuple[int, int]] = []
        for i in range(half_span + 1):
            px = x + i
            py = int(y + i * wing_angle)
            points_right.append((px, py))

        if len(points_left) >= 2:
            draw.line(points_left, fill=shadow_color, width=1)
        if len(points_right) >= 2:
            draw.line(points_right, fill=shadow_color, width=1)


def _render_clouds_animated(arr: np.ndarray, t: float, meta: dict) -> None:
    """Renderiza nuvens deslizando lentamente pela direita pra esquerda."""
    if meta["is_night"]:
        return

    W: int = meta["W"]
    total_positions: int = meta["total_positions"]

    # Posicoes base das nuvens (seed fixa pra consistencia entre frames)
    rng: random.Random = random.Random(7)
    num_clouds: int = 3 * total_positions

    for _ in range(num_clouds):
        base_cx: int = rng.randint(0, W - 1)
        cy: int = rng.randint(25, 95)
        cw: int = rng.randint(50, 130)
        ch: int = rng.randint(8, 18)
        alpha: float = rng.uniform(0.03, 0.07)
        drift_speed: float = rng.uniform(3.0, 8.0)

        # Drift lento — posicao muda com o tempo
        cx: int = int(base_cx + t * drift_speed) % W

        # Forma eliptica com gradiente suave (nao um retangulo duro)
        y_s: int = max(0, cy - ch)
        y_e: int = min(150, cy + ch)

        cloud_y: np.ndarray = np.arange(y_s, y_e).reshape(-1, 1).astype(np.float32)
        cloud_x: np.ndarray = np.arange(W).reshape(1, -1).astype(np.float32)

        # Distancia normalizada do centro da nuvem (elipse)
        dy: np.ndarray = (cloud_y - cy) / max(ch, 1)
        dx: np.ndarray = np.minimum(
            np.abs(cloud_x - cx),
            np.abs(cloud_x - cx + W),  # wrap-around
        ) / max(cw, 1)
        dx = np.minimum(dx, np.abs(cloud_x - cx - W) / max(cw, 1))

        dist_sq: np.ndarray = dx * dx + dy * dy
        cloud_mask: np.ndarray = dist_sq < 1.0
        intensity: np.ndarray = np.where(cloud_mask, (1.0 - dist_sq) * alpha * 255, 0)

        arr[y_s:y_e, :] = np.clip(arr[y_s:y_e, :] + intensity[:, :, np.newaxis], 0, 255)


def _draw_palm_trees(img: Image.Image, total_positions: int, is_night: bool) -> None:
    """Desenha palmeiras sobre a imagem. Chamado apos composicao das camadas."""
    W: int = img.width
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
            for pt in range(45):
                lx: int = int(leaf_bx + pt * math.cos(angle))
                ly: int = int(leaf_by - pt * math.sin(angle) + pt * pt * 0.007)
                points.append((lx, ly))
            if len(points) >= 2:
                draw.line(points, fill=leaf_color, width=4)


class PanoramicScene(SceneRenderer):
    """Cena panoramica multi-display com animacoes em tempo real."""

    SCROLL_SPEED: float = 15.0

    def render(self, ctx: RenderContext) -> bytes:
        # Camada estatica (cacheada por minuto)
        sky_arr, meta = _render_sky(ctx.total_devices, ctx.hour, ctx.minute)

        # Tempo fracionario pra animacoes sub-segundo
        t: float = time.monotonic()

        # Camada dinamica (por frame)
        _render_clouds_animated(sky_arr, t, meta)
        _render_ocean_animated(sky_arr, t, meta)
        _render_reflection_animated(sky_arr, t, meta)
        _render_stars_animated(sky_arr, t, meta)

        img: Image.Image = Image.fromarray(np.clip(sky_arr, 0, 255).astype(np.uint8))

        # Gaivotas (silhuetas no ceu, sobre a imagem PIL)
        _render_seagulls_animated(img, t, meta)

        # Palmeiras (sobre tudo)
        _draw_palm_trees(img, meta["total_positions"], meta["is_night"])

        # Textos scrolling
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
        W: int = img.width

        font_title = get_font_bold(28)
        font_info = get_font_bold(18)
        font_motiv = get_font_bold(14)

        tick: float = (
            ctx.hour * 3600 + ctx.minute * 60 + ctx.second + ctx.now.microsecond / 1_000_000
        )
        offset_px: int = int(tick * self.SCROLL_SPEED)

        title_str: str = "Vitoria Sports - ES"
        clock_str: str = f"Vitoria Sports  -  {ctx.timestamp}  -  ES"
        motiv_str: str = "Vitoria Sports  -  Bora treinar!  -  ES"

        draw_scrolling_text(
            draw,
            title_str,
            y=10,
            fill=(255, 220, 100),
            shadow=(20, 5, 0),
            font=font_title,
            canvas_width=W,
            offset_px=offset_px,
        )

        draw_scrolling_text(
            draw,
            clock_str,
            y=193,
            fill=(255, 255, 200),
            shadow=(20, 5, 0),
            font=font_info,
            canvas_width=W,
            offset_px=offset_px,
        )

        draw_scrolling_text(
            draw,
            motiv_str,
            y=220,
            fill=(0, 255, 150),
            shadow=(20, 5, 0),
            font=font_motiv,
            canvas_width=W,
            offset_px=offset_px,
        )

        x_start: int = ctx.position * FRAME_WIDTH
        x_end: int = x_start + FRAME_WIDTH
        return image_to_frame(img.crop((x_start, 0, x_end, FRAME_HEIGHT)))
