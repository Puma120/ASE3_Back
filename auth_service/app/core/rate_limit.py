"""Limite de intentos en memoria (ventana deslizante por clave).

Vive en el proceso: con mas de una replica de auth_service cada una cuenta por
separado (el limite efectivo se multiplica por el numero de replicas). Para el
piloto, con una sola replica, basta; si se escala hay que moverlo a Redis.
"""

import time
from collections import deque

_MAX_KEYS = 10_000  # tope de memoria ante claves inventadas por un atacante

_hits: dict[str, deque[float]] = {}


def _now() -> float:
    return time.monotonic()


def _live(key: str, window: float) -> deque[float]:
    q = _hits.get(key)
    if q is None:
        return deque()
    cutoff = _now() - window
    while q and q[0] <= cutoff:
        q.popleft()
    if not q:
        del _hits[key]
        return deque()
    return q


def retry_after(key: str, limit: int, window: float) -> int:
    """Segundos de espera si la clave ya agoto `limit` intentos en `window`; 0 si no."""
    q = _live(key, window)
    if len(q) < limit:
        return 0
    return max(1, int(q[0] + window - _now()) + 1)


def record(key: str, window: float) -> None:
    if len(_hits) >= _MAX_KEYS:
        for k in list(_hits):
            _live(k, window)
        if len(_hits) >= _MAX_KEYS:
            _hits.clear()
    _hits.setdefault(key, deque()).append(_now())


def reset(key: str) -> None:
    _hits.pop(key, None)


def clear_all() -> None:
    _hits.clear()
