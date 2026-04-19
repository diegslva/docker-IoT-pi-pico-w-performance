"""Entrypoint do servidor — guardas contra processos duplicados.

Ordem de verificacao no startup:
1. Health probe (GET /api/health) — se outra instancia responde, aborta
2. Lock file exclusivo (.run/server.lock) — impede 2 instancias simultaneas
3. Bind test na porta — se ocupada por outro programa, aborta
4. PID file — registro do PID para cleanup
5. Inicia uvicorn

Seguranca: nunca mata processos de terceiros. Se a porta esta ocupada por algo
que nao e nosso, aborta com mensagem clara.
"""

import atexit
import json
import logging
import msvcrt
import os
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import closing
from pathlib import Path

import uvicorn


# Carregar .env antes de qualquer import que dependa de env vars
def _load_dotenv() -> None:
    """Carrega .env do projeto sem depender de python-dotenv."""
    env_file: Path = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

from server.observability import setup_logging  # noqa: E402

setup_logging()
logger: logging.Logger = logging.getLogger("server.main")

SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
STREAM_PORT: int = int(os.getenv("STREAM_PORT", "8001"))

# --- Paths ---
RUN_DIR: Path = Path(__file__).parent.parent / ".run"
PID_FILE: Path = RUN_DIR / "server.pid"
LOCK_FILE: Path = RUN_DIR / "server.lock"


# --- Health Probe ---
def _probe_existing_server(port: int) -> dict | None:
    """Tenta GET /api/health na porta. Retorna JSON se responder, None se nao."""
    url: str = f"http://127.0.0.1:{port}/api/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode())
    except urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError:
        pass
    return None


# --- Lock File ---
def _acquire_lock() -> int | None:
    """Adquire lock exclusivo no arquivo. Retorna fd ou None se ja esta lockado."""
    RUN_DIR.mkdir(exist_ok=True)
    try:
        fd: int = os.open(str(LOCK_FILE), os.O_CREAT | os.O_RDWR)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return fd
    except OSError:
        return None


def _release_lock(fd: int) -> None:
    """Libera lock e fecha file descriptor."""
    import contextlib

    with contextlib.suppress(OSError):
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    os.close(fd)


# --- PID File ---
def _write_pid() -> None:
    """Escreve PID do processo atual no arquivo."""
    RUN_DIR.mkdir(exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    logger.info("PID file written: %s (PID %d)", PID_FILE, os.getpid())


def _read_pid() -> int | None:
    """Le PID do arquivo. Retorna None se nao existir."""
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except ValueError, OSError:
        return None


def _remove_pid() -> None:
    """Remove PID file."""
    import contextlib

    with contextlib.suppress(OSError):
        PID_FILE.unlink(missing_ok=True)


# --- Port Check ---
def _check_port_available(host: str, port: int) -> bool:
    """Verifica se a porta esta disponivel para bind."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _find_pid_on_port(port: int) -> int | None:
    """Encontra o PID do processo escutando na porta (Windows)."""
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts: list[str] = line.split()
                if len(parts) >= 5:
                    return int(parts[-1])
    except subprocess.TimeoutExpired, ValueError:
        logger.warning("Failed to find PID on port %d via netstat", port)
    return None


def _is_child_of(child_pid: int, parent_pid: int) -> bool:
    """Verifica se child_pid e filho de parent_pid (Windows via wmic)."""
    try:
        cmd: list[str] = [
            "wmic",
            "process",
            "where",
            f"ProcessId={child_pid}",
            "get",
            "ParentProcessId",
            "/value",
        ]
        result: subprocess.CompletedProcess[str] = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if "ParentProcessId=" in line:
                ppid: int = int(line.split("=")[1].strip())
                return ppid == parent_pid
    except subprocess.TimeoutExpired, ValueError, OSError:
        logger.warning(
            "Failed to check parent-child relationship: child=%d parent=%d",
            child_pid,
            parent_pid,
        )
    return False


def _kill_process(pid: int) -> bool:
    """Mata processo por PID."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid), "/T"],
            capture_output=True,
            timeout=5,
        )
        return True
    except subprocess.TimeoutExpired:
        return False


