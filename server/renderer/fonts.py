"""Font manager com cache — carrega fontes TrueType uma vez."""

import logging
from functools import lru_cache

from PIL import ImageFont

logger: logging.Logger = logging.getLogger("renderer.fonts")

_FONT_PATHS: list[str] = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

_BOLD_PATHS: list[str] = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


@lru_cache(maxsize=32)
def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carrega fonte regular com fallback. Resultado cacheado por tamanho."""
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=32)
def get_font_bold(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carrega fonte bold com fallback. Resultado cacheado por tamanho."""
    for path in _BOLD_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return get_font(size)
