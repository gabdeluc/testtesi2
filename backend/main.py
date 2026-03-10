"""
Backend Gateway - API Orchestrator (v3.2)

Orchestratore con:
- SENTIMENT: Abstract Predictor Pattern → positive/neutral/negative
- TOXICITY: Standalone Detector → is_toxic, severity, score

Architecture:
- BERT Sentiment Service: http://bert-sentiment:5001
- BERT Toxicity Service: http://bert-toxicity:5003
"""

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import httpx
import random
import os
from config.config_loader import config_loader
from models import (
    PredictorFactory,
    SentimentPredictor,
    ToxicityDetector,  # Standalone detector
    NormalizedPrediction,
    BatchNormalizedPrediction,
    ToxicityResult,  # Dedicated result
    BatchToxicityResult,
    SentimentLabel,
    ToxicitySeverity
)

# ============================================
# FASTAPI APP SETUP
# ============================================

app = FastAPI(
    title="Meeting Transcript API Gateway",
    description="Backend orchestrator: Sentiment (abstract pattern) + Toxicity (standalone detector)",
    version="3.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# MICROSERVICES CONFIGURATION
# ============================================

BERT_SERVICE_URL = os.getenv("BERT_SERVICE_URL", "http://bert-sentiment:5001")
TOXICITY_SERVICE_URL = os.getenv("TOXICITY_SERVICE_URL", "http://bert-toxicity:5003")

# HTTP client
http_client = httpx.AsyncClient(timeout=30.0)

# Predictor Factory
predictor_factory = PredictorFactory(http_client)

# Global predictors
sentiment_predictor: Optional[SentimentPredictor] = None
toxicity_detector: Optional[ToxicityDetector] = None  # Renamed: detector not predictor

# ============================================
# PYDANTIC MODELS
# ============================================

class TranscriptEntry(BaseModel):
    uid: str
    nickname: str
    text: str
    from_field: str = Field(..., alias="from", description="Timestamp HH:MM:SS.mmm")
    to: str = Field(..., description="Timestamp HH:MM:SS.mmm")

class Participant(BaseModel):
    id: str
    name: str

class MeetingMetadata(BaseModel):
    participants: List[Participant]
    date: str

class TranscriptMetadata(BaseModel):
    language: str

class TranscriptResponse(BaseModel):
    transcript: List[TranscriptEntry]
    metadata: TranscriptMetadata

class MeetingResponse(BaseModel):
    metadata: MeetingMetadata

# Request models for analysis
class UnifiedAnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)

class BatchUnifiedAnalysisRequest(BaseModel):
    texts: List[str] = Field(..., max_items=100)

class ToxicityAnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)

class BatchToxicityRequest(BaseModel):
    texts: List[str] = Field(..., max_items=100)

# ============================================
# LOAD CONFIGURATION
# ============================================

SAMPLE_PHRASES = config_loader.get_sample_phrases()
PARTICIPANTS_CONFIG = config_loader.get_participants()
MEETINGS_CONFIG = config_loader.get_meetings()
GENERATION_CONFIG = config_loader.get_generation_config()

PARTICIPANTS = [Participant(**p) for p in PARTICIPANTS_CONFIG]

# ============================================
# MOCK DATA GENERATION
# ============================================

