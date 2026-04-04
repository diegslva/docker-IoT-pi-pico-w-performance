"""FastAPI application — endpoints para Pico W Display Server.

Arquitetura:
- Scenes e effects sao plugaveis via registry
- Estado encapsulado em DeviceRegistry e EffectManager
- Dados externos via providers
- Observabilidade: structured logging, correlation ID, metricas Prometheus
"""

import logging
import time
from io import BytesIO

from fastapi import FastAPI, Form, Query, UploadFile
from fastapi.responses import Response
from PIL import Image

from server.device_registry import AUTO_POSITION, DeviceRegistry
from server.effect_manager import EffectManager
from server.models import (
    DeviceListResponse,
    DisplayData,
    EffectResponse,
    HealthResponse,
    PositionResponse,
    ReorderRequest,
    ReorderResponse,
)
from server.observability import (
    devices_online,
    devices_registered,
    frame_render_duration,
    frames_rendered_total,
    server_start_timestamp,
    setup_observability,
)
from server.providers.crypto import get_display_data
from server.renderer.effects import EFFECT_REGISTRY, EffectContext
from server.renderer.rgb332 import FRAME_HEIGHT, FRAME_WIDTH, image_to_rgb332
from server.renderer.scenes import SCENE_REGISTRY, RenderContext
from server.tz_utils import local_now

logger: logging.Logger = logging.getLogger("server")

app = FastAPI(
    title="Pico W Display Server",
    version="0.4.0",
)

# Observabilidade: logging estruturado + correlation ID + /metrics
setup_observability(app)
server_start_timestamp.set(time.time())

# --- Encapsulated state ---
device_registry: DeviceRegistry = DeviceRegistry()
effect_manager: EffectManager = EffectManager()


# --- Endpoints ---
@app.get("/api/display")
async def display_data() -> DisplayData:
    """JSON minimo com dados crypto."""
    return await get_display_data()


@app.get("/api/frame")
async def display_frame(
    id: str = Query(default="unknown", description="Device MAC address"),
    name: str = Query(default="unnamed", description="Device friendly name"),
    ip: str = Query(default="0.0.0.0", description="Device IP address"),
    pos: int = Query(default=0, description="Device position in display chain"),
) -> Response:
    """Frame RGB332 (76800 bytes) para escrita direta no framebuffer DVI.

    State machine: custom_frame > effect > panoramic (multi) > vitoria_sports (single)
    """
    actual_pos: int = await device_registry.register(device_id=id, name=name, ip=ip, position=pos)

    # Update device gauges
    device_list = await device_registry.list_devices()
    devices_online.set(device_list.online)
    devices_registered.set(device_list.total)

    # 1. Custom frame override
    if effect_manager.custom_frame is not None:
        frames_rendered_total.inc(scene="custom")
        return Response(content=effect_manager.custom_frame, media_type="application/octet-stream")

    now = local_now()
    ts: str = now.strftime("%H:%M:%S")
    device_info = await device_registry.get_device(id)
    fetch_count: int = int(device_info["fetch_count"]) if device_info else 0

    # 2. Active effect
    if effect_manager.mode != "default" and effect_manager.image is not None:
        effect = EFFECT_REGISTRY.get(effect_manager.mode)
        if effect is not None:
            ctx = EffectContext(
                image=effect_manager.image,
                position=actual_pos,
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
                duration, scene=f"effect:{effect_manager.mode}", device_id=id
            )
            frames_rendered_total.inc(scene=f"effect:{effect_manager.mode}")
            return Response(content=frame, media_type="application/octet-stream")

    # 3. Default scene (panoramic if multi, single if alone)
    total_devices: int = await device_registry.count()
    scene_name: str = "panoramic" if total_devices > 1 else "vitoria_sports"
    scene = SCENE_REGISTRY[scene_name]

    ctx = RenderContext(
        position=actual_pos,
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
    frame_render_duration.observe(duration, scene=scene_name, device_id=id)
    frames_rendered_total.inc(scene=scene_name)
    return Response(content=frame, media_type="application/octet-stream")


@app.get("/api/position")
async def get_position(
    id: str = Query(description="Device MAC address"),
    name: str = Query(default="unnamed", description="Device friendly name"),
    ip: str = Query(default="0.0.0.0", description="Device IP address"),
) -> PositionResponse:
    """Auto-discovery: Pico W solicita posicao no boot.

    Registra o device (se novo) e retorna posicao atribuida.
    """
    assigned: int = await device_registry.register(
        device_id=id, name=name, ip=ip, position=AUTO_POSITION
    )
    was_known: bool = (await device_registry.get_device(id) or {}).get("fetch_count", 0) > 1
    return PositionResponse(device_id=id, position=assigned, auto_assigned=not was_known)


@app.get("/api/devices")
async def list_devices() -> DeviceListResponse:
    """Lista todos os Pico W's registrados."""
    return await device_registry.list_devices()


@app.post("/api/image")
async def upload_image(file: UploadFile) -> dict[str, str]:
    """Recebe imagem (PNG/JPG), converte pra RGB332 e armazena como frame ativo."""
    contents: bytes = await file.read()
    img: Image.Image = Image.open(BytesIO(contents))
    img = img.convert("RGB").resize((FRAME_WIDTH, FRAME_HEIGHT))
    frame: bytes = image_to_rgb332(img)
    await effect_manager.set_custom_frame(frame)
    logger.info("Custom image uploaded: %s (%d bytes)", file.filename, len(contents))
    return {"status": "ok", "filename": file.filename or "unknown", "size": str(len(frame))}


@app.delete("/api/image")
async def clear_image() -> dict[str, str]:
    """Remove imagem customizada."""
    await effect_manager.clear_custom_frame()
    return {"status": "ok"}


@app.post("/api/effect")
async def set_effect(
    file: UploadFile,
    mode: str = Form(default="wave", description="wave, wall, or scroll"),
    speed: int = Form(default=20, description="Scroll speed in pixels per tick"),
    total_positions: int = Form(default=3, description="Total displays in chain"),
) -> EffectResponse:
    """Configura efeito multi-display com imagem."""
    contents: bytes = await file.read()
    img: Image.Image = Image.open(BytesIO(contents)).convert("RGB")
    await effect_manager.set_effect(
        mode=mode, image=img, speed=speed, total_positions=total_positions
    )
    return EffectResponse(status="ok", mode=mode, total_positions=total_positions, speed=speed)


@app.delete("/api/effect")
async def clear_effect() -> dict[str, str]:
    """Remove efeito e volta pro padrao."""
    await effect_manager.clear_effect()
    return {"status": "ok"}


@app.post("/api/devices/reorder")
async def reorder_devices(body: ReorderRequest) -> ReorderResponse:
    """Reordena posicoes dos devices. Aceita lista de MACs na ordem desejada."""
    positions: dict[str, int] = await device_registry.reorder(body.order)
    return ReorderResponse(status="ok", positions=positions)


@app.get("/api/health")
async def health() -> HealthResponse:
    """Health check."""
    device_list = await device_registry.list_devices()
    return HealthResponse(
        status="ok",
        devices_online=device_list.online,
        active_effect=effect_manager.mode,
    )
