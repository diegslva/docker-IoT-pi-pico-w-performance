"""Configuracao de color mode — despacha entre RGB332 e RGB565.

COLOR_MODE e lido do env. Default: "rgb332" (compativel com Pico W 264KB RAM).
Trocar para "rgb565" quando usar Pico 2 W (520KB RAM).
Todos os scenes/effects importam daqui: uma unica variavel muda o formato inteiro.
"""

import os
from collections.abc import Callable

from dotenv import load_dotenv

# Carrega .env antes de ler env vars (funciona em qualquer subprocess)
load_dotenv()

COLOR_MODE: str = os.getenv("COLOR_MODE", "rgb332")

if COLOR_MODE == "rgb332":
    from server.renderer.rgb332 import FRAME_HEIGHT, FRAME_SIZE, FRAME_WIDTH
    from server.renderer.rgb332 import image_to_rgb332 as _convert
else:
    from server.renderer.rgb565 import FRAME_HEIGHT, FRAME_SIZE, FRAME_WIDTH
    from server.renderer.rgb565 import image_to_rgb565 as _convert

image_to_frame: Callable[..., bytes] = _convert

__all__: list[str] = ["image_to_frame", "FRAME_WIDTH", "FRAME_HEIGHT", "FRAME_SIZE", "COLOR_MODE"]