def generate_mock_transcript(num_entries: int = 20) -> List[TranscriptEntry]:
    """
    Genera transcript mock con messaggi completamente random.
    
    Pesca casualmente da TUTTE le categorie del dataset (positive, neutral, toxic, ecc.)
    per simulare una riunione realistica con variazioni naturali.
    """
    # Fix: Validazione arrays vuoti
    if not PARTICIPANTS:
        raise ValueError("PARTICIPANTS list is empty - cannot generate transcript")
    if not SAMPLE_PHRASES:
        raise ValueError("SAMPLE_PHRASES list is empty - cannot generate transcript")
    
    transcript = []
    current_time = 0
    
    min_duration = GENERATION_CONFIG['min_duration_seconds']
    max_pause = GENERATION_CONFIG['max_pause_seconds']
    chars_per_sec = GENERATION_CONFIG['chars_per_second']
    
    for i in range(num_entries):
        participant = random.choice(PARTICIPANTS)
        text = random.choice(SAMPLE_PHRASES)  # Completamente random dal pool
        duration = max(min_duration, len(text) // chars_per_sec)
        
        from_time = f"{current_time // 3600:02d}:{(current_time % 3600) // 60:02d}:{current_time % 60:02d}.000"
        current_time += duration
        to_time = f"{current_time // 3600:02d}:{(current_time % 3600) // 60:02d}:{current_time % 60:02d}.000"
        
        transcript.append(TranscriptEntry(
            uid=str(12345 + i),
            nickname=participant.name,
            text=text,
            **{"from": from_time},
            to=to_time
        ))
        
        current_time += random.randint(1, max_pause)
    
    return transcript

# Initialize mock database
MOCK_MEETINGS = {}
for meeting_config in MEETINGS_CONFIG:
    meeting_id = meeting_config['id']
    
    MOCK_MEETINGS[meeting_id] = {
        "metadata": MeetingMetadata(
            participants=PARTICIPANTS,
            date=meeting_config['date']
        ),
        "transcript": generate_mock_transcript(meeting_config['num_entries'])
    }

# ============================================
# STARTUP/SHUTDOWN HANDLERS
# ============================================

@app.on_event("startup")
async def startup_event():
    """Inizializza i predictors/detectors all'avvio"""
    global sentiment_predictor, toxicity_detector
    
    sentiment_predictor = predictor_factory.create_sentiment_predictor(BERT_SERVICE_URL)
    toxicity_detector = predictor_factory.create_toxicity_detector(TOXICITY_SERVICE_URL)
    
    print("✅ Models initialized:")
    print(f"   - Sentiment Predictor (abstract): {BERT_SERVICE_URL}")
    print(f"   - Toxicity Detector (standalone): {TOXICITY_SERVICE_URL}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup al shutdown"""
    await http_client.aclose()

# ============================================
# HELPER FUNCTIONS
# ============================================

async def check_service_health(service_url: str) -> bool:
    """Verifica se un servizio è online"""
    try:
        response = await http_client.get(f"{service_url}/health", timeout=5.0)
        return response.status_code == 200
    except:
        return False

# ============================================
# MAIN ENDPOINTS
# ============================================

@app.get("/")
async def root():
    """Root endpoint con informazioni sul gateway"""
    bert_healthy = await check_service_health(BERT_SERVICE_URL)
    toxicity_healthy = await check_service_health(TOXICITY_SERVICE_URL)
    
    return {
        "status": "ok",
        "version": "3.2.0",
        "architecture": "microservices: sentiment (abstract) + toxicity (standalone)",
        "gateway": "FastAPI Backend",
        "services": {
            "bert_sentiment": {
                "url": BERT_SERVICE_URL,
                "healthy": bert_healthy,
                "port": 5001
            },
            "bert_toxicity": {
                "url": TOXICITY_SERVICE_URL,
                "healthy": toxicity_healthy,
                "port": 5003
            }
        },
        "output_formats": {
            "sentiment": {
                "type": "normalized (abstract pattern)",
                "labels": ["positive", "neutral", "negative"],
                "score_range": [0.0, 1.0]
            },
            "toxicity": {
                "type": "dedicated (standalone detector)",
                "fields": ["is_toxic", "toxicity_score", "severity"],
                "severity_levels": ["low", "medium", "high"]
            }
        },
        "endpoints": {
            "meeting": [
                "GET /meeting/{meetingId}",
                "GET /meeting/{meetingId}/transcript/",
                "GET /meeting/{meetingId}/analysis"
            ],
            "sentiment": [
                "POST /sentiment/analyze",
                "POST /sentiment/batch"
            ],
            "toxicity": [
                "POST /toxicity/detect",
                "POST /toxicity/detect/batch"
            ],
            "utility": [
                "GET /participants",
                "GET /meetings",
                "GET /services/status"
            ]
        }
    }

@app.get("/health")
def health_check():
    """Health check per il gateway"""
    return {"status": "healthy", "service": "backend-gateway"}

# ============================================
# MEETING ENDPOINTS
# ============================================

@app.get("/meeting/{meetingId}", response_model=MeetingResponse)
def get_meeting(meetingId: str):
    """Ottieni metadata del meeting"""
    meeting = MOCK_MEETINGS.get(meetingId)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meetingId} not found"
        )
    
    return MeetingResponse(metadata=meeting["metadata"])

