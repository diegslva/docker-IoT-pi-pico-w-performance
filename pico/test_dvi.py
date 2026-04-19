"""Teste minimo do PiCowBell HSTX — apenas framebuffer + cor solida.

Sem rede, sem servidor, sem complicacao. Se a TV nao ligar com isso,
e problema de hardware/PiCowBell. Se ligar, problema esta no streaming.

Para usar:
1. Renomear este arquivo para code.py no CIRCUITPY drive
2. Reset o Pico
3. TV deve mostrar tela vermelha solida com listras coloridas
"""

import board
import displayio
import picodvi

displayio.release_displays()

print("Inicializando framebuffer HSTX 320x240 16-bit...")

fb = picodvi.Framebuffer(
    320, 240,
    clk_dp=board.GP14, clk_dn=board.GP15,
    red_dp=board.GP12, red_dn=board.GP13,
    green_dp=board.GP18, green_dn=board.GP19,
    blue_dp=board.GP16, blue_dn=board.GP17,
    color_depth=16,
)

print("Framebuffer criado!")
print("Width:", fb.width, "Height:", fb.height)

# Memoryview byte-level
fbuf = memoryview(fb).cast("B")
print("Framebuffer size:", len(fbuf), "bytes")

# Preencher tela com listras coloridas em RGB565 little-endian
# RGB565: RRRRR GGGGGG BBBBB (16 bits = 2 bytes)
# Vermelho puro = 0xF800 = bytes 0x00 0xF8 (LE)
# Verde puro   = 0x07E0 = bytes 0xE0 0x07 (LE)
# Azul puro    = 0x001F = bytes 0x1F 0x00 (LE)
# Branco       = 0xFFFF = bytes 0xFF 0xFF (LE)

print("Desenhando listras de teste...")

# Tela dividida em 4 listras horizontais: vermelho, verde, azul, branco
WIDTH = 320
HEIGHT = 240
STRIPE_HEIGHT = HEIGHT // 4

colors = [
    (0x00, 0xF8),  # Vermelho LE
    (0xE0, 0x07),  # Verde LE
    (0x1F, 0x00),  # Azul LE
    (0xFF, 0xFF),  # Branco
]

for stripe_idx, (lo, hi) in enumerate(colors):
    y_start = stripe_idx * STRIPE_HEIGHT
    y_end = y_start + STRIPE_HEIGHT
    for y in range(y_start, y_end):
        offset = y * WIDTH * 2
        for x in range(WIDTH):
            fbuf[offset + x * 2] = lo
            fbuf[offset + x * 2 + 1] = hi

print("Pronto! TV deve mostrar 4 listras: vermelho, verde, azul, branco")
print("Se a TV esta preta/standby, problema e no PiCowBell ou cabo HDMI.")
print("Se mostrar listras, problema e no streaming/code.py.")

# Loop infinito pra manter framebuffer ativo
import time
while True:
    time.sleep(1)
