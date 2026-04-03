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
FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", "30"))
FRAME_SIZE = 76800  # 320 * 240 * 1 byte (RGB332)

# --- DVI Framebuffer (raw, no displayio overhead) ---
displayio.release_displays()

fb = picodvi.Framebuffer(
    320, 240,
    clk_dp=board.CKP, clk_dn=board.CKN,
    red_dp=board.D0P, red_dn=board.D0N,
    green_dp=board.D1P, green_dn=board.D1N,
    blue_dp=board.D2P, blue_dn=board.D2N,
    color_depth=8,
)

# Direct access to framebuffer memory
fbuf = memoryview(fb)

pool = socketpool.SocketPool(wifi.radio)
gc.collect()
print("Pico W Frame Client")
print("IP:", wifi.radio.ipv4_address)
print("Server:", SERVER_IP, ":", SERVER_PORT)
print("RAM:", gc.mem_free())


def fetch_frame() -> bool:
    """Busca frame do servidor e escreve direto no framebuffer via streaming."""
    gc.collect()
    s = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    s.setblocking(True)
    try:
        s.connect((SERVER_IP, SERVER_PORT))
        s.send(b"GET /api/frame HTTP/1.0\r\nHost: x\r\n\r\n")

        # Read HTTP headers first
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = bytearray(1)
            s.recv_into(chunk)
            header += chunk

        # Stream body directly into framebuffer in chunks
        written = 0
        chunk = bytearray(1024)
        while written < FRAME_SIZE:
            remaining = FRAME_SIZE - written
            to_read = min(1024, remaining)
            n = s.recv_into(chunk, to_read)
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
