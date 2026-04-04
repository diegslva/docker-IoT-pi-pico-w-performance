"""Utilidades de texto scrolling para renderizacao."""

from PIL import ImageDraw, ImageFont


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
    """Desenha texto scrollando da direita pra esquerda com wrap-around.

    Args:
        draw: ImageDraw instance
        text: texto a renderizar
        y: posicao vertical
        fill: cor do texto
        shadow: cor da sombra
        font: fonte
        canvas_width: largura total do canvas (todas as TVs)
        offset_px: deslocamento absoluto em pixels (compartilhado por todos os textos)
    """
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width: int = bbox[2] - bbox[0]
    spacing: int = canvas_width
    cycle: int = text_width + spacing

    x: int = canvas_width - (offset_px % cycle)

    for shift in [-cycle, 0, cycle]:
        draw_x: int = x + shift
        if -text_width <= draw_x <= canvas_width:
            draw.text((draw_x + 2, y + 2), text, fill=shadow, font=font, anchor="lt")
            draw.text((draw_x, y), text, fill=fill, font=font, anchor="lt")
