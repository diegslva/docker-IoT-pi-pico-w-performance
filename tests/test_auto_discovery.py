"""Testes do auto-discovery de posicao."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from server.app import app, device_registry


@pytest_asyncio.fixture(autouse=True)
async def _clean_registry() -> None:
    """Limpa o registry entre testes."""
    async with device_registry._lock:
        device_registry._devices.clear()


@pytest.mark.asyncio
class TestAutoAssignPosition:
    async def test_first_device_gets_position_zero(self) -> None:
        pos: int = await device_registry.register(
            device_id="aa:bb:cc:dd:ee:01", name="tv-1", ip="10.0.0.1", position=-1
        )
        assert pos == 0

    async def test_second_device_gets_position_one(self) -> None:
        await device_registry.register(
            device_id="aa:bb:cc:dd:ee:01", name="tv-1", ip="10.0.0.1", position=-1
        )
        pos: int = await device_registry.register(
            device_id="aa:bb:cc:dd:ee:02", name="tv-2", ip="10.0.0.2", position=-1
        )
        assert pos == 1

    async def test_returning_device_keeps_position(self) -> None:
        await device_registry.register(
            device_id="aa:bb:cc:dd:ee:01", name="tv-1", ip="10.0.0.1", position=-1
        )
        await device_registry.register(
            device_id="aa:bb:cc:dd:ee:02", name="tv-2", ip="10.0.0.2", position=-1
        )
        # Device 1 re-registers — should keep position 0
        pos: int = await device_registry.register(
            device_id="aa:bb:cc:dd:ee:01", name="tv-1", ip="10.0.0.1", position=-1
        )
        assert pos == 0

    async def test_fixed_position_respected(self) -> None:
        pos: int = await device_registry.register(
            device_id="aa:bb:cc:dd:ee:01", name="tv-1", ip="10.0.0.1", position=5
        )
        assert pos == 5

    async def test_mixed_auto_and_fixed(self) -> None:
        await device_registry.register(
            device_id="aa:bb:cc:dd:ee:01", name="tv-1", ip="10.0.0.1", position=3
        )
        pos: int = await device_registry.register(
            device_id="aa:bb:cc:dd:ee:02", name="tv-2", ip="10.0.0.2", position=-1
        )
        # Auto gets max(3) + 1 = 4
        assert pos == 4

    async def test_reorder(self) -> None:
        await device_registry.register(
            device_id="aa:bb:cc:dd:ee:01", name="tv-1", ip="10.0.0.1", position=-1
        )
        await device_registry.register(
            device_id="aa:bb:cc:dd:ee:02", name="tv-2", ip="10.0.0.2", position=-1
        )
        result: dict[str, int] = await device_registry.reorder(
            ["aa:bb:cc:dd:ee:02", "aa:bb:cc:dd:ee:01"]
        )
        assert result == {"aa:bb:cc:dd:ee:02": 0, "aa:bb:cc:dd:ee:01": 1}

    async def test_get_position(self) -> None:
        await device_registry.register(
            device_id="aa:bb:cc:dd:ee:01", name="tv-1", ip="10.0.0.1", position=7
        )
        pos = await device_registry.get_position("aa:bb:cc:dd:ee:01")
        assert pos == 7

    async def test_get_position_unknown_device(self) -> None:
        pos = await device_registry.get_position("unknown")
        assert pos is None


@pytest.mark.asyncio
class TestAutoDiscoveryEndpoints:
    async def test_position_endpoint_auto_assigns(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/position?id=aa:bb:cc:dd:ee:01&name=tv-1&ip=10.0.0.1")
        assert resp.status_code == 200
        data: dict = resp.json()
        assert data["device_id"] == "aa:bb:cc:dd:ee:01"
        assert data["position"] == 0
        assert data["auto_assigned"] is True

    async def test_position_endpoint_second_device(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/api/position?id=aa:bb:cc:dd:ee:01&name=tv-1&ip=10.0.0.1")
            resp = await client.get("/api/position?id=aa:bb:cc:dd:ee:02&name=tv-2&ip=10.0.0.2")
        assert resp.json()["position"] == 1

    async def test_reorder_endpoint(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/api/position?id=aa:bb:cc:dd:ee:01&name=tv-1&ip=10.0.0.1")
            await client.get("/api/position?id=aa:bb:cc:dd:ee:02&name=tv-2&ip=10.0.0.2")
            resp = await client.post(
                "/api/devices/reorder",
                json={"order": ["aa:bb:cc:dd:ee:02", "aa:bb:cc:dd:ee:01"]},
            )
        assert resp.status_code == 200
        data: dict = resp.json()
        assert data["status"] == "ok"
        assert data["positions"]["aa:bb:cc:dd:ee:02"] == 0
        assert data["positions"]["aa:bb:cc:dd:ee:01"] == 1
