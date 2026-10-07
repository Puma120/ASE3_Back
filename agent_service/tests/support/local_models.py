"""Modelos locales (Ollama) para pruebas y evaluacion de KPIs sin gastar en
Gemini. Vive en tests/ (no en app/) para que la imagen de produccion, que
solo copia app/, quede identica a la que corre en Railway.

Configurable con OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, OLLAMA_EMBEDDING_MODEL y
OLLAMA_EMBEDDING_SIZE.
"""

import os

import httpx
from langchain_ollama import ChatOllama, OllamaEmbeddings

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen3.8")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
OLLAMA_EMBEDDING_SIZE = int(os.getenv("OLLAMA_EMBEDDING_SIZE", "1024"))


def _con_tag(modelo: str) -> str:
    return modelo if ":" in modelo else f"{modelo}:latest"


def motivo_no_disponible(*modelos: str) -> str | None:
    """None si Ollama responde y tiene los modelos; si no, el motivo (para skip)."""
    try:
        respuesta = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        respuesta.raise_for_status()
    except httpx.HTTPError:
        return f"Ollama no responde en {OLLAMA_BASE_URL}"
    instalados = {m["name"] for m in respuesta.json().get("models", [])}
    faltan = [m for m in modelos if _con_tag(m) not in instalados]
    if faltan:
        return "Faltan modelos en Ollama: " + ", ".join(faltan) + " (usa `ollama pull <modelo>`)"
    return None


def build_chat_model(temperature: float, **kwargs) -> ChatOllama:
    # Sin razonamiento: qwen3.x piensa por defecto y eso solo agrega latencia.
    return ChatOllama(
        model=OLLAMA_CHAT_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
        reasoning=False,
        **kwargs,
    )


def get_llm_local():
    """Reemplazo de app.graph.nodes._get_llm: el modelo local con las tools del
    agente. Temperatura 0 sin importar el parametro: respuestas reproducibles."""
    from app.graph.tool_specs import TOOL_SPECS

    modelos = {}

    def get_llm(temperature: float, with_tools: bool = True):
        if with_tools not in modelos:
            llm = build_chat_model(temperature=0.0)
            modelos[with_tools] = llm.bind_tools(TOOL_SPECS) if with_tools else llm
        return modelos[with_tools]

    return get_llm


def build_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)


class ContadorTokens:
    """Cuenta tokens con el tokenizer del modelo local (prompt_eval_count de
    Ollama). Es una aproximacion del consumo en Gemini: los tokenizers difieren."""

    def __init__(self) -> None:
        self._llm = build_chat_model(temperature=0.0, num_predict=1)

    async def prompt(self, messages: list) -> int:
        respuesta = await self._llm.ainvoke(messages)
        return respuesta.usage_metadata["input_tokens"]

    async def embedding(self, texto: str) -> int:
        async with httpx.AsyncClient(base_url=OLLAMA_BASE_URL, timeout=120) as client:
            respuesta = await client.post("/api/embed", json={"model": OLLAMA_EMBEDDING_MODEL, "input": texto})
            respuesta.raise_for_status()
            return respuesta.json()["prompt_eval_count"]
