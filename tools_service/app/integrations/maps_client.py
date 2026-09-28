"""Cliente de bajo nivel para Google Maps Distance Matrix API.

Usado por app/tools/maps_tool.py para calcular tiempo de traslado y avisar al
usuario a que hora debe empezar a prepararse para su proximo evento (PDF:
"combatiendo la dificultad para estimar tiempos" en TDAH).

A diferencia de Calendar/Tasks/Gmail, Maps se llama con una API key a nivel
de app (settings.google_maps_api_key), no con OAuth por usuario - por eso
estas funciones no reciben `credentials`.
"""

from datetime import datetime, timedelta

import httpx

from app.core.config import settings

DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


async def get_travel_time(
    origin: str,
    destination: str,
    departure_time: datetime | None = None,
) -> timedelta:
    """Devuelve el tiempo de traslado estimado (con trafico si hay
    departure_time) entre origin y destination."""
    params = {
        "origins": origin,
        "destinations": destination,
        "key": settings.google_maps_api_key,
    }
    if departure_time is not None:
        params["departure_time"] = str(int(departure_time.timestamp()))

    async with httpx.AsyncClient() as client:
        response = await client.get(DISTANCE_MATRIX_URL, params=params)
        response.raise_for_status()
        data = response.json()

    element = data["rows"][0]["elements"][0]
    if element["status"] != "OK":
        raise ValueError(f"Distance Matrix no pudo calcular la ruta: {element['status']}")

    duration_seconds = element.get("duration_in_traffic", element["duration"])["value"]
    return timedelta(seconds=duration_seconds)
