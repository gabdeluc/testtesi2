"""
backend/main.py
===============
Gateway FastAPI — Meeting Intelligence
Fix applicati:
  • GET / root endpoint aggiunto
  • /health formato corretto (status/service)
  • /meetings con participants_count e messages_count
  • /services/status e /config aggiunti
  • /toxicity/detect/batch alias aggiunto
  • Endpoint BERT corretti (/predict→/analyze, /detect→/analyze, ecc.)
  • asyncio.gather per chiamate BERT parallele
  • BatchToxicityResult model allineato ai test
  • generation_overrides dal YAML applicati
  • random.Random(seed) per transcript deterministici
  • Query param: userId (schema Arianna)
"""

import asyncio
import os
import random
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi import status as http_status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

from config.config_loader import config_loader

# ─────────────────────────────────────────────────────────────────────────────
# COSTANTI / ENV
# ─────────────────────────────────────────────────────────────────────────────

SENTIMENT_SERVICE_URL = os.getenv("BERT_SERVICE_URL",      "http://bert-sentiment:5001")
TOXICITY_SERVICE_URL  = os.getenv("TOXICITY_SERVICE_URL",  "http://bert-toxicity:5003")

USE_ARIANNA      = os.getenv("USE_ARIANNA",      "false").lower() == "true"
ARIANNA_BASE_URL = os.getenv("ARIANNA_BASE_URL", "http://arianna-host:3000")

# CORS_ORIGINS: in produzione impostare la variabile d'ambiente con il dominio
# specifico del frontend (es. "https://meeting-intelligence.example.com").
# Il default "*" è accettabile solo in sviluppo locale.
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# ─────────────────────────────────────────────────────────────────────────────
# ENUMERAZIONI
# ─────────────────────────────────────────────────────────────────────────────

# Soglia classificazione tossicità — coerente tra backend e frontend
TOXICITY_THRESHOLD = 0.6

class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEUTRAL  = "neutral"
    NEGATIVE = "negative"


class ToxicitySeverity(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


# ─────────────────────────────────────────────────────────────────────────────
# MODELLI PYDANTIC — OUTPUT BERT
# ─────────────────────────────────────────────────────────────────────────────

class NormalizedPrediction(BaseModel):
    label:      SentimentLabel
    score:      float
    confidence: float
    raw_output: dict
    model_type: str = "sentiment"


class BatchPrediction(BaseModel):
    predictions:        List[NormalizedPrediction]
    total_processed:    int
    avg_score:          float
    label_distribution: dict


class ToxicityResult(BaseModel):
    is_toxic:       bool
    toxicity_score: float
    severity:       ToxicitySeverity
    confidence:     float
    raw_output:     dict
    model_type:     str = "toxicity"


class BatchToxicityResult(BaseModel):
    """Allineato ai test: total_processed, toxic_count, avg_toxicity_score."""
    results:            List[ToxicityResult]
    total_processed:    int
    toxic_count:        int
    toxic_ratio:        float
    avg_toxicity_score: float


# ─────────────────────────────────────────────────────────────────────────────
# MODELLI PYDANTIC — DOMINIO (schema Arianna-compatibile)
# ─────────────────────────────────────────────────────────────────────────────

class Participant(BaseModel):
    id:   str
    name: str
    role: str = "participant"


class TranscriptEntry(BaseModel):
    """Schema allineato al formato Arianna."""
    conversation_turn: int
    participant_name:  str
    transcribed_text:  str
    created_at:        str          # ISO 8601 assoluto
    audio_duration_ms: int

    user_id:          str       = ""
    room_id:          str       = ""
    session_id:       str       = ""
    language:         str       = "en"
    contains_trigger: bool      = False
    trigger_words:    List[str] = Field(default_factory=list)


class MeetingMetadata(BaseModel):
    participants: List[Participant]
    date:         str


class TranscriptMetadata(BaseModel):
    language: str = "en"


class TranscriptResponse(BaseModel):
    transcript: List[TranscriptEntry]
    metadata:   TranscriptMetadata


class MeetingResponse(BaseModel):
    metadata: MeetingMetadata


# ── Request models ────────────────────────────────────────────────

class UnifiedAnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)

    @validator("text")
    def text_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text cannot be empty or whitespace only")
        return v


