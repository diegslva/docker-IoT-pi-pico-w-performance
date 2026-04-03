"""Entrypoint do servidor — verifica porta disponivel antes de iniciar."""

import os
import sys

import uvicorn

from server.main import check_port_available, find_available_port, logger

SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))


def main() -> None:
    if check_port_available(SERVER_HOST, SERVER_PORT):
        port: int = SERVER_PORT
        logger.info("Port %d is available", port)
    else:
        logger.warning("Port %d is in use, searching for alternative...", SERVER_PORT)
        try:
            port = find_available_port(SERVER_HOST, SERVER_PORT)
            logger.info("Using alternative port: %d", port)
        except RuntimeError as e:
            logger.error("Failed to find available port: %s", e)
            sys.exit(1)

    uvicorn.run(
        "server.main:app",
        host=SERVER_HOST,
        port=port,
        reload=True,
    )


if __name__ == "__main__":
    main()
