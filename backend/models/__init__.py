"""
Models module - Unified prediction interface + Standalone toxicity detector
"""

from .predictor import (
    # Abstract class (solo per sentiment)
    ModelPredictor,
    
    # Sentiment predictor
    SentimentPredictor,
    NormalizedPrediction,
    BatchNormalizedPrediction,
    SentimentLabel,
    
    # Toxicity detector (standalone)
    ToxicityDetector,
    ToxicityResult,
    BatchToxicityResult,
    ToxicitySeverity,
    
    # Factory
    PredictorFactory
)

__all__ = [
    # Abstract
    'ModelPredictor',
    
    # Sentiment
    'SentimentPredictor',
    'NormalizedPrediction',
    'BatchNormalizedPrediction',
    'SentimentLabel',
    
    # Toxicity
    'ToxicityDetector',
    'ToxicityResult',
    'BatchToxicityResult',
    'ToxicitySeverity',
    
    # Factory
    'PredictorFactory'
]