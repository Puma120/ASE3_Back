"""El JWT del usuario no debe viajar en AgentState: LangGraph/LangSmith
registran el estado completo en las trazas. Va en una ContextVar."""

import asyncio
import uuid

from app.core import session
from app.graph import nodes
from app.graph.state import AgentState


def test_agent_state_no_declara_el_token():
    assert "bearer_token" not in AgentState.__annotations__


async def test_call_tool_envia_el_token_de_la_sesion(externos_falsos, monkeypatch):
    vistos: list[str] = []

    async def tool_que_registra(tool_name: str, payload: dict, bearer_token: str) -> dict:
        vistos.append(bearer_token)
        return {"items": []}

    monkeypatch.setattr(nodes, "invoke_tool", tool_que_registra)
    session.bearer_token.set("jwt-del-turno")

    estado = {
        "user_id": uuid.uuid4(),
        "pending_calls": [
            {"id": "1", "name": "list_tasks", "arguments": {}},
            {"id": "2", "name": "list_events", "arguments": {}},
        ],
    }
    resultado = await nodes.call_tool(estado)

    assert vistos == ["jwt-del-turno", "jwt-del-turno"]  # hereda dentro de asyncio.gather
    assert "jwt-del-turno" not in repr(resultado)  # tampoco se cuela al estado


async def test_el_token_no_se_mezcla_entre_peticiones_concurrentes(monkeypatch):
    vistos: dict[str, str] = {}

    async def tool_que_registra(tool_name: str, payload: dict, bearer_token: str) -> dict:
        await asyncio.sleep(0)  # cede el turno para entrelazar las dos peticiones
        vistos[payload["quien"]] = bearer_token
        return {"items": []}

    monkeypatch.setattr(nodes, "invoke_tool", tool_que_registra)

    async def peticion(quien: str):
        session.bearer_token.set(f"jwt-{quien}")
        await nodes.call_tool(
            {"pending_calls": [{"id": "1", "name": "list_tasks", "arguments": {"quien": quien}}]}
        )

    await asyncio.gather(asyncio.create_task(peticion("ana")), asyncio.create_task(peticion("beto")))
    assert vistos == {"ana": "jwt-ana", "beto": "jwt-beto"}


class _LlmFalso:
    """Primera ronda pide una tool; la segunda responde texto."""

    def __init__(self):
        self.llamadas = 0

    async def ainvoke(self, messages):
        from langchain_core.messages import AIMessage

        self.llamadas += 1
        if self.llamadas == 1:
            return AIMessage(content="", tool_calls=[{"id": "c1", "name": "list_tasks", "args": {}}])
        return AIMessage(content="Listo.")


async def test_chat_de_punta_a_punta_pasa_el_token_a_la_tool(client, auth_headers, monkeypatch):
    llm = _LlmFalso()
    monkeypatch.setattr(nodes, "_get_llm", lambda temperature, with_tools=True, client="": llm)
    vistos: list[str] = []

    async def tool_que_registra(tool_name: str, payload: dict, bearer_token: str) -> dict:
        vistos.append(bearer_token)
        return {"items": []}

    monkeypatch.setattr(nodes, "invoke_tool", tool_que_registra)

    headers = auth_headers(uuid.uuid4())
    respuesta = await client.post("/agent/chat", json={"message": "mis tareas"}, headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    assert vistos == [headers["Authorization"].removeprefix("Bearer ")]
