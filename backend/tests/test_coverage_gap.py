"""
test_coverage_gap.py - Test per Colmare Gap Coverage

Test specifici per raggiungere 98-100% coverage.
Testano branch, exception handling, e path alternativi
tipicamente non coperti dai test base.

Total: 10 test focalizzati su coverage gap
"""

import pytest
from fastapi import status


# ============================================
# CONFIG LOADER COVERAGE
# ============================================

class TestConfigLoaderCoverage:
    """Test per coprire config_loader.py completamente"""
    
    @pytest.mark.unit
    def test_config_loader_get_config_cached(self, client):
        """
        Test che get_config usi cache.
        
        Copre branch: if self._config is None
        """
        from config.config_loader import config_loader
        
        # Prima chiamata (cache miss)
        config1 = config_loader.get_config()
        assert config1 is not None
        
        # Seconda chiamata (cache hit)
        config2 = config_loader.get_config()
        assert config2 is not None
        
        # Dovrebbero essere lo stesso oggetto (cached)
        assert config1 is config2
    
    @pytest.mark.unit
    def test_config_loader_all_getters(self, client):
        """
        Test tutti i getter del config_loader.
        
        Copre:
        - get_sample_phrases()
        - get_participants()
        - get_meetings()
        - get_generation_config()
        """
        from config.config_loader import config_loader
        
        # Test ogni getter
        phrases = config_loader.get_sample_phrases()
        assert isinstance(phrases, list)
        assert len(phrases) > 0
        
        participants = config_loader.get_participants()
        assert isinstance(participants, list)
        assert len(participants) > 0
        
        meetings = config_loader.get_meetings()
        assert isinstance(meetings, list)
        assert len(meetings) > 0
        
        gen_config = config_loader.get_generation_config()
        assert isinstance(gen_config, dict)
        assert "min_duration_seconds" in gen_config
        assert "max_pause_seconds" in gen_config
        assert "chars_per_second" in gen_config


# ============================================
# PREDICTOR MODEL COVERAGE
# ============================================

class TestPredictorModelCoverage:
    """Test per coprire models/predictor.py"""
    
    @pytest.mark.unit
    def test_sentiment_predictor_model_type(self):
        """
        Test model_type property.
        
        Copre: _get_model_type() method
        """
        from models.predictor import SentimentPredictor
        import httpx
        
        predictor = SentimentPredictor(
            service_url="http://test:5001",
            http_client=httpx.AsyncClient()
        )
        
        assert predictor.model_type == "sentiment"
    
    @pytest.mark.unit
    def test_toxicity_detector_severity_levels(self):
        """
        Test severity level calculation.
        
        Copre: _get_severity() per tutti i branch
        """
        from models.predictor import ToxicityDetector
        import httpx
        
        detector = ToxicityDetector(
            service_url="http://test:5003",
            http_client=httpx.AsyncClient()
        )
        
        # Test LOW severity (score < 0.4)
        severity_low = detector._get_severity(0.2)
        assert severity_low.value == "low"
        
        # Test MEDIUM severity (0.4 <= score < 0.7)
        severity_medium = detector._get_severity(0.5)
        assert severity_medium.value == "medium"
        
        # Test HIGH severity (score >= 0.7)
        severity_high = detector._get_severity(0.8)
        assert severity_high.value == "high"
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_predictor_batch_normalize_all_results(self, client, sample_texts):
        """
        Test che batch normalizzi tutti i risultati.
        
        Copre: loop normalization in predict_batch()
        """
        texts = sample_texts["positive"][:3]
        response = client.post("/sentiment/batch", json={"texts": texts})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Ogni predizione deve essere normalizzata
        for pred in data["predictions"]:
            assert "label" in pred
            assert pred["label"] in ["positive", "neutral", "negative"]
            assert 0.0 <= pred["score"] <= 1.0
            assert "model_type" in pred
            assert pred["model_type"] == "sentiment"


# ============================================
# ERROR PATH COVERAGE
# ============================================

