# Imagen base ligera (Python 3.9)
FROM python:3.9-slim

# Dependencias del sistema para psycopg2 y Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Timeout largo para pip (evita que se corte en paquetes pesados)
ENV PIP_DEFAULT_TIMEOUT=600

# Primero solo dependencias → esta capa se cachea si requirements.txt no cambia
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Resto del código
COPY . .

# Puerto lo define Railway con $PORT
EXPOSE 8000

CMD ["sh", "-c", "gunicorn sistema_gonnet.wsgi --bind 0.0.0.0:${PORT:-8000} --workers=2 --threads=2 --timeout=120 --max-requests=1000 --max-requests-jitter=50 --log-file -"]
