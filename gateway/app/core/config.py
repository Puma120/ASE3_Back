from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion del Gateway, cargada desde variables de entorno / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gateway_port: int = 8000

    auth_service_url: str = "http://localhost:8001"
    tools_service_url: str = "http://localhost:8002"
    agent_service_url: str = "http://localhost:8003"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"


settings = Settings()
