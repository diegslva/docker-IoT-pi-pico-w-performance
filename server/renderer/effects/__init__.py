"""Effect registry — efeitos multi-display plugaveis."""

from server.renderer.effects.base import EffectContext, EffectRenderer
from server.renderer.effects.scroll import ScrollEffect
from server.renderer.effects.wall import WallEffect
from server.renderer.effects.wave import WaveEffect

EFFECT_REGISTRY: dict[str, EffectRenderer] = {
    "wave": WaveEffect(),
    "wall": WallEffect(),
    "scroll": ScrollEffect(),
}

__all__: list[str] = ["EffectContext", "EffectRenderer", "EFFECT_REGISTRY"]
