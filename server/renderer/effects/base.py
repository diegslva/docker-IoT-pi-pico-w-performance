"""Base class para efeitos multi-display."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class EffectContext:
    """Contexto imutavel para renderizacao de efeitos."""

    image: Image.Image
    position: int
    tick: int
    total_positions: int
    speed: int
    timestamp: str
    frame_index: int


class EffectRenderer(ABC):
    """Interface base para efeitos multi-display."""

    @abstractmethod
    def render(self, ctx: EffectContext) -> bytes:
        """Renderiza frame RGB332 do efeito para a posicao do device."""
        ...
