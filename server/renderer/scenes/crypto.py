"""Cena Crypto Ticker — exibe cotacoes BTC/ETH."""

from PIL import Image, ImageDraw

from server.renderer.fonts import get_font, get_font_bold
from server.renderer.rgb332 import FRAME_HEIGHT, FRAME_WIDTH, image_to_rgb332
from server.renderer.scenes.base import RenderContext, SceneRenderer

# Cores exatas RGB332
BLACK: tuple[int, int, int] = (0, 0, 0)
DARK_BLUE: tuple[int, int, int] = (0, 0, 85)
NAVY: tuple[int, int, int] = (0, 36, 85)
WHITE: tuple[int, int, int] = (255, 255, 255)
YELLOW: tuple[int, int, int] = (255, 255, 0)
ORANGE: tuple[int, int, int] = (255, 146, 0)
BLUE: tuple[int, int, int] = (73, 73, 255)
GREEN: tuple[int, int, int] = (0, 219, 0)
GRAY: tuple[int, int, int] = (73, 73, 85)
DARK_GRAY: tuple[int, int, int] = (36, 36, 85)
TEAL: tuple[int, int, int] = (0, 109, 170)


class CryptoScene(SceneRenderer):
    """Crypto ticker com BTC e ETH em layout com bordas."""

    def render(self, ctx: RenderContext) -> bytes:
        img: Image.Image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), color=BLACK)
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)

        mx: int = 20
        my: int = 16
        cw: int = FRAME_WIDTH - 2 * mx
        cx: int = mx
        cy: int = my

        draw.rectangle([(cx, cy), (cx + cw - 1, cy + FRAME_HEIGHT - 2 * my - 1)], fill=DARK_BLUE)
        draw.rectangle(
            [(cx, cy), (cx + cw - 1, cy + FRAME_HEIGHT - 2 * my - 1)], outline=DARK_GRAY, width=2
        )

        font_title = get_font_bold(20)
        font_label = get_font_bold(14)
        font_price = get_font_bold(32)
        font_footer = get_font(13)

        draw.rectangle([(cx + 2, cy + 2), (cx + cw - 3, cy + 32)], fill=NAVY)
        draw.text(
            (FRAME_WIDTH // 2, cy + 6), "CRYPTO TICKER", fill=YELLOW, font=font_title, anchor="mt"
        )
        draw.text((cx + 12, cy + 42), "BTC", fill=ORANGE, font=font_label)
        draw.text((cx + 12, cy + 58), f"${ctx.btc_price:,.0f}", fill=WHITE, font=font_price)
        draw.text((cx + 12, cy + 102), "ETH", fill=BLUE, font=font_label)
        draw.text((cx + 12, cy + 118), f"${ctx.eth_price:,.0f}", fill=WHITE, font=font_price)
        draw.line([(cx + 8, cy + 162), (cx + cw - 8, cy + 162)], fill=GRAY, width=1)
        draw.text((cx + 12, cy + 170), f"Updated: {ctx.timestamp}", fill=GREEN, font=font_footer)
        draw.text((cx + 12, cy + 188), "Pico W Display Server", fill=TEAL, font=font_footer)

        return image_to_rgb332(img)
