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
                    "focus": {
                        "type": "boolean",
                        "description": (
                            "true si la actividad exige concentracion sin interrupciones (estudiar, hacer tarea, "
                            "leer, escribir, trabajo profundo, meditar, examen); false en recados, citas, comidas, "
                            "llamadas, ejercicio o tareas ligeras. Con true la app activa No molestar en su horario."
                        ),
                    },
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
                    "focus": {
                        "type": "boolean",
                        "description": (
                            "true si la actividad exige concentracion sin interrupciones (estudiar, hacer tarea, "
                            "leer, escribir, trabajo profundo, meditar, examen); false en recados, citas, comidas, "
                            "llamadas, ejercicio o tareas ligeras. Con true la app activa No molestar en su horario."
                        ),
                    },
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
                    "fire_at": {
                        "type": "string",
                        "description": "ISO datetime, con zona horaria, en que debe sonar. Solo para horas concretas ('a las 6').",
                    },
                    "in_minutes": {
                        "type": "number",
                        "description": "Minutos desde ahora para tiempos relativos ('en 5 minutos', 'en media hora' = 30). Usalo en vez de fire_at; no calcules la hora tu.",
                    },
                    "title": {"type": "string"},
                },
                "required": ["message"],
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
            "name": "save_sleep_schedule",
            "description": (
                "Guarda a que hora despierta y a que hora duerme el usuario, entre semana y en fin de semana. "
                "Es lo que usa la app para no proponer huecos libres de madrugada. Puedes llamarla varias veces "
                "(se mezcla con lo anterior). Horas en formato 24 h HH:MM."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "wake_weekday": {"type": "string", "description": "Hora de despertar de lunes a viernes, HH:MM"},
                    "sleep_weekday": {"type": "string", "description": "Hora a la que se acuesta al terminar un dia de lunes a viernes, HH:MM"},
                    "wake_weekend": {"type": "string", "description": "Hora de despertar sabado y domingo, HH:MM"},
                    "sleep_weekend": {"type": "string", "description": "Hora a la que se acuesta al terminar un sabado o domingo, HH:MM (puede ser pasada la medianoche, p. ej. 01:00)"},
                },
                "required": [],
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

# Tools que un cliente no puede ejecutar: no se ofrecen al modelo. set_focus_mode
# solo existe en la app de Android con el modulo nativo (un APK anterior lo avisa).
# El cliente que no informa plataforma (APK viejo) conserva set_alarm.
_NOT_AVAILABLE = {
    "android": set(),
    "ios": {"set_alarm", "set_focus_mode"},
    "web": {"set_alarm", "set_focus_mode"},
}
_ALWAYS_OFF = {"set_focus_mode"}


def excluded_tools(client: str) -> frozenset[str]:
    return frozenset(_NOT_AVAILABLE.get(client, _ALWAYS_OFF))


def specs_for(client: str) -> list[dict]:
    off = excluded_tools(client)
    return [s for s in TOOL_SPECS if s["function"]["name"] not in off]


_COMMON_CAPS = (
    "- Calendario de Google (requiere Google conectado en Ajustes): find_free_slots, create_event "
    "(tambien recurrente), list_events.\n"
    "- Tareas y rutina: create_task, create_subtasks, list_tasks, complete_task, reschedule_task, "
    "get_routine_summary; ademas recuerdas la rutina fija que el usuario te conto.\n"
    "- Recordatorios con aviso a la hora: create_reminder, list_reminders.\n"
    "- Lugares y traslados (Google Maps): search_places, get_travel_time.\n"
    "- Correo (solo lectura, requiere Google): read_recent_emails.\n"
    "- Datos del usuario que ya tienes: nombre, jornada, hora y zona, y ubicacion si la hay; nunca "
    "credenciales ni contrasenas.\n"
)

CAPABILITIES = {
    "android": (
        "El usuario te escribe desde la APP DE ANDROID. Puedes:\n" + _COMMON_CAPS +
        "- Alarmas nativas del telefono: set_alarm.\n"
        "- No molestar automatico: al crear una tarea que exige concentracion (estudiar, tarea, leer, meditar) "
        "marca focus=true y la app lo activa sola en su horario y lo apaga al terminar (requiere el interruptor "
        "'Modo enfoque' de Ajustes y darle acceso a No molestar). Decide tu la clasificacion, sin preguntar; "
        "dile en una frase que se activara.\n"
        "- Modo No molestar manual: set_focus_mode (la primera vez Android pide al usuario darle acceso a la "
        "app; si el resultado lo indica, dile que lo active en la pantalla que se abrio y que te lo "
        "pida otra vez). Deja pasar alarmas y prioritarias.\n"
        "- Los avisos del telefono, la burbuja flotante del chat y la ubicacion GPS en el chat son "
        "ajustes del usuario (Ajustes de la app): tu no los activas; si los necesita, indicale donde.\n"
        "NO puedes: llamar, enviar mensajes o correos, pagar, ni controlar otras apps."
    ),
    "web": (
        "El usuario te escribe desde la PWA (navegador). Puedes:\n" + _COMMON_CAPS +
        "- La ubicacion del navegador solo llega si el usuario activo 'Usar mi ubicacion en el chat' "
        "en Ajustes y dio permiso; si no la tienes, preguntale la zona.\n"
        "NO puedes, porque el navegador no lo permite: crear alarmas (ofrece un recordatorio, o la "
        "app de Android si quiere alarmas) ni activar No molestar. Los avisos solo llegan si activo notificaciones en Ajustes; "
        "la burbuja de chat existe solo en la app de Android. Tampoco puedes llamar, enviar mensajes "
        "o correos, pagar, ni controlar otras apps."
    ),
    "ios": (
        "El usuario te escribe desde iOS. Puedes:\n" + _COMMON_CAPS +
        "NO puedes: crear alarmas, activar No molestar, burbuja de chat, llamar, enviar mensajes o "
        "correos, pagar, ni controlar otras apps."
    ),
}
_UNKNOWN_CAPS = (
    "No sabes desde que app te escribe el usuario. Puedes:\n" + _COMMON_CAPS +
    "- Alarmas (set_alarm) solo si el dispositivo las soporta: si falla, dilo.\n"
    "NO puedes: activar No molestar, llamar, enviar mensajes o correos, pagar, ni controlar otras apps."
)


def capabilities_for(client: str) -> str:
    return "Capacidades reales (solo existe lo de esta lista):\n" + CAPABILITIES.get(client, _UNKNOWN_CAPS)