@app.get("/meeting/{meetingId}/transcript/", response_model=TranscriptResponse)
def get_transcript_full(meetingId: str):
    """Ottieni transcript completo"""
    meeting = MOCK_MEETINGS.get(meetingId)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meetingId} not found"
        )
    
    return TranscriptResponse(
        transcript=meeting["transcript"],
        metadata=TranscriptMetadata(language="en")
    )

@app.get("/meeting/{meetingId}/transcript")
def get_transcript_filtered(
    meetingId: str,
    participant_id: Optional[str] = None
):
    """Ottieni transcript con filtro opzionale per partecipante"""
    meeting = MOCK_MEETINGS.get(meetingId)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meetingId} not found"
        )
    
    transcript = meeting["transcript"]
    
    if participant_id:
        participant_name = next(
            (p.name for p in PARTICIPANTS if p.id == participant_id),
            None
        )
        if participant_name:
            transcript = [e for e in transcript if e.nickname == participant_name]
    
    return {
        "transcript": transcript,
        "metadata": {"language": "en"}
    }

# ============================================
# UNIFIED ANALYSIS ENDPOINT
# ============================================

@app.get("/meeting/{meetingId}/analysis")
async def get_transcript_with_unified_analysis(
    meetingId: str,
    participant_id: Optional[str] = None
):
    """
    Ottieni transcript con SENTIMENT + TOXICITY analysis.
    
    Output formats:
    - Sentiment: {label: positive/neutral/negative, score: 0-1}
    - Toxicity: {is_toxic: bool, severity: low/medium/high, toxicity_score: 0-1}
    """
    # 1. Ottieni meeting
    meeting = MOCK_MEETINGS.get(meetingId)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meetingId} not found"
        )
    
    transcript = meeting["transcript"]
    
    # 2. Filtra per partecipante se richiesto
    if participant_id:
        participant_name = next(
            (p.name for p in PARTICIPANTS if p.id == participant_id),
            None
        )
        if participant_name:
            transcript = [e for e in transcript if e.nickname == participant_name]
    
    # 3. Estrai testi
    texts = [entry.text for entry in transcript]
    
    if not texts:
        return {
            "transcript": [],
            "metadata": {
                "language": "en",
                "formats": {
                    "sentiment": "normalized (positive/neutral/negative)",
                    "toxicity": "dedicated (is_toxic/severity/score)"
                },
                "stats": {
                    "total_messages": 0,
                    "sentiment": {},
                    "toxicity": {}
                }
            }
        }
    
    # 4. Sentiment prediction (batch)
    sentiment_results = await sentiment_predictor.predict_batch(texts)
    
    # 5. Toxicity detection (batch) - NUOVO: usa detect() non predict()
    toxicity_results = await toxicity_detector.detect_batch(texts)
    
    # Fix: Validazione lunghezze array prima di combinare
    if len(sentiment_results.predictions) != len(transcript):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sentiment predictions mismatch: expected {len(transcript)}, got {len(sentiment_results.predictions)}"
        )
    
    if len(toxicity_results.results) != len(transcript):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Toxicity results mismatch: expected {len(transcript)}, got {len(toxicity_results.results)}"
        )
    
    # 6. Combina transcript con analisi
    enriched_transcript = []
    
    # Stats accumulatori sentiment
    sentiment_positive = 0
    sentiment_neutral = 0
    sentiment_negative = 0
    total_sentiment_score = 0
    
    # Stats accumulatori toxicity (NUOVO formato)
    toxic_count = 0
    severity_low = 0
    severity_medium = 0
    severity_high = 0
    total_toxicity_score = 0
    
    for i, entry in enumerate(transcript):
        sent_pred = sentiment_results.predictions[i]
        tox_result = toxicity_results.results[i]  # NUOVO: result non prediction
        
        entry_dict = entry.dict(by_alias=True)
        
        # Sentiment (formato normalizzato)
        entry_dict['sentiment'] = {
            'label': sent_pred.label.value,
            'score': sent_pred.score,
            'confidence': sent_pred.confidence,
            'raw': sent_pred.raw_output
        }
        
        # Toxicity (formato dedicato) - NUOVO
        entry_dict['toxicity'] = {
            'is_toxic': tox_result.is_toxic,
            'toxicity_score': tox_result.toxicity_score,
            'severity': tox_result.severity.value,
            'confidence': tox_result.confidence,
            'raw': tox_result.raw_output
        }
        
        enriched_transcript.append(entry_dict)
        
        # Accumula stats sentiment
        if sent_pred.label == SentimentLabel.POSITIVE:
            sentiment_positive += 1
        elif sent_pred.label == SentimentLabel.NEUTRAL:
            sentiment_neutral += 1
        else:
            sentiment_negative += 1
        total_sentiment_score += sent_pred.score
        
        # Accumula stats toxicity (NUOVO)
        if tox_result.is_toxic:
            toxic_count += 1
        
        if tox_result.severity == ToxicitySeverity.LOW:
            severity_low += 1
        elif tox_result.severity == ToxicitySeverity.MEDIUM:
            severity_medium += 1
        else:
            severity_high += 1
        
        total_toxicity_score += tox_result.toxicity_score
    
    # 7. Calcola statistiche aggregate
    num_messages = len(sentiment_results.predictions)
    
    return {
        "transcript": enriched_transcript,
        "metadata": {
            "language": "en",
            "formats": {
                "sentiment": "normalized (positive/neutral/negative, score 0-1)",
                "toxicity": "dedicated (is_toxic bool, severity low/medium/high, score 0-1)"
            },
            "stats": {
                "total_messages": num_messages,
                "sentiment": {
                    "distribution": {
                        "positive": sentiment_positive,
                        "neutral": sentiment_neutral,
                        "negative": sentiment_negative
                    },
                    "average_score": round(total_sentiment_score / num_messages, 3),
                    "positive_ratio": round(sentiment_positive / num_messages, 3)
                },
                "toxicity": {
                    "toxic_count": toxic_count,
                    "toxic_ratio": round(toxic_count / num_messages, 3),
                    "severity_distribution": {
                        "low": severity_low,
                        "medium": severity_medium,
                        "high": severity_high
                    },
                    "average_toxicity_score": round(total_toxicity_score / num_messages, 3)
                }
            }
        }
    }

