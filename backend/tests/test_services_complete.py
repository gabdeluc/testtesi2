"""
test_services_complete.py — Test logica business.

Fix applicati:
  • generate_mock_transcript(n, meeting_config) — firma corretta
  • Campi schema Arianna: conversation_turn, participant_name,
    transcribed_text, created_at, audio_duration_ms
  • test_transcript_timing_progression usa created_at + audio_duration_ms
"""

import pytest
from typing import List, Dict


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG LOADER
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigLoader:

    def test_config_loader_loads_yaml(self):
        from config.config_loader import config_loader
        config = config_loader.get_config()
        assert config is not None
        assert isinstance(config, dict)

    def test_get_sample_phrases(self):
        from config.config_loader import config_loader
        phrases = config_loader.get_sample_phrases()
        assert isinstance(phrases, list)
        assert len(phrases) > 0
        for phrase in phrases:
            assert isinstance(phrase, str)
            assert len(phrase) > 0

    def test_get_participants(self):
        from config.config_loader import config_loader
        participants = config_loader.get_participants()
        assert isinstance(participants, list)
        assert len(participants) == 3
        for p in participants:
            assert "id"   in p
            assert "name" in p

    def test_get_meetings(self):
        from config.config_loader import config_loader
        meetings = config_loader.get_meetings()
        assert isinstance(meetings, list)
        assert len(meetings) >= 1
        for m in meetings:
            assert "id"          in m
            assert "date"        in m
            assert "num_entries" in m

    def test_get_generation_config(self):
        from config.config_loader import config_loader
        gen_config = config_loader.get_generation_config()
        assert isinstance(gen_config, dict)
        assert "min_duration_seconds" in gen_config
        assert "max_pause_seconds"    in gen_config
        assert "chars_per_second"     in gen_config
        assert gen_config["min_duration_seconds"] > 0
        assert gen_config["max_pause_seconds"]    > 0
        assert gen_config["chars_per_second"]     > 0

    def test_get_generation_overrides(self):
        from config.config_loader import config_loader
        overrides = config_loader.get_generation_overrides()
        assert isinstance(overrides, dict)
        # mtg001 ha override nel YAML
        if "mtg001" in overrides:
            assert "chars_per_second" in overrides["mtg001"]


# ─────────────────────────────────────────────────────────────────────────────
# SENTIMENT PREDICTOR (models/predictor.py — abstract pattern)
# ─────────────────────────────────────────────────────────────────────────────

class TestSentimentPredictor:

    @pytest.mark.unit
    def test_sentiment_predictor_initialization(self):
        from models import SentimentPredictor
        import httpx
        predictor = SentimentPredictor("http://test:5001", httpx.AsyncClient())
        assert predictor is not None
        assert predictor.model_name == "bert-sentiment"
        assert predictor.model_type == "sentiment"

    @pytest.mark.unit
    def test_normalize_output_positive(self):
        from models import SentimentPredictor
        import httpx
        predictor = SentimentPredictor("http://test:5001", httpx.AsyncClient())
        raw = {"stars": 4.5, "sentiment": "very_positive", "confidence": 0.92}
        result = predictor._normalize_output(raw)
        assert result.label.value == "positive"
        assert 0.75 <= result.score <= 1.0
        assert result.confidence == 0.92

    @pytest.mark.unit
    def test_normalize_output_neutral(self):
        from models import SentimentPredictor
        import httpx
        predictor = SentimentPredictor("http://test:5001", httpx.AsyncClient())
        raw = {"stars": 3.0, "sentiment": "neutral", "confidence": 0.75}
        result = predictor._normalize_output(raw)
        assert result.label.value == "neutral"
        assert 0.4 <= result.score <= 0.6

    @pytest.mark.unit
    def test_normalize_output_negative(self):
        from models import SentimentPredictor
        import httpx
        predictor = SentimentPredictor("http://test:5001", httpx.AsyncClient())
        raw = {"stars": 1.5, "sentiment": "very_negative", "confidence": 0.88}
        result = predictor._normalize_output(raw)
        assert result.label.value == "negative"
        assert 0.0 <= result.score <= 0.4


