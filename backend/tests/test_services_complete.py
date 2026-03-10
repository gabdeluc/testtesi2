"""
test_services.py - Test Logica Business

Test per logica interna, predictors, e configurazione.
"""

import pytest
from typing import List, Dict


# ============================================
# CONFIG LOADER TESTS
# ============================================

class TestConfigLoader:
    """Test per ConfigLoader"""
    
    def test_config_loader_loads_yaml(self):
        """Test che config loader carichi YAML correttamente"""
        from config.config_loader import config_loader
        
        config = config_loader.get_config()
        
        assert config is not None
        assert isinstance(config, dict)
    
    def test_get_sample_phrases(self):
        """Test recupero frasi di esempio"""
        from config.config_loader import config_loader
        
        phrases = config_loader.get_sample_phrases()
        
        assert isinstance(phrases, list)
        assert len(phrases) > 0
        
        # Verifica che siano stringhe
        for phrase in phrases:
            assert isinstance(phrase, str)
            assert len(phrase) > 0
    
    def test_get_participants(self):
        """Test recupero lista partecipanti"""
        from config.config_loader import config_loader
        
        participants = config_loader.get_participants()
        
        assert isinstance(participants, list)
        assert len(participants) == 3
        
        # Verifica struttura
        for p in participants:
            assert "id" in p
            assert "name" in p
    
    def test_get_meetings(self):
        """Test recupero configurazione meeting"""
        from config.config_loader import config_loader
        
        meetings = config_loader.get_meetings()
        
        assert isinstance(meetings, list)
        assert len(meetings) >= 3
        
        # Verifica struttura
        for m in meetings:
            assert "id" in m
            assert "date" in m
            assert "num_entries" in m
    
    def test_get_generation_config(self):
        """Test configurazione generazione"""
        from config.config_loader import config_loader
        
        gen_config = config_loader.get_generation_config()
        
        assert isinstance(gen_config, dict)
        assert "min_duration_seconds" in gen_config
        assert "max_pause_seconds" in gen_config
        assert "chars_per_second" in gen_config
        
        # Verifica valori logici
        assert gen_config["min_duration_seconds"] > 0
        assert gen_config["max_pause_seconds"] > 0
        assert gen_config["chars_per_second"] > 0


# ============================================
# PREDICTOR TESTS
# ============================================

class TestSentimentPredictor:
    """Test per SentimentPredictor"""
    
    @pytest.mark.unit
    def test_sentiment_predictor_initialization(self):
        """Test inizializzazione predictor"""
        from models import SentimentPredictor
        import httpx
        
        client = httpx.AsyncClient()
        predictor = SentimentPredictor("http://test:5001", client)
        
        assert predictor is not None
        assert predictor.model_name == "bert-sentiment"
        assert predictor.model_type == "sentiment"
    
    @pytest.mark.unit
    def test_normalize_output_positive(self):
        """Test normalizzazione output positivo"""
        from models import SentimentPredictor
        import httpx
        
        client = httpx.AsyncClient()
        predictor = SentimentPredictor("http://test:5001", client)
        
        # Simula output BERT (4.5 stelle)
        raw_output = {
            "stars": 4.5,
            "sentiment": "very_positive",
            "confidence": 0.92
        }
        
        result = predictor._normalize_output(raw_output)
        
        assert result.label.value == "positive"
        assert 0.75 <= result.score <= 1.0  # 4.5 stelle normalizzate
        assert result.confidence == 0.92
    
    @pytest.mark.unit
    def test_normalize_output_neutral(self):
        """Test normalizzazione output neutrale"""
        from models import SentimentPredictor
        import httpx
        
        client = httpx.AsyncClient()
        predictor = SentimentPredictor("http://test:5001", client)
        
        # Simula output BERT (3.0 stelle)
        raw_output = {
            "stars": 3.0,
            "sentiment": "neutral",
            "confidence": 0.75
        }
        
        result = predictor._normalize_output(raw_output)
        
        assert result.label.value == "neutral"
        assert 0.4 <= result.score <= 0.6  # Range neutrale
    
    @pytest.mark.unit
    def test_normalize_output_negative(self):
        """Test normalizzazione output negativo"""
        from models import SentimentPredictor
        import httpx
        
        client = httpx.AsyncClient()
        predictor = SentimentPredictor("http://test:5001", client)
        
        # Simula output BERT (1.5 stelle)
        raw_output = {
            "stars": 1.5,
            "sentiment": "very_negative",
            "confidence": 0.88
        }
        
        result = predictor._normalize_output(raw_output)
        
        assert result.label.value == "negative"
        assert 0.0 <= result.score <= 0.4  # Score basso


