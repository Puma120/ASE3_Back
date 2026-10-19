from contextlib import asynccontextmanager

from http.cookiejar import DefaultCookiePolicy

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import PROXY_TIMEOUT_SECONDS, router as api_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Un solo cliente para todo el proceso: reutiliza conexiones hacia los servicios.
    async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS) as client:
        # El cliente es compartido entre usuarios: que no guarde cookies de los servicios.
        client.cookies.jar.set_policy(DefaultCookiePolicy(allowed_domains=[]))
        app.state.http = client
        yield


app = FastAPI(
    lifespan=lifespan,
    title="TDAH Agent - Gateway",
    description="API Gateway / Orquestador: punto unico de entrada, valida sesion y enruta a los microservicios.",
    version="0.1.0",
)

# front/pwa corre en el navegador (origen distinto al gateway) y front/mobile
# en Expo Web usa el mismo mecanismo - sin esto el navegador bloquea toda
# llamada fetch por CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "gateway"}
