import gc
import time
import board
import displayio
import framebufferio
import picodvi
import terminalio
import wifi
from adafruit_display_text import label

gc.collect()
print(f"RAM start: {gc.mem_free():,}")

# Wi-Fi auto-connected via settings.toml
timeout = 10
start = time.monotonic()
while not wifi.radio.connected and (time.monotonic() - start) < timeout:
    time.sleep(0.5)

if wifi.radio.connected:
    wifi_ip = str(wifi.radio.ipv4_address)
    wifi_ok = True
    print(f"Wi-Fi OK | IP: {wifi_ip}")
else:
    wifi_ip = "N/A"
    wifi_ok = False
    print("Wi-Fi timeout")

gc.collect()
print(f"RAM before display: {gc.mem_free():,}")

# Display
displayio.release_displays()

fb = picodvi.Framebuffer(
    320, 240,
    clk_dp=board.CKP, clk_dn=board.CKN,
    red_dp=board.D0P, red_dn=board.D0N,
    green_dp=board.D1P, green_dn=board.D1N,
    blue_dp=board.D2P, blue_dn=board.D2N,
    color_depth=8,
)
display = framebufferio.FramebufferDisplay(fb)

main_group = displayio.Group()

bg_bitmap = displayio.Bitmap(320, 240, 1)
bg_palette = displayio.Palette(1)
bg_palette[0] = 0x0D1117
main_group.append(displayio.TileGrid(bg_bitmap, pixel_shader=bg_palette))

status_color = 0x00FF00 if wifi_ok else 0xFF4444
status_text = "HDMI + Wi-Fi OK" if wifi_ok else "HDMI OK | Wi-Fi FAIL"

title = label.Label(
    terminalio.FONT,
    text=status_text,
    color=status_color,
    anchor_point=(0.5, 0.0),
    anchored_position=(160, 20),
    scale=2,
)
main_group.append(title)

ip_label = label.Label(
    terminalio.FONT,
    text=f"IP: {wifi_ip}",
    color=0xFFFFFF,
    anchor_point=(0.0, 0.0),
    anchored_position=(10, 60),
    scale=2,
)
main_group.append(ip_label)

gc.collect()
ram_label = label.Label(
    terminalio.FONT,
    text=f"Free RAM: {gc.mem_free():,}",
    color=0x87CEEB,
    anchor_point=(0.0, 0.0),
    anchored_position=(10, 90),
    scale=2,
)
main_group.append(ram_label)

display.root_group = main_group

gc.collect()
print(f"RAM final: {gc.mem_free():,}")

while True:
    pass
