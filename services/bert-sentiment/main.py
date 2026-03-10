"""
BERT Sentiment Microservice

EDUCATIONAL NOTE FOR FUTURE STUDENTS:
This is an independent microservice that runs a BERT model for sentiment analysis.
It receives text as input and returns a 1-5 star rating. The backend gateway then
normalizes this to positive/neutral/negative labels for the frontend.

Port: 5001
Model: nlptown/bert-base-multilingual-uncased-sentiment (110M parameters)
Output: 1.0-5.0 stars (1=very negative, 5=very positive)
"""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import logging
import os
import time

# Setup logging so we can debug issues in production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# FastAPI App
# ============================================

app = FastAPI(
    title="BERT Sentiment Microservice",
    description="Sentiment analysis with 1-5 star classification",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class SentimentRequest(BaseModel):
    """Request for analyzing a single text."""
    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Text to analyze"
    )
    
    @validator('text')
    def text_not_empty(cls, v):
        """Ensure the text isn't just whitespace."""
        if not v.strip():
            raise ValueError('Text cannot be empty')
        return v.strip()


class BatchSentimentRequest(BaseModel):
    """Request for analyzing multiple texts in one go (much faster!)."""
    texts: List[str] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="List of texts to analyze (max 100)"
    )
    
    @validator('texts')
    def texts_not_empty(cls, v):
        """Filter out empty strings."""
        cleaned = [t.strip() for t in v if t.strip()]
        if not cleaned:
            raise ValueError('At least one text must be non-empty')
        return cleaned


class SentimentResponse(BaseModel):
    """Response with sentiment analysis results."""
    stars: float = Field(..., ge=1.0, le=5.0, description="Score from 1.0 to 5.0")
    sentiment: str = Field(..., description="Sentiment category")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence")
    processing_time_ms: Optional[float] = Field(None, description="Processing time in milliseconds")


class BatchSentimentResponse(BaseModel):
    """Response for batch predictions."""
    results: List[SentimentResponse]
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
    languages: List[str]
    parameters: str
    device: str
    max_input_length: int
    output_classes: int

# ============================================
# BERT MODEL MANAGER (Singleton)
# ============================================

