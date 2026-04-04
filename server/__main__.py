"""Entrypoint do servidor — gerencia porta via PID file antes de iniciar.

Seguranca: so mata processos que foram iniciados por este software (PID file).
Nunca mata processos de terceiros, mesmo que estejam na mesma porta.
"""

import logging
import os
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import uvicorn

from server.observability import setup_logging

setup_logging()
logger: logging.Logger = logging.getLogger("server.main")


def check_port_available(host: str, port: int) -> bool:
    """Verifica se a porta esta disponivel para bind."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))

# PID file — identifica processos que sao nossos
PID_DIR: Path = Path(__file__).parent.parent / ".run"
PID_FILE: Path = PID_DIR / "server.pid"


def _write_pid() -> None:
    """Escreve PID do processo atual no arquivo."""
    PID_DIR.mkdir(exist_ok=True)
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
            "Failed to check parent-child relationship: child=%d parent=%d", child_pid, parent_pid
        )
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


def ensure_port_available(host: str, port: int) -> None:
    """Garante que a porta esta disponivel.

    Logica de seguranca:
    1. Porta livre → OK
    2. Porta ocupada → verifica PID file
       a. PID file existe E o PID no arquivo == PID na porta → mata (e nosso)
       b. PID file existe mas PID diferente → nao mata (processo de terceiro)
       c. PID file nao existe → nao mata (nao sabemos quem e)
    """
    if check_port_available(host, port):
        logger.info("Port %d is available", port)
        _remove_pid()  # Limpa PID stale se existir
        return

    port_pid: int | None = _find_pid_on_port(port)
    if port_pid is None:
        logger.error("Port %d is in use but could not identify the process", port)
        sys.exit(1)

    our_pid: int | None = _read_pid()

    is_ours: bool = False
    if our_pid is not None:
        # PID direto ou processo filho (uvicorn --reload cria filho)
        is_ours = our_pid == port_pid or _is_child_of(port_pid, our_pid)

    if is_ours:
        # Sempre mata o pai (our_pid) — /T (tree kill) mata filhos junto
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
        # Sem PID file — nao temos como confirmar que e nosso
        logger.error(
            "Port %d is in use by process PID %d. "
            "No PID file found — cannot confirm ownership. NOT killing. "
            "If this is a stale process, kill it manually: taskkill /F /PID %d",
            port,
            port_pid,
            port_pid,
        )
        sys.exit(1)


def main() -> None:
    ensure_port_available(SERVER_HOST, SERVER_PORT)
    _write_pid()

    try:
        uvicorn.run(
            "server.app:app",
            host=SERVER_HOST,
            port=SERVER_PORT,
            reload=True,
        )
    finally:
        _remove_pid()


if __name__ == "__main__":
    main()
