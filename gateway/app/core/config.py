import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion del Gateway, cargada desde variables de entorno / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gateway_port: int = 8000

    auth_service_url: str = "http://localhost:8001"
    tools_service_url: str = "http://localhost:8002"
    agent_service_url: str = "http://localhost:8003"
    proactive_service_url: str = "http://localhost:8004"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"

    # Origenes web permitidos por CORS (separados por coma). La app nativa no usa CORS.
    # Por defecto: el PWA en Vercel y los servidores de desarrollo locales.
    cors_origins: str = (
        "https://ase3-front-pwa.vercel.app,"
        "http://localhost:8081,http://localhost:19006,http://localhost:5173"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _exigir_secreto_jwt_en_produccion(self) -> "Settings":
        """En Railway se rechaza arrancar con el secreto por defecto o uno corto
        (cualquiera podria firmar tokens). En local/tests se permite."""
        if os.getenv("RAILWAY_ENVIRONMENT") and (
            self.jwt_secret_key == "change-me" or len(self.jwt_secret_key) < 32
        ):
            raise ValueError("JWT_SECRET_KEY debe tener al menos 32 caracteres en produccion")
        return self


settings = Settings()