class BERTSentimentModel:
    """
    Singleton pattern for managing the BERT model.
    
    EDUCATIONAL NOTE:
    We use Singleton because BERT is heavy (~500MB in RAM). We want to load it ONCE
    when the service starts, not on every request. All requests share the same model instance.
    
    Features:
    - Lazy loading (loads on first use)
    - Thread-safe
    - Batch processing optimization
    - Error handling
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern: only one instance can exist."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize BERT model (runs only once due to singleton)."""
        if self._initialized:
            return
        
        self.model_name = os.getenv(
            'MODEL_NAME',
            'nlptown/bert-base-multilingual-uncased-sentiment'
        )
        
        # Use GPU if available (10x faster than CPU)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        logger.info("="*60)
        logger.info("🚀 Initializing BERT Sentiment Service")
        logger.info(f"📦 Model: {self.model_name}")
        logger.info(f"🖥️  Device: {self.device}")
        
        try:
            # Load tokenizer (converts text to numbers BERT understands)
            logger.info("📥 Loading tokenizer...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            
            # Load model (downloads ~500MB on first run, then cached)
            logger.info("📥 Loading model...")
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name
            ).to(self.device)
            
            # Set to evaluation mode (disables dropout, batch norm)
            self.model.eval()
            
            # Map model outputs to sentiment labels
            self.sentiment_map = {
                0: "very_negative",
                1: "negative",
                2: "neutral",
                3: "positive",
                4: "very_positive"
            }
            
            # Stars values for weighted average calculation
            self.stars_values = torch.tensor([1.0, 2.0, 3.0, 4.0, 5.0]).to(self.device)
            
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
        Analyze sentiment of a single text.
        
        EDUCATIONAL NOTE:
        The model outputs 5 probabilities (one per star rating).
        We calculate a weighted average: stars = sum(probability[i] * star[i])
        Example: [0.1, 0.1, 0.2, 0.4, 0.2] → 1*0.1 + 2*0.1 + 3*0.2 + 4*0.4 + 5*0.2 = 3.5 stars
        
        Args:
            text: Text to analyze
            return_probabilities: If True, include per-class probabilities
            
        Returns:
            Dict with stars, sentiment, confidence, processing_time_ms
        """
        start_time = time.time()
        
        try:
            # Tokenization: Convert text to token IDs
            # Example: "Hello world" → [101, 7592, 2088, 102]
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,  # BERT's max input length
                padding=True
            ).to(self.device)
            
            # Inference: Run the model
            # We use torch.no_grad() to save memory (we're not training)
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=1)[0]
            
            # Calculate weighted stars (more precise than just argmax)
            weighted_stars = (probs * self.stars_values).sum().item()
            
            # Predicted class (most likely star rating)
            predicted_class = torch.argmax(probs).item()
            confidence = probs[predicted_class].item()
            
            processing_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            result = {
                'stars': round(weighted_stars, 2),
                'sentiment': self.sentiment_map[predicted_class],
                'confidence': round(confidence, 3),
                'processing_time_ms': round(processing_time, 2)
            }
            
            if return_probabilities:
                result['probabilities'] = probs.cpu().numpy().tolist()
            
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
        
        EDUCATIONAL NOTE:
        Batch processing is faster because:
        1. GPU can process all texts in parallel
        2. Tokenization is vectorized
        3. Only 1 model forward pass instead of N
        
        Args:
            texts: List of texts to analyze
            
        Returns:
            List of sentiment results
        """
        start_time = time.time()
        
        try:
            # Batch tokenization (processes all texts at once)
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
            
            # Process each result
            results = []
            
            for i, prob in enumerate(probs):
                weighted_stars = (prob * self.stars_values).sum().item()
                predicted_class = torch.argmax(prob).item()
                confidence = prob[predicted_class].item()
                
                results.append({
                    'stars': round(weighted_stars, 2),
                    'sentiment': self.sentiment_map[predicted_class],
                    'confidence': round(confidence, 3),
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

# Model is initialized on service startup
bert_model: Optional[BERTSentimentModel] = None

# ============================================
# STARTUP/SHUTDOWN EVENTS
# ============================================

@app.on_event("startup")
async def startup_event():
    """Initialize model when service starts."""
    global bert_model
    
    logger.info("🚀 Starting BERT Sentiment Microservice...")
    
    try:
        bert_model = BERTSentimentModel()
        logger.info("✅ Service ready and listening on port 5001")
    except Exception as e:
        logger.error(f"❌ Failed to start service: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("🛑 Shutting down BERT Sentiment Microservice...")
    
    # Free GPU memory if using CUDA
    if bert_model and bert_model.device == "cuda":
        torch.cuda.empty_cache()
    
    logger.info("✅ Shutdown complete")

# ============================================
# API ENDPOINTS
# ============================================

@app.get("/", tags=["Health"])
def root():
    """Root endpoint with service information."""
    return {
        "service": "BERT Sentiment Analysis Microservice",
        "version": "1.0.0",
        "model": bert_model.model_name if bert_model else "Not loaded",
        "device": bert_model.device if bert_model else "Unknown",
        "status": "running" if bert_model and bert_model._initialized else "initializing",
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
    if not bert_model or not bert_model._initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded"
        )
    
    return HealthResponse(
        status="healthy",
        model_loaded=True,
        device=bert_model.device,
        model_name=bert_model.model_name
    )


@app.post("/analyze", response_model=SentimentResponse, tags=["Sentiment Analysis"])
def analyze_sentiment(request: SentimentRequest):
    """
    Analyze sentiment of a single text.
    
    Example Request:
        {"text": "This meeting was very productive!"}
    
    Example Response:
        {
            "stars": 4.8,
            "sentiment": "very_positive",
            "confidence": 0.92,
            "processing_time_ms": 45.23
        }
    """
    if not bert_model or not bert_model._initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not initialized"
        )
    
    try:
        result = bert_model.analyze(request.text)
        return SentimentResponse(**result)
        
    except Exception as e:
        logger.error(f"Sentiment analysis error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during sentiment analysis: {str(e)}"
        )


@app.post("/batch", response_model=BatchSentimentResponse, tags=["Sentiment Analysis"])
def batch_analyze_sentiment(request: BatchSentimentRequest):
    """
    Analyze sentiment for batch of texts (much faster!).
    
    EDUCATIONAL NOTE:
    Batch processing is ~10x faster than individual calls.
    Use this when analyzing multiple messages.
    
    Limits:
    - Minimum: 1 text
    - Maximum: 100 texts per request
    
    Example Request:
        {
            "texts": [
                "Great work!",
                "This is terrible",
                "Not sure about this"
            ]
        }
    
    Example Response:
        {
            "results": [
                {"stars": 4.9, "sentiment": "very_positive", "confidence": 0.95},
                {"stars": 1.2, "sentiment": "very_negative", "confidence": 0.88},
                {"stars": 2.8, "sentiment": "neutral", "confidence": 0.71}
            ],
            "total_processed": 3,
            "total_time_ms": 120.5
        }
    """
    if not bert_model or not bert_model._initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not initialized"
        )
    
    try:
        start_time = time.time()
        results = bert_model.batch_analyze(request.texts)
        total_time = (time.time() - start_time) * 1000
        
        return BatchSentimentResponse(
            results=[SentimentResponse(**r) for r in results],
            total_processed=len(results),
            total_time_ms=round(total_time, 2)
        )
        
    except Exception as e:
        logger.error(f"Batch analysis error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during batch sentiment analysis: {str(e)}"
        )


@app.get("/info", response_model=ModelInfoResponse, tags=["Info"])
def model_info():
    """
    Get detailed model information.
    
    Returns architecture details, supported languages, etc.
    """
    if not bert_model or not bert_model._initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not initialized"
        )
    
    return ModelInfoResponse(
        model_name=bert_model.model_name,
        architecture="BERT-base (12 layers, 768 hidden)",
        task="Sentiment Classification (1-5 stars)",
        languages=["en", "nl", "de", "fr", "it", "es"],
        parameters="~110M",
        device=bert_model.device,
        max_input_length=512,
        output_classes=5
    )

# ============================================
# MAIN (for local testing)
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 5001))
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )