"""Limite de peticiones por usuario en memoria (ventana deslizante).

Vive en el proceso: con mas de una replica del gateway cada una cuenta por
separado. Para el piloto (una replica) basta; si se escala hay que moverlo a Redis.
"""

import time
from collections import deque

_hits: dict[str, deque[float]] = {}
_PURGE_EVERY = 1000  # llamadas entre limpiezas de claves inactivas
_calls = 0


def _purge(now: float, window: float) -> None:
    """Libera las claves sin peticiones dentro de la ventana (evita crecer sin limite)."""
    for key in [k for k, q in _hits.items() if not q or q[-1] <= now - window]:
        del _hits[key]


def hit(key: str, limit: int, window: float) -> int:
    """Registra una peticion. Devuelve 0 si se permite o los segundos de espera si excede `limit`."""
    global _calls
    now = time.monotonic()
    _calls += 1
    if _calls % _PURGE_EVERY == 0:
        _purge(now, window)
    q = _hits.setdefault(key, deque())
    while q and q[0] <= now - window:
        q.popleft()
    if len(q) >= limit:
        return max(1, int(q[0] + window - now) + 1)
    q.append(now)
    return 0


def clear_all() -> None:
    _hits.clear()
