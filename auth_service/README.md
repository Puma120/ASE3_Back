# Auth Service

Microservicio de Autenticacion y configuracion. Maneja login, JWT/OAuth, perfil de
usuario y credenciales. Conecta a **PostgreSQL** (BD SQL de usuarios/metadata segun
la Capa de Persistencia del diagrama de arquitectura).

## Responsabilidades

* Registro / login (password y, opcionalmente, OAuth Google).
* Emision y verificacion de JWT de sesion (el `JWT_SECRET_KEY` debe coincidir con el
  que usa `gateway` para validar sesiones localmente).
* Perfil y configuracion del usuario (`/users/me`, `/users/me/settings`).

## Estructura

```
app/
  core/       # config, seguridad (hashing, JWT)
  db/         # sesion SQLAlchemy async
  models/     # tablas ORM (User, UserProfile, UserSettings)
  schemas/    # Pydantic request/response
  services/   # logica de negocio
  api/routes/ # endpoints FastAPI
alembic/      # migraciones (pendiente de inicializar)
tests/
```

## Estado

Esqueleto inicial, sin modelos/endpoints implementados todavia.

## Correr localmente (cuando este implementado)

```bash
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```