# ============================================
# SENTIMENT + TOXICITY ENDPOINTS
# ============================================

# SENTIMENT (Abstract Pattern)
@app.post("/sentiment/analyze", response_model=NormalizedPrediction)
async def analyze_sentiment(request: UnifiedAnalysisRequest):
    """
    Analizza sentiment di un singolo testo.
    
    Output normalizzato: {label: positive/neutral/negative, score: 0-1}
    """
    if not sentiment_predictor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sentiment predictor not initialized"
        )
    
    try:
        result = await sentiment_predictor.predict(request.text)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sentiment prediction error: {str(e)}"
        )

@app.post("/sentiment/batch", response_model=BatchNormalizedPrediction)
async def analyze_sentiment_batch(request: BatchUnifiedAnalysisRequest):
    """Batch prediction sentiment"""
    if not sentiment_predictor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sentiment predictor not initialized"
        )
    
    try:
        result = await sentiment_predictor.predict_batch(request.texts)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sentiment batch prediction error: {str(e)}"
        )

# TOXICITY (Standalone Detector)
@app.post("/toxicity/detect", response_model=ToxicityResult)
async def detect_toxicity(request: ToxicityAnalysisRequest):
    """
    Rileva tossicità di un singolo testo.
    
    Output dedicato:
    - is_toxic: boolean (True se score > 0.5)
    - severity: low/medium/high
    - toxicity_score: 0-1
    - confidence: 0-1
    """
    if not toxicity_detector:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Toxicity detector not initialized"
        )
    
    try:
        result = await toxicity_detector.detect(request.text)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Toxicity detection error: {str(e)}"
        )

