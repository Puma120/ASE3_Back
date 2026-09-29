"""Cliente HTTP async hacia tools_service, usado por app/graph/nodes.py para
invocar tools durante la ejecucion del grafo.

Reenvia el mismo Bearer token de sesion que llego al /chat del agente, para
que tools_service pueda identificar al usuario igual que si lo llamara el
gateway directamente.
"""

import httpx

from app.core.config import settings

# tool_name -> (metodo, path)
TOOL_ROUTES = {
    "find_free_slots": ("POST", "/tools/calendar/free-slots"),
    "create_event": ("POST", "/tools/calendar/events"),
    "create_task": ("POST", "/tools/tasks"),
    "create_subtasks": ("POST", "/tools/tasks/subtasks"),
    "get_travel_time": ("POST", "/tools/maps/travel-time"),
    "read_recent_emails": ("POST", "/tools/gmail/recent-emails"),
    "set_alarm": ("POST", "/tools/device/alarm"),
    "set_focus_mode": ("POST", "/tools/device/focus-mode"),
}


async def call_tool(tool_name: str, payload: dict, bearer_token: str) -> dict:
    if tool_name not in TOOL_ROUTES:
        return {"error": f"Tool desconocida: {tool_name}"}
    method, path = TOOL_ROUTES[tool_name]
    async with httpx.AsyncClient(base_url=settings.tools_service_url, timeout=30.0) as client:
        try:
            response = await client.request(
                method, path, json=payload, headers={"Authorization": f"Bearer {bearer_token}"}
            )
            if response.status_code >= 400:
                detail = response.text
                try:
                    detail = response.json().get("detail", detail)
                except Exception:
                    pass
                return {"error": f"Error al ejecutar {tool_name}: {detail}"}
            return response.json()
        except Exception as exc:
            return {"error": f"No se pudo conectar con el servicio de herramientas: {str(exc)}"}

