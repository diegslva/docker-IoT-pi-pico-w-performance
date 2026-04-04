"""Testes do modulo de observabilidade — metricas Prometheus e correlation ID."""

import pytest
from httpx import ASGITransport, AsyncClient

from server.app import app
from server.observability import (
    Counter,
    Gauge,
    Histogram,
    collect_metrics,
)


class TestCounter:
    def test_inc_default(self) -> None:
        c = Counter("test_counter", "test")
        c.inc()
        assert "test_counter 1" in c.collect()

    def test_inc_with_labels(self) -> None:
        c = Counter("test_labeled", "test", labels=["method"])
        c.inc(method="GET")
        c.inc(method="GET")
        c.inc(method="POST")
        output: str = c.collect()
        assert 'test_labeled{method="GET"} 2' in output
        assert 'test_labeled{method="POST"} 1' in output


class TestGauge:
    def test_set(self) -> None:
        g = Gauge("test_gauge", "test")
        g.set(42)
        assert "test_gauge 42" in g.collect()

    def test_inc(self) -> None:
        g = Gauge("test_gauge_inc", "test")
        g.inc(5)
        g.inc(3)
        assert "test_gauge_inc 8" in g.collect()


class TestHistogram:
    def test_observe_buckets(self) -> None:
        h = Histogram("test_hist", "test", buckets=[0.01, 0.05, 0.1, 1.0])
        h.observe(0.005)
        h.observe(0.03)
        h.observe(0.5)
        output: str = h.collect()
        # Cumulative: 0.01 has 1, 0.05 has 2, 0.1 has 2, 1.0 has 3
        assert 'test_hist_bucket{le="0.01"} 1' in output
        assert 'test_hist_bucket{le="0.05"} 2' in output
        assert 'test_hist_bucket{le="0.1"} 2' in output
        assert 'test_hist_bucket{le="1.0"} 3' in output
        assert 'test_hist_bucket{le="+Inf"} 3' in output
        assert "test_hist_count 3" in output

    def test_empty_histogram(self) -> None:
        h = Histogram("test_empty", "test", buckets=[0.1, 1.0])
        output: str = h.collect()
        assert 'test_empty_bucket{le="0.1"} 0' in output
        assert "test_empty_count 0" in output


class TestCollectMetrics:
    def test_returns_all_metrics(self) -> None:
        output: str = collect_metrics()
        assert "http_request_duration_seconds" in output
        assert "http_requests_total" in output
        assert "frame_render_duration_seconds" in output
        assert "frames_rendered_total" in output
        assert "devices_online" in output
        assert "devices_registered" in output
        assert "fetch_errors_total" in output
        assert "effect_changes_total" in output
        assert "server_start_timestamp_seconds" in output


@pytest.mark.asyncio
class TestMetricsEndpoint:
    async def test_metrics_endpoint(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "http_request_duration_seconds" in resp.text

    async def test_correlation_id_header(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
        assert "x-correlation-id" in resp.headers
        assert len(resp.headers["x-correlation-id"]) > 0

    async def test_custom_correlation_id(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health", headers={"x-correlation-id": "test-123"})
        assert resp.headers["x-correlation-id"] == "test-123"
