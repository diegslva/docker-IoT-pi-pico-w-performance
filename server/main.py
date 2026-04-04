"""Servidor central para Pico W thin clients.

Busca dados de APIs externas (crypto, etc), cacheia, e serve JSON
enxuto ou frames RGB332 para os Pico W's na rede local.

Configuracao via environment variables:
    CACHE_TTL_SECONDS: tempo de cache das cotacoes (default: 30)
    LOG_LEVEL: nivel de log (default: INFO)
    TZ_OFFSET_HOURS: offset do timezone local (default: -3 para BRT)
"""

import logging
import os
import socket
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from server.renderer import (
    FRAME_HEIGHT,
    FRAME_WIDTH,
    image_to_rgb332_direct,
    render_crypto_frame,
    render_vitoria_sports_frame,
)


def check_port_available(host: str, port: int) -> bool:
    """Verifica se a porta esta disponivel para bind."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(host: str, preferred: int, max_attempts: int = 10) -> int:
    """Retorna a porta preferida se disponivel, senao busca a proxima livre."""
    for offset in range(max_attempts):
        candidate: int = preferred + offset
        if check_port_available(host, candidate):
            return candidate
    raise RuntimeError(f"No available port found in range {preferred}-{preferred + max_attempts - 1}")


LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "30"))
TZ_OFFSET_HOURS: int = int(os.getenv("TZ_OFFSET_HOURS", "-3"))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger: logging.Logger = logging.getLogger("server")

app = FastAPI(
    title="Pico W Display Server",
    version="0.2.0",
)


# --- Models ---
class DisplayData(BaseModel):
    btc: float
    eth: float
    ts: str
    ok: bool


class DeviceInfo(BaseModel):
    device_id: str
    name: str
    ip: str
    last_seen: str
    fetch_count: int


class DeviceListResponse(BaseModel):
    devices: list[DeviceInfo]
    total: int
    online: int
    offline: int


class HealthResponse(BaseModel):
    status: str
    devices_online: int


# --- Device Registry ---
_devices: dict[str, dict[str, str | int]] = {}


def _register_device(device_id: str, name: str, ip: str) -> None:
    """Registra ou atualiza dispositivo no registry."""
    local_tz: timezone = timezone(timedelta(hours=TZ_OFFSET_HOURS))
    now_str: str = datetime.now(tz=local_tz).strftime("%Y-%m-%d %H:%M:%S")

    if device_id in _devices:
        _devices[device_id]["last_seen"] = now_str
        _devices[device_id]["ip"] = ip
        _devices[device_id]["name"] = name
        _devices[device_id]["fetch_count"] = int(_devices[device_id]["fetch_count"]) + 1
    else:
        _devices[device_id] = {
            "name": name,
            "ip": ip,
            "last_seen": now_str,
            "fetch_count": 1,
        }
        logger.info("New device registered: %s (%s) from %s", name, device_id, ip)


# --- Crypto Cache ---
_cache: DisplayData | None = None
_cache_ts: float = 0.0

COINGECKO_URL: str = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin,ethereum&vs_currencies=usd"
)


async def _fetch_crypto() -> dict[str, float]:
    """Busca cotacoes BTC e ETH via CoinGecko (free, sem API key)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp: httpx.Response = await client.get(COINGECKO_URL)
        resp.raise_for_status()
        data: dict = resp.json()

    return {
        "btc": float(data["bitcoin"]["usd"]),
        "eth": float(data["ethereum"]["usd"]),
    }


async def _get_display_data() -> DisplayData:
    """Retorna dados para o Pico W, com cache de CACHE_TTL_SECONDS."""
    global _cache, _cache_ts

    now: float = time.monotonic()
    if _cache is not None and (now - _cache_ts) < CACHE_TTL_SECONDS:
        return _cache

    try:
        prices: dict[str, float] = await _fetch_crypto()
        local_tz: timezone = timezone(timedelta(hours=TZ_OFFSET_HOURS))
        ts: str = datetime.now(tz=local_tz).strftime("%H:%M:%S")
        _cache = DisplayData(
            btc=prices["btc"],
            eth=prices["eth"],
            ts=ts,
            ok=True,
        )
        _cache_ts = now
        logger.info("Crypto updated: BTC=$%s ETH=$%s", prices["btc"], prices["eth"])
    except Exception:
        logger.exception("Failed to fetch crypto prices")
        if _cache is None:
            _cache = DisplayData(btc=0, eth=0, ts="??:??:??", ok=False)

    return _cache