class TestToxicityDetector:
    """Test per ToxicityDetector"""
    
    @pytest.mark.unit
    def test_toxicity_detector_initialization(self):
        """Test inizializzazione detector"""
        from models import ToxicityDetector
        import httpx
        
        client = httpx.AsyncClient()
        detector = ToxicityDetector("http://test:5003", client)
        
        assert detector is not None
        assert detector.threshold == 0.5
    
    @pytest.mark.unit
    def test_get_severity_low(self):
        """Test severity level basso"""
        from models import ToxicityDetector
        import httpx
        
        client = httpx.AsyncClient()
        detector = ToxicityDetector("http://test:5003", client)
        
        severity = detector._get_severity(0.2)
        assert severity.value == "low"
    
    @pytest.mark.unit
    def test_get_severity_medium(self):
        """Test severity level medio"""
        from models import ToxicityDetector
        import httpx
        
        client = httpx.AsyncClient()
        detector = ToxicityDetector("http://test:5003", client)
        
        severity = detector._get_severity(0.5)
        assert severity.value == "medium"
    
    @pytest.mark.unit
    def test_get_severity_high(self):
        """Test severity level alto"""
        from models import ToxicityDetector
        import httpx
        
        client = httpx.AsyncClient()
        detector = ToxicityDetector("http://test:5003", client)
        
        severity = detector._get_severity(0.8)
        assert severity.value == "high"


# ============================================
# DATA GENERATION TESTS
# ============================================

class TestMockDataGeneration:
    """Test generazione dati mock"""
    
    def test_generate_mock_transcript(self):
        """Test generazione transcript mock"""
        from main import generate_mock_transcript
        
        num_entries = 10
        transcript = generate_mock_transcript(num_entries)
        
        assert len(transcript) == num_entries
        
        # Verifica struttura
        for entry in transcript:
            assert hasattr(entry, 'uid')
            assert hasattr(entry, 'nickname')
            assert hasattr(entry, 'text')
            assert hasattr(entry, 'from_field')
            assert hasattr(entry, 'to')
            
            # Verifica valori non vuoti
            assert len(entry.uid) > 0
            assert len(entry.nickname) > 0
            assert len(entry.text) > 0
    
    def test_transcript_timing_progression(self):
        """Test che i timestamp siano progressivi"""
        from main import generate_mock_transcript
        
        transcript = generate_mock_transcript(5)
        
        # Converti timestamp in secondi
        def time_to_seconds(time_str):
            parts = time_str.split(':')
            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
            return h * 3600 + m * 60 + s
        
        prev_end = 0
        for entry in transcript:
            start = time_to_seconds(entry.from_field)
            end = time_to_seconds(entry.to)
            
            # Verifica progressione
            assert start >= prev_end
            assert end > start
            
            prev_end = end
    
    def test_transcript_participants_valid(self):
        """Test che partecipanti siano validi"""
        from main import generate_mock_transcript, PARTICIPANTS
        
        transcript = generate_mock_transcript(20)
        
        valid_names = [p.name for p in PARTICIPANTS]
        
        for entry in transcript:
            assert entry.nickname in valid_names


# ============================================
# PREDICTOR FACTORY TESTS
# ============================================

class TestPredictorFactory:
    """Test per PredictorFactory"""
    
    def test_create_sentiment_predictor(self):
        """Test creazione sentiment predictor"""
        from models import PredictorFactory
        import httpx
        
        client = httpx.AsyncClient()
        factory = PredictorFactory(client)
        
        predictor = factory.create_sentiment_predictor("http://test:5001")
        
        assert predictor is not None
        assert predictor.model_type == "sentiment"
    
    def test_create_toxicity_detector(self):
        """Test creazione toxicity detector"""
        from models import PredictorFactory
        import httpx
        
        client = httpx.AsyncClient()
        factory = PredictorFactory(client)
        
        detector = factory.create_toxicity_detector("http://test:5003")
        
        assert detector is not None
        assert detector.threshold == 0.5