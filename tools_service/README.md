# Tools Service

Microservicio de herramientas. El Microservicio del Agente lo invoca para ejecutar
acciones concretas en nombre del usuario. Conecta a **PostgreSQL** (datos
relacionales compartidos) y **MongoDB** (rutinas y registros, BD NoSQL segun la
Capa de Persistencia del diagrama de arquitectura).

## Responsabilidades

Tools especificas para TDAH (ver `implementation_plan.md` / PDF de tesina):

* **`calendar_tool`** — agendado proactivo de eventos en espacios libres (Google Calendar API).
* **`tasks_tool`** — subdivision de tareas grandes en subtareas accionables (Google Tasks API).
* **`maps_tool`** — calculo de tiempo de traslado, combate time blindness (Google Maps API).
* **`gmail_tool`** — lectura/resumen de correos largos, extraccion de acciones (Gmail API).
* **`device_tool`** — comandos hacia el dispositivo (alarmas nativas, DND). No llama una API
  externa: el comando se reenvia al frontend `front/mobile`. DND solo disponible en Android
  (limitacion de plataforma iOS, ver `.antigravity/project_map.md`).

## Estructura

```
app/
  core/         # config
  db/           # clientes Postgres (asyncpg) y MongoDB (motor)
  models/       # modelos de datos
  schemas/      # Pydantic request/response por tool
  integrations/ # clientes de bajo nivel por API de Google (1 archivo por servicio)
  tools/        # logica de negocio de cada tool (envuelve integrations/)
  api/routes/   # endpoints FastAPI expuestos al agent_service
tests/
```

## Estado

Esqueleto inicial, sin tools implementadas todavia.

## Correr localmente (cuando este implementado)

```bash
pip install -e .
uvicorn app.main:app --reload --port 8002
```