@app.post("/toxicity/detect/batch", response_model=BatchToxicityResult)
async def detect_toxicity_batch(request: BatchToxicityRequest):
    """
    Rileva tossicità per batch di testi.
    
    Batch processing è ~10x più veloce di chiamate singole.
    """
    if not toxicity_detector:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Toxicity detector not initialized"
        )
    
    try:
        result = await toxicity_detector.detect_batch(request.texts)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Toxicity batch detection error: {str(e)}"
        )

# ============================================
# UTILITY ENDPOINTS
# ============================================

@app.get("/participants")
def get_participants():
    """Lista tutti i partecipanti disponibili"""
    return {"participants": PARTICIPANTS}

@app.get("/meetings")
def get_all_meetings():
    """Lista tutti i meeting disponibili con metadata"""
    return {
        "meetings": [
            {
                "id": meeting_id,
                "date": meeting["metadata"].date,
                "participants_count": len(meeting["metadata"].participants),
                "messages_count": len(meeting["transcript"])
            }
            for meeting_id, meeting in MOCK_MEETINGS.items()
        ]
    }

@app.get("/services/status")
async def get_services_status():
    """Status dettagliato di tutti i microservizi"""
    bert_healthy = await check_service_health(BERT_SERVICE_URL)
    toxicity_healthy = await check_service_health(TOXICITY_SERVICE_URL)
    
    bert_info = None
    toxicity_info = None
    
    if bert_healthy:
        try:
            response = await http_client.get(f"{BERT_SERVICE_URL}/info", timeout=5.0)
            bert_info = response.json()
        except:
            pass
    
    if toxicity_healthy:
        try:
            response = await http_client.get(f"{TOXICITY_SERVICE_URL}/info", timeout=5.0)
            toxicity_info = response.json()
        except:
            pass
    
    return {
        "bert_sentiment": {
            "healthy": bert_healthy,
            "url": BERT_SERVICE_URL,
            "port": 5001,
            "info": bert_info,
            "predictor": "SentimentPredictor",
            "output_format": "positive/neutral/negative (score 0-1)"
        },
        "bert_toxicity": {
            "healthy": toxicity_healthy,
            "url": TOXICITY_SERVICE_URL,
            "port": 5003,
            "info": toxicity_info,
            "predictor": "ToxicityPredictor",
            "output_format": "positive/neutral/negative (score 0-1)"
        }
    }

@app.get("/config")
def get_config():
    """Visualizza configurazione corrente (debug)"""
    return {
        "sample_phrases": SAMPLE_PHRASES,
        "participants": [p.dict() for p in PARTICIPANTS],
        "meetings": MEETINGS_CONFIG,
        "generation": GENERATION_CONFIG
    }

# ============================================
# DEBUG ENDPOINTS
# ============================================

@app.post("/debug/toxicity-test")
async def debug_toxicity_test():
    """
    Test toxicity model su frasi problematiche.
    
    Usato per identificare false positive e verificare threshold.
    """
    if not toxicity_detector:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Toxicity detector not initialized"
        )
    
    test_phrases = [
        # Frasi innocue che NON dovrebbero essere tossiche
        "Let me share my screen to show the dashboard.",
        "Can everyone see the slides properly?",
        "I'll send the document via email after this.",
        "Great work everyone!",
        "Thank you for your time.",
        
        # Frasi borderline
        "I don't agree with this approach.",
        "This is not what I expected.",
        "I'm concerned about the timeline.",
        
        # Frasi chiaramente tossiche
        "This is completely stupid.",
        "You're wasting everyone's time.",
        "You have no idea what you're talking about.",
        "Shut up and let someone competent handle this."
    ]
    
    results = []
    for phrase in test_phrases:
        try:
            result = await toxicity_detector.detect(phrase)
            results.append({
                "text": phrase,
                "toxicity_score": result.toxicity_score,
                "is_toxic": result.is_toxic,
                "severity": result.severity.value,
                "confidence": result.confidence
            })
        except Exception as e:
            results.append({
                "text": phrase,
                "error": str(e)
            })
    
    return {
        "test_phrases_count": len(test_phrases),
        "results": results,
        "note": "Check for false positives (innocent phrases marked toxic)"
    }