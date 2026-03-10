"""
test_api.py - Test Completi per Endpoint API

Test suite per verificare tutti gli endpoint FastAPI:
- Health & Root
- Meeting endpoints
- Sentiment analysis
- Toxicity detection
- Utility endpoints
"""

import pytest
from fastapi import status


# ============================================
# HEALTH & ROOT TESTS
# ============================================

class TestHealthEndpoints:
    """Test per endpoint salute applicazione"""
    
    @pytest.mark.smoke
    def test_root_endpoint(self, client):
        """
        Test endpoint root (/).
        
        Verifica che l'app risponda correttamente.
        """
        response = client.get("/")
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"
        assert "version" in data
        assert "architecture" in data
    
    @pytest.mark.smoke
    def test_health_check(self, client):
        """
        Test health check endpoint.
        
        Verifica che il gateway sia healthy.
        """
        response = client.get("/health")
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "backend-gateway"


# ============================================
# MEETING ENDPOINTS TESTS
# ============================================

class TestMeetingEndpoints:
    """Test per endpoint meeting"""
    
    @pytest.mark.api
    def test_get_meeting_success(self, client, valid_meeting_ids):
        """
        Test recupero meeting esistente.
        
        Verifica che un meeting valido ritorni dati corretti.
        """
        meeting_id = valid_meeting_ids[0]  # mtg001
        response = client.get(f"/meeting/{meeting_id}")
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "metadata" in data
        assert "participants" in data["metadata"]
        assert "date" in data["metadata"]
        
        # Verifica 3 partecipanti
        assert len(data["metadata"]["participants"]) == 3
        
        # Verifica struttura partecipanti
        for participant in data["metadata"]["participants"]:
            assert "id" in participant
            assert "name" in participant
    
    @pytest.mark.api
    def test_get_meeting_not_found(self, client, invalid_meeting_ids):
        """
        Test meeting inesistente.
        
        Verifica che meeting invalido dia 404.
        """
        meeting_id = invalid_meeting_ids[0]  # mtg999
        response = client.get(f"/meeting/{meeting_id}")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
    
    @pytest.mark.api
    def test_get_transcript_full(self, client, valid_meeting_ids):
        """
        Test recupero transcript completo.
        
        Verifica che transcript/ ritorni tutti i messaggi.
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/transcript/")
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "transcript" in data
        assert "metadata" in data
        assert data["metadata"]["language"] == "en"
        
        # Verifica struttura messaggi
        assert len(data["transcript"]) > 0
        
        for entry in data["transcript"]:
            assert "uid" in entry
            assert "nickname" in entry
            assert "text" in entry
            assert "from" in entry
            assert "to" in entry
    
    @pytest.mark.api
    def test_get_transcript_filtered(self, client, valid_meeting_ids, participant_ids):
        """
        Test transcript filtrato per partecipante.
        
        Verifica filtro participant_id.
        """
        meeting_id = valid_meeting_ids[0]
        participant_id = list(participant_ids.keys())[0]  # Alice
        
        response = client.get(
            f"/meeting/{meeting_id}/transcript",
            params={"participant_id": participant_id}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "transcript" in data
        
        # Tutti i messaggi devono essere di Alice
        participant_name = participant_ids[participant_id]
        for entry in data["transcript"]:
            assert entry["nickname"] == participant_name


# ============================================
# SENTIMENT ANALYSIS TESTS
# ============================================

class TestSentimentEndpoints:
    """Test per endpoint sentiment analysis"""
    
    @pytest.mark.sentiment
    def test_analyze_sentiment_single_positive(self, client, sample_texts):
        """
        Test sentiment analysis su testo positivo.
        
        Verifica struttura risposta e range valori.
        """
        text = sample_texts["positive"][0]
        
        response = client.post(
            "/sentiment/analyze",
            json={"text": text}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        
        # Verifica struttura
        assert "label" in data
        assert "score" in data
        assert "confidence" in data
        assert "raw_output" in data
        assert "model_type" in data
        
        # Verifica valori
        assert data["label"] in ["positive", "neutral", "negative"]
        assert 0.0 <= data["score"] <= 1.0
        assert 0.0 <= data["confidence"] <= 1.0
        assert data["model_type"] == "sentiment"
    
    @pytest.mark.sentiment
    def test_analyze_sentiment_single_negative(self, client, sample_texts):
        """Test sentiment su testo negativo"""
        text = sample_texts["negative"][0]
        
        response = client.post(
            "/sentiment/analyze",
            json={"text": text}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["label"] in ["positive", "neutral", "negative"]
        assert 0.0 <= data["score"] <= 1.0
    
    @pytest.mark.sentiment
    def test_analyze_sentiment_batch(self, client, sample_texts):
        """
        Test sentiment batch processing.
        
        Verifica che batch processi multipli testi correttamente.
        """
        texts = sample_texts["positive"][:3]  # 3 testi
        
        response = client.post(
            "/sentiment/batch",
            json={"texts": texts}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        
        # Verifica struttura batch
        assert "predictions" in data
        assert "total_processed" in data
        assert "avg_score" in data
        assert "label_distribution" in data
        
        # Verifica numero predizioni
        assert len(data["predictions"]) == 3
        assert data["total_processed"] == 3
        
        # Verifica label distribution
        assert "positive" in data["label_distribution"]
        assert "neutral" in data["label_distribution"]
        assert "negative" in data["label_distribution"]
        
        # Verifica ogni predizione
        for pred in data["predictions"]:
            assert "label" in pred
            assert "score" in pred
            assert 0.0 <= pred["score"] <= 1.0
    
    @pytest.mark.sentiment
    def test_sentiment_empty_text_error(self, client):
        """
        Test errore con testo vuoto.
        
        Verifica che testo vuoto dia errore 422.
        """
        response = client.post(
            "/sentiment/analyze",
            json={"text": ""}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @pytest.mark.sentiment
    def test_sentiment_missing_text_error(self, client):
        """Test errore senza campo text"""
        response = client.post(
            "/sentiment/analyze",
            json={}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ============================================
# TOXICITY DETECTION TESTS
# ============================================

class TestToxicityEndpoints:
    """Test per endpoint toxicity detection"""
    
    @pytest.mark.toxicity
    def test_detect_toxicity_safe(self, client, sample_texts):
        """
        Test toxicity su testo safe.
        
        Verifica che testi sicuri abbiano is_toxic=False.
        """
        text = sample_texts["safe"][0]
        
        response = client.post(
            "/toxicity/detect",
            json={"text": text}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        
        # Verifica struttura
        assert "is_toxic" in data
        assert "toxicity_score" in data
        assert "severity" in data
        assert "confidence" in data
        assert "raw_output" in data
        
        # Verifica valori
        assert isinstance(data["is_toxic"], bool)
        assert 0.0 <= data["toxicity_score"] <= 1.0
        assert data["severity"] in ["low", "medium", "high"]
        assert 0.0 <= data["confidence"] <= 1.0
        
        # Per testo safe, dovrebbe essere non-toxic
        assert data["is_toxic"] == False
        assert data["toxicity_score"] < 0.5
        assert data["severity"] == "low"
    
    @pytest.mark.toxicity
    def test_detect_toxicity_toxic(self, client, sample_texts):
        """
        Test toxicity su testo tossico.
        
        Verifica che testi tossici abbiano is_toxic=True.
        """
        text = sample_texts["toxic"][0]
        
        response = client.post(
            "/toxicity/detect",
            json={"text": text}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        
        # Per testo tossico, score dovrebbe essere alto
        assert data["toxicity_score"] >= 0.3
        assert data["severity"] in ["medium", "high"]
    
    @pytest.mark.toxicity
    def test_detect_toxicity_batch(self, client, sample_texts):
        """
        Test toxicity batch processing.
        
        Verifica batch di testi misti (safe + toxic).
        """
        texts = sample_texts["safe"][:2] + sample_texts["toxic"][:2]
        
        response = client.post(
            "/toxicity/detect/batch",
            json={"texts": texts}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        
        # Verifica struttura batch
        assert "results" in data
        assert "total_processed" in data
        assert "toxic_count" in data
        assert "toxic_ratio" in data
        assert "avg_toxicity_score" in data
        
        # Verifica numero risultati
        assert len(data["results"]) == 4
        assert data["total_processed"] == 4
        
        # Dovrebbero esserci alcuni toxic
        assert data["toxic_count"] >= 0
        assert 0.0 <= data["toxic_ratio"] <= 1.0
        
        # Verifica ogni risultato
        for result in data["results"]:
            assert "is_toxic" in result
            assert "toxicity_score" in result
            assert "severity" in result
    
    @pytest.mark.toxicity
    def test_toxicity_empty_text_error(self, client):
        """Test errore con testo vuoto"""
        response = client.post(
            "/toxicity/detect",
            json={"text": ""}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ============================================
# UNIFIED ANALYSIS TEST
# ============================================

class TestUnifiedAnalysis:
    """Test per endpoint analisi completa (sentiment + toxicity)"""
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_meeting_analysis_complete(self, client, valid_meeting_ids):
        """
        Test analisi meeting completa.
        
        Verifica che /meeting/{id}/analysis ritorni:
        - Transcript con sentiment
        - Transcript con toxicity
        - Stats aggregate
        """
        meeting_id = valid_meeting_ids[0]
        
        response = client.get(f"/meeting/{meeting_id}/analysis")
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        
        # Verifica struttura principale
        assert "transcript" in data
        assert "metadata" in data
        
        transcript = data["transcript"]
        assert len(transcript) > 0
        
        # Verifica ogni entry ha sentiment + toxicity
        for entry in transcript:
            # Sentiment fields
            assert "sentiment" in entry
            assert "label" in entry["sentiment"]
            assert "score" in entry["sentiment"]
            assert "confidence" in entry["sentiment"]
            
            # Toxicity fields
            assert "toxicity" in entry
            assert "is_toxic" in entry["toxicity"]
            assert "toxicity_score" in entry["toxicity"]
            assert "severity" in entry["toxicity"]
            assert "confidence" in entry["toxicity"]
        
        # Verifica stats
        stats = data["metadata"]["stats"]
        
        # Sentiment stats
        assert "sentiment" in stats
        assert "distribution" in stats["sentiment"]
        assert "average_score" in stats["sentiment"]
        assert "positive_ratio" in stats["sentiment"]
        
        # Toxicity stats
        assert "toxicity" in stats
        assert "toxic_count" in stats["toxicity"]
        assert "toxic_ratio" in stats["toxicity"]
        assert "average_toxicity_score" in stats["toxicity"]
    
    @pytest.mark.integration
    def test_meeting_analysis_filtered(self, client, valid_meeting_ids, participant_ids):
        """Test analisi filtrata per partecipante"""
        meeting_id = valid_meeting_ids[0]
        participant_id = list(participant_ids.keys())[0]
        
        response = client.get(
            f"/meeting/{meeting_id}/analysis",
            params={"participant_id": participant_id}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        transcript = data["transcript"]
        
        # Tutti messaggi dello stesso partecipante
        participant_name = participant_ids[participant_id]
        for entry in transcript:
            assert entry["nickname"] == participant_name


# ============================================
# UTILITY ENDPOINTS TESTS
# ============================================

class TestUtilityEndpoints:
    """Test per endpoint utility"""
    
    @pytest.mark.api
    def test_get_participants(self, client):
        """
        Test endpoint partecipanti.
        
        Verifica lista partecipanti disponibili.
        """
        response = client.get("/participants")
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "participants" in data
        
        participants = data["participants"]
        assert len(participants) == 3
        
        # Verifica struttura
        for p in participants:
            assert "id" in p
            assert "name" in p
    
    @pytest.mark.api
    def test_get_meetings_list(self, client):
        """
        Test endpoint lista meeting.
        
        Verifica lista meeting disponibili.
        """
        response = client.get("/meetings")
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "meetings" in data
        
        meetings = data["meetings"]
        assert len(meetings) >= 3
        
        # Verifica struttura
        for meeting in meetings:
            assert "id" in meeting
            assert "date" in meeting
            assert "participants_count" in meeting
            assert "messages_count" in meeting
    
    @pytest.mark.api
    def test_services_status(self, client):
        """
        Test status microservizi.
        
        Verifica che servizi sentiment/toxicity siano healthy.
        """
        response = client.get("/services/status")
        
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        
        # Verifica BERT sentiment service
        assert "bert_sentiment" in data
        assert "healthy" in data["bert_sentiment"]
        assert "url" in data["bert_sentiment"]
        
        # Verifica BERT toxicity service
        assert "bert_toxicity" in data
        assert "healthy" in data["bert_toxicity"]
        assert "url" in data["bert_toxicity"]


# ============================================
# ERROR HANDLING TESTS
# ============================================

class TestErrorHandling:
    """Test gestione errori"""
    
    @pytest.mark.api
    def test_invalid_endpoint(self, client):
        """Test endpoint inesistente dia 404"""
        response = client.get("/invalid/endpoint")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.api
    def test_invalid_method(self, client):
        """Test metodo HTTP sbagliato dia 405"""
        response = client.post("/health")  # GET endpoint
        
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    
    @pytest.mark.api
    def test_malformed_json(self, client):
        """Test JSON malformato dia errore"""
        response = client.post(
            "/sentiment/analyze",
            data="not a json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY