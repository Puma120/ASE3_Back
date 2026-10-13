"""Token de sesion del usuario del turno actual.

Va en una ContextVar y no en AgentState: LangGraph/LangSmith registran el
estado completo como entrada de cada nodo, asi que un JWT ahi quedaria
guardado en las trazas. La ContextVar se hereda en las tareas de asyncio
(asyncio.gather, nodos del grafo) y no se traza.
"""

from contextvars import ContextVar

bearer_token: ContextVar[str] = ContextVar("bearer_token", default="")
