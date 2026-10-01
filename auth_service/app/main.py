from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.google_auth import router as google_auth_router
from app.api.routes.users import router as users_router

app = FastAPI(
    title="TDAH Agent - Auth Service",
    description="Login, JWT/OAuth, perfil, credenciales. Conecta a BD SQL (PostgreSQL).",
    version="0.1.0",
)

app.include_router(auth_router)
app.include_router(google_auth_router)
app.include_router(users_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "auth_service"}
