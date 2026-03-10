"""
Abstract Model Predictor + Standalone Toxicity Detector

EDUCATIONAL NOTE FOR FUTURE STUDENTS:
This file implements two design patterns:

1. ABSTRACT PREDICTOR PATTERN (for sentiment):
   Problem: Different ML models return different formats (stars, scores, percentages)
   Solution: Abstract class that normalizes everything to positive/neutral/negative
   
2. STANDALONE DETECTOR (for toxicity):
   Problem: Toxicity is binary (toxic/non-toxic), not a sentiment spectrum
   Solution: Dedicated class with specific output format (is_toxic, severity, score)

Why separate patterns?
- Sentiment is multiclass (positive/neutral/negative) → abstract pattern makes sense
- Toxicity is binary → dedicated output is more semantic and clear
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


# ============================================
# ENUMS
# ============================================

class SentimentLabel(str, Enum):
    """Normalized sentiment labels (used by all sentiment models)."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class ToxicitySeverity(str, Enum):
    """Toxicity severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ============================================
# SENTIMENT RESPONSE MODELS
# ============================================

class NormalizedPrediction(BaseModel):
    """
    Normalized output for SENTIMENT analysis.
    
    EDUCATIONAL NOTE:
    Different models output different formats:
    - BERT: 1-5 stars
    - TextBlob: -1 to +1
    - VADER: compound score
    
    We normalize ALL of them to this format:
    - label: positive/neutral/negative
    - score: 0-1 (always normalized)
    """
    label: SentimentLabel = Field(..., description="positive, neutral, or negative")
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized score 0-1")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence")
    raw_output: Dict[str, Any] = Field(..., description="Original model output")
    model_type: str = Field(..., description="Type of model")


class BatchNormalizedPrediction(BaseModel):
    """Batch of normalized sentiment predictions."""
    predictions: List[NormalizedPrediction]
    total_processed: int
    avg_score: float = Field(..., ge=0.0, le=1.0)
    label_distribution: Dict[str, int] = Field(..., description="Count per label")


# ============================================
# TOXICITY RESPONSE MODELS
# ============================================

class ToxicityResult(BaseModel):
    """
    Dedicated output for TOXICITY detection.
    
    EDUCATIONAL NOTE:
    We DON'T use positive/neutral/negative for toxicity because:
    - It doesn't make semantic sense (toxicity is not a "sentiment")
    - Binary classification (toxic/non-toxic) is clearer
    - Severity levels (low/medium/high) provide more useful information
    """
    is_toxic: bool = Field(..., description="True if toxic (score > 0.5)")
    toxicity_score: float = Field(..., ge=0.0, le=1.0, description="Toxicity score 0-1")
    severity: ToxicitySeverity = Field(..., description="low/medium/high")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence")
    raw_output: Dict[str, Any] = Field(..., description="Original model output")


class BatchToxicityResult(BaseModel):
    """Batch of toxicity predictions."""
    results: List[ToxicityResult]
    total_processed: int
    toxic_count: int = Field(..., description="Number of toxic messages")
    toxic_ratio: float = Field(..., ge=0.0, le=1.0, description="Percentage toxic")
    avg_toxicity_score: float = Field(..., ge=0.0, le=1.0)


# ============================================
# ABSTRACT BASE CLASS (for Sentiment only)
# ============================================

class ModelPredictor(ABC):
    """
    Abstract base class for SENTIMENT predictors.
    
    DESIGN PATTERN: Abstract Predictor Pattern
    
    EDUCATIONAL NOTE:
    This is an abstract class (cannot be instantiated directly).
    Subclasses MUST implement _raw_predict() and _normalize_output().
    
    How to add a new sentiment model:
    1. Create class: class MyPredictor(ModelPredictor)
    2. Implement _raw_predict() → call your ML API
    3. Implement _normalize_output() → convert to standard format
    4. Done! The base class handles the rest.
    
    Example:
        class TextBlobPredictor(ModelPredictor):
            async def _raw_predict(self, text):
                blob = TextBlob(text)
                return {"polarity": blob.sentiment.polarity}
            
            def _normalize_output(self, raw):
                polarity = raw['polarity']  # -1 to +1
                score = (polarity + 1) / 2   # normalize to 0-1
                
                if polarity < -0.3:
                    label = SentimentLabel.NEGATIVE
                elif polarity > 0.3:
                    label = SentimentLabel.POSITIVE
                else:
                    label = SentimentLabel.NEUTRAL
                
                return NormalizedPrediction(
                    label=label,
                    score=score,
                    confidence=abs(polarity),
                    raw_output=raw,
                    model_type="textblob"
                )
    """
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.model_type = self._get_model_type()
    
    @abstractmethod
    def _get_model_type(self) -> str:
        """Return the type of model (e.g., 'sentiment')."""
        pass
    
    @abstractmethod
    async def _raw_predict(self, text: str) -> Dict[str, Any]:
        """Call the ML model and return raw output."""
        pass
    
    @abstractmethod
    async def _raw_batch_predict(self, texts: List[str]) -> Dict[str, Any]:
        """Call the ML model with batch input."""
        pass
    
    @abstractmethod
    def _normalize_output(self, raw_output: Dict[str, Any]) -> NormalizedPrediction:
        """
        Normalize model output to standard format.
        
        This is the KEY method that makes the pattern work!
        """
        pass
    
    async def predict(self, text: str) -> NormalizedPrediction:
        """Unified API for single prediction."""
        raw_output = await self._raw_predict(text)
        return self._normalize_output(raw_output)
    
    async def predict_batch(self, texts: List[str]) -> BatchNormalizedPrediction:
        """Unified API for batch prediction."""
        raw_batch = await self._raw_batch_predict(texts)
        
        predictions = [
            self._normalize_output(result)
            for result in raw_batch.get('results', [])
        ]
        
        total = len(predictions)
        avg_score = sum(p.score for p in predictions) / total if total > 0 else 0.0
        
        label_distribution = {
            "positive": sum(1 for p in predictions if p.label == SentimentLabel.POSITIVE),
            "neutral": sum(1 for p in predictions if p.label == SentimentLabel.NEUTRAL),
            "negative": sum(1 for p in predictions if p.label == SentimentLabel.NEGATIVE)
        }
        
        return BatchNormalizedPrediction(
            predictions=predictions,
            total_processed=total,
            avg_score=round(avg_score, 3),
            label_distribution=label_distribution
        )


# ============================================
# SENTIMENT ADAPTER (BERT Implementation)
# ============================================

class SentimentPredictor(ModelPredictor):
    """
    Adapter for BERT Sentiment (1-5 stars).
    
    EDUCATIONAL NOTE:
    This class wraps the BERT sentiment microservice and normalizes its output.
    
    Normalization rules:
    - 1.0-2.5 stars → NEGATIVE (unhappy customers)
    - 2.5-3.5 stars → NEUTRAL (mixed feelings)
    - 3.5-5.0 stars → POSITIVE (happy customers)
    """
    
    def __init__(self, service_url: str, http_client):
        super().__init__(model_name="bert-sentiment")
        self.service_url = service_url
        self.http_client = http_client
    
    def _get_model_type(self) -> str:
        return "sentiment"
    
    async def _raw_predict(self, text: str) -> Dict[str, Any]:
        """Call BERT sentiment microservice."""
        response = await self.http_client.post(
            f"{self.service_url}/analyze",
            json={"text": text},
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    
    async def _raw_batch_predict(self, texts: List[str]) -> Dict[str, Any]:
        """Call BERT sentiment microservice with batch."""
        response = await self.http_client.post(
            f"{self.service_url}/batch",
            json={"texts": texts},
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    
    def _normalize_output(self, raw_output: Dict[str, Any]) -> NormalizedPrediction:
        """
        Normalize BERT stars (1-5) to positive/neutral/negative.
        
        EDUCATIONAL NOTE:
        We convert continuous stars to discrete labels:
        - < 2.5: NEGATIVE (1-2 stars = unhappy)
        - 2.5-3.5: NEUTRAL (3 stars = okay)
        - > 3.5: POSITIVE (4-5 stars = happy)
        """
        stars = raw_output.get('stars', 3.0)
        confidence = raw_output.get('confidence', 0.0)
        
        # Normalize stars (1-5) to score (0-1)
        normalized_score = (stars - 1) / 4  # 1→0, 3→0.5, 5→1
        
        # Determine label based on stars
        if stars < 2.5:
            label = SentimentLabel.NEGATIVE
        elif stars <= 3.5:
            label = SentimentLabel.NEUTRAL
        else:
            label = SentimentLabel.POSITIVE
        
        return NormalizedPrediction(
            label=label,
            score=round(normalized_score, 3),
            confidence=round(confidence, 3),
            raw_output=raw_output,
            model_type=self.model_type
        )


# ============================================
# TOXICITY DETECTOR (Standalone - NO Abstract)
# ============================================

class ToxicityDetector:
    """
    Standalone Toxicity Detector.
    
    EDUCATIONAL NOTE:
    This does NOT inherit from ModelPredictor because:
    1. Toxicity is binary (toxic/non-toxic), not multiclass
    2. Output format is fundamentally different (boolean + severity)
    3. Semantics are different (not a "sentiment")
    
    Severity calculation:
    - LOW: score < 0.4 (safe, normal conversation)
    - MEDIUM: score 0.4-0.7 (borderline, monitor)
    - HIGH: score > 0.7 (toxic, needs intervention)
    
    Why these thresholds?
    - More conservative than default 0.5 to reduce false positives
    - Based on testing with real meeting transcripts
    """
    
    def __init__(self, service_url: str, http_client):
        self.service_url = service_url
        self.http_client = http_client
        self.threshold = 0.5  # Binary classification threshold
    
    def _get_severity(self, score: float) -> ToxicitySeverity:
        """
        Determine severity level from toxicity score.
        
        EDUCATIONAL NOTE:
        Conservative thresholds to avoid false positives:
        - < 0.4: LOW (was 0.3, now more permissive)
        - 0.4-0.7: MEDIUM (watch zone)
        - > 0.7: HIGH (definitely toxic)
        """
        if score < 0.4:
            return ToxicitySeverity.LOW
        elif score < 0.7:
            return ToxicitySeverity.MEDIUM
        else:
            return ToxicitySeverity.HIGH
    
    async def detect(self, text: str) -> ToxicityResult:
        """
        Detect toxicity in a single text.
        
        Returns:
            ToxicityResult with is_toxic, severity, score
        """
        response = await self.http_client.post(
            f"{self.service_url}/analyze",
            json={"text": text},
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()
        
        toxicity_score = data['toxicity_score']
        
        return ToxicityResult(
            is_toxic=data['is_toxic'],
            toxicity_score=round(toxicity_score, 3),
            severity=self._get_severity(toxicity_score),
            confidence=round(data['confidence'], 3),
            raw_output=data
        )
    
    async def detect_batch(self, texts: List[str]) -> BatchToxicityResult:
        """
        Detect toxicity for batch of texts.
        
        Returns:
            BatchToxicityResult with aggregated statistics
        """
        response = await self.http_client.post(
            f"{self.service_url}/batch",
            json={"texts": texts},
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()
        
        results = []
        toxic_count = 0
        total_toxicity = 0.0
        
        for item in data['results']:
            toxicity_score = item['toxicity_score']
            is_toxic = item['is_toxic']
            
            result = ToxicityResult(
                is_toxic=is_toxic,
                toxicity_score=round(toxicity_score, 3),
                severity=self._get_severity(toxicity_score),
                confidence=round(item['confidence'], 3),
                raw_output=item
            )
            
            results.append(result)
            if is_toxic:
                toxic_count += 1
            total_toxicity += toxicity_score
        
        total = len(results)
        
        return BatchToxicityResult(
            results=results,
            total_processed=total,
            toxic_count=toxic_count,
            toxic_ratio=round(toxic_count / total, 3) if total > 0 else 0.0,
            avg_toxicity_score=round(total_toxicity / total, 3) if total > 0 else 0.0
        )


# ============================================
# FACTORY PATTERN
# ============================================

class PredictorFactory:
    """
    Factory for creating predictors and detectors.
    
    DESIGN PATTERN: Factory Pattern
    
    EDUCATIONAL NOTE:
    The factory centralizes object creation logic.
    
    Benefits:
    - Hide complex initialization
    - Easy to add new models (just add factory method)
    - Consistent configuration across all predictors
    
    Example usage:
        factory = PredictorFactory(http_client)
        sentiment = factory.create_sentiment_predictor(url)
        toxicity = factory.create_toxicity_detector(url)
    """
    
    def __init__(self, http_client):
        self.http_client = http_client
    
    def create_sentiment_predictor(self, service_url: str) -> SentimentPredictor:
        """Create sentiment predictor (abstract pattern)."""
        return SentimentPredictor(service_url, self.http_client)
    
    def create_toxicity_detector(self, service_url: str) -> ToxicityDetector:
        """Create toxicity detector (standalone)."""
        return ToxicityDetector(service_url, self.http_client)