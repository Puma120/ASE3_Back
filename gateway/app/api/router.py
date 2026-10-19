"""Enrutamiento del gateway hacia los microservicios internos.

Proxy generico: reenvia metodo/headers/body/query tal cual al microservicio
destino segun el prefijo de la ruta. Valida el JWT de sesion antes de
reenviar, excepto en las rutas publicas del login con Google (el usuario aun
no tiene token en ese punto).
"""

import asyncio

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.core import rate_limit
from app.core.config import settings
from app.middleware.session import validate_session

router = APIRouter()

# Rutas de auth_service que no requieren sesion previa: son pre-login, el
# usuario todavia no tiene JWT propio (Google lo redirige de vuelta a
# "google/callback"; "register" y "login" son el acceso con email/password).
PUBLIC_AUTH_PATHS = {"google/login", "google/callback", "register", "login", "verify-email"}

# Railway a veces tarda unos segundos en levantar el DNS/socket interno de un
# servicio recien redeployado o "dormido" (cold start / red privada) -> se
# reintenta antes de devolver 500 al cliente en vez de fallar al primer intento.
PROXY_RETRIES = 4
PROXY_RETRY_DELAY_SECONDS = 2.0
PROXY_TIMEOUT_SECONDS = 90.0

# Peticiones por usuario y minuto segun el destino. El chat es el mas caro
# (cada mensaje dispara llamadas al LLM), por eso el tope es bajo.
RATE_WINDOW_SECONDS = 60.0
RATE_LIMITS = {"agent": 30, "tools": 120, "proactive": 120, "auth": 120}


def _authorize(request: Request, group: str) -> None:
    """Valida el JWT y aplica el limite por usuario; 429 con Retry-After si lo excede."""
    payload = validate_session(request)
    wait = rate_limit.hit(
        f"{group}:{payload.get('sub')}", RATE_LIMITS[group], RATE_WINDOW_SECONDS
    )
    if wait:
        raise HTTPException(
            status_code=429,
            detail="Demasiadas solicitudes, espera unos segundos",
            headers={"Retry-After": str(wait)},
        )


async def _proxy(base_url: str, path: str, request: Request) -> Response:
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in ("host", "content-length")
    }
    client: httpx.AsyncClient = request.app.state.http
    for attempt in range(PROXY_RETRIES):
        try:
            upstream = await client.request(
                request.method,
                f"{base_url}/{path}",
                params=request.query_params,
                headers=headers,
                content=body,
            )
            break
        except httpx.ConnectError:
            if attempt == PROXY_RETRIES - 1:
                raise HTTPException(status_code=502, detail="Servicio no disponible") from None
            await asyncio.sleep(PROXY_RETRY_DELAY_SECONDS)
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504, detail="El servicio tardo demasiado en responder"
            ) from None
        except httpx.TransportError:
            raise HTTPException(status_code=502, detail="Servicio no disponible") from None
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in ("content-length", "transfer-encoding", "connection")
        },
    )


@router.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_auth(path: str, request: Request) -> Response:
    if path not in PUBLIC_AUTH_PATHS:
        _authorize(request, "auth")
    return await _proxy(settings.auth_service_url, f"auth/{path}", request)


@router.api_route("/tools/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_tools(path: str, request: Request) -> Response:
    _authorize(request, "tools")
    return await _proxy(settings.tools_service_url, f"tools/{path}", request)


@router.api_route("/agent/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_agent(path: str, request: Request) -> Response:
    _authorize(request, "agent")
    return await _proxy(settings.agent_service_url, f"agent/{path}", request)


@router.api_route("/proactive/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_proactive(path: str, request: Request) -> Response:
    _authorize(request, "proactive")
    return await _proxy(settings.proactive_service_url, f"proactive/{path}", request)
