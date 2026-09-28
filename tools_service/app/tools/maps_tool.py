"""Tool: calculo de tiempo de traslado y notificacion de hora de salida
(combate time blindness).

Envuelve app/integrations/maps_client.py. No requiere OAuth por usuario
(Maps usa API key de app), asi que no toma `db`/`user_id` como los demas.
"""

from datetime import datetime, timedelta

from app.integrations import maps_client


async def get_prepare_by_time(
    origin: str,
    destination: str,
    event_start: datetime,
) -> tuple[timedelta, datetime]:
    """Devuelve (tiempo_de_traslado, hora_a_la_que_debe_empezar_a_prepararse)
    para llegar a tiempo a event_start."""
    travel_time = await maps_client.get_travel_time(origin, destination, event_start)
    prepare_by = event_start - travel_time
    return travel_time, prepare_by
