"""Cena Vitoria Sports — single display com sunset e mensagens."""

import logging
import math

from PIL import Image, ImageDraw

from server.renderer.config import FRAME_HEIGHT, FRAME_WIDTH, image_to_frame
from server.renderer.fonts import get_font, get_font_bold
from server.renderer.scenes.base import RenderContext, SceneRenderer

logger: logging.Logger = logging.getLogger("scene.vitoria_sports")

MESSAGES: list[str] = [
    "Bem-vindo!",
    "Bora treinar!",
    "Supere seus limites",
    "Foco e disciplina",
    "Seu corpo agradece",
    "Mais forte a cada dia",
]

_sunset_base: Image.Image | None = None


def _render_sunset_base() -> Image.Image:
    """Renderiza background do por do sol (cacheado permanentemente)."""
    global _sunset_base
    if _sunset_base is not None:
        return _sunset_base.copy()

    img: Image.Image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), color=(0, 0, 0))
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

    for y in range(140):
        r: int = int(20 + (235 * y / 140))
        g: int = int(10 + (100 * (1 - y / 140)))
        b: int = int(80 * (1 - y / 140))
        draw.line([(0, y), (319, y)], fill=(min(255, r), max(0, g), max(0, b)))

    cx, cy, radius = 160, 70, 30
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            dist: float = math.sqrt(dx * dx + dy * dy)
            if dist <= radius:
                intensity: float = 1.0 - (dist / radius) * 0.3
                px, py = cx + dx, cy + dy
                if 0 <= px < 320 and 0 <= py < 240:
                    img.putpixel(
                        (px, py),
                        (
                            min(255, int(255 * intensity)),
                            min(255, int(220 * intensity)),
                            min(255, int(50 * intensity)),
                        ),
                    )

    for y in range(140, 240):
        depth: float = (y - 140) / 100
        for x in range(320):
            wave: float = math.sin(x * 0.05 + y * 0.1) * 10
            img.putpixel(
                (x, y),
                (
                    max(0, min(255, int(10 * (1 - depth) + wave * 0.3))),
                    max(0, min(255, int(50 + 30 * (1 - depth) + wave * 0.5))),
                    max(0, min(255, int(120 + 40 * (1 - depth) + wave))),
                ),
            )

    for y in range(145, 200):
        spread: float = (y - 140) * 0.8
        for dx in range(int(-spread), int(spread) + 1):
            x: int = 160 + dx
            if 0 <= x < 320:
                ref: float = 0.6 * (1 - abs(dx) / max(1, spread)) * (1 - (y - 145) / 55)
                pr, pg, pb = img.getpixel((x, y))
                img.putpixel(
                    (x, y),
                    (
                        min(255, int(pr + 200 * ref)),
                        min(255, int(pg + 150 * ref)),
                        min(255, int(pb + 30 * ref)),
                    ),
                )

    trunk_x: int = 60
    for y in range(80, 145):
        lean: int = int((145 - y) * 0.15)
        for dx in range(-2, 3):
            px = trunk_x + lean + dx
            if 0 <= px < 320:
                img.putpixel((px, y), (15, 10, 5))

    leaf_bx: int = trunk_x + int(65 * 0.15)
    leaf_by: int = 80
    for angle_deg in [-30, -10, 15, 40, 60, -50]:
        angle: float = math.radians(angle_deg)
        for t in range(40):
            lx: int = int(leaf_bx + t * math.cos(angle))
            ly: int = int(leaf_by - t * math.sin(angle) + t * t * 0.008)
            for w in range(-1, 2):
                if 0 <= lx < 320 and 0 <= ly + w < 240:
                    img.putpixel((lx, ly + w), (10, 8, 3))

    _sunset_base = img.copy()
    logger.info("Sunset base rendered and cached")
    return img


class VitoriaSportsScene(SceneRenderer):
    """Cena single-display com sunset, titulo, horario e mensagem."""

    def render(self, ctx: RenderContext) -> bytes:
        img: Image.Image = _render_sunset_base()
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

        font_title = get_font_bold(24)
        font_sub = get_font(14)
        font_clock = get_font_bold(18)
        font_msg = get_font_bold(16)

        draw.text((162, 12), "Vitoria Sports", fill=(30, 10, 0), font=font_title, anchor="mt")
        draw.text((160, 10), "Vitoria Sports", fill=(255, 220, 100), font=font_title, anchor="mt")

        draw.text((162, 38), "- ES -", fill=(30, 10, 0), font=font_sub, anchor="mt")
        draw.text((160, 36), "- ES -", fill=(200, 180, 120), font=font_sub, anchor="mt")

        draw.text((162, 198), ctx.timestamp, fill=(20, 5, 0), font=font_clock, anchor="mt")
        draw.text((160, 196), ctx.timestamp, fill=(255, 255, 200), font=font_clock, anchor="mt")

        msg: str = MESSAGES[ctx.frame_index % len(MESSAGES)]
        draw.text((162, 220), msg, fill=(20, 5, 0), font=font_msg, anchor="mt")
        draw.text((160, 218), msg, fill=(0, 255, 150), font=font_msg, anchor="mt")

        return image_to_frame(img)
