"""Pydantic models para request/response do servidor."""

from pydantic import BaseModel


class DisplayData(BaseModel):
    btc: float
    eth: float
    ts: str
    ok: bool


class DeviceInfo(BaseModel):
    device_id: str
    name: str
    ip: str
    position: int
    last_seen: str
    fetch_count: int


class DeviceListResponse(BaseModel):
    devices: list[DeviceInfo]
    total: int
    online: int
    offline: int


class EffectResponse(BaseModel):
    status: str
    mode: str
    total_positions: int
    speed: int


class HealthResponse(BaseModel):
    status: str
    devices_online: int
    active_effect: str
