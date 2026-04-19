"""Teste minimo do PiCowBell HSTX — testa varias resolucoes pra encontrar a que funciona.

Edita TEST_MODE pra testar diferentes configuracoes:
- "320x240_8"   -> 320x240 RGB332 (8-bit)
- "320x240_16"  -> 320x240 RGB565 (16-bit)
- "320x200_8"   -> 320x200 RGB332 (sugerido como mais compativel)
- "400x240_8"   -> 400x240 RGB332
- "640x480_8"   -> 640x480 RGB332 (resolucao nativa)
"""

import board
import displayio
import picodvi

TEST_MODE = "320x240_8"  # Editar e testar

CONFIGS = {
    "320x240_8":  (320, 240, 8),
    "320x240_16": (320, 240, 16),
    "320x200_8":  (320, 200, 8),
    "400x240_8":  (400, 240, 8),
    "640x480_8":  (640, 480, 8),
}

WIDTH, HEIGHT, COLOR_DEPTH = CONFIGS[TEST_MODE]

displayio.release_displays()

print("==============================")
print("Teste:", TEST_MODE)
print("Resolucao:", WIDTH, "x", HEIGHT, "color_depth=", COLOR_DEPTH)
print("==============================")

try:
    fb = picodvi.Framebuffer(
        WIDTH, HEIGHT,
        clk_dp=board.GP14, clk_dn=board.GP15,
        red_dp=board.GP12, red_dn=board.GP13,
        green_dp=board.GP18, green_dn=board.GP19,
        blue_dp=board.GP16, blue_dn=board.GP17,
        color_depth=COLOR_DEPTH,
    )
    print("Framebuffer OK!")
    print("  width=", fb.width, "height=", fb.height)
except Exception as e:
    print("ERRO ao criar framebuffer:", e)
    raise

fbuf = memoryview(fb).cast("B")
print("  buffer size=", len(fbuf), "bytes")

# Preencher tudo com 0xFF (branco em qualquer formato)
for i in range(len(fbuf)):
    fbuf[i] = 0xFF

print("Buffer preenchido com 0xFF (branco). TV deve mostrar tela branca.")
print("Se TV ainda em standby, problema e hardware (PiCowBell/cabo).")

import time
while True:
    time.sleep(1)
