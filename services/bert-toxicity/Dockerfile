FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stesso principio del bert-sentiment: il modello si scarica al primo avvio
# e viene salvato nel volume bert-toxicity-cache:/app/.cache.
# Riavvii successivi usano la cache: build rapida, nessun download ripetuto.
ENV TRANSFORMERS_CACHE=/app/.cache/transformers
ENV HF_HUB_DISABLE_PROGRESS_BARS=1

COPY main.py .
EXPOSE 5003
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5003"]