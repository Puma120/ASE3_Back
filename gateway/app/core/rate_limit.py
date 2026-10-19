"""Limite de peticiones por usuario en memoria (ventana deslizante).

Vive en el proceso: con mas de una replica del gateway cada una cuenta por
separado. Para el piloto (una replica) basta; si se escala hay que moverlo a Redis.
"""

import time
from collections import deque

_hits: dict[str, deque[float]] = {}


def hit(key: str, limit: int, window: float) -> int:
    """Registra una peticion. Devuelve 0 si se permite o los segundos de espera si excede `limit`."""
    now = time.monotonic()
    q = _hits.setdefault(key, deque())
    while q and q[0] <= now - window:
        q.popleft()
    if len(q) >= limit:
        return max(1, int(q[0] + window - now) + 1)
    q.append(now)
    return 0


def clear_all() -> None:
    _hits.clear()