# ─────────────────────────────────────────────────────────────────────────────
# TOXICITY DETECTOR (models/predictor.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestToxicityDetector:

    @pytest.mark.unit
    def test_toxicity_detector_initialization(self):
        from models import ToxicityDetector
        import httpx
        detector = ToxicityDetector("http://test:5003", httpx.AsyncClient())
        assert detector is not None
        assert detector.threshold == 0.6

    @pytest.mark.unit
    def test_get_severity_low(self):
        from models import ToxicityDetector
        import httpx
        detector = ToxicityDetector("http://test:5003", httpx.AsyncClient())
        assert detector._get_severity(0.2).value == "low"

    @pytest.mark.unit
    def test_get_severity_medium(self):
        from models import ToxicityDetector
        import httpx
        detector = ToxicityDetector("http://test:5003", httpx.AsyncClient())
        assert detector._get_severity(0.5).value == "medium"

    @pytest.mark.unit
    def test_get_severity_high(self):
        from models import ToxicityDetector
        import httpx
        detector = ToxicityDetector("http://test:5003", httpx.AsyncClient())
        assert detector._get_severity(0.8).value == "high"


# ─────────────────────────────────────────────────────────────────────────────
# MOCK DATA GENERATION — schema Arianna
# ─────────────────────────────────────────────────────────────────────────────

class TestMockDataGeneration:

    def _default_meeting_config(self):
        from main import MEETINGS_CONFIG
        return MEETINGS_CONFIG[0]

    def test_generate_mock_transcript(self):
        from main import generate_mock_transcript
        num_entries    = 10
        meeting_config = self._default_meeting_config()
        transcript     = generate_mock_transcript(num_entries, meeting_config)

        assert len(transcript) == num_entries
        for entry in transcript:
            assert hasattr(entry, "conversation_turn")
            assert hasattr(entry, "participant_name")
            assert hasattr(entry, "transcribed_text")
            assert hasattr(entry, "created_at")
            assert hasattr(entry, "audio_duration_ms")
            assert entry.conversation_turn  >  0
            assert len(entry.participant_name) > 0
            assert len(entry.transcribed_text) > 0

    def test_transcript_timing_progression(self):
        """created_at deve essere crescente; audio_duration_ms > 0."""
        from main import generate_mock_transcript
        from datetime import datetime

        meeting_config = self._default_meeting_config()
        transcript     = generate_mock_transcript(5, meeting_config)

        prev_ts = None
        for entry in transcript:
            ts = datetime.fromisoformat(entry.created_at.replace("Z", ""))
            if prev_ts is not None:
                assert ts >= prev_ts
            assert entry.audio_duration_ms > 0
            prev_ts = ts

    def test_transcript_participants_valid(self):
        from main import generate_mock_transcript, PARTICIPANTS
        meeting_config = self._default_meeting_config()
        transcript     = generate_mock_transcript(20, meeting_config)
        valid_names    = [p.name for p in PARTICIPANTS]
        for entry in transcript:
            assert entry.participant_name in valid_names

    def test_transcript_is_deterministic(self):
        """Stesso meeting_config → stesso transcript (seed deterministico)."""
        from main import generate_mock_transcript
        meeting_config = self._default_meeting_config()
        t1 = generate_mock_transcript(5, meeting_config)
        t2 = generate_mock_transcript(5, meeting_config)
        for e1, e2 in zip(t1, t2):
            assert e1.participant_name == e2.participant_name
            assert e1.transcribed_text == e2.transcribed_text


# ─────────────────────────────────────────────────────────────────────────────
# PREDICTOR FACTORY
# ─────────────────────────────────────────────────────────────────────────────

class TestPredictorFactory:

    def test_create_sentiment_predictor(self):
        from models import PredictorFactory
        import httpx
        factory   = PredictorFactory(httpx.AsyncClient())
        predictor = factory.create_sentiment_predictor("http://test:5001")
        assert predictor is not None
        assert predictor.model_type == "sentiment"

    def test_create_toxicity_detector(self):
        from models import PredictorFactory
        import httpx
        factory  = PredictorFactory(httpx.AsyncClient())
        detector = factory.create_toxicity_detector("http://test:5003")
        assert detector is not None
        assert detector.threshold == 0.6