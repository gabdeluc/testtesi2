# Ambiente di Sviluppo Containerizzato - Frontend e Backend

Questo progetto fornisce un ambiente di sviluppo containerizzato completo con un backend FastAPI (Python) e un frontend React (JavaScript), orchestrati tramite Docker Compose.

## Indice

- [Prerequisiti](#prerequisiti)
- [Struttura del Progetto](#struttura-del-progetto)
- [Installazione e Avvio](#installazione-e-avvio)
- [Architettura](#architettura)
- [Endpoint API](#endpoint-api)
- [Troubleshooting](#troubleshooting)

## Prerequisiti

Prima di iniziare, assicurati di avere installato:

- **Docker**: [Installa Docker](https://docs.docker.com/get-docker/)
- **Docker Compose**: Solitamente incluso con Docker Desktop

Per verificare l'installazione:

```bash
docker --version
docker-compose --version
```

## 📁 Struttura del Progetto

```
project-root/
├── backend/
│   ├── .gitignore
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── main.py
├── frontend/
│   ├── .gitignore
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── App.jsx
│       └── main.jsx
├── docker-compose.yml
└── README.md
```

## Installazione e Avvio

### 1. Clona o crea la struttura del progetto

Assicurati di avere tutti i file nella struttura corretta come mostrato sopra.

### 2. Avvia lo stack completo

Dalla directory principale del progetto, esegui:

```bash
docker-compose up --build
```

Questo comando:

- Costruisce le immagini Docker per backend e frontend
- Avvia entrambi i container
- Configura la rete interna per la comunicazione

### 3. Accedi alle applicazioni

Una volta avviato, potrai accedere a:

- **Frontend React**: [http://localhost:3000](http://localhost:3000)
- **Backend FastAPI**: [http://localhost:8000](http://localhost:8000)
- **Documentazione API**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. Verifica della connessione

Apri il browser e visita [http://localhost:3000](http://localhost:3000). Dovresti vedere:

- Il titolo "Frontend React"
- Il messaggio "Hello from FastAPI" restituito dal backend
- Una conferma "✓ Connessione al backend riuscita!"

## Architettura

### Backend (FastAPI)

- **Framework**: FastAPI
- **Gestore dipendenze**: uv
- **Porta**: 8000
- **File principale**: `backend/main.py`

Il backend espone un endpoint GET alla radice (`/`) che restituisce un semplice messaggio JSON.

### Frontend (React)

- **Framework**: React 18
- **Build tool**: Vite
- **Gestore pacchetti**: npm
- **Porta**: 3000
- **File principale**: `frontend/src/App.jsx`

Il frontend effettua una chiamata HTTP GET al backend al caricamento e mostra il messaggio ricevuto.

### Docker Compose

Orchestrazione dei servizi con:

- Rete condivisa tra backend e frontend
- Volume mounting per lo sviluppo in tempo reale
- Riavvio automatico dei container

## 🔌 Endpoint API

### GET `/`

Restituisce un messaggio di benvenuto.

**Response:**

```json
{
  "message": "Hello from FastAPI"
}
```

**Status Code:** 200 OK

## Troubleshooting

### Il frontend non riesce a connettersi al backend

1. Verifica che entrambi i container siano in esecuzione:

   ```bash
   docker-compose ps
   ```

2. Controlla i log del backend:

   ```bash
   docker-compose logs backend
   ```

3. Verifica che il backend sia accessibile:
   ```bash
   curl http://localhost:8000
   ```

### Errore "port already in use"

Se le porte 3000 o 8000 sono già in uso, puoi modificarle nel file `docker-compose.yml`:

```yaml
ports:
  - "PORTA_NUOVA:PORTA_INTERNA"
```

### Modifiche al codice non si riflettono

1. Ferma i container:

   ```bash
   docker-compose down
   ```

2. Ricostruisci le immagini:
   ```bash
   docker-compose up --build
   ```

### Visualizzare i log in tempo reale

```bash
# Tutti i servizi
docker-compose logs -f

# Solo il backend
docker-compose logs -f backend

# Solo il frontend
docker-compose logs -f frontend
```

## Fermare lo stack

Per fermare tutti i container:

```bash
docker-compose down
```

Per fermare e rimuovere anche i volumi:

```bash
docker-compose down -v
```

# docker-compose up --build

# docker-compose down -v

# docker system prune -a --volumes
# docker-compose exec backend sh