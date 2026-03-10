"""
BERT Toxicity Microservice

EDUCATIONAL NOTE FOR FUTURE STUDENTS:
This microservice detects toxic/offensive content in text using BERT.
Unlike sentiment (1-5 stars), this is a binary classification: toxic or non-toxic.
The output includes a 0-1 score and a severity level (low/medium/high).

Port: 5003
Model: gravitee-io/bert-small-toxicity
Output: toxicity_score (0-1), is_toxic (bool), severity (low/medium/high)
"""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import logging
import os
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# FastAPI App
# ============================================

app = FastAPI(
    title="BERT Toxicity Microservice",
    description="Toxicity detection with 0-1 classification",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class ToxicityRequest(BaseModel):
    """Request for analyzing toxicity in a single text."""
    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Text to analyze"
    )
    
    @validator('text')
    def text_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Text cannot be empty')
        return v.strip()


class BatchToxicityRequest(BaseModel):
    """Request for analyzing toxicity in multiple texts."""
    texts: List[str] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="List of texts to analyze (max 100)"
    )
    
    @validator('texts')
    def texts_not_empty(cls, v):
        cleaned = [t.strip() for t in v if t.strip()]
        if not cleaned:
            raise ValueError('At least one text must be non-empty')
        return cleaned


class ToxicityResponse(BaseModel):
    """Response with toxicity detection results."""
    toxicity_score: float = Field(..., ge=0.0, le=1.0, description="Toxicity score 0.0-1.0")
    is_toxic: bool = Field(..., description="True if toxic (score > 0.5)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence")
    label: str = Field(..., description="toxic/non-toxic")
    processing_time_ms: Optional[float] = Field(None, description="Processing time in ms")


class BatchToxicityResponse(BaseModel):
    """Response for batch toxicity detection."""
    results: List[ToxicityResponse]
    total_processed: int
    total_time_ms: float


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    model_loaded: bool
    device: str
    model_name: str


class ModelInfoResponse(BaseModel):
    """Detailed model information."""
    model_name: str
    architecture: str
    task: str
    output_range: str
    device: str
    max_input_length: int
    threshold: float

# ============================================
# BERT TOXICITY MODEL MANAGER (Singleton)
# ============================================

