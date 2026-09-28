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
