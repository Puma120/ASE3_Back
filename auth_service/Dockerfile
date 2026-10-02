FROM python:3.12-slim

WORKDIR /app

# pip install directamente de las dependencias (sin build backend/packaging:
# el codigo se ejecuta via `uvicorn app.main:app` con /app en sys.path, no
# como paquete instalado).
RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic-settings>=2.6" \
    "pydantic[email]>=2.9" \
    "sqlalchemy[asyncio]>=2.0" "asyncpg>=0.30" "alembic>=1.14" "pyjwt>=2.9" \
    "passlib[bcrypt]>=1.7" "bcrypt<4.1" "httpx>=0.27" "tzdata>=2024.1"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
