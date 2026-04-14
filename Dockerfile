# Imagen oficial de Python (Docker Hub), sin mise ni descargas desde GitHub releases.
# Útil cuando el build con Nixpacks/mise falla con 502 al bajar cpython desde GitHub.
FROM python:3.9-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

# PORT lo inyectan Railway, Fly, Coolify, etc.
CMD ["sh", "-c", "gunicorn sistema_gonnet.wsgi --bind 0.0.0.0:${PORT:-8000} --workers=2 --threads=2 --timeout=120 --max-requests=1000 --max-requests-jitter=50 --log-file -"]
