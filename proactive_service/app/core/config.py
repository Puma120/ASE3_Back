from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion del Proactive Service, cargada desde variables de entorno / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    proactive_service_port: int = 8004

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "tdah_routines"

    tools_service_url: str = "http://localhost:8002"
    agent_service_url: str = "http://localhost:8003"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"

    tick_interval_seconds: int = 300


settings = Settings()
