"""Registry de devices Pico W com lock async."""

import asyncio
import logging
from datetime import datetime

from server.models import DeviceInfo, DeviceListResponse
from server.tz_utils import local_now

logger: logging.Logger = logging.getLogger("device_registry")

DEVICE_OFFLINE_SECONDS: int = 60


class DeviceRegistry:
    """Gerencia registro de Pico W's com thread safety via asyncio.Lock."""

    def __init__(self) -> None:
        self._devices: dict[str, dict[str, str | int]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def register(self, device_id: str, name: str, ip: str, position: int = 0) -> None:
        """Registra ou atualiza dispositivo."""
        async with self._lock:
            now_str: str = local_now().strftime("%Y-%m-%d %H:%M:%S")

            if device_id in self._devices:
                self._devices[device_id]["last_seen"] = now_str
                self._devices[device_id]["ip"] = ip
                self._devices[device_id]["name"] = name
                self._devices[device_id]["position"] = position
                self._devices[device_id]["fetch_count"] = (
                    int(self._devices[device_id]["fetch_count"]) + 1
                )
            else:
                self._devices[device_id] = {
                    "name": name,
                    "ip": ip,
                    "position": position,
                    "last_seen": now_str,
                    "fetch_count": 1,
                }
                logger.info("New device: %s (%s) pos=%d from %s", name, device_id, position, ip)

    async def get_device(self, device_id: str) -> dict[str, str | int] | None:
        """Retorna info do device ou None."""
        async with self._lock:
            return self._devices.get(device_id)

    async def count(self) -> int:
        """Retorna total de devices registrados."""
        async with self._lock:
            return len(self._devices)

    async def list_devices(self) -> DeviceListResponse:
        """Lista todos os devices com status online/offline."""
        async with self._lock:
            now: datetime = local_now()
            online_count: int = 0
            devices: list[DeviceInfo] = []

            for did, info in self._devices.items():
                try:
                    last: datetime = datetime.strptime(str(info["last_seen"]), "%Y-%m-%d %H:%M:%S")
                    last = last.replace(tzinfo=now.tzinfo)
                    is_online: bool = (now - last).total_seconds() < DEVICE_OFFLINE_SECONDS
                except ValueError, TypeError:
                    is_online = False

                if is_online:
                    online_count += 1

                devices.append(
                    DeviceInfo(
                        device_id=did,
                        name=str(info["name"]),
                        ip=str(info["ip"]),
                        position=int(info.get("position", 0)),
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
