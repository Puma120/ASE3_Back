from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion del Proactive Service, cargada desde variables de entorno / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    proactive_service_port: int = 8004

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "tdah_routines"

    auth_service_url: str = "http://localhost:8001"
    tools_service_url: str = "http://localhost:8002"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"

    # Tick silencioso: cada cuantos segundos se evalua a cada usuario activo.
    tick_interval_seconds: int = 120
    tick_enabled: bool = True

    # Alertas de salida: avisar `prepare_lead_minutes` antes de la hora de
    # salida, con `leave_buffer_minutes` de colchon sobre el traslado.
    prepare_lead_minutes: int = 15
    leave_buffer_minutes: int = 5
    # Solo se calcula la ruta de eventos que empiezan dentro de esta ventana.
    travel_lookahead_minutes: int = 180
    # Ubicacion mas vieja que esto se ignora para estimar el traslado.
    location_max_age_minutes: int = 180

    # Firebase Cloud Messaging (HTTP v1). Vacio = push deshabilitado: las
    # notificaciones igual se guardan y se leen por /proactive/notifications.
    fcm_project_id: str = ""
    fcm_service_account_json: str = ""


settings = Settings()
