FROM python:3.12-slim

WORKDIR /app

# pip install directamente de las dependencias (sin build backend/packaging:
# el codigo se ejecuta via `uvicorn app.main:app` con /app en sys.path, no
# como paquete instalado).
RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic-settings>=2.6" \
    "httpx>=0.27" "pyjwt>=2.9"

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