# --- Startup Guard ---
def ensure_safe_startup(host: str, port: int) -> None:
    """Garante que e seguro iniciar o servidor.

    Logica em camadas:
    1. Health probe — se responde, outra instancia esta ativa
    2. Lock file — se nao consegue lock, processo concorrente em startup
    3. Porta — se ocupada, verifica se e processo nosso (PID file) e mata
    """
    # Camada 1: health probe
    health = _probe_existing_server(port)
    if health is not None:
        logger.error(
            "Another server instance is already running on port %d. "
            "Health: devices_online=%s, active_effect=%s. "
            "Kill it first or use a different port.",
            port,
            health.get("devices_online", "?"),
            health.get("active_effect", "?"),
        )
        sys.exit(1)

    # Camada 2: porta disponivel?
    if _check_port_available(host, port):
        logger.info("Port %d is available", port)
        _remove_pid()
        return

    # Porta ocupada mas health probe falhou — pode ser processo nosso morrendo
    # ou outro programa. Verificar via PID file.
    port_pid: int | None = _find_pid_on_port(port)
    if port_pid is None:
        logger.error("Port %d is in use but could not identify the process", port)
        sys.exit(1)

    our_pid: int | None = _read_pid()
    is_ours: bool = False
    if our_pid is not None:
        is_ours = our_pid == port_pid or _is_child_of(port_pid, our_pid)

    if is_ours:
        kill_target: int = our_pid
        logger.warning(
            "Port %d in use by our previous instance (PID file=%d, port=%d) — killing",
            port,
            our_pid,
            port_pid,
        )
        if _kill_process(kill_target):
            logger.info("Process %d terminated (tree kill)", kill_target)
            _remove_pid()
            time.sleep(2)
        else:
            logger.error("Failed to kill process %d", kill_target)
            sys.exit(1)
    elif our_pid is not None:
        logger.error(
            "Port %d in use by PID %d (our PID file=%d) — NOT our process. NOT killing.",
            port,
            port_pid,
            our_pid,
        )
        sys.exit(1)
    else:
        logger.error(
            "Port %d is in use by process PID %d. "
            "No PID file found — cannot confirm ownership. NOT killing. "
            "If this is a stale process, kill it manually: taskkill /F /PID %d",
            port,
            port_pid,
            port_pid,
        )
        sys.exit(1)


def _free_stale_port(port: int) -> None:
    """Libera porta se ocupada por processo nosso (best-effort, nao aborta)."""
    if _check_port_available("0.0.0.0", port):
        return
    port_pid: int | None = _find_pid_on_port(port)
    our_pid: int | None = _read_pid()
    if port_pid and our_pid and (our_pid == port_pid or _is_child_of(port_pid, our_pid)):
        logger.warning("Freeing stale port %d (PID %d from previous instance)", port, port_pid)
        _kill_process(port_pid)
        time.sleep(1)
    elif port_pid:
        logger.warning(
            "Port %d in use by PID %d (not ours), stream server will retry", port, port_pid
        )


_cleaned_up: bool = False


def _cleanup(lock_fd: int) -> None:
    """Cleanup gracioso: PID file + lock. Idempotente — so executa 1x."""
    global _cleaned_up
    if _cleaned_up:
        return
    _cleaned_up = True
    _remove_pid()
    _release_lock(lock_fd)
    logger.info("Shutdown complete — PID file removed, lock released")


def _check_wifi_network() -> None:
    """Verifica se o computador esta na mesma rede Wi-Fi dos Pico W's."""
    from pathlib import Path as _Path

    env_file: _Path = _Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        return

    expected_ssid: str = ""
    for line in env_file.read_text().splitlines():
        if line.startswith("WIFI_SSID="):
            expected_ssid = line.split("=", 1)[1].strip()
            break

    if not expected_ssid:
        return

    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        current_ssid: str = ""
        for line in result.stdout.splitlines():
            if "SSID" in line and "BSSID" not in line:
                current_ssid = line.split(":", 1)[1].strip()
                break

        if current_ssid and current_ssid != expected_ssid:
            logger.warning(
                "REDE WI-FI DIFERENTE! Conectado em '%s' mas Pico W's usam '%s'. "
                "Devices nao vao encontrar o servidor.",
                current_ssid,
                expected_ssid,
            )
        elif current_ssid:
            logger.info("Wi-Fi OK: '%s' (mesma rede dos Pico W's)", current_ssid)
    except subprocess.TimeoutExpired, OSError:
        logger.warning("Nao foi possivel verificar rede Wi-Fi")


def main() -> None:
    # Guard 0: verificar rede Wi-Fi
    _check_wifi_network()

    # Guard 1: health probe + porta + PID (porta principal)
    ensure_safe_startup(SERVER_HOST, SERVER_PORT)

    # Guard 1b: liberar porta de streaming se stale
    _free_stale_port(STREAM_PORT)

    # Guard 2: lock file exclusivo
    lock_fd: int | None = _acquire_lock()
    if lock_fd is None:
        logger.error(
            "Cannot acquire lock file %s — another instance is starting up. Aborting.",
            LOCK_FILE,
        )
        sys.exit(1)
    logger.info("Lock acquired: %s", LOCK_FILE)

    _write_pid()

    # Safety net: atexit como ultimo recurso
    atexit.register(_cleanup, lock_fd)

    try:
        uvicorn.run(
            "server.app:app",
            host=SERVER_HOST,
            port=SERVER_PORT,
            reload=True,
            reload_excludes=["__pycache__", "*.pyc", ".run", ".git", "monitoring"],
        )
    finally:
        _cleanup(lock_fd)


if __name__ == "__main__":
    main()
