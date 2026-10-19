"""Pruebas del gateway: errores de los servicios, limite por usuario y sesion."""

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app.api import router as router_mod
from app.core import rate_limit
from app.core.config import settings
from app.main import app


def _token(sub: str = "u1") -> dict:
    token = jwt.encode({"sub": sub}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _client(handler) -> TestClient:
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TestClient(app)


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    rate_limit.clear_all()
    monkeypatch.setattr(router_mod, "PROXY_RETRY_DELAY_SECONDS", 0)


def test_sin_token_responde_401():
    c = _client(lambda r: httpx.Response(200))
    assert c.get("/tools/tasks").status_code == 401


def test_reenvia_y_devuelve_respuesta_del_servicio():
    c = _client(lambda r: httpx.Response(200, json={"ok": True}))
    r = c.get("/tools/tasks", headers=_token())
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_timeout_del_servicio_responde_504():
    def handler(request):
        raise httpx.ReadTimeout("lento")

    r = _client(handler).post("/agent/chat", headers=_token(), json={"message": "hola"})
    assert r.status_code == 504
    assert "tardo" in r.json()["detail"]


def test_servicio_caido_responde_502_tras_reintentar():
    llamadas = []

    def handler(request):
        llamadas.append(1)
        raise httpx.ConnectError("caido")

    r = _client(handler).get("/tools/tasks", headers=_token())
    assert r.status_code == 502
    assert len(llamadas) == router_mod.PROXY_RETRIES


def test_limite_por_usuario_responde_429_con_retry_after(monkeypatch):
    monkeypatch.setitem(router_mod.RATE_LIMITS, "agent", 3)
    c = _client(lambda r: httpx.Response(200, json={}))
    estados = [c.post("/agent/chat", headers=_token("a"), json={}).status_code for _ in range(4)]
    assert estados == [200, 200, 200, 429]
    limitado = c.post("/agent/chat", headers=_token("a"), json={})
    assert int(limitado.headers["Retry-After"]) >= 1
    # Otro usuario no se ve afectado.
    assert c.post("/agent/chat", headers=_token("b"), json={}).status_code == 200


def test_rutas_publicas_de_auth_no_piden_token():
    c = _client(lambda r: httpx.Response(200, json={}))
    assert c.post("/auth/login", json={}).status_code == 200


def test_produccion_rechaza_secreto_jwt_por_defecto_o_corto(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    with pytest.raises(ValueError):
        Settings(jwt_secret_key="change-me")
    with pytest.raises(ValueError):
        Settings(jwt_secret_key="corto")
    assert Settings(jwt_secret_key="x" * 32).jwt_secret_key == "x" * 32


def test_cors_solo_permite_origenes_configurados():
    c = _client(lambda r: httpx.Response(200, json={}))
    ok = c.options(
        "/tools/tasks",
        headers={"Origin": "https://ase3-front-pwa.vercel.app", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "https://ase3-front-pwa.vercel.app"
    ajeno = c.options(
        "/tools/tasks",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in ajeno.headers


def test_limitador_libera_claves_inactivas(monkeypatch):
    monkeypatch.setattr(rate_limit, "_PURGE_EVERY", 1)
    rate_limit.hit("viejo", 5, 0.0001)
    import time as _t
    _t.sleep(0.01)
    rate_limit.hit("nuevo", 5, 0.0001)
    assert "viejo" not in rate_limit._hits
