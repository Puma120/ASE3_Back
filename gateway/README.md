# Gateway

Punto unico de entrada del backend. Valida la sesion (JWT emitido por `auth_service`)
y enruta las peticiones hacia el microservicio correspondiente (`auth_service`,
`tools_service`, `agent_service`), segun la Figura 3.1 de la arquitectura.

## Responsabilidades

* Autenticacion/validacion de sesion antes de reenviar a servicios internos.
* Enrutamiento (proxy) hacia `auth_service`, `tools_service`, `agent_service`.
* Punto de observabilidad centralizado (logs/metricas de entrada) — no implementado aun.

## Estado

Esqueleto inicial. `app/api/router.py` y `app/middleware/session.py` tienen la
estructura pero el proxy real hacia los microservicios (via `httpx`) esta pendiente
de implementar una vez que los endpoints de cada servicio queden definidos.

## Correr localmente (cuando este implementado)

```bash
pip install -e .
uvicorn app.main:app --reload --port 8000
```
