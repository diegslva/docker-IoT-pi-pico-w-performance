"""Observabilidade centralizada — structured logging, correlation ID, metricas Prometheus.

Configuracao unica de logging para todo o servidor:
- Dev: human-readable colorido
- Prod: JSON estruturado para ingestao

Metricas Prometheus:
- Histograms com buckets padrao
- Gauges para estado do sistema
- Counters para erros e eventos

Correlation ID:
- Middleware FastAPI injeta X-Correlation-ID em cada request
- Propagado via contextvars para todos os loggers
"""

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# --- Correlation ID ---
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


# --- Structured Logging ---

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT: str = os.getenv("LOG_FORMAT", "dev")  # "dev" or "json"


class StructuredFormatter(logging.Formatter):
    """JSON formatter para producao — cada linha e um objeto JSON."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": correlation_id_var.get("-"),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


class DevFormatter(logging.Formatter):
    """Formatter legivel para dev — colorido com correlation ID."""

    COLORS: dict[str, str] = {
        "DEBUG": "\033[36m",  # cyan
        "INFO": "\033[32m",  # green
        "WARNING": "\033[33m",  # yellow
        "ERROR": "\033[31m",  # red
        "CRITICAL": "\033[1;31m",  # bold red
    }
    RESET: str = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color: str = self.COLORS.get(record.levelname, "")
        cid: str = correlation_id_var.get("-")
        ts: str = self.formatTime(record, "%H:%M:%S")
        msg: str = record.getMessage()
        base: str = f"{ts} {color}{record.levelname:<7}{self.RESET} [{record.name}] [{cid}] {msg}"
        if record.exc_info and record.exc_info[0] is not None:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_logging() -> None:
    """Configura logging estruturado para todo o processo."""
    root: logging.Logger = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Remove handlers existentes (evita duplicacao no reload do uvicorn)
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler: logging.StreamHandler = logging.StreamHandler(sys.stderr)  # type: ignore[type-arg]
    if LOG_FORMAT == "json":
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(DevFormatter())

    root.addHandler(handler)

    # Silencia loggers ruidosos
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


# --- Prometheus Metrics (inline, zero deps) ---

# Buckets padrao do CLAUDE.md
HISTOGRAM_BUCKETS: list[float] = [
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
]


class Counter:
    """Prometheus counter — monotonically increasing."""

    def __init__(self, name: str, help_text: str, labels: list[str] | None = None) -> None:
        self.name: str = name
        self.help_text: str = help_text
        self.labels: list[str] = labels or []
        self._values: dict[tuple[str, ...], float] = {}

    def inc(self, amount: float = 1.0, **label_values: str) -> None:
        key: tuple[str, ...] = tuple(label_values.get(lbl, "") for lbl in self.labels)
        self._values[key] = self._values.get(key, 0.0) + amount

    def collect(self) -> str:
        lines: list[str] = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} counter"]
        if not self._values:
            lines.append(f"{self.name} 0")
        else:
            for key, val in sorted(self._values.items()):
                label_str: str = self._format_labels(key)
                lines.append(f"{self.name}{label_str} {val}")
        return "\n".join(lines)

    def _format_labels(self, key: tuple[str, ...]) -> str:
        if not self.labels:
            return ""
        pairs: list[str] = [f'{lbl}="{v}"' for lbl, v in zip(self.labels, key, strict=True)]
        return "{" + ",".join(pairs) + "}"


class Gauge:
    """Prometheus gauge — can go up and down."""

    def __init__(self, name: str, help_text: str, labels: list[str] | None = None) -> None:
        self.name: str = name
        self.help_text: str = help_text
        self.labels: list[str] = labels or []
        self._values: dict[tuple[str, ...], float] = {}

    def set(self, value: float, **label_values: str) -> None:
        key: tuple[str, ...] = tuple(label_values.get(lbl, "") for lbl in self.labels)
        self._values[key] = value

    def inc(self, amount: float = 1.0, **label_values: str) -> None:
        key: tuple[str, ...] = tuple(label_values.get(lbl, "") for lbl in self.labels)
        self._values[key] = self._values.get(key, 0.0) + amount

    def collect(self) -> str:
        lines: list[str] = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} gauge"]
        if not self._values:
            lines.append(f"{self.name} 0")
        else:
            for key, val in sorted(self._values.items()):
                label_str: str = self._format_labels(key)
                lines.append(f"{self.name}{label_str} {val}")
        return "\n".join(lines)

    def _format_labels(self, key: tuple[str, ...]) -> str:
        if not self.labels:
            return ""
        pairs: list[str] = [f'{lbl}="{v}"' for lbl, v in zip(self.labels, key, strict=True)]
        return "{" + ",".join(pairs) + "}"


class Histogram:
    """Prometheus histogram com buckets cumulativos."""

    def __init__(
        self,
        name: str,
        help_text: str,
        buckets: list[float] | None = None,
        labels: list[str] | None = None,
    ) -> None:
        self.name: str = name
        self.help_text: str = help_text
        self.buckets: list[float] = buckets or HISTOGRAM_BUCKETS
        self.labels: list[str] = labels or []
        # Per label-key: {bucket_le: count}
        self._bucket_counts: dict[tuple[str, ...], dict[float, int]] = {}
        self._sums: dict[tuple[str, ...], float] = {}
        self._counts: dict[tuple[str, ...], int] = {}

    def observe(self, value: float, **label_values: str) -> None:
        key: tuple[str, ...] = tuple(label_values.get(lbl, "") for lbl in self.labels)
        if key not in self._bucket_counts:
            self._bucket_counts[key] = {b: 0 for b in self.buckets}
            self._sums[key] = 0.0
            self._counts[key] = 0

        # Increment only the matching bucket (cumulative on export)
        for b in self.buckets:
            if value <= b:
                self._bucket_counts[key][b] += 1
                break

        self._sums[key] = self._sums.get(key, 0.0) + value
        self._counts[key] = self._counts.get(key, 0) + 1

    def collect(self) -> str:
        lines: list[str] = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} histogram",
        ]
        if not self._counts:
            # Emit zero-value histogram for "no data" dashboards
            for b in self.buckets:
                lines.append(f'{self.name}_bucket{{le="{b}"}} 0')
            lines.append(f'{self.name}_bucket{{le="+Inf"}} 0')
            lines.append(f"{self.name}_sum 0")
            lines.append(f"{self.name}_count 0")
        else:
            for key in sorted(self._counts.keys()):
                label_str: str = self._format_labels(key)
                # Cumulative buckets
                cumulative: int = 0
                for b in self.buckets:
                    cumulative += self._bucket_counts[key].get(b, 0)
                    le_labels: str = self._format_labels_with_le(key, str(b))
                    lines.append(f"{self.name}_bucket{le_labels} {cumulative}")
                # +Inf bucket == total count
                inf_labels: str = self._format_labels_with_le(key, "+Inf")
                lines.append(f"{self.name}_bucket{inf_labels} {self._counts[key]}")
                lines.append(f"{self.name}_sum{label_str} {self._sums[key]}")
                lines.append(f"{self.name}_count{label_str} {self._counts[key]}")
        return "\n".join(lines)

    def _format_labels(self, key: tuple[str, ...]) -> str:
        if not self.labels:
            return ""
        pairs: list[str] = [f'{lbl}="{v}"' for lbl, v in zip(self.labels, key, strict=True)]
        return "{" + ",".join(pairs) + "}"

    def _format_labels_with_le(self, key: tuple[str, ...], le: str) -> str:
        pairs: list[str] = [f'{lbl}="{v}"' for lbl, v in zip(self.labels, key, strict=True)]
        pairs.append(f'le="{le}"')
        return "{" + ",".join(pairs) + "}"


# --- Global Metrics Instances ---

http_request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labels=["method", "endpoint", "status"],
)

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labels=["method", "endpoint", "status"],
)

frame_render_duration = Histogram(
    "frame_render_duration_seconds",
    "Frame render duration in seconds",
    labels=["scene", "device_id"],
)

frames_rendered_total = Counter(
    "frames_rendered_total",
    "Total frames rendered",
    labels=["scene"],
)

devices_online = Gauge(
    "devices_online",
    "Number of devices currently online",
)

devices_registered = Gauge(
    "devices_registered",
    "Total number of registered devices",
)

fetch_errors_total = Counter(
    "fetch_errors_total",
    "Total external fetch errors",
    labels=["provider"],
)

crypto_cache_hits = Counter(
    "crypto_cache_hits_total",
    "Crypto provider cache hits",
)

crypto_cache_misses = Counter(
    "crypto_cache_misses_total",
    "Crypto provider cache misses",
)

effect_changes_total = Counter(
    "effect_changes_total",
    "Total effect mode changes",
    labels=["mode"],
)

server_start_timestamp = Gauge(
    "server_start_timestamp_seconds",
    "Unix timestamp when the server started",
)

stream_connections_active = Gauge(
    "stream_connections_active",
    "Number of active TCP streaming connections",
)

stream_frames_pushed_total = Counter(
    "stream_frames_pushed_total",
    "Total frames pushed via TCP streaming",
)

stream_fps = Gauge(
    "stream_fps",
    "Current FPS per streaming connection",
    labels=["device_id"],
)

stream_disconnects_total = Counter(
    "stream_disconnects_total",
    "Total stream disconnects by reason",
    labels=["reason", "device_id"],
)

_ALL_METRICS: list[Counter | Gauge | Histogram] = [
    http_request_duration,
    http_requests_total,
    frame_render_duration,
    frames_rendered_total,
    devices_online,
    devices_registered,
    fetch_errors_total,
    crypto_cache_hits,
    crypto_cache_misses,
    effect_changes_total,
    server_start_timestamp,
    stream_connections_active,
    stream_frames_pushed_total,
    stream_fps,
    stream_disconnects_total,
]


def collect_metrics() -> str:
    """Coleta todas as metricas no formato Prometheus text exposition."""
    return "\n\n".join(m.collect() for m in _ALL_METRICS) + "\n"


# --- Middleware ---

# Endpoints internos que nao devem gerar metricas/logs de request
_SKIP_PATHS: set[str] = {"/metrics", "/api/health"}


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware que injeta correlation ID e coleta metricas por request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Correlation ID — usa header se presente, senao gera
        cid: str = request.headers.get("x-correlation-id", uuid.uuid4().hex[:12])
        correlation_id_var.set(cid)

        path: str = request.url.path
        method: str = request.method

        start: float = time.perf_counter()
        response: Response = await call_next(request)
        duration: float = time.perf_counter() - start

        # Injeta correlation ID na response
        response.headers["X-Correlation-ID"] = cid

        # Metricas (skip endpoints internos)
        if path not in _SKIP_PATHS:
            status: str = str(response.status_code)
            http_request_duration.observe(duration, method=method, endpoint=path, status=status)
            http_requests_total.inc(method=method, endpoint=path, status=status)

        return response


def setup_observability(app: FastAPI) -> None:
    """Configura logging, middleware e endpoint /metrics no app FastAPI."""
    setup_logging()
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(content=collect_metrics(), media_type="text/plain; charset=utf-8")
