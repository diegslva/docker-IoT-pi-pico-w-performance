"""Conversao de imagens para formato RGB565 (16-bit) via NumPy.

RGB565: 5 bits red (bits 15-11) + 6 bits green (bits 10-5) + 5 bits blue (bits 4-0)
Total: 65.536 cores. Big-endian (MSB first) para compatibilidade com picodvi.
"""

import logging

import numpy as np
from PIL import Image

logger: logging.Logger = logging.getLogger("renderer.rgb565")

FRAME_WIDTH: int = 320
FRAME_HEIGHT: int = 240
BYTES_PER_PIXEL: int = 2
FRAME_SIZE: int = FRAME_WIDTH * FRAME_HEIGHT * BYTES_PER_PIXEL  # 153600 bytes


def image_to_rgb565(
    img: Image.Image, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT
) -> bytes:
    """Converte imagem Pillow para RGB565 big-endian via NumPy vetorizado."""
    img = img.convert("RGB")
    if img.size != (width, height):
        img = img.resize((width, height))

    arr: np.ndarray = np.array(img, dtype=np.uint16)
    r: np.ndarray = (arr[:, :, 0] >> 3) << 11  # 5 bits red
    g: np.ndarray = (arr[:, :, 1] >> 2) << 5  # 6 bits green
    b: np.ndarray = arr[:, :, 2] >> 3  # 5 bits blue

    rgb565: np.ndarray = (r | g | b).astype(">u2")  # big-endian uint16
    return rgb565.tobytes()
