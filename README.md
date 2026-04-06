# Meeting Intelligence

> Sistema distribuito per l'analisi automatica di riunioni in tempo reale, basato su modelli BERT per sentiment analysis e rilevamento tossicità. Sviluppato nell'ambito dell'OR3 del progetto ARIANNA.

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
9. [Simulazione Live](#9-simulazione-live)
10. [Dataset di riferimento](#10-dataset-di-riferimento)
11. [Testing](#11-testing)
12. [Integrazione con Arianna](#12-integrazione-con-arianna)
13. [Troubleshooting](#13-troubleshooting)
14. [Glossario tecnico](#14-glossario-tecnico)

---

## 1. Panoramica del progetto

Meeting Intelligence è un sistema distribuito che analizza le trascrizioni di riunioni in tempo reale. Ogni messaggio del transcript viene classificato su due dimensioni indipendenti:

- **Sentiment** — tono del messaggio (positivo/neutro/negativo), normalizzato in `[0, 1]` con Sentiment Polarity Index di sessione in `[-1, +1]`
- **Tossicità** — linguaggio offensivo o inappropriato, score `[0, 1]` con soglia binaria a `0.5` e tre livelli di severity (low/medium/high)

Il sistema è progettato per integrarsi con la piattaforma **ARIANNA** (videoconferenza e ASR), ma include un layer di simulazione live lato backend e dati mock che permettono sviluppo e test completamente autonomi.

### Modalità operative

- **Live** — il backend avvia un clock reale, rilascia progressivamente i messaggi in base al tempo trascorso, il frontend fa polling e aggiorna la dashboard
- **Review** — playback client-side dell'intero transcript a velocità configurabile (1×–20×)

---

## 2. Architettura del sistema

```
┌─────────────────┐        HTTP         ┌──────────────────────┐
│                 │ ──────────────────► │                      │
│  Frontend React │                     │   Backend Gateway    │
│   (port 3000)   │ ◄────────────────── │    FastAPI (8000)    │
│                 │      JSON           │                      │
└─────────────────┘                     └──────────┬───────────┘
                                                   │
                              ┌────────────────────┼─────────────────────┐
                              │                    │                     │
                              ▼                    ▼                     │
                   ┌─────────────────┐  ┌─────────────────┐             │
                   │  BERT Sentiment │  │  BERT Toxicity  │             │
                   │   (port 5001)   │  │   (port 5003)   │             │
                   └─────────────────┘  └─────────────────┘             │
                                                                         │
                                         ┌───────────────────────────┐  │
                                         │   Mock / Live Simulation  │◄─┘
                                         │   MEETING_SESSIONS (dict) │
                                         │   mock_data.yaml          │
                                         └───────────────────────────┘
```

| Componente | Tecnologia | Porta | Responsabilità |
|---|---|---|---|
| Frontend | React 18 + Vite + Chart.js | 3000 | Dashboard, playback live e review |
| Backend Gateway | FastAPI Python 3.11 | 8000 | Orchestrazione, live simulation, aggregazione |
| BERT Sentiment | HuggingFace Transformers | 5001 | Inferenza sentiment, score [0,1] |
| BERT Toxicity | HuggingFace Transformers | 5003 | Inferenza toxicity, classificazione binaria |

### Pattern architetturali

**API Gateway** — unico punto di ingresso per il frontend; `asyncio.gather` esegue le due inferenze BERT in parallelo.

**Abstract Predictor** — `SentimentPredictor` e `ToxicityDetector` attivano il fallback mock al primo errore di connessione, in modo permanente.

**Mock Fallback** — classificatori rule-based deterministici (`hash(text)` come seed), attivi quando i microservizi BERT non sono raggiungibili.

**Singleton** — ogni microservizio carica il modello una volta al boot e lo condivide tra tutte le richieste.

---

## 3. Prerequisiti

| Software | Versione minima |
|---|---|
| Docker Desktop | 24.x |
| Docker Compose | 2.x |
| Python (solo locale) | 3.11+ |
| Node.js (solo locale) | 20 LTS |

**RAM**: 512 MB solo backend+mock, **4 GB** per lo stack completo con BERT.

---

## 4. Struttura del repository

```
meeting-intelligence/
├── backend/
│   ├── main.py                  # Gateway: endpoint REST, live simulation
│   ├── pytest.ini               # Configurazione test
│   ├── config/
│   │   └── mock_data.yaml       # Frasi campione, partecipanti, meeting
│   ├── models/
│   │   └── predictor.py         # SentimentPredictor + ToxicityDetector
│   └── tests/
│       ├── conftest.py
│       ├── test_api_extended.py     # 23 test — endpoint HTTP
│       ├── test_integration.py      # 13 test — end-to-end
│       ├── test_services_complete.py # 20 test — logica business
│       ├── test_statistics.py       # 12 test — invarianti matematiche
│       ├── test_parametrized.py     # 13 test — data-driven
│       └── test_coverage_gap.py     # 22 test — branch coverage
├── frontend/
│   └── src/App.jsx              # Dashboard React (1300+ righe)
├── services/
│   ├── bert-sentiment/          # Microservizio porta 5001
│   └── bert-toxicity/           # Microservizio porta 5003
└── docker-compose.yml           # Orchestrazione con healthcheck
```

---

## 5. Setup locale (senza Docker)

> I microservizi BERT **non vengono avviati**. Il mock fallback si attiva automaticamente.

```bash
# Backend
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" httpx pyyaml
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend (altro terminale)
cd frontend && npm install && npm run dev
```

---

## 6. Avvio con Docker

```bash
docker compose up --build    # Prima esecuzione (~700 MB download modelli)
docker compose up            # Esecuzioni successive
```

| URL | Servizio |
|---|---|
| `http://localhost:3000` | Dashboard React |
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:5001/docs` | Swagger BERT Sentiment |
| `http://localhost:5003/docs` | Swagger BERT Toxicity |

```bash
docker compose down          # Ferma tutto
docker compose down -v       # Ferma e rimuove volumi (cache modelli)
docker compose logs -f       # Log in tempo reale
```

---

## 7. Configurazione

Il file `backend/config/mock_data.yaml` controlla il layer mock. La generazione è **deterministica**: stesso `meeting_id` → stesso transcript.

```yaml
sample_phrases:         # Frasi dal GitHub Gold Standard (Novielli et al. 2020)
  - "This meeting was very productive!"
  - "I disagree with this approach."

participants:
  - {id: fj93829, name: Alice}
  - {id: dkd9320, name: Bob}
  - {id: abc1234, name: Charlie}

meetings:
  - id: mtg001
    date: '2024-06-01T10:00:00Z'
    num_entries: 30

generation:
  min_duration_seconds: 3
  max_pause_seconds: 4
  chars_per_second: 15
```

---

## 8. API Reference

Documentazione interattiva: `http://localhost:8000/docs`

### Endpoint principali

| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/health` | GET | Stato gateway, flag mock |
| `/meetings` | GET | Lista meeting |
| `/meeting/{id}/analysis` | GET | Transcript arricchito + statistiche |
| `/meeting/{id}/start` | POST | Avvia simulazione live |
| `/meeting/{id}/status` | GET | Stato live (not_started/active/ended) |
| `/meeting/{id}/reset` | POST | Resetta sessione live |
| `/sentiment/analyze` | POST | Analisi singolo testo |
| `/sentiment/batch` | POST | Analisi batch (max 100) |
| `/toxicity/detect` | POST | Rilevamento singolo testo |
| `/toxicity/detect/batch` | POST | Rilevamento batch |

---

## 9. Simulazione Live

Il backend è la fonte di verità del tempo. La simulazione non è client-side.

```bash
# Avvia meeting con join_offset = 120s (entra a meeting già in corso)
curl -X POST "http://localhost:8000/meeting/mtg001/start?speed=1.0&join_offset=120"

# Controlla lo stato
curl "http://localhost:8000/meeting/mtg001/status"
# → { "status": "active", "elapsed_seconds": 127.3, "messages_available": 14, ... }

# Ottieni i messaggi disponibili finora
curl "http://localhost:8000/meeting/mtg001/analysis"

# Resetta
curl -X POST "http://localhost:8000/meeting/mtg001/reset"
```

Il frontend fa polling ogni N secondi (configurabile tramite framerate), aggiornando transcript e timer. Il timer usa un riferimento temporale assoluto per evitare drift:
```
wallSec = wallAtSync + (Date.now() - realAtSync) / 1000
```

---

## 10. Dataset di riferimento

Le frasi campione in `mock_data.yaml` derivano da dataset accademici reali.

### Sentiment — GitHub Gold Standard

**Novielli et al., MSR 2020**  
*"Can We Use SE-specific Sentiment Analysis Tools in a Cross-Platform Setting?"*  
DOI: [10.1145/3379597.3387446](https://doi.org/10.1145/3379597.3387446)  
Dataset: [figshare.com/articles/11604597](https://doi.org/10.6084/m9.figshare.11604597)

7.122 commenti GitHub annotati manualmente (κ = .84), distribuiti 43% neutro, 28% positivo, 29% negativo.

### Toxicity — GitHub Issues annotate

**Raman et al., ICSE-NIER 2020**  
*"Stress and Burnout in Open Source: Toward Finding, Understanding, and Mitigating Unhealthy Interactions"*  
DOI: [10.1145/3377816.3381732](https://doi.org/10.1145/3377816.3381732)  
Dataset: [github.com/CMUSTRUDEL/toxicity-detector](https://github.com/CMUSTRUDEL/toxicity-detector)

386 thread di issue GitHub (167 con contenuto tossico), identificati tramite issue bloccate come *too heated*.

---

## 11. Testing

**202 test automatizzati** — non richiedono microservizi BERT attivi.

```bash
cd backend && source .venv/bin/activate
pip install pytest pytest-asyncio pytest-cov httpx

pytest                              # Tutti i test
pytest -m smoke                    # Test base veloci
pytest -m integration              # End-to-end
pytest --cov --cov-report=html     # Coverage report
```

| File | Test | Cosa testa |
|---|---|---|
| `test_api_extended.py` | 23 | Endpoint HTTP |
| `test_coverage_gap.py` | 22 | Branch coverage, validator |
| `test_services_complete.py` | 20 | Logica business, determinismo |
| `test_integration.py` | 13 | End-to-end, consistenza |
| `test_parametrized.py` | 13 | Data-driven, label attesi |
| `test_statistics.py` | 12 | Invarianti matematiche |
| `test_edge_cases.py` | 29 | Input boundary, Unicode, stress |
| `test_performance.py` | 12 | SLA, throughput, p95 |

Copertura: ~95% statement, ~91% branch. Tutti i 202 test completano in 2.73 secondi.

---

## 12. Integrazione con Arianna

```bash
# backend/.env
USE_ARIANNA=true
ARIANNA_BASE_URL=http://arianna-host:3000
```

Con `USE_ARIANNA=true`, `/meeting/{id}/analysis` chiama:
```
GET {ARIANNA_BASE_URL}/api/rooms/{id}/transcriptions
```

I filtri `userId`, `startTime`, `endTime`, `search`, `limit`, `offset` vengono passati direttamente ad ARIANNA.

---

## 13. Troubleshooting

**Frontend non carica**: `curl http://localhost:8000/health` → backend attivo?

**Container OOMKilled**: aumentare `memory: 3G` in docker-compose.yml per bert-sentiment.

**Porta in uso**: cambiare mapping in docker-compose.yml, es. `"8080:8000"`.

**Test falliscono ModuleNotFoundError**: `pip install pytest pytest-asyncio httpx pyyaml fastapi`.

---

## 14. Glossario

**BERT** — modello linguistico pre-addestrato di Google. Usati: `nlptown/bert-base-multilingual-uncased-sentiment` e `gravitee-io/bert-small-toxicity`.

**SPI** — Sentiment Polarity Index: `(positivi − negativi) / totale ∈ [-1, +1]` (Liu 2012).

**Severity** — intensità tossicità: low (< 0.4), medium (0.4–0.7), high (> 0.7). Indipendente da `is_toxic`.

**Mock Fallback** — keyword matching deterministico (`hash(text)` come seed), calibrato sui dataset di Novielli et al. e Raman et al.

**MEETING_SESSIONS** — dizionario in-memory `{ meeting_id: { started_at, speed } }`. Non persistente.

**join_offset** — retrodatata `started_at` di `join_offset/speed` secondi per simulare ingresso a meeting in corso.

# docker-compose up --build

# docker-compose down -v

# docker system prune -a --volumes
# docker-compose exec backend sh

# pip install pytest pytest-asyncio pytest-cov httpx --break-system-packages