class BERTToxicityModel:
    """
    Singleton for managing the BERT toxicity model.
    
    EDUCATIONAL NOTE:
    Binary classification: the model outputs 2 probabilities (non-toxic, toxic).
    We use probability of "toxic" class as the toxicity score.
    
    Severity levels based on score:
    - LOW: score < 0.4 (safe conversation)
    - MEDIUM: score 0.4-0.7 (borderline, watch carefully)
    - HIGH: score > 0.7 (toxic, needs moderation)
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern: only one instance can exist."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize BERT toxicity model (runs only once)."""
        if self._initialized:
            return
        
        self.model_name = os.getenv(
            'MODEL_NAME',
            'gravitee-io/bert-small-toxicity'
        )
        
        # Use GPU if available
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Threshold for binary classification
        self.threshold = 0.5
        
        logger.info("="*60)
        logger.info("🚀 Initializing BERT Toxicity Service")
        logger.info(f"📦 Model: {self.model_name}")
        logger.info(f"🖥️  Device: {self.device}")
        logger.info(f"🎯 Threshold: {self.threshold}")
        
        try:
            # Load tokenizer
            logger.info("📥 Loading tokenizer...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            
            # Load model
            logger.info("📥 Loading model...")
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name
            ).to(self.device)
            
            # Set to evaluation mode
            self.model.eval()
            
            # Label mapping (0=non-toxic, 1=toxic)
            self.id2label = {0: "non-toxic", 1: "toxic"}
            
            self._initialized = True
            
            logger.info("✅ Model loaded successfully!")
            logger.info("="*60)
            
        except Exception as e:
            logger.error(f"❌ Model loading error: {e}")
            raise
    
    def analyze(
        self,
        text: str,
        return_probabilities: bool = False
    ) -> Dict[str, Any]:
        """
        Analyze toxicity of a single text.
        
        Args:
            text: Text to analyze
            return_probabilities: If True, include per-class probabilities
            
        Returns:
            Dict with toxicity_score, is_toxic, confidence, label
        """
        start_time = time.time()
        
        try:
            # Tokenization
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            ).to(self.device)
            
            # Inference
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=1)[0]
            
            # Toxicity score = probability of "toxic" class
            toxicity_score = probs[1].item()
            
            # Binary classification
            is_toxic = toxicity_score > self.threshold
            predicted_class = 1 if is_toxic else 0
            
            # Confidence = probability of the predicted class
            confidence = probs[predicted_class].item()
            
            processing_time = (time.time() - start_time) * 1000
            
            result = {
                'toxicity_score': round(toxicity_score, 3),
                'is_toxic': is_toxic,
                'confidence': round(confidence, 3),
                'label': self.id2label[predicted_class],
                'processing_time_ms': round(processing_time, 2)
            }
            
            if return_probabilities:
                result['probabilities'] = {
                    'non-toxic': round(probs[0].item(), 3),
                    'toxic': round(probs[1].item(), 3)
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            raise
    
    def batch_analyze(
        self,
        texts: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Analyze batch of texts (10x faster than individual calls).
        
        Args:
            texts: List of texts to analyze
            
        Returns:
            List of toxicity results
        """
        start_time = time.time()
        
        try:
            # Batch tokenization
            inputs = self.tokenizer(
                texts,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            ).to(self.device)
            
            # Batch inference
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=1)
            
            # Process results
            results = []
            
            for i, prob in enumerate(probs):
                toxicity_score = prob[1].item()
                is_toxic = toxicity_score > self.threshold
                predicted_class = 1 if is_toxic else 0
                confidence = prob[predicted_class].item()
                
                results.append({
                    'toxicity_score': round(toxicity_score, 3),
                    'is_toxic': is_toxic,
                    'confidence': round(confidence, 3),
                    'label': self.id2label[predicted_class],
                    'processing_time_ms': None  # Calculated at batch level
                })
            
            total_time = (time.time() - start_time) * 1000
            avg_time = total_time / len(texts)
            
            # Add average time to each result
            for result in results:
                result['processing_time_ms'] = round(avg_time, 2)
            
            return results
            
        except Exception as e:
            logger.error(f"Batch analysis error: {e}")
            raise

# ============================================
# GLOBAL MODEL INSTANCE
# ============================================

toxicity_model: Optional[BERTToxicityModel] = None

# ============================================
# STARTUP/SHUTDOWN EVENTS
# ============================================

@app.on_event("startup")
async def startup_event():
    """Initialize model when service starts."""
    global toxicity_model
    
    logger.info("🚀 Starting BERT Toxicity Microservice...")
    
    try:
        toxicity_model = BERTToxicityModel()
        logger.info("✅ Service ready and listening on port 5003")
    except Exception as e:
        logger.error(f"❌ Failed to start service: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("🛑 Shutting down BERT Toxicity Microservice...")
    
    # Free GPU memory if using CUDA
    if toxicity_model and toxicity_model.device == "cuda":
        torch.cuda.empty_cache()
    
    logger.info("✅ Shutdown complete")

# ============================================
# API ENDPOINTS
# ============================================

@app.get("/", tags=["Health"])
def root():
    """Root endpoint with service information."""
    return {
        "service": "BERT Toxicity Analysis Microservice",
        "version": "1.0.0",
        "model": toxicity_model.model_name if toxicity_model else "Not loaded",
        "device": toxicity_model.device if toxicity_model else "Unknown",
        "status": "running" if toxicity_model and toxicity_model._initialized else "initializing",
        "endpoints": {
            "analyze": "POST /analyze",
            "batch": "POST /batch",
            "health": "GET /health",
            "info": "GET /info"
        }
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """
    Health check endpoint.
    
    Used by Docker healthcheck and monitoring tools.
    """
    if not toxicity_model or not toxicity_model._initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded"
        )
    
    return HealthResponse(
        status="healthy",
        model_loaded=True,
        device=toxicity_model.device,
        model_name=toxicity_model.model_name
    )


@app.post("/analyze", response_model=ToxicityResponse, tags=["Toxicity Analysis"])
def analyze_toxicity(request: ToxicityRequest):
    """
    Analyze toxicity of a single text.
    
    Example Request:
        {"text": "You are stupid and useless!"}
    
    Example Response:
        {
            "toxicity_score": 0.89,
            "is_toxic": true,
            "confidence": 0.89,
            "label": "toxic",
            "processing_time_ms": 42.15
        }
    """
    if not toxicity_model or not toxicity_model._initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not initialized"
        )
    
    try:
        result = toxicity_model.analyze(request.text)
        return ToxicityResponse(**result)
        
    except Exception as e:
        logger.error(f"Toxicity analysis error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during toxicity analysis: {str(e)}"
        )


@app.post("/batch", response_model=BatchToxicityResponse, tags=["Toxicity Analysis"])
def batch_analyze_toxicity(request: BatchToxicityRequest):
    """
    Analyze toxicity for batch of texts (much faster!).
    
    EDUCATIONAL NOTE:
    Batch processing is ~10x faster than individual calls.
    
    Limits:
    - Minimum: 1 text
    - Maximum: 100 texts per request
    
    Example Request:
        {
            "texts": [
                "Great work!",
                "This is terrible and you are awful",
                "Thank you for your help"
            ]
        }
    
    Example Response:
        {
            "results": [
                {"toxicity_score": 0.05, "is_toxic": false, "label": "non-toxic"},
                {"toxicity_score": 0.92, "is_toxic": true, "label": "toxic"},
                {"toxicity_score": 0.03, "is_toxic": false, "label": "non-toxic"}
            ],
            "total_processed": 3,
            "total_time_ms": 115.8
        }
    """
    if not toxicity_model or not toxicity_model._initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not initialized"
        )
    
    try:
        start_time = time.time()
        results = toxicity_model.batch_analyze(request.texts)
        total_time = (time.time() - start_time) * 1000
        
        return BatchToxicityResponse(
            results=[ToxicityResponse(**r) for r in results],
            total_processed=len(results),
            total_time_ms=round(total_time, 2)
        )
        
    except Exception as e:
        logger.error(f"Batch analysis error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during batch toxicity analysis: {str(e)}"
        )


@app.get("/info", response_model=ModelInfoResponse, tags=["Info"])
def model_info():
    """
    Get detailed model information.
    
    Returns architecture details, thresholds, etc.
    """
    if not toxicity_model or not toxicity_model._initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not initialized"
        )
    
    return ModelInfoResponse(
        model_name=toxicity_model.model_name,
        architecture="BERT-small (6 layers, 512 hidden)",
        task="Binary Toxicity Classification",
        output_range="0.0 (non-toxic) - 1.0 (toxic)",
        device=toxicity_model.device,
        max_input_length=512,
        threshold=toxicity_model.threshold
    )

# ============================================
# MAIN (for local testing)
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 5003))
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )