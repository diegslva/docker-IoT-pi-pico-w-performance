"""Conversao de imagens para formato RGB332 (8-bit) via NumPy.

RGB332: 3 bits red (bits 7-5) + 3 bits green (bits 4-2) + 2 bits blue (bits 1-0)
Total: 256 cores possiveis.
"""

import numpy as np
from PIL import Image

FRAME_WIDTH: int = 320
FRAME_HEIGHT: int = 240
FRAME_SIZE: int = FRAME_WIDTH * FRAME_HEIGHT  # 76800 bytes


def image_to_rgb332(
    img: Image.Image, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT
) -> bytes:
    """Converte imagem Pillow para RGB332 via NumPy vetorizado."""
    img = img.convert("RGB")
    if img.size != (width, height):
        img = img.resize((width, height))

    arr: np.ndarray = np.array(img, dtype=np.uint8)
    r: np.ndarray = arr[:, :, 0] & 0xE0
    g: np.ndarray = (arr[:, :, 1] >> 3) & 0x1C
    b: np.ndarray = (arr[:, :, 2] >> 6) & 0x03

    return (r | g | b).tobytes()
