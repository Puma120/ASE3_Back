"""Grafo LangGraph del agente conversacional.

nodes.py    - nodos individuales del grafo (retrieve_context, call_llm,
              decide_tool_call, call_tool, generate_suggestion, ...).
edges.py    - logica de transicion condicional entre nodos.
builder.py  - ensambla nodes.py + edges.py en el StateGraph compilado.
state.py    - definicion del estado compartido (TypedDict) que fluye por el grafo.
"""
