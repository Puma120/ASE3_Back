FROM python:3.12-slim

WORKDIR /app

# pip install directamente de las dependencias (sin build backend/packaging:
# el codigo se ejecuta via `uvicorn app.main:app` con /app en sys.path, no
# como paquete instalado).
RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic-settings>=2.6" \
    "sqlalchemy[asyncio]>=2.0" "asyncpg>=0.30" "motor>=3.6" \
    "google-api-python-client>=2.150" "google-auth-oauthlib>=1.2" \
    "httpx>=0.27" "pyjwt>=2.9"

COPY app ./app

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
