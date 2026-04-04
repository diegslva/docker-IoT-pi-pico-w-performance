"""Pico W framebuffer client — recebe frames do servidor e escreve direto no DVI.

Modos de operacao:
1. TCP Streaming (default): conexao persistente, servidor empurra frames (~15 FPS)
2. HTTP Polling (fallback): GET /api/frame a cada FETCH_INTERVAL

Resiliencia:
- Reconexao Wi-Fi automatica se cair
- Fallback automatico de streaming pra HTTP apos 3 falhas
- Watchdog via hard reset apos MAX_CONSECUTIVE_ERRORS

Auto-discovery:
- DEVICE_POSITION = "auto" → solicita posicao ao servidor
- DEVICE_POSITION = "3" → usa posicao fixa
"""

import gc
import json
import os
import time

import board
import displayio
import microcontroller
import picodvi
import socketpool
import supervisor
import wifi

gc.collect()

SERVER_IP = os.getenv("DISPLAY_SERVER_IP", "192.168.86.21")
SERVER_PORT = int(os.getenv("DISPLAY_SERVER_PORT", "8000"))
STREAM_PORT = int(os.getenv("STREAM_PORT", "8001"))
FETCH_INTERVAL = float(os.getenv("FETCH_INTERVAL", "0.5"))
DEVICE_NAME = os.getenv("DEVICE_NAME", "unnamed")
DEVICE_POSITION_RAW = os.getenv("DEVICE_POSITION", "auto")
COLOR_DEPTH = int(os.getenv("COLOR_DEPTH", "8"))
BYTES_PER_PIXEL = COLOR_DEPTH // 8
FRAME_SIZE = 320 * 240 * BYTES_PER_PIXEL
MAX_BACKOFF = 60
MAX_CONSECUTIVE_ERRORS = 30
MAX_STREAM_FAILURES = 3

# --- Device identity ---
mac_bytes = wifi.radio.mac_address
DEVICE_ID = ":".join(f"{b:02x}" for b in mac_bytes)

# --- DVI Framebuffer ---
displayio.release_displays()

fb = picodvi.Framebuffer(
    320, 240,
    clk_dp=board.CKP, clk_dn=board.CKN,
    red_dp=board.D0P, red_dn=board.D0N,
    green_dp=board.D1P, green_dn=board.D1N,
    blue_dp=board.D2P, blue_dn=board.D2N,
    color_depth=COLOR_DEPTH,
)

fbuf = memoryview(fb)
pool = socketpool.SocketPool(wifi.radio)
gc.collect()


def ensure_wifi() -> bool:
    """Garante que o Wi-Fi esta conectado. Retorna True se OK."""
    if wifi.radio.connected:
        return True

    print("Wi-Fi disconnected, reconnecting...")
    for attempt in range(5):
        try:
            ssid = os.getenv("CIRCUITPY_WIFI_SSID", "")
            password = os.getenv("CIRCUITPY_WIFI_PASSWORD", "")
            if ssid:
                wifi.radio.connect(ssid, password)
            if wifi.radio.connected:
                print("Wi-Fi reconnected | IP:", wifi.radio.ipv4_address)
                return True
        except Exception as e:
            print("Wi-Fi attempt", attempt + 1, "failed:", e)
        time.sleep(2)

    print("Wi-Fi reconnection failed after 5 attempts")
    return False


def http_get_json(path: str) -> dict:
    """HTTP GET simples que retorna JSON parsed."""
    s = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    s.setblocking(True)
    try:
        s.connect((SERVER_IP, SERVER_PORT))
        request = ("GET " + path + " HTTP/1.0\r\nHost: x\r\n\r\n").encode()
        s.send(request)

        data = b""
        buf = bytearray(512)
        while True:
            n = s.recv_into(buf)
            if n == 0:
                break
            data += buf[:n]

        parts = data.split(b"\r\n\r\n", 1)
        if len(parts) < 2:
            raise ValueError("Invalid HTTP response")
        return json.loads(parts[1])
    finally:
        s.close()


def discover_position() -> str:
    """Solicita posicao ao servidor via /api/position."""
    device_ip = str(wifi.radio.ipv4_address)
    path = (
        "/api/position?id=" + DEVICE_ID
        + "&name=" + DEVICE_NAME
        + "&ip=" + device_ip
    )
    for attempt in range(5):
        try:
            result = http_get_json(path)
            pos = str(result["position"])
            auto = result.get("auto_assigned", True)
            print("Position assigned:", pos, "(auto)" if auto else "(kept)")
            return pos
        except Exception as e:
            print("Position discovery attempt", attempt + 1, "failed:", e)
            time.sleep(2)

    print("Position discovery failed, using fallback 0")
    return "0"


# --- Resolve position ---
if DEVICE_POSITION_RAW.lower() in ("auto", ""):
    print("Auto-discovery mode, requesting position from server...")
    if ensure_wifi():
        DEVICE_POSITION = discover_position()
    else:
        DEVICE_POSITION = "0"
        print("No Wi-Fi for discovery, using fallback position 0")
