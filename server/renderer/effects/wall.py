"""Efeito Video Wall — imagem panoramica dividida entre TVs."""

from PIL import Image

from server.renderer.effects.base import EffectContext, EffectRenderer
from server.renderer.rgb332 import FRAME_HEIGHT, FRAME_WIDTH, image_to_rgb332


class WallEffect(EffectRenderer):
    """Cada TV mostra um pedaco da imagem panoramica."""

    def render(self, ctx: EffectContext) -> bytes:
        wall_width: int = FRAME_WIDTH * ctx.total_positions
        img: Image.Image = ctx.image.copy().resize((wall_width, FRAME_HEIGHT))

        x_start: int = ctx.position * FRAME_WIDTH
        x_end: int = x_start + FRAME_WIDTH
        return image_to_rgb332(img.crop((x_start, 0, x_end, FRAME_HEIGHT)))
