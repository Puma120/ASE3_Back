# Agent Service

Nucleo conversacional del sistema. Orquesta el flujo de IA con **LangGraph**,
recupera contexto via RAG desde **Qdrant** (BD Vectorial) y llama a
`tools_service` para ejecutar acciones. Conexion a proveedor LLM externo
(OpenAI o Gemini, configurable via `LLM_PROVIDER`).

## Responsabilidades

* Recuperacion Aumentada (RAG) sobre el historial/contexto del usuario (Qdrant).
* Memoria a corto plazo acotada por ventana de sesion (evita saturar el contexto).
* Orquestacion del grafo conversacional (LangGraph): decidir cuando invocar una
  tool, cuando generar una sugerencia proactiva, cuando responder directo.
* Streaming del razonamiento en tiempo real durante la conversacion (antecedente
  directo: agente "Nova" del equipo, Cap. 2.1.3 del PDF de tesina).

## Estructura

```
app/
  core/       # config
  memory/     # vector_store.py (Qdrant/RAG), short_term.py (ventana de sesion)
  graph/      # state.py, nodes.py, edges.py, builder.py (LangGraph)
  clients/    # cliente HTTP hacia tools_service
  schemas/    # Pydantic request/response (chat, streaming)
  api/routes/ # endpoint /chat
tests/
```

## Estado

Esqueleto inicial, grafo sin implementar todavia.

## Correr localmente (cuando este implementado)

```bash
pip install -e .
uvicorn app.main:app --reload --port 8003
```

## Pruebas

Todo vive en `tests/` (la imagen de Docker solo copia `app/`). Las pruebas
nunca llaman a Gemini ni a Railway: Mongo y Qdrant corren en memoria y el
modelo es local (Ollama).

```bash
pip install -e ".[dev]"
python -m pytest                 # unitarias, sin red (~1 s)
python -m pytest -m ollama -v    # integracion con qwen3.8 y qwen3-embedding:0.6b (~1 min)

# KPIs del Objetivo 2 (latencia, tokens y tasa de acierto hit@k de la recuperacion) y
# exactitud de respuesta del agente. Para latencia representativa:
# docker compose up -d qdrant
python -m tests.kpi.eval_obj2 --top-k 1,3,5 [--embeddings gemini] [--sin-respuestas]
```

La corrida completa tarda unas 1.5-2.5 h; la mayor parte es la exactitud de
respuesta (qwen3.8 responde las 220 consultas por cada top_k). Con
`--sin-respuestas` baja a unos 15-20 min. El reporte (Markdown, JSON con cada
respuesta calificada y tablas LaTeX) queda en `tests/kpi/resultados/`.
