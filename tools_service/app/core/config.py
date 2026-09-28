from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion del Tools Service, cargada desde variables de entorno / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    tools_service_port: int = 8002

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/tdah_auth"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "tdah_routines"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_maps_api_key: str = ""


settings = Settings()
