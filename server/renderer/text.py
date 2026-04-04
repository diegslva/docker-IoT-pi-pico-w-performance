"""Utilidades de texto scrolling para renderizacao."""

import logging

from PIL import ImageDraw, ImageFont

from server.renderer.rgb332 import FRAME_WIDTH

logger: logging.Logger = logging.getLogger("renderer.text")


def draw_scrolling_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    fill: tuple[int, int, int],
    shadow: tuple[int, int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    canvas_width: int,
    offset_px: int,
) -> None:
    """Desenha texto scrollando da direita pra esquerda com repeticao continua.

    O texto se repete com spacing fixo de 1 TV (320px) entre copias,
    garantindo que sempre ha texto visivel em cada display.
    """
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width: int = bbox[2] - bbox[0]

    # Spacing entre repeticoes = largura de 2 TVs (gap generoso)
    spacing: int = FRAME_WIDTH * 2
    cycle: int = text_width + spacing

    # Posicao base
    base_x: int = -(offset_px % cycle)

    # Desenha repeticoes suficientes pra cobrir todo o canvas
    x: int = base_x
    while x < canvas_width:
        if x + text_width > 0:
            draw.text((x + 2, y + 2), text, fill=shadow, font=font, anchor="lt")
            draw.text((x, y), text, fill=fill, font=font, anchor="lt")
        x += cycle
