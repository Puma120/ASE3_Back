"""Aislamiento de pruebas y evaluaciones respecto de produccion (Railway).

configurar_entorno() se llama ANTES de importar `app`: las variables de
entorno tienen prioridad sobre agent_service/.env, asi que ninguna prueba usa
las credenciales ni las bases reales. verificar_entorno() se llama despues,
sobre los settings ya cargados, como segunda barrera.
"""

import os

COLECCION_PRODUCCION = "tdah_agent_memory"
_MARCAS_REMOTAS = ("railway", "rlwy", "mongodb.net", "cloud.qdrant.io")

# Lo que build_user_context armaria para un usuario tipico; fijo para que las
# pruebas no dependan de auth_service/proactive_service ni de la hora real.
CONTEXTO_USUARIO_FIJO = (
    "Fecha y hora actuales del usuario: lunes 2026-10-05T09:00-06:00 "
    "(zona horaria America/Mexico_City). Usa SIEMPRE esta zona para fechas relativas "
    "como 'manana' o 'a las 5', y manda los datetime ISO con su offset.\n"
    "Nombre del usuario: Ana.\n"
    "Jornada: 9:00 a 18:00. No agendes cosas proactivas fuera de ese horario.\n"
    "Ubicacion actual: desconocida. Si necesitas un origen, preguntalo."
)


def configurar_entorno(
    coleccion: str, qdrant_url: str = "http://localhost:6333", conservar_gemini: bool = False
) -> None:
    """Apunta el servicio a recursos locales. Con conservar_gemini=False la
    API key queda vacia: una llamada accidental a Gemini falla en vez de cobrar."""
    valores = {
        "QDRANT_URL": qdrant_url,
        "QDRANT_COLLECTION_NAME": coleccion,
        "MONGO_URI": "mongodb://localhost:27017",
        "MONGO_DB_NAME": "tdah_routines_test",
        "JWT_SECRET_KEY": "secreto-local-de-pruebas-no-es-produccion",
        "JWT_ALGORITHM": "HS256",
        "TOOLS_SERVICE_URL": "http://localhost:8002",
        "AUTH_SERVICE_URL": "http://localhost:8001",
        "PROACTIVE_SERVICE_URL": "http://localhost:8004",
        # Defaults de config.py, explicitos para no heredar valores del .env local.
        "SHORT_TERM_MEMORY_WINDOW": "10",
        "RAG_TOP_K": "5",
        "LLM_TEMPERATURE": "0.3",
        "MAX_TOOL_ROUNDS": "6",
    }
    if not conservar_gemini:
        valores["GEMINI_API_KEY"] = ""
    os.environ.update(valores)


def verificar_entorno(settings) -> None:
    urls = [
        settings.qdrant_url,
        settings.mongo_uri,
        settings.tools_service_url,
        settings.auth_service_url,
        settings.proactive_service_url,
    ]
    remotas = [url for url in urls if any(marca in url.lower() for marca in _MARCAS_REMOTAS)]
    if remotas:
        raise RuntimeError(f"Las pruebas no deben apuntar a servicios remotos: {remotas}")
    if settings.qdrant_collection_name == COLECCION_PRODUCCION:
        raise RuntimeError(f"Las pruebas no deben usar la coleccion de produccion '{COLECCION_PRODUCCION}'")