# --- Endpoints ---
@app.get("/api/display")
async def display_data() -> DisplayData:
    """JSON minimo para o Pico W renderizar no TV."""
    return await _get_display_data()


@app.get("/api/frame")
async def display_frame(
    id: str = Query(default="unknown", description="Device MAC address"),
    name: str = Query(default="unnamed", description="Device friendly name"),
    ip: str = Query(default="0.0.0.0", description="Device IP address"),
) -> Response:
    """Frame RGB332 (76800 bytes) para escrita direta no framebuffer DVI."""
    _register_device(device_id=id, name=name, ip=ip)

    if _custom_frame is not None:
        return Response(content=_custom_frame, media_type="application/octet-stream")

    # Default: Vitoria Sports com horario e mensagem rotativa
    local_tz: timezone = timezone(timedelta(hours=TZ_OFFSET_HOURS))
    ts: str = datetime.now(tz=local_tz).strftime("%H:%M:%S")
    device_info: dict[str, str | int] | None = _devices.get(id)
    fetch_count: int = int(device_info["fetch_count"]) if device_info else 0
    frame: bytes = render_vitoria_sports_frame(timestamp=ts, frame_index=fetch_count)
    return Response(content=frame, media_type="application/octet-stream")


DEVICE_OFFLINE_THRESHOLD: int = int(os.getenv("DEVICE_OFFLINE_SECONDS", "60"))


@app.get("/api/devices")
async def list_devices() -> DeviceListResponse:
    """Lista todos os Pico W's registrados com status online/offline."""
    local_tz: timezone = timezone(timedelta(hours=TZ_OFFSET_HOURS))
    now: datetime = datetime.now(tz=local_tz)
    online_count: int = 0

    devices: list[DeviceInfo] = []
    for did, info in _devices.items():
        try:
            last: datetime = datetime.strptime(str(info["last_seen"]), "%Y-%m-%d %H:%M:%S")
            last = last.replace(tzinfo=local_tz)
            is_online: bool = (now - last).total_seconds() < DEVICE_OFFLINE_THRESHOLD
        except (ValueError, TypeError):
            is_online = False

        if is_online:
            online_count += 1

        devices.append(
            DeviceInfo(
                device_id=did,
                name=str(info["name"]),
                ip=str(info["ip"]),
                last_seen=str(info["last_seen"]),
                fetch_count=int(info["fetch_count"]),
            )
        )

    return DeviceListResponse(
        devices=devices,
        total=len(devices),
        online=online_count,
        offline=len(devices) - online_count,
    )


# --- Custom image storage (per device or global) ---
_custom_frame: bytes | None = None


@app.post("/api/image")
async def upload_image(file: UploadFile) -> dict[str, str]:
    """Recebe uma imagem (PNG/JPG), converte para RGB332 e armazena como frame ativo."""
    global _custom_frame
    from PIL import Image
    from io import BytesIO

    contents: bytes = await file.read()
    img: Image.Image = Image.open(BytesIO(contents))
    img = img.convert("RGB").resize((FRAME_WIDTH, FRAME_HEIGHT))
    _custom_frame = image_to_rgb332_direct(img)

    logger.info("Custom image uploaded: %s (%dx%d)", file.filename, img.width, img.height)
    return {"status": "ok", "filename": file.filename or "unknown", "size": str(len(_custom_frame))}


@app.delete("/api/image")
async def clear_image() -> dict[str, str]:
    """Remove imagem customizada e volta pro conteudo padrao (crypto)."""
    global _custom_frame
    _custom_frame = None
    logger.info("Custom image cleared")
    return {"status": "ok"}


@app.get("/api/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", devices_online=len(_devices))
