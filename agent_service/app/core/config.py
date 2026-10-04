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
    rag_top_k: int = 5
    llm_temperature: float = 0.3
    # Tope de rondas LLM -> tools por mensaje (evita bucles).
    max_tool_rounds: int = 6


settings = Settings()
