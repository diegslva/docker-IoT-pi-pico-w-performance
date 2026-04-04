"""Efeito Wave — imagem viaja de TV em TV."""

import logging

from PIL import Image

from server.renderer.effects.base import EffectContext, EffectRenderer
from server.renderer.rgb332 import FRAME_HEIGHT, FRAME_WIDTH, image_to_rgb332
from server.renderer.scenes.base import RenderContext
from server.renderer.scenes.vitoria_sports import VitoriaSportsScene

logger: logging.Logger = logging.getLogger("effect.wave")

_fallback_scene: VitoriaSportsScene = VitoriaSportsScene()


class WaveEffect(EffectRenderer):
    """Imagem aparece na TV ativa, outras mostram Vitoria Sports."""

    def render(self, ctx: EffectContext) -> bytes:
        active_position: int = ctx.tick % ctx.total_positions
        if ctx.position == active_position:
            img: Image.Image = ctx.image.copy().resize((FRAME_WIDTH, FRAME_HEIGHT))
            return image_to_rgb332(img)

        fallback_ctx: RenderContext = RenderContext(
            position=ctx.position,
            total_devices=1,
            timestamp=ctx.timestamp,
            hour=0,
            minute=0,
            second=0,
            frame_index=ctx.frame_index,
            now=__import__("datetime").datetime.now(),
        )
        return _fallback_scene.render(fallback_ctx)
