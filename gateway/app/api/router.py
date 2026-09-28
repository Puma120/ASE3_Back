"""Enrutamiento del gateway hacia los microservicios internos.

Proxy generico: reenvia metodo/headers/body/query tal cual al microservicio
destino segun el prefijo de la ruta. Valida el JWT de sesion antes de
reenviar, excepto en las rutas publicas de registro/login (el usuario aun
no tiene token en ese punto).
"""

import asyncio

import httpx
from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.middleware.session import validate_session

router = APIRouter()

# Rutas de auth_service que no requieren sesion previa (el usuario esta
# obteniendo su primer token o aun no tiene cuenta).
PUBLIC_AUTH_PATHS = {"register", "login"}

# Railway a veces tarda unos segundos en levantar el DNS/socket interno de un
# servicio recien redeployado o "dormido" (cold start / red privada) -> se
# reintenta antes de devolver 500 al cliente en vez de fallar al primer intento.
PROXY_RETRIES = 4
PROXY_RETRY_DELAY_SECONDS = 2.0


async def _proxy(base_url: str, path: str, request: Request) -> Response:
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in ("host", "content-length")
    }
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        for attempt in range(PROXY_RETRIES):
            try:
                upstream = await client.request(
                    request.method,
                    f"/{path}",
                    params=request.query_params,
                    headers=headers,
                    content=body,
                )
                break
            except httpx.ConnectError:
                if attempt == PROXY_RETRIES - 1:
                    raise
                await asyncio.sleep(PROXY_RETRY_DELAY_SECONDS)
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
        validate_session(request)
    return await _proxy(settings.auth_service_url, f"auth/{path}", request)


@router.api_route("/tools/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_tools(path: str, request: Request) -> Response:
    validate_session(request)
    return await _proxy(settings.tools_service_url, f"tools/{path}", request)


@router.api_route("/agent/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_agent(path: str, request: Request) -> Response:
    validate_session(request)
    return await _proxy(settings.agent_service_url, f"agent/{path}", request)