class BatchUnifiedAnalysisRequest(BaseModel):
    texts: List[str] = Field(..., max_items=100)

    @validator("texts")
    def texts_list_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("texts list must contain at least one item")
        return v

    @validator("texts", each_item=True)
    def each_text_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("each text must be non-empty")
        return v


class ToxicityAnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)

    @validator("text")
    def text_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text cannot be empty or whitespace only")
        return v


class BatchToxicityRequest(BaseModel):
    texts: List[str] = Field(..., max_items=100)

    @validator("texts")
    def texts_list_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("texts list must contain at least one item")
        return v

    @validator("texts", each_item=True)
    def each_text_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("each text must be non-empty")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# MOCK BERT — fallback rule-based quando i microservizi non sono raggiungibili
# ─────────────────────────────────────────────────────────────────────────────

_POS_KEYWORDS = {
    "great", "good", "excellent", "perfect", "love", "thanks", "helpful",
    "nice", "well", "clean", "easy", "fast", "improved", "appreciate",
    "incredible", "joy", "happy", "fix", "solved", "works", "amazing",
    "outstanding", "wonderful", "brilliant", "fantastic", "superb",
}
_NEG_KEYWORDS = {
    "bad", "wrong", "broken", "fail", "error", "slow", "crash", "bug",
    "issue", "problem", "useless", "stupid", "garbage", "terrible",
    "awful", "hate", "worse", "ugly", "disappointing", "sucks", "shut",
    "disagree", "frustrated", "disappointed", "confused", "concerned",
}
_TOX_KEYWORDS = {
    "stupid", "idiot", "garbage", "shut up", "useless", "hate", "awful",
    "damn", "crap", "jerk", "moron",
}


def _mock_sentiment(text: str) -> NormalizedPrediction:
    lower = text.lower()
    words = set(re.findall(r"\w+", lower))
    pos   = len(words & _POS_KEYWORDS)
    neg   = len(words & _NEG_KEYWORDS)
    rng   = random.Random(hash(text) & 0xFFFFFFFF)
    if pos > neg:
        label, score = SentimentLabel.POSITIVE, 0.55 + min(pos * 0.08, 0.40)
    elif neg > pos:
        label, score = SentimentLabel.NEGATIVE, 0.55 + min(neg * 0.08, 0.40)
    else:
        label, score = SentimentLabel.NEUTRAL, 0.50 + rng.uniform(0, 0.15)
    confidence = round(0.70 + rng.uniform(0, 0.25), 4)
    score      = round(min(score, 0.98), 4)
    return NormalizedPrediction(
        label=label, score=score, confidence=confidence,
        raw_output={"mock": True}, model_type="sentiment",
    )


