"""Definiciones de tools (formato OpenAI function-calling, compatible con
ChatGoogleGenerativeAI.bind_tools) para que Gemini decida cuando invocar
cada una. Los nombres deben coincidir con app/clients/tools_client.py:TOOL_ROUTES.
"""

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "find_free_slots",
            "description": "Busca huecos libres en el calendario del usuario dentro de una ventana de tiempo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "window_start": {"type": "string", "description": "ISO datetime de inicio de la ventana"},
                    "window_end": {"type": "string", "description": "ISO datetime de fin de la ventana"},
                    "duration_minutes": {"type": "integer", "description": "Duracion minima del hueco en minutos"},
                },
                "required": ["window_start", "window_end", "duration_minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Crea un evento en el calendario del usuario (agendado proactivo).",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "start": {"type": "string", "description": "ISO datetime de inicio"},
                    "end": {"type": "string", "description": "ISO datetime de fin"},
                    "description": {"type": "string"},
                },
                "required": ["summary", "start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Crea una tarea simple en Google Tasks. Con due queda fechada (la hora se guarda en las notas).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "notes": {"type": "string"},
                    "due": {
                        "type": "string",
                        "description": "ISO datetime con offset de la fecha/hora limite (opcional)",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_subtasks",
            "description": "Subdivide una tarea grande/abrumadora en subtareas accionables mas pequenas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_title": {"type": "string"},
                    "subtasks": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["parent_title", "subtasks"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_travel_time",
            "description": "Calcula el tiempo de traslado hacia un evento y a que hora debe salir el usuario (combate time blindness).",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Direccion o coordenadas lat,lng (usa la ubicacion actual del usuario si la conoces)"},
                    "destination": {"type": "string"},
                    "event_start": {"type": "string", "description": "ISO datetime del evento destino"},
                },
                "required": ["origin", "destination", "event_start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_recent_emails",
            "description": "Lee los correos mas recientes de la bandeja de entrada del usuario para resumirlos o extraer pendientes.",
            "parameters": {
                "type": "object",
                "properties": {"max_results": {"type": "integer"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "Programa una alarma nativa en el dispositivo del usuario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time": {"type": "string", "description": "ISO datetime de la alarma"},
                    "label": {"type": "string"},
                },
                "required": ["time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_focus_mode",
            "description": "Activa o desactiva el modo No Molestar del dispositivo (solo Android).",
            "parameters": {
                "type": "object",
                "properties": {"enabled": {"type": "boolean"}},
                "required": ["enabled"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_events",
            "description": "Lista los eventos del calendario del usuario en una ventana de tiempo (para saber que tiene hoy, manana o esta semana).",
            "parameters": {
                "type": "object",
                "properties": {
                    "window_start": {"type": "string", "description": "ISO datetime de inicio, con zona horaria"},
                    "window_end": {"type": "string", "description": "ISO datetime de fin, con zona horaria"},
                },
                "required": ["window_start", "window_end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Lista las tareas pendientes del usuario en Google Tasks.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Marca una tarea como completada. Usa el id que devolvio list_tasks.",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_routine_summary",
            "description": "Resumen de la rutina del usuario: racha de dias activos y tareas/eventos de los ultimos 7 dias. Sirve para revisar como le va y adaptar sugerencias.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Programa una notificacion push inteligente para el usuario a una hora concreta (recordatorio, preparacion, tomar algo, salir).",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Texto breve y accionable de la notificacion"},
                    "fire_at": {"type": "string", "description": "ISO datetime, con zona horaria, en que debe sonar"},
                    "title": {"type": "string"},
                },
                "required": ["message", "fire_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "Lista los recordatorios pendientes que ya estan programados para el usuario.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
