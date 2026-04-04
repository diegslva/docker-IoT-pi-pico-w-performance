"""Gerenciador de efeitos multi-display com lock async."""

import asyncio
import logging
import time

from PIL import Image

from server.observability import effect_changes_total

logger: logging.Logger = logging.getLogger("effect_manager")


class EffectManager:
    """Estado dos efeitos com thread safety via asyncio.Lock."""

    def __init__(self) -> None:
        self._mode: str = "default"
        self._image: Image.Image | None = None
        self._speed: int = 20
        self._total_positions: int = 12
        self._start_time: float = 0.0
        self._custom_frame: bytes | None = None
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def custom_frame(self) -> bytes | None:
        return self._custom_frame

    @property
    def image(self) -> Image.Image | None:
        return self._image

    @property
    def speed(self) -> int:
        return self._speed

    @property
    def total_positions(self) -> int:
        return self._total_positions

    def tick(self) -> int:
        """Retorna tick baseado em tempo desde o inicio do efeito."""
        return int(time.monotonic() - self._start_time)

    async def set_effect(
        self,
        mode: str,
        image: Image.Image,
        speed: int = 20,
        total_positions: int = 12,
    ) -> None:
        """Configura efeito ativo."""
        async with self._lock:
            self._mode = mode
            self._image = image
            self._speed = speed
            self._total_positions = total_positions
            self._start_time = time.monotonic()
            effect_changes_total.inc(mode=mode)
            logger.info("Effect set: mode=%s positions=%d speed=%d", mode, total_positions, speed)

    async def clear_effect(self) -> None:
        """Remove efeito, volta pro padrao."""
        async with self._lock:
            self._mode = "default"
            self._image = None
            self._start_time = 0.0
            effect_changes_total.inc(mode="default")
            logger.info("Effect cleared")

    async def set_custom_frame(self, frame: bytes) -> None:
        """Define frame customizado (imagem upload)."""
        async with self._lock:
            self._custom_frame = frame
            logger.info("Custom frame set (%d bytes)", len(frame))

    async def clear_custom_frame(self) -> None:
        """Remove frame customizado."""
        async with self._lock:
            self._custom_frame = None
            logger.info("Custom frame cleared")
