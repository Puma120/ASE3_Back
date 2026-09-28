from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion del Auth Service, cargada desde variables de entorno / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    auth_service_port: int = 8001

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/tdah_auth"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""


settings = Settings()
