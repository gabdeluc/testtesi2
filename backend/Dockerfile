FROM python:3.11-slim

WORKDIR /app

# Installa curl per healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Installa dipendenze Python
COPY pyproject.toml ./
RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx pyyaml

# Copia codice
COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]