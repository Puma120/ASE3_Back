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
                    "window_start": {"type": "string", "description": "ISO datetime con offset de inicio de la ventana"},
                    "window_end": {"type": "string", "description": "ISO datetime con offset de fin de la ventana"},
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
            "description": (
                "Crea un evento en el calendario del usuario (agendado proactivo). Para un horario que "
                "se repite cada semana (clases, trabajo, gimnasio) manda weekdays + until + timezone: "
                "crea UN evento recurrente, no uno por dia."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "start": {"type": "string", "description": "ISO datetime con offset de inicio (de la primera ocurrencia)"},
                    "end": {"type": "string", "description": "ISO datetime con offset de fin (misma fecha que start)"},
                    "description": {"type": "string"},
                    "weekdays": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]},
                        "description": "Dias de la semana en que se repite (solo eventos recurrentes)",
                    },
                    "until": {"type": "string", "description": "Ultimo dia en que se repite, YYYY-MM-DD (obligatorio si es recurrente)"},
                    "timezone": {"type": "string", "description": "Zona IANA del usuario (obligatorio si es recurrente)"},
                },
                "required": ["summary", "start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": (
                "Crea una tarea contra calendario: queda en Google Tasks y bloquea start-end en el "
                "calendario. TODA tarea necesita inicio y fin; si el usuario no los dio, elige un "
                "hueco con find_free_slots antes de crearla. Si llega a su fin sin completarse, "
                "la app le pregunta si la reagenda."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "notes": {"type": "string"},
                    "start": {"type": "string", "description": "ISO datetime con offset de cuando empieza"},
                    "end": {"type": "string", "description": "ISO datetime con offset de cuando debe terminar"},
                },
                "required": ["title", "start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_subtasks",
            "description": "Subdivide una tarea grande/abrumadora en subtareas accionables mas pequenas. El conjunto lleva su ventana start-end en el calendario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_title": {"type": "string"},
                    "subtasks": {"type": "array", "items": {"type": "string"}},
                    "start": {"type": "string", "description": "ISO datetime con offset de cuando empieza el conjunto"},
                    "end": {"type": "string", "description": "ISO datetime con offset de cuando debe quedar terminado"},
                },
                "required": ["parent_title", "subtasks", "start", "end"],
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
                    "event_start": {"type": "string", "description": "ISO datetime con offset del evento destino"},
                },
                "required": ["origin", "destination", "event_start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_places",
            "description": "Busca lugares REALES (direccion, horario semanal, si estan abiertos) cerca del usuario con Google Maps. Usala siempre que pregunten donde ir a hacer algo, o a que hora abre/cierra un lugar; nunca inventes lugares ni horarios.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Que buscar, p. ej. 'modulo de pago CFE' o 'farmacia 24 horas'"},
                    "lat": {"type": "number", "description": "Latitud de la ubicacion del usuario, si la conoces"},
                    "lng": {"type": "number", "description": "Longitud de la ubicacion del usuario, si la conoces"},
                    "at": {"type": "string", "description": "ISO datetime con offset de cuando planea llegar; la tool indica si el lugar estara abierto a esa hora"},
                },
                "required": ["query"],
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
            "name": "reschedule_task",
            "description": (
                "Mueve una tarea (y su bloque de calendario) a una nueva ventana start-end. "
                "Usala cuando el usuario acepta reagendar una tarea vencida o pide cambiarla de hora. "
                "Usa el id que devolvio list_tasks y busca antes un hueco con find_free_slots."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "start": {"type": "string", "description": "ISO datetime con offset del nuevo inicio"},
                    "end": {"type": "string", "description": "ISO datetime con offset del nuevo fin"},
                },
                "required": ["task_id", "start", "end"],
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
            "name": "save_routine_fact",
            "description": (
                "Guarda en tu memoria un dato fijo de la rutina del usuario (hora de despertar, horario de "
                "clases o trabajo, horas ocupadas, habitos) para recordarlo todo el tiempo que el diga. "
                "Mismo key = reemplaza el dato anterior."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Nombre corto y estable, p. ej. despertar_entre_semana, clases, gimnasio"},
                    "text": {"type": "string", "description": "El dato completo con dias y horas, p. ej. 'Lunes a viernes 8:00-14:00 clases'"},
                    "until": {"type": "string", "description": "YYYY-MM-DD hasta cuando es valido el dato; omitelo si no caduca"},
                },
                "required": ["key", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_onboarding",
            "description": "Cierra la configuracion inicial de la rutina. Solo al terminar todas las preguntas y haber resumido lo guardado.",
            "parameters": {"type": "object", "properties": {}, "required": []},
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
