"""Cliente HTTP async hacia los servicios que el agente usa como herramientas
(tools_service y proactive_service), invocado por app/graph/nodes.py.

Reenvia el mismo Bearer token de sesion que llego al /chat del agente, para
que el servicio destino identifique al usuario igual que si lo llamara el
gateway directamente.
"""

import httpx

from app.core.config import settings

# tool_name -> (servicio, metodo, path). Los {placeholders} del path se
# rellenan con argumentos de la tool; el resto va en query (GET) o JSON.
TOOL_ROUTES = {
    "find_free_slots": ("tools", "POST", "/tools/calendar/free-slots"),
    "create_event": ("tools", "POST", "/tools/calendar/events"),
    "list_events": ("tools", "GET", "/tools/calendar/events"),
    "create_task": ("tools", "POST", "/tools/tasks"),
    "create_subtasks": ("tools", "POST", "/tools/tasks/subtasks"),
    "list_tasks": ("tools", "GET", "/tools/tasks"),
    "complete_task": ("tools", "POST", "/tools/tasks/{task_id}/complete"),
    "get_routine_summary": ("tools", "GET", "/tools/routines/summary"),
    "get_travel_time": ("tools", "POST", "/tools/maps/travel-time"),
    "read_recent_emails": ("tools", "POST", "/tools/gmail/recent-emails"),
    "set_alarm": ("tools", "POST", "/tools/device/alarm"),
    "set_focus_mode": ("tools", "POST", "/tools/device/focus-mode"),
    "create_reminder": ("proactive", "POST", "/proactive/reminders"),
    "list_reminders": ("proactive", "GET", "/proactive/reminders"),
}

# Tools que cambian algo en la vida del usuario. Tras leer contenido no
# confiable (correos) quedan bloqueadas en ese turno: ver nodes.call_tool.
WRITE_TOOLS = {
    "create_event",
    "create_task",
    "create_subtasks",
    "complete_task",
    "set_alarm",
    "set_focus_mode",
    "create_reminder",
}

# Tools cuyo resultado contiene texto escrito por terceros.
UNTRUSTED_TOOLS = {"read_recent_emails"}

_BASES = {
    "tools": lambda: settings.tools_service_url,
    "proactive": lambda: settings.proactive_service_url,
}


async def call_tool(tool_name: str, payload: dict, bearer_token: str) -> dict:
    if tool_name not in TOOL_ROUTES:
        return {"error": f"Tool desconocida: {tool_name}"}
    service, method, path = TOOL_ROUTES[tool_name]
    payload = dict(payload or {})
    try:
        path = path.format(**{k: payload.pop(k) for k in _placeholders(path)})
    except KeyError as exc:
        return {"error": f"Falta el argumento {exc} para {tool_name}"}

    request_kwargs = {"params": payload} if method == "GET" else {"json": payload}
    async with httpx.AsyncClient(base_url=_BASES[service](), timeout=30.0) as client:
        try:
            response = await client.request(
                method, path, headers={"Authorization": f"Bearer {bearer_token}"}, **request_kwargs
            )
            if response.status_code >= 400:
                detail = response.text
                try:
                    detail = response.json().get("detail", detail)
                except Exception:
                    pass
                return {"error": f"Error al ejecutar {tool_name}: {detail}"}
            if response.status_code == 204 or not response.content:
                return {"ok": True}
            data = response.json()
            # Las tools de lista devuelven arrays; el LLM espera un objeto.
            return data if isinstance(data, dict) else {"items": data}
        except Exception as exc:
            return {"error": f"No se pudo conectar con el servicio de herramientas: {str(exc)}"}


def _placeholders(path: str) -> list[str]:
    return [part[1:-1] for part in path.split("/") if part.startswith("{") and part.endswith("}")]


async def fetch_json(service: str, path: str, bearer_token: str):
    """GET simple para armar el contexto del usuario; None si falla (el
    contexto es opcional, nunca debe tumbar el chat)."""
    try:
        async with httpx.AsyncClient(base_url=_service_base(service), timeout=8.0) as client:
            response = await client.get(path, headers={"Authorization": f"Bearer {bearer_token}"})
        return response.json() if response.status_code == 200 else None
    except Exception:
        return None


def _service_base(service: str) -> str:
    if service == "auth":
        return settings.auth_service_url
    return _BASES[service]()