class TestErrorPathCoverage:
    """Test per coprire path di errore"""
    
    @pytest.mark.api
    def test_nonexistent_route_404(self, client):
        """
        Test route inesistente.
        
        Copre: FastAPI 404 handler
        """
        response = client.get("/this/route/does/not/exist")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.api
    def test_invalid_json_body(self, client):
        """
        Test body JSON invalido.
        
        Copre: JSON parsing error path
        """
        response = client.post(
            "/sentiment/analyze",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )
        
        # FastAPI dovrebbe dare 422 per JSON invalido
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @pytest.mark.api
    def test_missing_required_field(self, client):
        """
        Test campo obbligatorio mancante.
        
        Copre: Pydantic validation error path
        """
        # POST sentiment senza "text"
        response = client.post("/sentiment/analyze", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # POST toxicity senza "text"
        response = client.post("/toxicity/detect", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @pytest.mark.api
    def test_wrong_field_type(self, client):
        """
        Test tipo campo sbagliato.
        
        Copre: Pydantic type validation
        """
        # "text" deve essere string, non int
        response = client.post("/sentiment/analyze", json={"text": 12345})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # "text" deve essere string, non array
        response = client.post("/toxicity/detect", json={"text": ["array"]})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ============================================
# BRANCH COVERAGE
# ============================================

class TestBranchCoverage:
    """Test per coprire tutti i branch condizionali"""
    
    @pytest.mark.integration
    def test_transcript_filter_with_valid_participant(self, client, valid_meeting_ids, participant_ids):
        """
        Test branch: participant filter TROVATO.
        
        Copre: if participant_name branch
        """
        meeting_id = valid_meeting_ids[0]
        participant_id = list(participant_ids.keys())[0]
        participant_name = participant_ids[participant_id]
        
        response = client.get(
            f"/meeting/{meeting_id}/transcript",
            params={"participant_id": participant_id}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Tutti messaggi devono essere del partecipante
        for entry in data["transcript"]:
            assert entry["nickname"] == participant_name
    
    @pytest.mark.integration
    def test_transcript_filter_with_invalid_participant(self, client, valid_meeting_ids):
        """
        Test branch: participant filter NON trovato.
        
        Copre: else branch quando participant non esiste
        """
        meeting_id = valid_meeting_ids[0]
        
        response = client.get(
            f"/meeting/{meeting_id}/transcript",
            params={"participant_id": "INVALID_ID_999"}
        )
        
        # Dovrebbe funzionare (ritorna lista vuota o completa)
        assert response.status_code == status.HTTP_200_OK
    
    @pytest.mark.integration
    def test_analysis_without_participant_filter(self, client, valid_meeting_ids):
        """
        Test branch: NESSUN filtro partecipante.
        
        Copre: if not participant_id branch
        """
        meeting_id = valid_meeting_ids[0]
        
        # Nessun filtro
        response = client.get(f"/meeting/{meeting_id}/analysis")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Dovrebbe avere tutti i messaggi
        assert len(data["transcript"]) > 0


# ============================================
# UTILITY ENDPOINT COVERAGE
# ============================================

class TestUtilityEndpointsCoverage:
    """Test per coprire utility endpoints"""
    
    @pytest.mark.api
    def test_participants_endpoint(self, client):
        """
        Test GET /participants.
        
        Copre: get_participants() endpoint
        """
        response = client.get("/participants")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "participants" in data
        assert isinstance(data["participants"], list)
        assert len(data["participants"]) > 0
        
        # Verifica struttura partecipante
        for participant in data["participants"]:
            assert "id" in participant
            assert "name" in participant
    
    @pytest.mark.api
    def test_meetings_list_endpoint(self, client):
        """
        Test GET /meetings.
        
        Copre: get_all_meetings() endpoint
        """
        response = client.get("/meetings")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "meetings" in data
        assert isinstance(data["meetings"], list)
        assert len(data["meetings"]) > 0
        
        # Verifica struttura meeting
        for meeting in data["meetings"]:
            assert "id" in meeting
            assert "date" in meeting
            assert "participants_count" in meeting
            assert "messages_count" in meeting
    
    @pytest.mark.api
    def test_services_status_endpoint(self, client):
        """
        Test GET /services/status.
        
        Copre: get_services_status() endpoint
        """
        response = client.get("/services/status")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verifica presenza info servizi
        assert "bert_sentiment" in data
        assert "bert_toxicity" in data
        
        for service_name in ["bert_sentiment", "bert_toxicity"]:
            service = data[service_name]
            assert "healthy" in service
            assert "url" in service
            assert "port" in service
    
    @pytest.mark.api
    def test_config_debug_endpoint(self, client):
        """
        Test GET /config (debug endpoint).
        
        Copre: get_config() debug endpoint
        """
        response = client.get("/config")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verifica struttura config
        assert "sample_phrases" in data
        assert "participants" in data
        assert "meetings" in data
        assert "generation" in data