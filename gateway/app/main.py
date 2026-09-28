from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router as api_router
from app.core.config import settings

app = FastAPI(
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