else:
    DEVICE_POSITION = DEVICE_POSITION_RAW

print("Pico W Frame Client")
print("ID:", DEVICE_ID)
print("Name:", DEVICE_NAME)
print("Position:", DEVICE_POSITION)
print("IP:", wifi.radio.ipv4_address)
print("Server:", SERVER_IP, ":", SERVER_PORT)
print("Stream port:", STREAM_PORT)
print("Color depth:", COLOR_DEPTH)
print("Frame size:", FRAME_SIZE)
print("RAM:", gc.mem_free())


# --- TCP Streaming ---
def recv_exact(sock, buf, size):
    """Recebe exatamente size bytes no buffer. Retorna True se OK."""
    received = 0
    while received < size:
        remaining = size - received
        n = sock.recv_into(buf[received:], min(1024, remaining))
        if n == 0:
            return False
        received += n
    return True


def stream_frames() -> int:
    """Conecta via TCP streaming e recebe frames em loop.

    Retorna numero de frames recebidos antes de desconectar.
    """
    gc.collect()
    s = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    s.setblocking(True)
    frames = 0

    try:
        s.connect((SERVER_IP, STREAM_PORT))

        # Handshake: enviar registro JSON
        handshake = json.dumps({
            "id": DEVICE_ID,
            "name": DEVICE_NAME,
            "ip": str(wifi.radio.ipv4_address),
            "pos": int(DEVICE_POSITION),
        }) + "\n"
        s.send(handshake.encode())

        # Ler resposta do servidor
        resp_buf = bytearray(256)
        n = s.recv_into(resp_buf)
        resp_line = resp_buf[:n].decode().strip()
        resp = json.loads(resp_line)
        frame_size = resp.get("frame_size", FRAME_SIZE)

        print("Stream connected | pos:", resp.get("position"), "| frame:", frame_size)

        # Loop de streaming — receber frames direto no framebuffer
        while True:
            if not recv_exact(s, fbuf, frame_size):
                print("Stream ended (server closed)")
                break
            frames += 1
            if frames % 100 == 0:
                gc.collect()
                print("Stream:", frames, "frames | RAM:", gc.mem_free())

    except Exception as e:
        print("Stream error:", e)
    finally:
        s.close()
        gc.collect()

    return frames


# --- HTTP Polling (fallback) ---
def build_request() -> bytes:
    """Constroi request HTTP com identidade do device."""
    device_ip = str(wifi.radio.ipv4_address)
    return (
        "GET /api/frame"
        "?id=" + DEVICE_ID
        + "&name=" + DEVICE_NAME
        + "&ip=" + device_ip
        + "&pos=" + DEVICE_POSITION
        + " HTTP/1.0\r\nHost: x\r\n\r\n"
    ).encode()


def fetch_frame() -> bool:
    """Busca frame via HTTP e escreve no framebuffer."""
    gc.collect()
    s = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    s.setblocking(True)
    try:
        s.connect((SERVER_IP, SERVER_PORT))
        s.send(build_request())

        header = b""
        while b"\r\n\r\n" not in header:
            chunk = bytearray(1)
            s.recv_into(chunk)
            header += chunk

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


# --- Main loop ---
stream_failures: int = 0
use_streaming: bool = True
error_count: int = 0
backoff: float = FETCH_INTERVAL

while True:
    try:
        if not ensure_wifi():
            print("No Wi-Fi, retrying in", backoff, "s")
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
            error_count += 1
            if error_count >= MAX_CONSECUTIVE_ERRORS:
                print("Too many errors, hard reset")
                microcontroller.reset()
            continue

        if use_streaming:
            print("Connecting to stream server...")
            frames = stream_frames()
            if frames > 0:
                stream_failures = 0
                error_count = 0
                print("Stream session ended after", frames, "frames")
            else:
                stream_failures += 1
                error_count += 1
                print("Stream failed (", stream_failures, "/", MAX_STREAM_FAILURES, ")")
                if stream_failures >= MAX_STREAM_FAILURES:
                    print("Falling back to HTTP polling")
                    use_streaming = False
            time.sleep(2)
        else:
            # HTTP polling fallback
            ok = fetch_frame()
            gc.collect()

            if ok:
                error_count = 0
                backoff = FETCH_INTERVAL
            else:
                print("Frame incomplete")
                error_count += 1

            if error_count > 0:
                backoff = min(FETCH_INTERVAL * (2 ** min(error_count, 4)), MAX_BACKOFF)
                print("Backoff:", backoff, "s | Errors:", error_count)

            time.sleep(backoff if error_count > 0 else FETCH_INTERVAL)

    except Exception as e:
        print("Err:", e)
        error_count += 1
        gc.collect()

    if error_count >= MAX_CONSECUTIVE_ERRORS:
        print("Too many errors, hard reset")
        microcontroller.reset()
