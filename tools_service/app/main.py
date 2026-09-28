from fastapi import FastAPI

from app.api.routes.tools import router as tools_router

app = FastAPI(
    title="TDAH Agent - Tools Service",
    description="Logica de negocio e integraciones con APIs de Google (Calendar, Tasks, Maps, Gmail). Conecta a PostgreSQL y MongoDB.",
    version="0.1.0",
)

app.include_router(tools_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "tools_service"}
