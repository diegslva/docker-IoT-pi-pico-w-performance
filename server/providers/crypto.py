"""Provider de dados crypto com cache."""

import logging
import os
import time

import httpx

from server.models import DisplayData
from server.observability import crypto_cache_hits, crypto_cache_misses, fetch_errors_total
from server.tz_utils import local_timestamp

logger: logging.Logger = logging.getLogger("provider.crypto")

CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "30"))
COINGECKO_URL: str = (
    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
)

_cache: DisplayData | None = None
_cache_ts: float = 0.0


async def fetch_crypto() -> dict[str, float]:
    """Busca cotacoes BTC e ETH via CoinGecko."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp: httpx.Response = await client.get(COINGECKO_URL)
        resp.raise_for_status()
        data: dict = resp.json()

    return {
        "btc": float(data["bitcoin"]["usd"]),
        "eth": float(data["ethereum"]["usd"]),
    }


async def get_display_data() -> DisplayData:
    """Retorna dados crypto com cache de CACHE_TTL_SECONDS."""
    global _cache, _cache_ts

    now: float = time.monotonic()
    if _cache is not None and (now - _cache_ts) < CACHE_TTL_SECONDS:
        crypto_cache_hits.inc()
        return _cache

    crypto_cache_misses.inc()
    try:
        prices: dict[str, float] = await fetch_crypto()
        ts: str = local_timestamp()
        _cache = DisplayData(
            btc=prices["btc"],
            eth=prices["eth"],
            ts=ts,
            ok=True,
        )
        _cache_ts = now
        logger.info("Crypto updated: BTC=$%s ETH=$%s", prices["btc"], prices["eth"])
    except Exception:
        fetch_errors_total.inc(provider="coingecko")
        logger.exception("Failed to fetch crypto prices")
        if _cache is None:
            _cache = DisplayData(btc=0, eth=0, ts="??:??:??", ok=False)

    return _cache
