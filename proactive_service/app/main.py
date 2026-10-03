from fastapi import FastAPI

app = FastAPI(
    title="TDAH Agent - Proactive Service",
    description="Motor proactivo: tick silencioso por usuario, recordatorios inteligentes y envio de push.",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "proactive_service"}
