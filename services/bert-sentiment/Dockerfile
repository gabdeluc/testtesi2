FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# TRANSFORMERS_CACHE punta al volume Docker (bert-model-cache:/app/.cache).
# Il modello viene scaricato al primo avvio del container e salvato nel volume.
# Ai riavvii successivi HuggingFace lo trova già nella cache: nessun re-download.
# NON scaricare il modello qui a build-time: userebbe un layer temporaneo che
# verrebbe comunque nascosto dal volume mount a runtime.
ENV TRANSFORMERS_CACHE=/app/.cache/transformers
ENV HF_HUB_DISABLE_PROGRESS_BARS=1

COPY main.py .
EXPOSE 5001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001"]