def _mock_toxicity(text: str) -> ToxicityResult:
    lower = text.lower()
    words = set(re.findall(r"\w+", lower))
    hits  = len(words & _TOX_KEYWORDS)
    rng   = random.Random(hash(text) & 0xFFFFFFFF)
    if hits >= 2:
        is_toxic, score, severity = True,  0.80 + rng.uniform(0, 0.15), ToxicitySeverity.HIGH
    elif hits == 1:
        is_toxic, score, severity = True,  0.55 + rng.uniform(0, 0.20), ToxicitySeverity.MEDIUM
    else:
        is_toxic, score, severity = False, rng.uniform(0.02, 0.25),     ToxicitySeverity.LOW
    confidence = round(0.72 + rng.uniform(0, 0.23), 4)
    score      = round(min(score, 0.98), 4)
    return ToxicityResult(
        is_toxic=(score > TOXICITY_THRESHOLD), toxicity_score=score, severity=severity,
        confidence=confidence, raw_output={"mock": True}, model_type="toxicity",
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT BERT MICROSERVICES  (con fallback automatico al mock)
# Endpoint corretti: /analyze (single), /batch (batch)
# ─────────────────────────────────────────────────────────────────────────────

class SentimentPredictor:
    def __init__(self, base_url: str):
        self.base_url  = base_url
        self._use_mock = False

    async def predict(self, text: str) -> NormalizedPrediction:
        if self._use_mock:
            return _mock_sentiment(text)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(f"{self.base_url}/analyze", json={"text": text})
                r.raise_for_status()
                return NormalizedPrediction(**r.json())
        except Exception:
            print(f"[sentiment] unreachable at {self.base_url} — mock ON")
            self._use_mock = True
            return _mock_sentiment(text)

    async def predict_batch(self, texts: List[str]) -> BatchPrediction:
        if self._use_mock:
            return self._mock_batch(texts)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(f"{self.base_url}/batch", json={"texts": texts})
                r.raise_for_status()
                return BatchPrediction(**r.json())
        except Exception:
            print(f"[sentiment] unreachable at {self.base_url} — mock ON")
            self._use_mock = True
            return self._mock_batch(texts)

    def _mock_batch(self, texts: List[str]) -> BatchPrediction:
        preds = [_mock_sentiment(t) for t in texts]
        avg   = round(sum(p.score for p in preds) / len(preds), 4) if preds else 0.0
        dist  = {"positive": 0, "neutral": 0, "negative": 0}
        for p in preds:
            dist[p.label.value] += 1
        return BatchPrediction(
            predictions=preds,
            total_processed=len(preds),
            avg_score=avg,
            label_distribution=dist,
        )


class ToxicityDetector:
    def __init__(self, base_url: str):
        self.base_url  = base_url
        self._use_mock = False

    async def detect(self, text: str) -> ToxicityResult:
        if self._use_mock:
            return _mock_toxicity(text)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(f"{self.base_url}/analyze", json={"text": text})
                r.raise_for_status()
                item = r.json()
                item["is_toxic"] = item.get("toxicity_score", 0) > TOXICITY_THRESHOLD
                return ToxicityResult(**item)
        except Exception:
            print(f"[toxicity] unreachable at {self.base_url} — mock ON")
            self._use_mock = True
            return _mock_toxicity(text)

    async def detect_batch(self, texts: List[str]) -> BatchToxicityResult:
        if self._use_mock:
            return self._mock_batch(texts)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(f"{self.base_url}/batch", json={"texts": texts})
                r.raise_for_status()
                data = r.json()
                # Trasforma la risposta del microservizio nel formato atteso
                raw_results = data.get("results", [])
                # Soglia 0.6: il microservizio BERT calcola is_toxic internamente; qui la ricalcoliamo
                for item in raw_results:
                    item["is_toxic"] = item.get("toxicity_score", 0) > TOXICITY_THRESHOLD
                results = [ToxicityResult(**item) for item in raw_results]
                toxic_n = sum(1 for res in results if res.is_toxic)
                avg_sc  = round(sum(res.toxicity_score for res in results) / len(results), 4) if results else 0.0
                return BatchToxicityResult(
                    results=results,
                    total_processed=len(results),
                    toxic_count=toxic_n,
                    toxic_ratio=round(toxic_n / len(results), 4) if results else 0.0,
                    avg_toxicity_score=avg_sc,
                )
        except Exception:
            print(f"[toxicity] unreachable at {self.base_url} — mock ON")
            self._use_mock = True
            return self._mock_batch(texts)

    def _mock_batch(self, texts: List[str]) -> BatchToxicityResult:
        results  = [_mock_toxicity(t) for t in texts]
        toxic_n  = sum(1 for r in results if r.is_toxic)
        avg_sc   = round(sum(r.toxicity_score for r in results) / len(results), 4) if results else 0.0
        return BatchToxicityResult(
            results=results,
            total_processed=len(results),
            toxic_count=toxic_n,
            toxic_ratio=round(toxic_n / len(results), 4) if results else 0.0,
            avg_toxicity_score=avg_sc,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ISTANZE PREDICTOR
# ─────────────────────────────────────────────────────────────────────────────

sentiment_predictor: SentimentPredictor = None
toxicity_detector:   ToxicityDetector   = None


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_PHRASES       = config_loader.get_sample_phrases()
PARTICIPANTS_CONFIG  = config_loader.get_participants()
MEETINGS_CONFIG      = config_loader.get_meetings()
GENERATION_CONFIG    = config_loader.get_generation_config()
GENERATION_OVERRIDES = config_loader.get_generation_overrides()

PARTICIPANTS = [Participant(**p) for p in PARTICIPANTS_CONFIG]


# ─────────────────────────────────────────────────────────────────────────────
# GENERAZIONE DATI MOCK (deterministica, schema Arianna)
# ─────────────────────────────────────────────────────────────────────────────

def generate_mock_transcript(
    num_entries: int,
    meeting_config: dict,
    gen_cfg: dict = None,
) -> List[TranscriptEntry]:
    """
    Genera transcript mock deterministico (seed basato su meeting_id).
    gen_cfg: override della configurazione di generazione (opzionale).
    """
    if not PARTICIPANTS:
        raise ValueError("PARTICIPANTS list is empty")
    if not SAMPLE_PHRASES:
        raise ValueError("SAMPLE_PHRASES list is empty")

    if gen_cfg is None:
        gen_cfg = GENERATION_CONFIG

    meeting_id    = meeting_config["id"]
    min_duration  = gen_cfg["min_duration_seconds"]
    max_pause     = gen_cfg["max_pause_seconds"]
    chars_per_sec = gen_cfg["chars_per_second"]

    # Seed deterministico per riproducibilità nei test
    rng = random.Random(hash(meeting_id) & 0xFFFFFFFF)

    raw_date = meeting_config["date"].replace("Z", "").split("+")[0]
    try:
        base_dt = datetime.fromisoformat(raw_date)
    except ValueError:
        base_dt = datetime(2024, 1, 1, 9, 0, 0)

    transcript = []
    offset_sec = 0

    # Campionamento senza ripetizione delle frasi (se possibile) per maggior realismo
    phrases_pool = SAMPLE_PHRASES.copy()
    rng.shuffle(phrases_pool)
    phrase_cycle = (phrases_pool * ((num_entries // len(phrases_pool)) + 1))[:num_entries]

    for i in range(num_entries):
        participant  = rng.choice(PARTICIPANTS)
        text         = phrase_cycle[i]
        duration_sec = max(min_duration, len(text) // chars_per_sec)
        duration_ms  = duration_sec * 1000

        msg_dt     = base_dt + timedelta(seconds=offset_sec)
        created_at = (
            msg_dt.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{msg_dt.microsecond // 1000:03d}Z"
        )

        transcript.append(TranscriptEntry(
            conversation_turn = i + 1,
            participant_name  = participant.name,
            transcribed_text  = text,
            created_at        = created_at,
            audio_duration_ms = duration_ms,
            user_id           = participant.id,
            room_id           = meeting_id,
            session_id        = f"{meeting_id}_sess",
            language          = "en",
            contains_trigger  = False,
            trigger_words     = [],
        ))

        offset_sec += duration_sec + rng.randint(1, max_pause)

    return transcript


# ─────────────────────────────────────────────────────────────────────────────
# INIZIALIZZAZIONE DATABASE MOCK (con generation_overrides)
# ─────────────────────────────────────────────────────────────────────────────

MOCK_MEETINGS: dict = {}

# Sessioni live in-memory:
# { meeting_id: { started_at: datetime, speed: float } }
# speed=1.0 → tempo reale, speed=10.0 → 10x accelerato (per demo)
MEETING_SESSIONS: dict = {}

def _ts_to_epoch(ts: str) -> float:
    """Converte ISO 8601 in unix epoch float."""
    from datetime import timezone
    try:
        return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
    except Exception:
        return 0.0

def _meeting_elapsed(meeting_id: str) -> float:
    """Secondi di meeting trascorsi (considerando speed)."""
    session = MEETING_SESSIONS.get(meeting_id)
    if not session:
        return -1.0  # not started
    elapsed = (datetime.now() - session['started_at']).total_seconds()
    return elapsed * session['speed']

def _available_transcript(meeting_id: str) -> List['TranscriptEntry']:
    """
    Restituisce solo i messaggi 'già avvenuti' in base al clock del meeting.
    Se il meeting non è started → nessun messaggio.
    Se il meeting è ended (elapsed >= durata) → tutti i messaggi.
    """
    transcript = _get_transcript(meeting_id)
    elapsed = _meeting_elapsed(meeting_id)
    if elapsed < 0:
        return []   # meeting not started
    if not transcript:
        return []
    base = _ts_to_epoch(transcript[0].created_at)
    return [m for m in transcript if _ts_to_epoch(m.created_at) - base <= elapsed]

for _meeting_cfg in MEETINGS_CONFIG:
    _mid     = _meeting_cfg["id"]
    _override = GENERATION_OVERRIDES.get(_mid, {})
    _effective_gen = {**GENERATION_CONFIG, **_override}

    MOCK_MEETINGS[_mid] = {
        "metadata": MeetingMetadata(
            participants=PARTICIPANTS,
            date=_meeting_cfg["date"],
        ),
        "transcript": generate_mock_transcript(
            _meeting_cfg["num_entries"],
            _meeting_cfg,
            gen_cfg=_effective_gen,
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global sentiment_predictor, toxicity_detector
    sentiment_predictor = SentimentPredictor(SENTIMENT_SERVICE_URL)
    toxicity_detector   = ToxicityDetector(TOXICITY_SERVICE_URL)
    print(f"[startup] Sentiment  → {SENTIMENT_SERVICE_URL}")
    print(f"[startup] Toxicity   → {TOXICITY_SERVICE_URL}")
    print(f"[startup] Meetings   → {list(MOCK_MEETINGS.keys())}")
    yield
    print("[shutdown] Gateway fermato")


# ─────────────────────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Meeting Intelligence Gateway",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _get_transcript(meeting_id: str) -> List[TranscriptEntry]:
    meeting = MOCK_MEETINGS.get(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meeting_id} not found",
        )
    return meeting["transcript"]


async def fetch_transcript_from_arianna(room_id: str, **params) -> List[TranscriptEntry]:
    # httpx non filtra i None — filtriamo prima per evitare "userId=None" nella query string
    clean_params = {k: v for k, v in params.items() if v is not None and v is not False}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=25.0, write=5.0, pool=5.0)) as client:
            r = await client.get(
                f"{ARIANNA_BASE_URL}/api/rooms/{room_id}/transcriptions",
                params=clean_params,
            )
            r.raise_for_status()
            body = r.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=http_status.HTTP_504_GATEWAY_TIMEOUT,
                            detail=f"Arianna non risponde (timeout) per la stanza {room_id}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code,
                            detail=f"Arianna ha restituito errore {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY,
                            detail=f"Errore di comunicazione con Arianna: {str(e)}")

    if not isinstance(body, dict) or "transcriptions" not in body:
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY,
                            detail="Risposta Arianna in formato non atteso")
    raw = body.get("transcriptions", [])
    return [
        TranscriptEntry(
            conversation_turn = e["conversation_turn"],
            participant_name  = e["participant_name"],
            transcribed_text  = e["transcribed_text"],
            created_at        = e["created_at"],
            audio_duration_ms = e.get("audio_duration_ms", 3000),
            user_id           = e.get("user_id", ""),
            room_id           = e.get("room_id", room_id),
            session_id        = e.get("session_id", ""),
            language          = e.get("language", "en"),
            contains_trigger  = e.get("contains_trigger", False),
            trigger_words     = e.get("trigger_words", []),
        )
        for e in raw
    ]


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — ROOT & HEALTH
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Root — informazioni gateway."""
    return {
        "status":       "ok",
        "version":      "2.0.0",
        "architecture": "microservices",
        "service":      "meeting-intelligence-gateway",
    }


@app.get("/health")
def health():
    """Health check."""
    return {
        "status":         "healthy",
        "service":        "backend-gateway",
        "use_arianna":    USE_ARIANNA,
        "sentiment_mock": sentiment_predictor._use_mock if sentiment_predictor else None,
        "toxicity_mock":  toxicity_detector._use_mock   if toxicity_detector  else None,
        "meetings":       list(MOCK_MEETINGS.keys()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — UTILITY
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/participants")
def list_participants():
    return {"participants": PARTICIPANTS}


@app.get("/meetings")
def list_meetings():
    return {
        "meetings": [
            {
                "id":                mid,
                "date":              mdata["metadata"].date,
                "participants_count": len(mdata["metadata"].participants),
                "messages_count":    len(mdata["transcript"]),
            }
            for mid, mdata in MOCK_MEETINGS.items()
        ]
    }


@app.get("/services/status")
async def get_services_status():
    """Stato dei microservizi BERT."""
    bert_ok = False
    tox_ok  = False

    async def _ping(url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{url}/health")
                return r.status_code == 200
        except Exception:
            return False

    bert_ok, tox_ok = await asyncio.gather(
        _ping(SENTIMENT_SERVICE_URL),
        _ping(TOXICITY_SERVICE_URL),
    )

    return {
        "bert_sentiment": {
            "healthy": bert_ok,
            "url":     SENTIMENT_SERVICE_URL,
            "port":    5001,
        },
        "bert_toxicity": {
            "healthy": tox_ok,
            "url":     TOXICITY_SERVICE_URL,
            "port":    5003,
        },
    }


@app.get("/config")
def get_config():
    """Endpoint di debug — configurazione corrente."""
    return {
        "sample_phrases": SAMPLE_PHRASES[:5],
        "participants":   PARTICIPANTS_CONFIG,
        "meetings":       MEETINGS_CONFIG,
        "generation":     GENERATION_CONFIG,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — MEETINGS
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — LIVE MEETING SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/meeting/{meetingId}/start")
def start_meeting(
    meetingId: str,
    speed:       float = Query(1.0, description="Fattore velocità: 1.0=reale, 5.0=5× accelerato"),
    join_offset: float = Query(0.0, description="Secondi di meeting da cui entrare (simulazione join in corso)"),
):
    """
    Avvia il clock del meeting. Da questo momento il backend rilascia
    progressivamente i messaggi in base al tempo trascorso.
    Idempotente: ri-chiamare con lo stesso meetingId riavvia il meeting.
    """
    if meetingId not in MOCK_MEETINGS:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meetingId} not found",
        )
    # join_offset: permette al frontend di simulare l'ingresso a meeting in corso.
    # Il backend retrodatata started_at di join_offset secondi (diviso speed),
    # così al primo poll il meeting risulta già in corso di join_offset secondi.
    MEETING_SESSIONS[meetingId] = {
        "started_at": datetime.now() - timedelta(seconds=join_offset / max(0.1, min(speed, 100.0))),
        "speed":      max(0.1, min(speed, 100.0)),
    }
    transcript = MOCK_MEETINGS[meetingId]["transcript"]
    total_sec  = (
        _ts_to_epoch(transcript[-1].created_at) - _ts_to_epoch(transcript[0].created_at)
    ) if transcript else 0.0

    print(f"[live] Meeting {meetingId} avviato · speed={speed}x · durata={total_sec:.0f}s")
    return {
        "status":       "started",
        "meeting_id":   meetingId,
        "speed":        speed,
        "total_seconds": round(total_sec, 1),
        "started_at":   MEETING_SESSIONS[meetingId]["started_at"].isoformat(),
    }


@app.get("/meeting/{meetingId}/status")
def get_meeting_live_status(meetingId: str):
    """
    Stato live del meeting:
    - not_started: il meeting non è ancora avviato
    - active:      il meeting è in corso, messages_available < messages_total
    - ended:       tutti i messaggi sono stati rilasciati
    """
    if meetingId not in MOCK_MEETINGS:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meetingId} not found",
        )
    transcript = MOCK_MEETINGS[meetingId]["transcript"]
    total_msgs = len(transcript)

    session = MEETING_SESSIONS.get(meetingId)
    if not session:
        return {
            "status":             "not_started",
            "meeting_id":         meetingId,
            "messages_available": 0,
            "messages_total":     total_msgs,
            "elapsed_seconds":    0,
            "total_seconds":      round(
                (_ts_to_epoch(transcript[-1].created_at) - _ts_to_epoch(transcript[0].created_at))
                if transcript else 0.0, 1
            ),
            "progress_pct":       0,
        }

    elapsed  = _meeting_elapsed(meetingId)
    available = _available_transcript(meetingId)
    total_sec = (
        _ts_to_epoch(transcript[-1].created_at) - _ts_to_epoch(transcript[0].created_at)
    ) if transcript else 1.0

    is_ended = elapsed >= total_sec
    return {
        "status":             "ended" if is_ended else "active",
        "meeting_id":         meetingId,
        "speed":              session["speed"],
        "messages_available": len(available),
        "messages_total":     total_msgs,
        "elapsed_seconds":    round(elapsed, 1),
        "total_seconds":      round(total_sec, 1),
        "progress_pct":       round(min(elapsed / total_sec * 100, 100), 1) if total_sec > 0 else 0,
        "started_at":         session["started_at"].isoformat(),
    }


@app.post("/meeting/{meetingId}/reset")
def reset_meeting(meetingId: str):
    """Rimuove la sessione live — il meeting torna a not_started."""
    if meetingId not in MOCK_MEETINGS:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND)
    MEETING_SESSIONS.pop(meetingId, None)
    return {"status": "reset", "meeting_id": meetingId}


@app.get("/meeting/{meetingId}", response_model=MeetingResponse)
def get_meeting(meetingId: str):
    meeting = MOCK_MEETINGS.get(meetingId)
    if not meeting:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meetingId} not found",
        )
    return MeetingResponse(metadata=meeting["metadata"])


@app.get("/meeting/{meetingId}/transcript/", response_model=TranscriptResponse)
def get_transcript_full(meetingId: str):
    transcript = _get_transcript(meetingId)
    return TranscriptResponse(
        transcript=transcript,
        metadata=TranscriptMetadata(language="en"),
    )


@app.get("/meeting/{meetingId}/transcript")
def get_transcript_filtered(
    meetingId: str,
    userId:    Optional[str] = Query(None, description="Filtra per user_id (Arianna)"),
):
    transcript = _get_transcript(meetingId)
    if userId:
        name = next((p.name for p in PARTICIPANTS if p.id == userId), None)
        if name:
            transcript = [e for e in transcript if e.participant_name == name]
    return {"transcript": transcript, "metadata": {"language": "en"}}


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — UNIFIED ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

_LABEL_SIGN = {
    SentimentLabel.POSITIVE:  1.0,
    SentimentLabel.NEUTRAL:   0.0,
    SentimentLabel.NEGATIVE: -1.0,
}


@app.get("/meeting/{meetingId}/analysis")
async def get_transcript_with_unified_analysis(
    meetingId:    str,
    userId:       Optional[str] = Query(None,  description="Filtra per user_id (Arianna)"),
    triggersOnly: bool          = Query(False, description="Solo contains_trigger=true"),
    startTime:    Optional[str] = Query(None,  description="ISO 8601 — created_at >= startTime"),
    endTime:      Optional[str] = Query(None,  description="ISO 8601 — created_at <= endTime"),
    search:       Optional[str] = Query(None,  description="Full-text su transcribed_text"),
    limit:        int           = Query(200,   description="Max messaggi"),
    offset:       int           = Query(0,     description="Offset paginazione"),
):
    if USE_ARIANNA:
        transcript = await fetch_transcript_from_arianna(
            meetingId, userId=userId, triggersOnly=triggersOnly,
            startTime=startTime, endTime=endTime,
            search=search, limit=limit, offset=offset,
        )
    else:
        # In modalità mock con sessione live attiva, rispetta il clock del meeting.
        # Se il meeting non è stato avviato, restituisce tutti i messaggi (modalità review).
        session = MEETING_SESSIONS.get(meetingId)
        if session:
            transcript = _available_transcript(meetingId)
        else:
            transcript = _get_transcript(meetingId)

        if search:
            transcript = [e for e in transcript if search.lower() in e.transcribed_text.lower()]
        elif triggersOnly:
            transcript = [e for e in transcript if e.contains_trigger]
        elif startTime and endTime:
            transcript = [e for e in transcript if startTime <= e.created_at <= endTime]

        if userId:
            name = next((p.name for p in PARTICIPANTS if p.id == userId), None)
            if name:
                transcript = [e for e in transcript if e.participant_name == name]

        transcript = transcript[offset: offset + limit]

    if not transcript:
        return {
            "transcript": [],
            "metadata": {
                "language": "en",
                "stats": {"total_messages": 0, "sentiment": {}, "toxicity": {}},
            },
        }

    texts = [entry.transcribed_text for entry in transcript]

    # Chiamate BERT in parallelo — dimezza la latenza
    sentiment_results, toxicity_results = await asyncio.gather(
        sentiment_predictor.predict_batch(texts),
        toxicity_detector.detect_batch(texts),
    )

    if len(sentiment_results.predictions) != len(transcript):
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sentiment predictions count mismatch",
        )
    if len(toxicity_results.results) != len(transcript):
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Toxicity results count mismatch",
        )

    enriched_transcript = []
    sentiment_positive = sentiment_neutral = sentiment_negative = 0
    total_sentiment_score = total_polarity_score = 0.0
    toxic_count = severity_low = severity_medium = severity_high = 0
    total_toxicity_score = 0.0

    for i, entry in enumerate(transcript):
        sent  = sentiment_results.predictions[i]
        tox   = toxicity_results.results[i]

        entry_dict = entry.dict() if hasattr(entry, "dict") else entry.model_dump()

        label_sign   = _LABEL_SIGN[sent.label]
        msg_polarity = round(label_sign * sent.score * sent.confidence, 4)

        entry_dict["sentiment"] = {
            "label":      sent.label.value,
            "score":      round(sent.score, 4),
            "confidence": round(sent.confidence, 4),
            "polarity":   msg_polarity,
        }
        entry_dict["confidence_score"] = round(sent.confidence, 4)

        entry_dict["toxicity"] = {
            "is_toxic":       tox.is_toxic,
            "toxicity_score": round(tox.toxicity_score, 4),
            "severity":       tox.severity.value,
            "confidence":     round(tox.confidence, 4),
        }

        enriched_transcript.append(entry_dict)

        if sent.label == SentimentLabel.POSITIVE:
            sentiment_positive += 1
        elif sent.label == SentimentLabel.NEUTRAL:
            sentiment_neutral  += 1
        else:
            sentiment_negative += 1
        total_sentiment_score += sent.score
        total_polarity_score  += msg_polarity

        if tox.is_toxic:
            toxic_count += 1
        if tox.severity == ToxicitySeverity.LOW:
            severity_low    += 1
        elif tox.severity == ToxicitySeverity.MEDIUM:
            severity_medium += 1
        else:
            severity_high   += 1
        total_toxicity_score += tox.toxicity_score

    n = len(enriched_transcript)

    return {
        "transcript": enriched_transcript,
        "metadata": {
            "language": "en",
            "stats": {
                "total_messages": n,
                "sentiment": {
                    "distribution": {
                        "positive": sentiment_positive,
                        "neutral":  sentiment_neutral,
                        "negative": sentiment_negative,
                    },
                    "average_score":    round(total_sentiment_score / n, 3),
                    "positive_ratio":   round(sentiment_positive    / n, 3),
                    "average_polarity": round(total_polarity_score  / n, 4),
                },
                "toxicity": {
                    "toxic_count": toxic_count,
                    "toxic_ratio": round(toxic_count / n, 3),
                    "severity_distribution": {
                        "low":    severity_low,
                        "medium": severity_medium,
                        "high":   severity_high,
                    },
                    "average_toxicity_score": round(total_toxicity_score / n, 3),
                },
            },
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — SENTIMENT
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/sentiment/analyze", response_model=NormalizedPrediction)
async def analyze_sentiment(request: UnifiedAnalysisRequest):
    return await sentiment_predictor.predict(request.text)


@app.post("/sentiment/batch", response_model=BatchPrediction)
async def analyze_sentiment_batch(request: BatchUnifiedAnalysisRequest):
    return await sentiment_predictor.predict_batch(request.texts)


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — TOXICITY
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/toxicity/detect", response_model=ToxicityResult)
async def detect_toxicity(request: ToxicityAnalysisRequest):
    return await toxicity_detector.detect(request.text)


@app.post("/toxicity/batch", response_model=BatchToxicityResult)
async def detect_toxicity_batch(request: BatchToxicityRequest):
    return await toxicity_detector.detect_batch(request.texts)


@app.post("/toxicity/detect/batch", response_model=BatchToxicityResult)
async def detect_toxicity_batch_alias(request: BatchToxicityRequest):
    """Alias per compatibilità con i test esistenti."""
    return await toxicity_detector.detect_batch(request.texts)