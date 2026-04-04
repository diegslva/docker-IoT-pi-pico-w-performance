"""Servidor TCP streaming — empurra frames em tempo real para Pico W's.

Protocolo:
1. Pico W conecta e envia handshake JSON + newline
2. Servidor responde com posicao + frame_size JSON + newline
3. Servidor entra em loop: renderiza frame → envia bytes → sleep(1/FPS)
4. Pico W le exatamente frame_size bytes por iteracao

Porta default: 8001 (separada do FastAPI na 8000).
Compartilha DeviceRegistry e EffectManager com o app FastAPI.
"""

import asyncio
import contextlib
import json
import logging
import os
import time

from server.device_registry import AUTO_POSITION, DeviceRegistry
from server.effect_manager import EffectManager
from server.observability import (
    frame_render_duration,
    frames_rendered_total,
    stream_connections_active,
    stream_fps,
    stream_frames_pushed_total,
)
from server.renderer.config import FRAME_SIZE
from server.renderer.effects import EFFECT_REGISTRY, EffectContext
from server.renderer.scenes import SCENE_REGISTRY, RenderContext
from server.tz_utils import local_now

logger: logging.Logger = logging.getLogger("stream_server")

STREAM_PORT: int = int(os.getenv("STREAM_PORT", "8001"))
STREAM_FPS: int = int(os.getenv("STREAM_FPS", "15"))


def _render_frame(
    device_id: str,
    position: int,
    fetch_count: int,
    effect_manager: EffectManager,
    total_devices: int,
) -> bytes:
    """Renderiza um frame para o device. Mesma logica do /api/frame."""
    if effect_manager.custom_frame is not None:
        frames_rendered_total.inc(scene="custom")
        return effect_manager.custom_frame

    now = local_now()
    ts: str = now.strftime("%H:%M:%S")

    if effect_manager.mode != "default" and effect_manager.image is not None:
        effect = EFFECT_REGISTRY.get(effect_manager.mode)
        if effect is not None:
            ctx = EffectContext(
                image=effect_manager.image,
                position=position,
                tick=effect_manager.tick(),
                total_positions=effect_manager.total_positions,
                speed=effect_manager.speed,
                timestamp=ts,
                frame_index=fetch_count,
            )
            start: float = time.perf_counter()
            frame: bytes = effect.render(ctx)
            duration: float = time.perf_counter() - start
            frame_render_duration.observe(
                duration, scene=f"effect:{effect_manager.mode}", device_id=device_id
            )
            frames_rendered_total.inc(scene=f"effect:{effect_manager.mode}")
            return frame

    scene_name: str = "panoramic" if total_devices > 1 else "vitoria_sports"
    scene = SCENE_REGISTRY[scene_name]

    ctx = RenderContext(
        position=position,
        total_devices=max(total_devices, 1),
        timestamp=ts,
        hour=now.hour,
        minute=now.minute,
        second=now.second,
        frame_index=fetch_count,
        now=now,
    )
    start = time.perf_counter()
    frame = scene.render(ctx)
    duration = time.perf_counter() - start
    frame_render_duration.observe(duration, scene=scene_name, device_id=device_id)
    frames_rendered_total.inc(scene=scene_name)
    return frame


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    device_registry: DeviceRegistry,
    effect_manager: EffectManager,
    shutdown_event: asyncio.Event,
) -> None:
    """Handler para cada conexao de Pico W."""
    addr: str = writer.get_extra_info("peername", ("?", 0))[0]
    device_id: str = "unknown"

    try:
        # 1. Handshake: ler JSON de registro
        line: bytes = await asyncio.wait_for(reader.readline(), timeout=10.0)
        if not line:
            logger.warning("Empty handshake from %s", addr)
            return

        handshake: dict = json.loads(line.decode().strip())
        device_id = handshake.get("id", "unknown")
        name: str = handshake.get("name", "unnamed")
        ip: str = handshake.get("ip", addr)
        pos: int = handshake.get("pos", AUTO_POSITION)

        # Registrar device
        assigned_pos: int = await device_registry.register(
            device_id=device_id, name=name, ip=ip, position=pos
        )

        # 2. Responder com posicao + frame_size
        response: dict = {"position": assigned_pos, "frame_size": FRAME_SIZE}
        writer.write(json.dumps(response).encode() + b"\n")
        await writer.drain()

        logger.info(
            "Stream connected: %s (%s) pos=%d from %s",
            name,
            device_id,
            assigned_pos,
            addr,
        )
        stream_connections_active.inc()

        # 3. Loop de streaming
        target_interval: float = 1.0 / STREAM_FPS
        frame_count: int = 0
        fps_timer: float = time.monotonic()
        fps_frame_count: int = 0
        LOG_INTERVAL: int = 100  # logar a cada N frames

        while not shutdown_event.is_set():
            frame_start: float = time.monotonic()

            total_devices: int = await device_registry.count()

            # Atualizar registro (last_seen + fetch_count)
            await device_registry.register(
                device_id=device_id, name=name, ip=ip, position=assigned_pos
            )

            frame: bytes = _render_frame(
                device_id=device_id,
                position=assigned_pos,
                fetch_count=frame_count,
                effect_manager=effect_manager,
                total_devices=total_devices,
            )

            writer.write(frame)
            await writer.drain()

            frame_count += 1
            fps_frame_count += 1
            stream_frames_pushed_total.inc()

            # FPS real a cada LOG_INTERVAL frames
            if fps_frame_count >= LOG_INTERVAL:
                elapsed: float = time.monotonic() - fps_timer
                fps: float = fps_frame_count / elapsed if elapsed > 0 else 0
                render_ms: float = (time.monotonic() - frame_start) * 1000
                stream_fps.set(fps, device_id=device_id)
                logger.info(
                    "Stream %s (%s): %.1f FPS (target %d) | %d frames | render ~%.1fms",
                    name,
                    device_id,
                    fps,
                    STREAM_FPS,
                    frame_count,
                    render_ms,
                )
                fps_timer = time.monotonic()
                fps_frame_count = 0

            await asyncio.sleep(target_interval)

    except ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError:
        logger.info("Stream disconnected: %s (%s)", device_id, addr)
    except TimeoutError:
        logger.warning("Handshake timeout from %s", addr)
    except Exception:
        logger.exception("Stream error for %s (%s)", device_id, addr)
    finally:
        stream_connections_active.inc(-1)
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def start_stream_server(
    device_registry: DeviceRegistry,
    effect_manager: EffectManager,
) -> tuple[asyncio.Server, asyncio.Event]:
    """Inicia servidor TCP streaming. Retorna (server, shutdown_event)."""
    shutdown_event: asyncio.Event = asyncio.Event()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _handle_client(reader, writer, device_registry, effect_manager, shutdown_event)

    for attempt in range(5):
        try:
            server: asyncio.Server = await asyncio.start_server(
                handler, host="0.0.0.0", port=STREAM_PORT
            )
            logger.info("Stream server started on port %d (%d FPS target)", STREAM_PORT, STREAM_FPS)
            return server, shutdown_event
        except OSError:
            if attempt < 4:
                logger.warning(
                    "Port %d in use, retrying in 2s (attempt %d/5)", STREAM_PORT, attempt + 1
                )
                await asyncio.sleep(2)
            else:
                logger.error(
                    "Failed to bind stream server on port %d after 5 attempts", STREAM_PORT
                )
                raise
