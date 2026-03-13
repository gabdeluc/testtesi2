"""
backend/main.py
===============
Gateway FastAPI — Meeting Intelligence
Versione con:
  • Campi schema Arianna-compatibili (conversation_turn, participant_name,
    transcribed_text, created_at, audio_duration_ms, …)
  • Formula polarity:  sign(label) × score × confidence  →  [-1, +1]
  • Flag USE_ARIANNA (default false) per futura integrazione live
"""

import os
import random
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi import status as http_status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config.config_loader import config_loader   # backend/config_loader.py  (invariato)

# ─────────────────────────────────────────────────────────────────────────────
# COSTANTI / ENV
# ─────────────────────────────────────────────────────────────────────────────

SENTIMENT_SERVICE_URL = os.getenv("BERT_SERVICE_URL", "http://bert-sentiment:5001")
TOXICITY_SERVICE_URL  = os.getenv("TOXICITY_SERVICE_URL",  "http://bert-toxicity:5003")

# Fase 2: set USE_ARIANNA=true in .env per usare l'API live di Arianna
USE_ARIANNA     = os.getenv("USE_ARIANNA",     "false").lower() == "true"
ARIANNA_BASE_URL = os.getenv("ARIANNA_BASE_URL", "http://arianna-host:3000")

# ─────────────────────────────────────────────────────────────────────────────
# ENUMERAZIONI
# ─────────────────────────────────────────────────────────────────────────────

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
    results:       List[ToxicityResult]
    total_detected: int
    toxic_ratio:    float


# ─────────────────────────────────────────────────────────────────────────────
# MODELLI PYDANTIC — DOMINIO (schema Arianna-compatibile)
# ─────────────────────────────────────────────────────────────────────────────

class Participant(BaseModel):
    id:   str
    name: str
    role: str = "participant"


class TranscriptEntry(BaseModel):
    """
    Schema allineato al formato Arianna
    GET /api/rooms/:roomId/transcriptions
    """
    # ── Campi Arianna ──────────────────────────────────────────────
    conversation_turn: int                    # era: uid
    participant_name:  str                    # era: nickname
    transcribed_text:  str                    # era: text
    created_at:        str                    # era: from  — ISO 8601 assoluto
    audio_duration_ms: int                    # era: to    — durata in ms

    # ── Campi Arianna aggiuntivi ───────────────────────────────────
    user_id:          str       = ""          # Participant.id
    room_id:          str       = ""          # meeting_id
    session_id:       str       = ""          # "<meeting_id>_sess"
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


# ── Request models per gli endpoint di analisi ────────────────────

class UnifiedAnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class BatchUnifiedAnalysisRequest(BaseModel):
    texts: List[str] = Field(..., max_items=100)


class ToxicityAnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class BatchToxicityRequest(BaseModel):
    texts: List[str] = Field(..., max_items=100)


# ─────────────────────────────────────────────────────────────────────────────
# MOCK BERT — usato quando i microservizi non sono raggiungibili
# ─────────────────────────────────────────────────────────────────────────────

# Frasi chiave per mock sentiment rule-based
_POS_KEYWORDS = {"great","good","excellent","perfect","love","thanks","helpful",
                 "nice","well","clean","easy","fast","improved","appreciate",
                 "incredible","joy","happy","fix","solved","works","amazing"}
_NEG_KEYWORDS = {"bad","wrong","broken","fail","error","slow","crash","bug",
                 "issue","problem","useless","stupid","garbage","terrible",
                 "awful","hate","worse","ugly","disappointing","sucks","shut"}
_TOX_KEYWORDS = {"stupid","idiot","garbage","shut up","useless","hate","awful",
                 "damn","crap","jerk","moron"}

