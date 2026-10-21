"""Cliente de bajo nivel para Google Maps (Routes API y Places API New).

Usado por app/tools/maps_tool.py para calcular tiempo de traslado y avisar al
usuario a que hora debe empezar a prepararse para su proximo evento (PDF:
"combatiendo la dificultad para estimar tiempos" en TDAH).

A diferencia de Calendar/Tasks/Gmail, Maps se llama con una API key a nivel
de app (settings.google_maps_api_key), no con OAuth por usuario - por eso
estas funciones no reciben `credentials`.
"""

from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def _waypoint(value: str) -> dict:
    """'lat,lng' -> coordenadas; cualquier otra cosa se manda como direccion."""
    parts = [p.strip() for p in value.split(",")]
    if len(parts) == 2:
        try:
            return {"location": {"latLng": {"latitude": float(parts[0]), "longitude": float(parts[1])}}}
        except ValueError:
            pass
    return {"address": value}


async def get_travel_time(
    origin: str,
    destination: str,
    departure_time: datetime | None = None,
) -> timedelta:
    """Devuelve el tiempo de traslado estimado en auto (con trafico si
    departure_time es futuro) entre origin y destination (Routes API)."""
    body: dict = {
        "origin": _waypoint(origin),
        "destination": _waypoint(destination),
        "travelMode": "DRIVE",
    }
    # Routes rechaza departureTime en el pasado: sin el, usa el trafico actual.
    if departure_time is not None and departure_time > datetime.now(timezone.utc):
        body["routingPreference"] = "TRAFFIC_AWARE"
        body["departureTime"] = departure_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"X-Goog-Api-Key": settings.google_maps_api_key, "X-Goog-FieldMask": "routes.duration"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(ROUTES_URL, json=body, headers=headers)
    if response.status_code >= 400:
        try:
            message = response.json()["error"]["message"]
        except Exception:
            message = response.text[:200]
        raise ValueError(f"Routes API rechazo la consulta ({response.status_code}): {message}")
    routes = response.json().get("routes")
    if not routes:
        raise ValueError("Routes API no encontro una ruta entre origen y destino")
    return timedelta(seconds=int(routes[0]["duration"].rstrip("s")))


PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELDS = ",".join(
    f"places.{f}"
    for f in (
        "displayName",
        "formattedAddress",
        "location",
        "businessStatus",
        "regularOpeningHours",
        "currentOpeningHours.openNow",
        "utcOffsetMinutes",
    )
)


async def search_places(
    query: str,
    lat: float | None = None,
    lng: float | None = None,
    max_results: int = 3,
) -> list[dict]:
    """Busca lugares reales (Places API New, Text Search). Con lat/lng sesga los
    resultados a ~15 km a la redonda; sin ellos busca sin sesgo."""
    body: dict = {"textQuery": query, "languageCode": "es", "maxResultCount": max_results}
    if lat is not None and lng is not None:
        body["locationBias"] = {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 15000.0}
        }
    headers = {"X-Goog-Api-Key": settings.google_maps_api_key, "X-Goog-FieldMask": PLACES_FIELDS}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(PLACES_URL, json=body, headers=headers)
    if response.status_code >= 400:
        try:
            message = response.json()["error"]["message"]
        except Exception:
            message = response.text[:200]
        raise ValueError(f"Places API rechazo la consulta ({response.status_code}): {message}")
    return response.json().get("places", [])
