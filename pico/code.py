"""Pico W framebuffer client — recebe frames RGB332 do servidor e escreve direto no DVI."""

import gc
import os
import time

import board
import displayio
import picodvi
import socketpool
import wifi

gc.collect()

SERVER_IP = os.getenv("DISPLAY_SERVER_IP", "192.168.86.21")
SERVER_PORT = int(os.getenv("DISPLAY_SERVER_PORT", "8000"))
FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", "10"))
DEVICE_NAME = os.getenv("DEVICE_NAME", "unnamed")
FRAME_SIZE = 76800  # 320 * 240 * 1 byte (RGB332)

# --- Device identity ---
mac_bytes = wifi.radio.mac_address
DEVICE_ID = ":".join(f"{b:02x}" for b in mac_bytes)
DEVICE_IP = str(wifi.radio.ipv4_address)

# --- DVI Framebuffer ---
displayio.release_displays()

fb = picodvi.Framebuffer(
    320, 240,
    clk_dp=board.CKP, clk_dn=board.CKN,
    red_dp=board.D0P, red_dn=board.D0N,
    green_dp=board.D1P, green_dn=board.D1N,
    blue_dp=board.D2P, blue_dn=board.D2N,
    color_depth=8,
)

fbuf = memoryview(fb)

pool = socketpool.SocketPool(wifi.radio)
gc.collect()
print("Pico W Frame Client")
print("ID:", DEVICE_ID)
print("Name:", DEVICE_NAME)
print("IP:", DEVICE_IP)
print("Server:", SERVER_IP, ":", SERVER_PORT)
print("RAM:", gc.mem_free())

# Build request line once (save RAM on each fetch)
REQ_LINE = (
    "GET /api/frame"
    "?id=" + DEVICE_ID
    + "&name=" + DEVICE_NAME
    + "&ip=" + DEVICE_IP
    + " HTTP/1.0\r\nHost: x\r\n\r\n"
).encode()


def fetch_frame() -> bool:
    """Busca frame do servidor e escreve direto no framebuffer via streaming."""
    gc.collect()
    s = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    s.setblocking(True)
    try:
        s.connect((SERVER_IP, SERVER_PORT))
        s.send(REQ_LINE)

        # Read HTTP headers
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = bytearray(1)
            s.recv_into(chunk)
            header += chunk

        # Stream body directly into framebuffer
        written = 0
        chunk = bytearray(1024)
        while written < FRAME_SIZE:
            remaining = FRAME_SIZE - written
            n = s.recv_into(chunk, min(1024, remaining))
            if n == 0:
                break
            fbuf[written : written + n] = chunk[:n]
            written += n

        return written == FRAME_SIZE
    finally:
        s.close()


while True:
    try:
        ok = fetch_frame()
        gc.collect()
        if ok:
            print("Frame OK | RAM:", gc.mem_free())
        else:
            print("Frame incomplete")
    except Exception as e:
        print("Err:", e)
    gc.collect()
    time.sleep(FETCH_INTERVAL)
