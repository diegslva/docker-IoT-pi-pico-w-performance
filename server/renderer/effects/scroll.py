"""Efeito Scroll — imagem desliza continuamente entre TVs."""

from PIL import Image

from server.renderer.effects.base import EffectContext, EffectRenderer
from server.renderer.rgb332 import FRAME_HEIGHT, FRAME_WIDTH, image_to_rgb332


class ScrollEffect(EffectRenderer):
    """Imagem larga scrolla continuamente por todas as TVs."""

    def render(self, ctx: EffectContext) -> bytes:
        wall_width: int = FRAME_WIDTH * ctx.total_positions
        img: Image.Image = ctx.image.copy().resize((wall_width, FRAME_HEIGHT))
        img_width: int = img.width

        offset: int = (ctx.tick * ctx.speed) % img_width
        x_start: int = (offset + ctx.position * FRAME_WIDTH) % img_width

        frame: Image.Image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT))
        if x_start + FRAME_WIDTH <= img_width:
            frame.paste(img.crop((x_start, 0, x_start + FRAME_WIDTH, FRAME_HEIGHT)), (0, 0))
        else:
            first_part: int = img_width - x_start
            frame.paste(img.crop((x_start, 0, img_width, FRAME_HEIGHT)), (0, 0))
            frame.paste(img.crop((0, 0, FRAME_WIDTH - first_part, FRAME_HEIGHT)), (first_part, 0))

        return image_to_rgb332(frame)
