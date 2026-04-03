import gc
import json
import os
import time
import board
import displayio
import framebufferio
import picodvi
import socketpool
import wifi

gc.collect()

SERVER_IP = os.getenv("DISPLAY_SERVER_IP", "192.168.86.21")
SERVER_PORT = int(os.getenv("DISPLAY_SERVER_PORT", "8000"))

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

pool = socketpool.SocketPool(wifi.radio)
gc.collect()
print("Pico W Thin Client")
print("IP:", wifi.radio.ipv4_address)
print("Server:", SERVER_IP)
print("RAM:", gc.mem_free())
print("---")

while True:
    try:
        gc.collect()
        s = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
        s.setblocking(True)
        s.connect((SERVER_IP, SERVER_PORT))
        s.send(b"GET /api/display HTTP/1.0\r\nHost: x\r\n\r\n")
        r = b""
        b = bytearray(128)
        while True:
            n = s.recv_into(b)
            if n == 0:
                break
            r += b[:n]
        s.close()
        del s, b
        i = r.find(b"\r\n\r\n")
        body = r[i + 4:] if i >= 0 else b"{}"
        del r
        gc.collect()
        d = json.loads(body)
        del body
        print("BTC:", d.get("btc"), "| ETH:", d.get("eth"))
        del d
    except Exception as e:
        print("Err:", e)
    gc.collect()
    time.sleep(30)
