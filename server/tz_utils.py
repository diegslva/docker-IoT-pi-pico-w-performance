"""Utilidades de timezone centralizadas."""

import os
from datetime import datetime, timedelta, timezone

TZ_OFFSET_HOURS: int = int(os.getenv("TZ_OFFSET_HOURS", "-3"))

_local_tz: timezone = timezone(timedelta(hours=TZ_OFFSET_HOURS))


def local_now() -> datetime:
    """Retorna datetime atual no timezone local configurado."""
    return datetime.now(tz=_local_tz)


def local_timestamp() -> str:
    """Retorna horario local formatado HH:MM:SS."""
    return local_now().strftime("%H:%M:%S")


def local_datetime_str() -> str:
    """Retorna datetime local formatado YYYY-MM-DD HH:MM:SS."""
    return local_now().strftime("%Y-%m-%d %H:%M:%S")
