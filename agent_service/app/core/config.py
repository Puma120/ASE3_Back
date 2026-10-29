import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion del Agent Service, cargada desde variables de entorno / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_service_port: int = 8003

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "tdah_agent_memory"

    # MongoDB - lectura de activity_logs (misma BD que tools_service, ver
    # Objetivo 4 del PDF: analizar historial de rutinas para sugerencias proactivas)
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "tdah_routines"

    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-3.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"

    tools_service_url: str = "http://localhost:8002"
    auth_service_url: str = "http://localhost:8001"
    proactive_service_url: str = "http://localhost:8004"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"

    short_term_memory_window: int = 10
    # Compactacion: al pasar de este numero de mensajes sin resumir, los mas
    # viejos se funden en un resumen y solo la ventana reciente va literal.
    compaction_threshold: int = 30
    rag_top_k: int = 5
    # Similitud coseno minima para inyectar un fragmento; por debajo es ruido.
    # Calibrar con tests/kpi/eval_obj2.py contra gemini-embedding-001.
    rag_min_score: float = 0.5
    # Dias que se conserva un fragmento en Qdrant; 0 = nunca se purga.
    rag_retention_days: int = 0
    llm_temperature: float = 0.3
    # Gemini: reintentos con backoff exponencial ante 429 (cuota) y 5xx, y tope por
    # intento. 5 x 15 s + ~15 s de esperas cabe en el timeout de 90 s del gateway.
    llm_max_retries: int = 3
    # The SDK forwards this as X-Server-Timeout, so Gemini enforces it as a hard deadline (504).
    llm_timeout_seconds: float = 210.0
    # Tope de rondas LLM -> tools por mensaje (evita bucles).
    max_tool_rounds: int = 6

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