def _mock_sentiment(text: str) -> NormalizedPrediction:
    """Sentiment rule-based deterministico basato su parole chiave."""
    lower = text.lower()
    words = set(re.findall(r"\w+", lower))
    pos = len(words & _POS_KEYWORDS)
    neg = len(words & _NEG_KEYWORDS)
    if pos > neg:
        label, score = SentimentLabel.POSITIVE, 0.55 + min(pos * 0.08, 0.40)
    elif neg > pos:
        label, score = SentimentLabel.NEGATIVE, 0.55 + min(neg * 0.08, 0.40)
    else:
        label, score = SentimentLabel.NEUTRAL, 0.50 + random.uniform(0, 0.15)
    confidence = round(0.70 + random.uniform(0, 0.25), 4)
    score      = round(min(score, 0.98), 4)
    return NormalizedPrediction(
        label=label, score=score, confidence=confidence,
        raw_output={"mock": True}, model_type="sentiment"
    )

def _mock_toxicity(text: str) -> ToxicityResult:
    """Toxicity rule-based deterministico basato su parole chiave."""
    lower = text.lower()
    words = set(re.findall(r"\w+", lower))
    hits  = len(words & _TOX_KEYWORDS)
    if hits >= 2:
        is_toxic, score, severity = True,  0.80 + random.uniform(0, 0.15), ToxicitySeverity.HIGH
    elif hits == 1:
        is_toxic, score, severity = True,  0.55 + random.uniform(0, 0.20), ToxicitySeverity.MEDIUM
    else:
        is_toxic, score, severity = False, random.uniform(0.02, 0.25),     ToxicitySeverity.LOW
    confidence = round(0.72 + random.uniform(0, 0.23), 4)
    score      = round(min(score, 0.98), 4)
    return ToxicityResult(
        is_toxic=is_toxic, toxicity_score=score, severity=severity,
        confidence=confidence, raw_output={"mock": True}, model_type="toxicity"
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT BERT MICROSERVICES  (con fallback automatico al mock)
# ─────────────────────────────────────────────────────────────────────────────

class SentimentPredictor:
    """
    HTTP client verso il microservizio BERT Sentiment.
    Se il servizio non è raggiungibile (ConnectError / timeout),
    cade automaticamente sul predictor rule-based mock — la dashboard
    rimane funzionante in ogni caso.
    """

    def __init__(self, base_url: str):
        self.base_url   = base_url
        self._use_mock  = False   # diventa True al primo ConnectError

    async def predict(self, text: str) -> NormalizedPrediction:
        if self._use_mock:
            return _mock_sentiment(text)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(f"{self.base_url}/predict", json={"text": text})
                r.raise_for_status()
                return NormalizedPrediction(**r.json())
        except (httpx.ConnectError, httpx.TimeoutException, Exception):
            print(f"[sentiment] service unreachable at {self.base_url} — switching to mock")
            self._use_mock = True
            return _mock_sentiment(text)

    async def predict_batch(self, texts: List[str]) -> BatchPrediction:
        if self._use_mock:
            return self._mock_batch(texts)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{self.base_url}/predict/batch",
                    json={"texts": texts}
                )
                r.raise_for_status()
                return BatchPrediction(**r.json())
        except (httpx.ConnectError, httpx.TimeoutException, Exception):
            print(f"[sentiment] service unreachable at {self.base_url} — switching to mock")
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
    """
    HTTP client verso il microservizio BERT Toxicity.
    Fallback automatico al rilevatore rule-based mock se il servizio
    non è raggiungibile.
    """

    def __init__(self, base_url: str):
        self.base_url  = base_url
        self._use_mock = False

    async def detect(self, text: str) -> ToxicityResult:
        if self._use_mock:
            return _mock_toxicity(text)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(f"{self.base_url}/detect", json={"text": text})
                r.raise_for_status()
                return ToxicityResult(**r.json())
        except (httpx.ConnectError, httpx.TimeoutException, Exception):
            print(f"[toxicity] service unreachable at {self.base_url} — switching to mock")
            self._use_mock = True
            return _mock_toxicity(text)

    async def detect_batch(self, texts: List[str]) -> BatchToxicityResult:
        if self._use_mock:
            return self._mock_batch(texts)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{self.base_url}/detect/batch",
                    json={"texts": texts}
                )
                r.raise_for_status()
                return BatchToxicityResult(**r.json())
        except (httpx.ConnectError, httpx.TimeoutException, Exception):
            print(f"[toxicity] service unreachable at {self.base_url} — switching to mock")
            self._use_mock = True
            return self._mock_batch(texts)

    def _mock_batch(self, texts: List[str]) -> BatchToxicityResult:
        results    = [_mock_toxicity(t) for t in texts]
        toxic_n    = sum(1 for r in results if r.is_toxic)
        toxic_ratio = round(toxic_n / len(results), 4) if results else 0.0
        return BatchToxicityResult(
            results=results,
            total_detected=toxic_n,
            toxic_ratio=toxic_ratio,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ISTANZE PREDICTOR  (inizializzate nel lifespan)
# ─────────────────────────────────────────────────────────────────────────────

sentiment_predictor: SentimentPredictor = None
toxicity_detector:   ToxicityDetector   = None


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_PHRASES     = config_loader.get_sample_phrases()
PARTICIPANTS_CONFIG = config_loader.get_participants()
MEETINGS_CONFIG     = config_loader.get_meetings()
GENERATION_CONFIG   = config_loader.get_generation_config()

PARTICIPANTS = [Participant(**p) for p in PARTICIPANTS_CONFIG]


# ─────────────────────────────────────────────────────────────────────────────
# GENERAZIONE DATI MOCK
# ─────────────────────────────────────────────────────────────────────────────

def generate_mock_transcript(
    num_entries: int,
    meeting_config: dict
) -> List[TranscriptEntry]:
    """
    Genera transcript mock con messaggi completamente random.
    Pesca da TUTTE le categorie del dataset per simulare variazioni naturali.

    Campi allineati al formato Arianna:
      created_at        — ISO 8601 assoluto basato sulla data del meeting
      audio_duration_ms — durata del turno in millisecondi
    """
    if not PARTICIPANTS:
        raise ValueError("PARTICIPANTS list is empty — cannot generate transcript")
    if not SAMPLE_PHRASES:
        raise ValueError("SAMPLE_PHRASES list is empty — cannot generate transcript")

    meeting_id = meeting_config["id"]

    # Data base dal campo 'date' del meeting (es. "2024-06-01T00:00:00Z")
    # Parsing robusto: supporta "2024-06-01", "2024-06-01T09:00:00", "2024-06-01T09:00:00Z"
    raw_date = meeting_config["date"].replace("Z", "").split("+")[0]
    try:
        base_dt = datetime.fromisoformat(raw_date)
    except ValueError:
        base_dt = datetime(2024, 1, 1, 9, 0, 0)

    min_duration  = GENERATION_CONFIG["min_duration_seconds"]
    max_pause     = GENERATION_CONFIG["max_pause_seconds"]
    chars_per_sec = GENERATION_CONFIG["chars_per_second"]

    transcript    = []
    offset_sec    = 0   # secondi dall'inizio del meeting

    for i in range(num_entries):
        participant  = random.choice(PARTICIPANTS)
        text         = random.choice(SAMPLE_PHRASES)
        duration_sec = max(min_duration, len(text) // chars_per_sec)
        duration_ms  = duration_sec * 1000

        # Timestamp ISO 8601 assoluto
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

        offset_sec += duration_sec + random.randint(1, max_pause)

    return transcript


# ─────────────────────────────────────────────────────────────────────────────
# INIZIALIZZAZIONE DATABASE MOCK
# ─────────────────────────────────────────────────────────────────────────────

MOCK_MEETINGS: dict = {}

for meeting_config in MEETINGS_CONFIG:
    meeting_id = meeting_config["id"]
    MOCK_MEETINGS[meeting_id] = {
        "metadata": MeetingMetadata(
            participants=PARTICIPANTS,
            date=meeting_config["date"]
        ),
        "transcript": generate_mock_transcript(
            meeting_config["num_entries"],
            meeting_config
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN (STARTUP / SHUTDOWN)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global sentiment_predictor, toxicity_detector
    sentiment_predictor = SentimentPredictor(SENTIMENT_SERVICE_URL)
    toxicity_detector   = ToxicityDetector(TOXICITY_SERVICE_URL)
    print(f"[startup] Sentiment  → {SENTIMENT_SERVICE_URL}")
    print(f"[startup] Toxicity   → {TOXICITY_SERVICE_URL}")
    print(f"[startup] USE_ARIANNA = {USE_ARIANNA}")
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — Arianna Fase 2
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_transcript_from_arianna(room_id: str, **params) -> List[TranscriptEntry]:
    """
    Chiama GET /api/rooms/:roomId/transcriptions di Arianna
    e mappa i campi nel formato interno.
    Attivo solo quando USE_ARIANNA=true.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{ARIANNA_BASE_URL}/api/rooms/{room_id}/transcriptions",
            params=params,
        )
        r.raise_for_status()
        raw = r.json().get("transcriptions", [])

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


def _get_transcript(meeting_id: str) -> List[TranscriptEntry]:
    """Ritorna transcript mock (USE_ARIANNA=false, default)."""
    meeting = MOCK_MEETINGS.get(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meeting_id} not found",
        )
    return meeting["transcript"]


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — MEETINGS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/meetings")
def list_meetings():
    """Elenco meeting disponibili."""
    meetings = []
    for mid, mdata in MOCK_MEETINGS.items():
        meetings.append({
            "id":   mid,
            "date": mdata["metadata"].date,
            "num_participants": len(mdata["metadata"].participants),
        })
    return {"meetings": meetings}


@app.get("/meeting/{meetingId}", response_model=MeetingResponse)
def get_meeting(meetingId: str):
    """Metadati di un singolo meeting."""
    meeting = MOCK_MEETINGS.get(meetingId)
    if not meeting:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meetingId} not found",
        )
    return MeetingResponse(metadata=meeting["metadata"])


@app.get("/meeting/{meetingId}/transcript/", response_model=TranscriptResponse)
def get_transcript_full(meetingId: str):
    """Transcript completo (senza analisi)."""
    transcript = _get_transcript(meetingId)
    return TranscriptResponse(
        transcript=transcript,
        metadata=TranscriptMetadata(language="en"),
    )


@app.get("/meeting/{meetingId}/transcript")
def get_transcript_filtered(
    meetingId:    str,
    userId:       Optional[str] = Query(None, description="Filtra per user_id partecipante"),
):
    """Transcript con filtro opzionale per partecipante (userId = Arianna user_id)."""
    transcript = _get_transcript(meetingId)

    if userId:
        participant_name = next(
            (p.name for p in PARTICIPANTS if p.id == userId), None
        )
        if participant_name:
            transcript = [e for e in transcript if e.participant_name == participant_name]

    return {"transcript": transcript, "metadata": {"language": "en"}}


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — UNIFIED ANALYSIS  (transcript + BERT sentiment + toxicity)
# ─────────────────────────────────────────────────────────────────────────────

# Mappa segno per la formula polarity
_LABEL_SIGN = {
    SentimentLabel.POSITIVE:  1.0,
    SentimentLabel.NEUTRAL:   0.0,
    SentimentLabel.NEGATIVE: -1.0,
}


@app.get("/meeting/{meetingId}/analysis")
async def get_transcript_with_unified_analysis(
    meetingId:    str,
    userId:       Optional[str] = Query(None,  description="Filtra per user_id (Arianna)"),
    triggersOnly: bool          = Query(False, description="Solo messaggi con contains_trigger=true"),
    startTime:    Optional[str] = Query(None,  description="ISO 8601 — created_at >= startTime"),
    endTime:      Optional[str] = Query(None,  description="ISO 8601 — created_at <= endTime"),
    search:       Optional[str] = Query(None,  description="Full-text su transcribed_text"),
    limit:        int           = Query(200,   description="Max messaggi (default 200)"),
    offset:       int           = Query(0,     description="Paginazione offset"),
):
    """
    Transcript + SENTIMENT + TOXICITY analysis.

    Priorità filtri (allineata ad Arianna):
      1. search        — full-text su transcribed_text
      2. triggersOnly  — solo contains_trigger=true
      3. startTime + endTime — range su created_at
      4. userId        — filtro per partecipante
    """
    # ── 1. Sorgente dati ────────────────────────────────────────────
    if USE_ARIANNA:
        transcript = await fetch_transcript_from_arianna(
            meetingId,
            userId=userId,
            triggersOnly=triggersOnly,
            startTime=startTime,
            endTime=endTime,
            search=search,
            limit=limit,
            offset=offset,
        )
    else:
        transcript = _get_transcript(meetingId)

        # Filtri applicati lato gateway sul mock
        if search:
            transcript = [e for e in transcript
                          if search.lower() in e.transcribed_text.lower()]
        elif triggersOnly:
            transcript = [e for e in transcript if e.contains_trigger]
        elif startTime and endTime:
            transcript = [e for e in transcript
                          if startTime <= e.created_at <= endTime]

        if userId:
            participant_name = next(
                (p.name for p in PARTICIPANTS if p.id == userId), None
            )
            if participant_name:
                transcript = [e for e in transcript
                              if e.participant_name == participant_name]

        transcript = transcript[offset: offset + limit]

    # ── 2. Risposta vuota se nessun messaggio ────────────────────────
    if not transcript:
        return {
            "transcript": [],
            "metadata": {
                "language": "en",
                "formats": {
                    "sentiment": "normalized (positive/neutral/negative, score 0-1, polarity -1..+1)",
                    "toxicity":  "dedicated (is_toxic bool, severity low/medium/high, score 0-1)",
                },
                "stats": {
                    "total_messages": 0,
                    "sentiment": {},
                    "toxicity":  {},
                },
            },
        }

    # ── 3. Estrai testi per BERT ─────────────────────────────────────
    texts = [entry.transcribed_text for entry in transcript]

    # ── 4. Sentiment prediction (batch) ─────────────────────────────
    sentiment_results = await sentiment_predictor.predict_batch(texts)

    # ── 5. Toxicity detection (batch) ───────────────────────────────
    toxicity_results = await toxicity_detector.detect_batch(texts)

    # Validazione lunghezze
    if len(sentiment_results.predictions) != len(transcript):
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Sentiment predictions mismatch: "
                f"expected {len(transcript)}, got {len(sentiment_results.predictions)}"
            ),
        )
    if len(toxicity_results.results) != len(transcript):
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Toxicity results mismatch: "
                f"expected {len(transcript)}, got {len(toxicity_results.results)}"
            ),
        )

    # ── 6. Combina transcript con analisi ────────────────────────────
    enriched_transcript = []

    # Accumulatori sentiment
    sentiment_positive    = 0
    sentiment_neutral     = 0
    sentiment_negative    = 0
    total_sentiment_score = 0.0
    total_polarity_score  = 0.0   # ← formula polarity

    # Accumulatori toxicity
    toxic_count          = 0
    severity_low         = 0
    severity_medium      = 0
    severity_high        = 0
    total_toxicity_score = 0.0

    for i, entry in enumerate(transcript):
        sent_pred  = sentiment_results.predictions[i]
        tox_result = toxicity_results.results[i]

        # Serializza l'entry (campi Arianna)
        # dict() funziona sia in Pydantic v1 che v2
        entry_dict = entry.dict() if hasattr(entry, 'dict') else entry.model_dump()

        # ── Polarity per questo messaggio ─────────────────────────
        # Formula: sign(label) × score × confidence  →  [-1, +1]
        label_sign  = _LABEL_SIGN[sent_pred.label]
        msg_polarity = round(label_sign * sent_pred.score * sent_pred.confidence, 4)

        # ── Sentiment enrichment ──────────────────────────────────
        entry_dict["sentiment"] = {
            "label":      sent_pred.label.value,
            "score":      round(sent_pred.score, 4),
            "confidence": round(sent_pred.confidence, 4),
            "polarity":   msg_polarity,
        }

        # confidence_score Arianna = proxy della confidence BERT
        entry_dict["confidence_score"] = round(sent_pred.confidence, 4)

        # ── Toxicity enrichment ───────────────────────────────────
        entry_dict["toxicity"] = {
            "is_toxic":       tox_result.is_toxic,
            "toxicity_score": round(tox_result.toxicity_score, 4),
            "severity":       tox_result.severity.value,
            "confidence":     round(tox_result.confidence, 4),
        }

        enriched_transcript.append(entry_dict)

        # ── Accumula stats sentiment ──────────────────────────────
        if sent_pred.label == SentimentLabel.POSITIVE:
            sentiment_positive += 1
        elif sent_pred.label == SentimentLabel.NEUTRAL:
            sentiment_neutral += 1
        else:
            sentiment_negative += 1
        total_sentiment_score += sent_pred.score
        total_polarity_score  += msg_polarity

        # ── Accumula stats toxicity ───────────────────────────────
        if tox_result.is_toxic:
            toxic_count += 1
        if tox_result.severity == ToxicitySeverity.LOW:
            severity_low += 1
        elif tox_result.severity == ToxicitySeverity.MEDIUM:
            severity_medium += 1
        else:
            severity_high += 1
        total_toxicity_score += tox_result.toxicity_score

    # ── 7. Calcola statistiche aggregate ────────────────────────────
    num_messages = len(enriched_transcript)

    return {
        "transcript": enriched_transcript,
        "metadata": {
            "language": "en",
            "formats": {
                "sentiment": (
                    "normalized (positive/neutral/negative, "
                    "score 0-1, polarity -1..+1 weighted by confidence)"
                ),
                "toxicity": (
                    "dedicated (is_toxic bool, severity low/medium/high, score 0-1)"
                ),
            },
            "stats": {
                "total_messages": num_messages,
                "sentiment": {
                    "distribution": {
                        "positive": sentiment_positive,
                        "neutral":  sentiment_neutral,
                        "negative": sentiment_negative,
                    },
                    # backward-compat
                    "average_score":  round(total_sentiment_score / num_messages, 3),
                    "positive_ratio": round(sentiment_positive    / num_messages, 3),
                    # metrica corretta su scala bipolare [-1, +1]
                    # +1 = unanimemente positivo con massima confidence
                    # -1 = unanimemente negativo con massima confidence
                    #  0 = neutro o bilanciato
                    "average_polarity": round(total_polarity_score / num_messages, 4),
                },
                "toxicity": {
                    "toxic_count": toxic_count,
                    "toxic_ratio": round(toxic_count / num_messages, 3),
                    "severity_distribution": {
                        "low":    severity_low,
                        "medium": severity_medium,
                        "high":   severity_high,
                    },
                    "average_toxicity_score": round(total_toxicity_score / num_messages, 3),
                },
            },
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — PARTECIPANTI
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/participants")
def list_participants():
    """Elenco partecipanti disponibili."""
    return {"participants": PARTICIPANTS}


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — SENTIMENT (passthrough al microservizio BERT)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/sentiment/analyze", response_model=NormalizedPrediction)
async def analyze_sentiment(request: UnifiedAnalysisRequest):
    """Analizza sentiment di un singolo testo."""
    return await sentiment_predictor.predict(request.text)


@app.post("/sentiment/batch", response_model=BatchPrediction)
async def analyze_sentiment_batch(request: BatchUnifiedAnalysisRequest):
    """Analizza sentiment in batch (max 100 testi)."""
    return await sentiment_predictor.predict_batch(request.texts)


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — TOXICITY (passthrough al microservizio BERT)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/toxicity/detect", response_model=ToxicityResult)
async def detect_toxicity(request: ToxicityAnalysisRequest):
    """Rileva tossicità di un singolo testo."""
    return await toxicity_detector.detect(request.text)


@app.post("/toxicity/batch", response_model=BatchToxicityResult)
async def detect_toxicity_batch(request: BatchToxicityRequest):
    """Rileva tossicità in batch (max 100 testi)."""
    return await toxicity_detector.detect_batch(request.texts)


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status":            "ok",
        "use_arianna":       USE_ARIANNA,
        "sentiment_mock":    sentiment_predictor._use_mock if sentiment_predictor else None,
        "toxicity_mock":     toxicity_detector._use_mock   if toxicity_detector  else None,
        "meetings":          list(MOCK_MEETINGS.keys()),
    }