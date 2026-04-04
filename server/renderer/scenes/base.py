"""Base class para cenas renderizaveis."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RenderContext:
    """Contexto imutavel passado pra cada cena no momento da renderizacao."""

    position: int
    total_devices: int
    timestamp: str
    hour: int
    minute: int
    second: int
    frame_index: int
    now: datetime

    # Dados opcionais por cena
    btc_price: float = 0.0
    eth_price: float = 0.0


class SceneRenderer(ABC):
    """Interface base para cenas renderizaveis."""

    @abstractmethod
    def render(self, ctx: RenderContext) -> bytes:
        """Renderiza frame para a posicao do device."""
        ...
