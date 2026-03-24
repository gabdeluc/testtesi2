# Meeting Intelligence

> Piattaforma di analisi automatica di riunioni in tempo reale basata su modelli BERT per sentiment analysis e rilevamento tossicità.

---

## Indice

1. [Panoramica del progetto](#1-panoramica-del-progetto)
2. [Architettura del sistema](#2-architettura-del-sistema)
3. [Prerequisiti](#3-prerequisiti)
4. [Struttura del repository](#4-struttura-del-repository)
5. [Setup locale (senza Docker)](#5-setup-locale-senza-docker)
6. [Avvio con Docker](#6-avvio-con-docker)
7. [Configurazione](#7-configurazione)
8. [API Reference](#8-api-reference)
9. [Testing](#9-testing)
10. [Integrazione con Arianna](#10-integrazione-con-arianna)
11. [Troubleshooting](#11-troubleshooting)
12. [Glossario tecnico](#12-glossario-tecnico)

---

## 1. Panoramica del progetto

Meeting Intelligence è un sistema distribuito che analizza le trascrizioni di riunioni in tempo reale. Ogni messaggio del transcript viene classificato su due dimensioni indipendenti:

- **Sentiment** — quanto è positivo, neutro o negativo il tono del messaggio (scala 1–5 stelle, normalizzata in `[−1, +1]`)
- **Tossicità** — se il messaggio contiene linguaggio offensivo o inappropriato (score `[0, 1]` con soglia a `0.5`)

Il sistema è stato progettato per integrarsi con la piattaforma **Arianna** (sistema di videoconferenza e trascrizione automatica), ma include un layer di dati mock che permette di sviluppare e testare in modo completamente autonomo, senza dipendere da Arianna.

### Cosa fa il sistema

1. Legge un transcript di riunione (real-time o storico)
2. Manda i testi ai microservizi BERT per l'analisi
3. Restituisce il transcript arricchito con metadati di sentiment e tossicità
4. Calcola statistiche aggregate (distribuzione etichette, polarity media, ratio tossicità)
5. Espone tutto via API REST al frontend React che visualizza la dashboard in tempo reale con playback simulato

---

## 2. Architettura del sistema

Il sistema segue un'architettura a **microservizi** con un gateway centrale. Ogni componente è containerizzato e comunicano tra loro via rete Docker interna.

```
┌─────────────────┐        HTTP         ┌──────────────────────┐
│                 │ ──────────────────► │                      │
│  Frontend React │                     │   Backend Gateway    │
│   (port 3000)   │ ◄────────────────── │    FastAPI (8000)    │
│                 │      JSON           │                      │
└─────────────────┘                     └──────────┬───────────┘
                                                   │
                              ┌────────────────────┼────────────────────┐
                              │                    │                    │
                              ▼                    ▼                    │
                   ┌─────────────────┐  ┌─────────────────┐            │
                   │  BERT Sentiment │  │  BERT Toxicity  │            │
                   │   (port 5001)   │  │   (port 5003)   │            │
                   │                 │  │                 │            │
                   │ nlptown/bert-   │  │ gravitee-io/    │            │
                   │ multilingual    │  │ bert-small-tox  │            │
                   └─────────────────┘  └─────────────────┘            │
                                                                        │
                                         ┌──────────────────────────┐  │
                                         │   Mock Data Layer        │◄─┘
                                         │   (config/mock_data.yaml)│
                                         │   In-memory dict         │
                                         └──────────────────────────┘
```

### Componenti

| Componente | Tecnologia | Porta | Responsabilità |
|---|---|---|---|
| **Frontend** | React 18 + Vite + Chart.js | 3000 | Dashboard interattiva con playback del meeting |
| **Backend Gateway** | FastAPI (Python 3.11) | 8000 | Routing, aggregazione, normalizzazione dati |
| **BERT Sentiment** | HuggingFace Transformers | 5001 | Classificazione 1–5 stelle del tono |
| **BERT Toxicity** | HuggingFace Transformers | 5003 | Classificazione binaria tossicità |

### Pattern architetturali utilizzati

**Gateway Pattern** — il backend è l'unico punto di ingresso per il frontend. Aggrega le risposte dei due microservizi BERT in un'unica risposta arricchita, in modo che il frontend non debba conoscere i microservizi interni.

**Abstract Predictor Pattern** — `models/predictor.py` definisce una classe astratta `ModelPredictor` che normalizza output eterogenei (stelle BERT → label positivo/neutro/negativo). Aggiungere un nuovo modello di sentiment richiede solo implementare `_raw_predict()` e `_normalize_output()`.

**Mock Fallback** — se i microservizi BERT non sono raggiungibili (es. sviluppo locale senza Docker), il gateway attiva automaticamente un classificatore rule-based basato su keyword. Questo permette di sviluppare il frontend e testare la logica di business senza GPU o container pesanti.

**Singleton** — ogni microservizio BERT carica il modello una sola volta in memoria al boot (`BERTSentimentModel._instance`). Le richieste successive condividono la stessa istanza, evitando reload costosi (~500 MB per il modello sentiment).

---

## 3. Prerequisiti

### Software richiesto

| Software | Versione minima | Verifica |
|---|---|---|
| Docker Desktop | 24.x | `docker --version` |
| Docker Compose | 2.x (incluso in Docker Desktop) | `docker compose version` |
| Git | qualsiasi | `git --version` |

> **Nota per Windows**: assicurarsi che WSL 2 sia abilitato e che Docker Desktop utilizzi il backend WSL 2. Verificare in *Settings → General → Use WSL 2 based engine*.

### Per lo sviluppo locale (senza Docker)

| Software | Versione | Note |
|---|---|---|
| Python | 3.11+ | Versioni precedenti non supportate (uso di `match/case` e `tomllib`) |
| Node.js | 20 LTS | Richiesto dal frontend |
| pip | ultima versione | `pip install --upgrade pip` |

### Risorse hardware

| Configurazione | RAM minima | Note |
|---|---|---|
| Solo backend gateway + mock | 512 MB | I microservizi BERT **non** vengono avviati |
| Stack completo con BERT | **4 GB** | BERT Sentiment ~2 GB + BERT Toxicity ~1.5 GB |
| Con GPU (opzionale) | 4 GB RAM + 4 GB VRAM | Inference ~10× più veloce; richede CUDA 11.8+ |

---

## 4. Struttura del repository

```
meeting-intelligence/
│
├── backend/                        # Gateway FastAPI
│   ├── main.py                     # Entry point, tutti gli endpoint REST
│   ├── pyproject.toml              # Dipendenze Python (PEP 517)
│   ├── pytest.ini                  # Configurazione test suite
│   ├── Dockerfile
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── config_loader.py        # Lettura mock_data.yaml con cache
│   │   └── mock_data.yaml          # Frasi campione, partecipanti, meeting
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── predictor.py            # Abstract predictor + ToxicityDetector
│   │
│   └── tests/
│       ├── conftest.py             # Fixtures condivise (client, sample_texts, ecc.)
│       ├── test_api_extended.py    # Test endpoint HTTP
│       ├── test_integration.py     # Test end-to-end con dati reali
│       ├── test_services_complete.py  # Test logica business e mock data
│       ├── test_statistics.py      # Validazione matematica delle statistiche
│       ├── test_parametrized.py    # Test data-driven con pytest.mark.parametrize
│       ├── test_coverage_gap.py    # Test per coprire branch mancanti
│       ├── test_edge_cases.py      # Input boundary, Unicode, stress test
│       └── test_performance.py     # SLA e tempi di risposta
│
├── frontend/                       # Dashboard React
│   ├── src/
│   │   ├── main.jsx                # Entry point React
│   │   └── App.jsx                 # Componente principale (dashboard, playback)
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
│
├── services/
│   ├── bert-sentiment/             # Microservizio sentiment
│   │   ├── main.py                 # FastAPI con modello nlptown/bert-multilingual
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   └── bert-toxicity/              # Microservizio tossicità
│       ├── main.py                 # FastAPI con modello gravitee-io/bert-small-toxicity
│       ├── requirements.txt
│       └── Dockerfile
│
└── docker-compose.yml              # Orchestrazione completa
```

### File chiave da conoscere

**`backend/main.py`** — contiene tutta la logica del gateway: endpoint REST, modelli Pydantic, fallback mock BERT, generazione transcript deterministico, aggregazione statistica. Se stai aggiungendo un endpoint nuovo, questo è il file.

**`backend/config/mock_data.yaml`** — fonte di verità per lo sviluppo. Contiene le frasi di esempio usate per generare i transcript mock, l'elenco dei partecipanti (`Alice`, `Bob`, `Charlie`) e la configurazione del meeting `mtg001`. Modificare questo file cambia il comportamento di tutto il sistema mock.

**`backend/models/predictor.py`** — pattern architetturale per i modelli ML. Se in futuro si vuole aggiungere un modello di sentiment diverso da BERT (es. TextBlob, VADER, GPT), si estende `ModelPredictor` qui.

---

## 5. Setup locale (senza Docker)

Questa sezione descrive come avviare backend e frontend direttamente sulla propria macchina, senza Docker. È utile quando si vuole sviluppare con hot-reload veloce o non si ha RAM sufficiente per i container BERT.

> I microservizi BERT **non vengono avviati** in questa modalità. Il gateway rileva automaticamente che non sono raggiungibili e attiva il fallback mock rule-based. Tutto funziona normalmente con dati simulati.

### 5.1 Setup backend Python

```bash
# Entrare nella cartella backend
cd backend

# Creare il virtual environment (isolamento dipendenze — non usare il Python di sistema)
python3.11 -m venv .venv

# Attivare il virtual environment
source .venv/bin/activate          # Linux / macOS
.venv\Scripts\activate             # Windows PowerShell

# Verificare che Python punti al venv e non al sistema
which python                       # deve mostrare .../backend/.venv/bin/python

# Installare le dipendenze dell'applicazione
pip install fastapi "uvicorn[standard]" httpx pyyaml

# Installare le dipendenze di test
pip install pytest pytest-asyncio pytest-cov httpx

# Avviare il gateway in modalità sviluppo (hot-reload attivo)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Il gateway è pronto quando appare nel log:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

Verificare che risponda: `curl http://localhost:8000/health`

Il campo `sentiment_mock: true` nella risposta conferma che il fallback mock è attivo — comportamento atteso senza i container BERT.

### 5.2 Setup frontend Node.js

In un secondo terminale, separato dal backend:

```bash
# Entrare nella cartella frontend
cd frontend

# Installare le dipendenze npm (crea node_modules/ — non committare questa cartella)
npm install

# Avviare in modalità sviluppo con hot-reload
npm run dev
```

Il frontend si avvia su `http://localhost:3000`.

> **Importante**: il frontend si aspetta il backend su `http://localhost:8000`. Se si usa una porta diversa, modificare la costante `API_URL` in `frontend/src/App.jsx` riga 7.

### 5.3 Variabili d'ambiente

Il backend legge le seguenti variabili d'ambiente all'avvio. In locale non è necessario configurarle — i valori di default funzionano tutti.

| Variabile | Default | Descrizione |
|---|---|---|
| `BERT_SERVICE_URL` | `http://bert-sentiment:5001` | URL microservizio sentiment. In locale usare `http://localhost:5001` se si avvia il container BERT separatamente. |
| `TOXICITY_SERVICE_URL` | `http://bert-toxicity:5003` | URL microservizio tossicità. |
| `USE_ARIANNA` | `false` | Se `true`, il gateway chiama Arianna invece del mock per i transcript. |
| `ARIANNA_BASE_URL` | `http://arianna-host:3000` | URL base di Arianna. Usato solo se `USE_ARIANNA=true`. |
| `CORS_ORIGINS` | `*` | Origini CORS permesse. In produzione sostituire con il dominio specifico del frontend. |

Per lo sviluppo locale, creare il file `backend/.env` (già incluso nel `.gitignore` — non verrà committato):

```bash
# backend/.env
BERT_SERVICE_URL=http://localhost:5001
TOXICITY_SERVICE_URL=http://localhost:5003
USE_ARIANNA=false
CORS_ORIGINS=http://localhost:3000
```

---

## 6. Avvio con Docker

Docker Compose è il modo **consigliato** per avviare l'intero stack in modo riproducibile. Gestisce automaticamente la rete interna tra i servizi, i volumi per la cache dei modelli BERT e l'ordine di avvio.

### 6.1 Clonare il repository

```bash
git clone <url-repository>
cd meeting-intelligence
```

### 6.2 Stack completo

```bash
# Prima esecuzione — scarica le immagini Docker e i modelli BERT da HuggingFace (~700 MB, 5–10 min)
docker compose up --build

# Esecuzioni successive (le immagini sono già in cache)
docker compose up
```

> **Attenzione**: il primo avvio scarica i modelli BERT da HuggingFace Hub (~700 MB per sentiment, ~200 MB per toxicity). Richede connessione internet stabile.

Servizi disponibili dopo l'avvio:

| URL | Servizio |
|---|---|
| `http://localhost:3000` | Dashboard React |
| `http://localhost:8000` | API Gateway |
| `http://localhost:8000/docs` | Swagger UI (documentazione interattiva API) |
| `http://localhost:8000/redoc` | ReDoc (documentazione alternativa) |
| `http://localhost:5001/docs` | Swagger BERT Sentiment |
| `http://localhost:5003/docs` | Swagger BERT Toxicity |

### 6.3 Solo backend + mock (sviluppo frontend)

Se si sta sviluppando solo il frontend e non si vogliono avviare i microservizi BERT pesanti:

```bash
# Avvia solo gateway e frontend
docker compose up backend frontend
```

Il gateway riconosce automaticamente che i microservizi BERT non sono raggiungibili e attiva il fallback mock. La dashboard funziona normalmente con dati simulati.

### 6.4 Comandi utili Docker

```bash
# Fermare tutto
docker compose down

# Fermare e rimuovere anche i volumi (cache modelli)
# Usare quando si vuole ripartire da zero o cambiare modello
docker compose down -v

# Vedere i log in tempo reale
docker compose logs -f

# Log di un servizio specifico
docker compose logs -f backend
docker compose logs -f bert-sentiment

# Aprire una shell nel container backend (per debug)
docker compose exec backend sh

# Forzare rebuild di un singolo servizio
docker compose up --build backend

# Pulizia completa di tutto Docker (immagini, volumi, network)
# Usare solo se si vuole liberare spazio disco
docker system prune -a --volumes
```

### 6.5 Verifica che tutto funzioni

```bash
# Health check del gateway
curl http://localhost:8000/health

# Lista dei meeting disponibili
curl http://localhost:8000/meetings

# Analisi sentiment di un testo
curl -X POST http://localhost:8000/sentiment/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "This meeting was incredibly productive!"}'

# Analisi completa del meeting mtg001
curl http://localhost:8000/meeting/mtg001/analysis
```

---

## 7. Configurazione

### 7.1 Modificare i dati mock (`mock_data.yaml`)

Il file `backend/config/mock_data.yaml` controlla tutto il layer di dati mock. Struttura:

```yaml
# Lista delle frasi usate per generare i transcript
# Aggiungere frasi rappresentative del dominio per test più realistici
sample_phrases:
  - "This meeting was very productive!"
  - "I disagree with this approach."
  # ... altre frasi

# Partecipanti disponibili nei meeting mock
participants:
  - id: fj93829      # ID univoco (usato nelle chiamate API con ?userId=)
    name: Alice
  - id: dkd9320
    name: Bob
  - id: abc1234
    name: Charlie

# Definizione dei meeting
meetings:
  - id: mtg001                        # ID usato nell'URL /meeting/mtg001/...
    date: '2024-06-01T10:00:00Z'      # Data del meeting (ISO 8601)
    num_entries: 30                   # Numero di messaggi nel transcript

# Parametri globali di generazione transcript
generation:
  min_duration_seconds: 3            # Durata minima di ogni messaggio audio
  max_pause_seconds: 4               # Pausa massima tra un messaggio e il successivo
  chars_per_second: 15               # Velocità di lettura (usata per calcolare durata)

# Override per-meeting (sovrascrivono i parametri globali)
generation_overrides:
  mtg001:
    min_duration_seconds: 2
    max_pause_seconds: 3
    chars_per_second: 18
```

> **Nota**: la generazione è **deterministica**. Lo stesso `mock_data.yaml` produce sempre lo stesso transcript, garantendo la riproducibilità dei test.

### 7.2 Aggiungere un secondo meeting

Per aggiungere un secondo meeting (utile per test di scenario diversi):

```yaml
meetings:
  - id: mtg001
    date: '2024-06-01T10:00:00Z'
    num_entries: 30
  - id: mtg002                        # Nuovo meeting
    date: '2024-06-08T14:30:00Z'
    num_entries: 20
```

Dopo la modifica, riavviare il backend (`docker compose restart backend`).

---

## 8. API Reference

Il gateway espone un'API REST su porta `8000`. La documentazione interattiva completa è disponibile su `http://localhost:8000/docs`.

### Endpoint principali

#### `GET /health`
Stato del gateway e dei microservizi.

```json
{
  "status": "healthy",
  "service": "backend-gateway",
  "use_arianna": false,
  "sentiment_mock": true,
  "toxicity_mock": true,
  "meetings": ["mtg001"]
}
```

`sentiment_mock: true` indica che il gateway sta usando il fallback rule-based invece del vero BERT.

---

#### `GET /meetings`
Lista dei meeting disponibili.

```json
{
  "meetings": [
    {
      "id": "mtg001",
      "date": "2024-06-01T10:00:00Z",
      "participants_count": 3,
      "messages_count": 30
    }
  ]
}
```

---

#### `GET /meeting/{meetingId}/analysis`
**Endpoint principale della piattaforma.** Restituisce il transcript completo con sentiment e tossicità per ogni messaggio, più le statistiche aggregate.

Query parameters opzionali:

| Parametro | Tipo | Descrizione |
|---|---|---|
| `userId` | string | Filtra i messaggi per partecipante (usa l'`id` del partecipante) |
| `search` | string | Full-text search sul testo trascritto |
| `triggersOnly` | bool | Solo messaggi con `contains_trigger: true` |
| `startTime` / `endTime` | ISO 8601 | Finestra temporale |
| `limit` | int (default: 200) | Max messaggi restituiti |
| `offset` | int (default: 0) | Paginazione |

Risposta (struttura semplificata):

```json
{
  "transcript": [
    {
      "conversation_turn": 1,
      "participant_name": "Alice",
      "transcribed_text": "This meeting was very productive!",
      "created_at": "2024-06-01T10:00:00.000Z",
      "audio_duration_ms": 5000,
      "sentiment": {
        "label": "positive",
        "score": 0.875,
        "confidence": 0.92,
        "polarity": 0.805
      },
      "toxicity": {
        "is_toxic": false,
        "toxicity_score": 0.04,
        "severity": "low",
        "confidence": 0.96
      }
    }
  ],
  "metadata": {
    "language": "en",
    "stats": {
      "total_messages": 30,
      "sentiment": {
        "distribution": { "positive": 18, "neutral": 8, "negative": 4 },
        "average_score": 0.623,
        "positive_ratio": 0.6,
        "average_polarity": 0.312
      },
      "toxicity": {
        "toxic_count": 3,
        "toxic_ratio": 0.1,
        "severity_distribution": { "low": 25, "medium": 4, "high": 1 },
        "average_toxicity_score": 0.148
      }
    }
  }
}
```

**Campo `polarity`**: valore in `[-1, +1]` calcolato come `sign(label) × score × confidence`. Rappresenta la polarità pesata per confidenza — un messaggio molto positivo con alta confidenza contribuisce più di uno positivo con confidenza bassa.

---

#### `POST /sentiment/analyze`
Analisi sentiment di un singolo testo.

```bash
curl -X POST http://localhost:8000/sentiment/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "Great work on the presentation!"}'
```

```json
{
  "label": "positive",
  "score": 0.87,
  "confidence": 0.91,
  "raw_output": { "mock": true },
  "model_type": "sentiment"
}
```

---

#### `POST /toxicity/detect`
Rilevamento tossicità di un singolo testo.

```bash
curl -X POST http://localhost:8000/toxicity/detect \
  -H "Content-Type: application/json" \
  -d '{"text": "You are completely useless!"}'
```

```json
{
  "is_toxic": true,
  "toxicity_score": 0.87,
  "severity": "high",
  "confidence": 0.89,
  "raw_output": { "mock": true },
  "model_type": "toxicity"
}
```

---

#### `GET /services/status`
Stato di salute dei microservizi BERT.

```json
{
  "bert_sentiment": { "healthy": true,  "url": "http://bert-sentiment:5001", "port": 5001 },
  "bert_toxicity":  { "healthy": false, "url": "http://bert-toxicity:5003",  "port": 5003 }
}
```

---

## 9. Testing

Il progetto ha una suite di test completa organizzata per categoria. Tutti i test usano il layer mock e **non richiedono** i microservizi BERT attivi.

### 9.1 Installare le dipendenze di test

```bash
cd backend

# Attivare il venv (se non già attivo)
source .venv/bin/activate

pip install pytest pytest-asyncio pytest-cov httpx
```

### 9.2 Eseguire i test

```bash
# Tutti i test
pytest

# Solo una categoria (usando i marker)
pytest -m smoke          # Test di base, veloci (~5 sec)
pytest -m unit           # Test unitari senza I/O
pytest -m integration    # Test end-to-end
pytest -m sentiment      # Solo test sentiment
pytest -m toxicity       # Solo test tossicità
pytest -m performance    # Test SLA e tempi di risposta
pytest -m "not slow"     # Tutto tranne i test lenti

# Con report di coverage
pytest --cov --cov-report=html
# Aprire htmlcov/index.html nel browser per il report dettagliato

# Un singolo file di test
pytest tests/test_api_extended.py -v

# Un singolo test
pytest tests/test_api_extended.py::TestHealthEndpoints::test_root_endpoint -v
```

### 9.3 Struttura dei test

| File | Marker | Cosa testa |
|---|---|---|
| `test_api_extended.py` | `api`, `smoke` | Tutti gli endpoint HTTP: status code, struttura JSON, campi obbligatori |
| `test_integration.py` | `integration` | Flussi end-to-end: filtri partecipante, consistenza dati, concorrenza |
| `test_statistics.py` | `integration` | Correttezza matematica: distribuzione sentiment somma a totale, formula polarity |
| `test_services_complete.py` | `unit` | Logica business: config loader, predictor normalization, generazione mock |
| `test_parametrized.py` | vari | Test data-driven: label attese, batch sizes, metodi HTTP vietati |
| `test_coverage_gap.py` | `unit`, `api` | Branch coverage: path di errore, filter con userId valido/invalido |
| `test_edge_cases.py` | `edge` | Input boundary: testo vuoto, lunghezza massima, Unicode, emoji, arabo |
| `test_performance.py` | `performance`, `slow` | SLA: root < 1s, sentiment < 2s, analisi completa < 10s |

### 9.4 Convenzioni dei test

I test seguono lo schema **Arrange → Act → Assert**:

```python
@pytest.mark.sentiment
def test_analyze_sentiment_single_positive(self, client, sample_texts):
    # Arrange
    text = sample_texts["positive"][0]

    # Act
    response = client.post("/sentiment/analyze", json={"text": text})

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["label"] == "positive"
    assert 0.0 <= data["score"] <= 1.0
```

La fixture `client` (definita in `conftest.py`) crea un `TestClient` FastAPI con scope di sessione — viene istanziato una volta sola per l'intera suite, il che rende i test molto più veloci rispetto a una istanziazione per test.

---

## 10. Integrazione con Arianna

Arianna è la piattaforma di videoconferenza che fornisce i transcript reali. L'integrazione è gestita tramite la variabile d'ambiente `USE_ARIANNA`.

### Attivare la modalità Arianna

```bash
# Nel file backend/.env
USE_ARIANNA=true
ARIANNA_BASE_URL=http://indirizzo-arianna:3000
```

Quando `USE_ARIANNA=true`, l'endpoint `/meeting/{meetingId}/analysis` chiama l'API di Arianna invece di usare i dati mock:

```
GET http://arianna-host:3000/api/rooms/{meetingId}/transcriptions
```

### Schema dei dati Arianna

Il sistema si aspetta che Arianna restituisca transcript nel seguente formato. Ogni messaggio deve avere:

| Campo | Tipo | Obbligatorio | Descrizione |
|---|---|---|---|
| `conversation_turn` | int | sì | Numero progressivo del messaggio |
| `participant_name` | string | sì | Nome del partecipante |
| `transcribed_text` | string | sì | Testo trascritto |
| `created_at` | string (ISO 8601) | sì | Timestamp assoluto con millisecondi |
| `audio_duration_ms` | int | sì | Durata audio in millisecondi |
| `user_id` | string | no | ID utente Arianna |
| `room_id` | string | no | ID stanza Arianna |
| `session_id` | string | no | ID sessione |
| `language` | string | no | Codice lingua (default: `"en"`) |
| `contains_trigger` | bool | no | Flag per parole trigger (default: `false`) |
| `trigger_words` | string[] | no | Lista parole trigger trovate |

### Filtri supportati con Arianna

I query parameter `userId`, `triggersOnly`, `startTime`, `endTime`, `search`, `limit`, `offset` vengono passati direttamente all'API Arianna come parametri. Assicurarsi che l'API Arianna li supporti.

---

## 11. Troubleshooting

### I container si avviano ma il frontend non carica

1. Verificare che il backend sia healthy: `curl http://localhost:8000/health`
2. Controllare i log del backend: `docker compose logs backend`
3. Verificare che la porta 3000 non sia già occupata: `lsof -i :3000` (Linux/macOS)

### Il modello BERT non si carica (OOMKilled)

Il container BERT viene terminato per esaurimento memoria. Soluzioni:

```yaml
# In docker-compose.yml, aumentare il limite memoria
services:
  bert-sentiment:
    deploy:
      resources:
        limits:
          memory: 3G    # era 2G
```

Oppure, se la macchina ha poca RAM, sviluppare senza i microservizi BERT (il mock si attiva in automatico).

### Errore "port already in use"

Un'altra applicazione sta già usando la porta. Cambiare il mapping in `docker-compose.yml`:

```yaml
ports:
  - "8080:8000"    # Espone sulla porta 8080 invece di 8000
```

### I test falliscono con `ModuleNotFoundError`

Il virtual environment non è attivato o le dipendenze non sono installate:

```bash
source .venv/bin/activate
pip install pytest pytest-asyncio httpx pyyaml fastapi uvicorn
```

### Il transcript mock è sempre lo stesso

È intenzionale — la generazione è deterministica per garantire la riproducibilità dei test. Per variare il contenuto, modificare `sample_phrases` in `mock_data.yaml`.

### `USE_ARIANNA=true` ma ricevo 500

Arianna non è raggiungibile o restituisce un formato diverso. Verificare:
1. `ARIANNA_BASE_URL` è corretto e raggiungibile dal container backend
2. Il transcript di Arianna contiene tutti i campi obbligatori (`conversation_turn`, `participant_name`, `transcribed_text`, `created_at`, `audio_duration_ms`)

---

## 12. Glossario tecnico

**BERT** (Bidirectional Encoder Representations from Transformers) — famiglia di modelli linguistici pre-addestrati sviluppata da Google. In questo progetto si usano due varianti: `nlptown/bert-base-multilingual-uncased-sentiment` (110M parametri, output 1–5 stelle) e `gravitee-io/bert-small-toxicity` (output binario tossico/non-tossico).

**Polarity** — metrica composita in `[-1, +1]` che rappresenta la polarità di un messaggio pesata per confidenza: `polarity = sign(label) × score × confidence`. Un valore di `+0.8` indica un messaggio fortemente positivo con alta confidenza; `0.0` indica neutralità o incertezza.

**Severity** — livello di severità della tossicità calcolato dallo score: `low` (< 0.4), `medium` (0.4–0.7), `high` (> 0.7). Le soglie sono conservative per ridurre i falsi positivi.

**Mock Fallback** — classificatore rule-based che si attiva automaticamente quando i microservizi BERT non sono raggiungibili. Usa keyword list (`_POS_KEYWORDS`, `_NEG_KEYWORDS`, `_TOX_KEYWORDS`) e produce risultati deterministici tramite `random.Random(hash(text))`.

**Schema Arianna** — formato dei dati di trascrizione definito dalla piattaforma Arianna. Il campo chiave è `conversation_turn` (intero progressivo) invece del tradizionale `id`, e `participant_name` invece di `nickname` o `author`.

**Transcript** — sequenza ordinata di messaggi di una riunione. Ogni elemento rappresenta un singolo intervento, con timestamp, partecipante, testo trascritto e durata audio.

**TestClient (FastAPI)** — client HTTP sincrono fornito da Starlette/FastAPI per i test. Permette di fare richieste all'applicazione senza avviare un vero server HTTP, rendendo i test più veloci e affidabili.

**HuggingFace Hub** — repository pubblico di modelli ML pre-addestrati. Al primo avvio dei container BERT, i modelli vengono scaricati automaticamente e memorizzati nel volume Docker (`bert-model-cache`, `bert-toxicity-cache`).

# docker-compose up --build

# docker-compose down -v

# docker system prune -a --volumes
# docker-compose exec backend sh

# pip install pytest pytest-asyncio pytest-cov httpx --break-system-packages