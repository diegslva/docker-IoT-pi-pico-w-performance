"""Servidor central para Pico W thin clients.

Busca dados de APIs externas (crypto, etc), cacheia, e serve JSON
enxuto via HTTP puro para os Pico W's na rede local.

Configuracao via environment variables:
    CACHE_TTL_SECONDS: tempo de cache das cotacoes (default: 30)
    LOG_LEVEL: nivel de log (default: INFO)
"""

import logging
import os
import socket
import time
from contextlib import closing
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

from server.renderer import render_crypto_frame


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

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger: logging.Logger = logging.getLogger("server")

app = FastAPI(
    title="Pico W Display Server",
    version="0.1.0",
)


# --- Models ---
class DisplayData(BaseModel):
    btc: float
    eth: float
    ts: str
    ok: bool


class HealthResponse(BaseModel):
    status: str


# --- Cache ---
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
        tz_offset: int = int(os.getenv("TZ_OFFSET_HOURS", "-3"))
        local_tz: timezone = timezone(timedelta(hours=tz_offset))
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


@app.get("/api/display")
async def display_data() -> DisplayData:
    """JSON minimo para o Pico W renderizar no TV."""
    return await _get_display_data()


@app.get("/api/frame")
async def display_frame() -> Response:
    """Frame RGB332 (76800 bytes) para escrita direta no framebuffer DVI."""
    data: DisplayData = await _get_display_data()
    frame: bytes = render_crypto_frame(
        btc_price=data.btc,
        eth_price=data.eth,
        timestamp=data.ts,
    )
    return Response(content=frame, media_type="application/octet-stream")


@app.get("/api/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
