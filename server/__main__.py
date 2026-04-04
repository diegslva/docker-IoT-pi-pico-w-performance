"""Entrypoint do servidor — gerencia porta automaticamente antes de iniciar."""

import os
import subprocess
import sys

import uvicorn

from server.main import check_port_available, logger

SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
APP_SIGNATURE: str = "uvicorn server.main"


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
    except (subprocess.TimeoutExpired, ValueError):
        pass
    return None


def _is_our_process(pid: int) -> bool:
    """Verifica se o processo e nosso (uvicorn server.main)."""
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/V", "/FO", "CSV"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output: str = result.stdout.lower()
        return "python" in output or "uvicorn" in output
    except subprocess.TimeoutExpired:
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


def ensure_port_available(host: str, port: int) -> None:
    """Garante que a porta esta disponivel, matando processo anterior se necessario."""
    if check_port_available(host, port):
        logger.info("Port %d is available", port)
        return

    pid: int | None = _find_pid_on_port(port)
    if pid is None:
        logger.error("Port %d is in use but could not identify the process", port)
        sys.exit(1)

    if _is_our_process(pid):
        logger.warning("Port %d is in use by our previous process (PID %d) — killing it", port, pid)
        if _kill_process(pid):
            logger.info("Process %d terminated", pid)
            import time
            time.sleep(2)
        else:
            logger.error("Failed to kill process %d", pid)
            sys.exit(1)
    else:
        logger.error(
            "Port %d is in use by an unrelated process (PID %d) — not killing it",
            port,
            pid,
        )
        sys.exit(1)


def main() -> None:
    ensure_port_available(SERVER_HOST, SERVER_PORT)

    uvicorn.run(
        "server.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
