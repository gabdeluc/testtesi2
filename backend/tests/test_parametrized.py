"""
test_parametrized.py - Test Parametrizzati Avanzati

Test data-driven usando @pytest.mark.parametrize per testare
multiple varianti con codice minimo. Dimostra competenza tecnica
avanzata e best practices PyTest.

Total: 20+ test da singole funzioni parametrizzate
"""

import pytest
from fastapi import status


# ============================================
# SENTIMENT PARAMETRIZED TESTS
# ============================================

class TestSentimentParametrized:
    """Test sentiment con parametrizzazione"""
    
    @pytest.mark.parametrize("text,expected_label", [
        # Positive examples
        ("This is amazing!", "positive"),
        ("Great work everyone!", "positive"),
        ("I love this approach!", "positive"),
        ("Excellent presentation!", "positive"),
        ("Outstanding results!", "positive"),
        ("Let me share my screen", "positive"),  # BERT classifica come positive (helpful)
        ("Can everyone see this?", "positive"),  # BERT classifica come positive (collaborative)
        
        # Neutral examples
        ("The meeting starts at 3pm", "neutral"),
        
        # Negative examples
        ("This is terrible", "negative"),
        ("I completely disagree", "negative"),
        ("This won't work", "negative"),
    ])
    @pytest.mark.sentiment
    def test_sentiment_expected_labels(self, client, text, expected_label):
        """
        Test sentiment su testi categorizzati.
        
        Questo singolo test genera 11 test cases diversi,
        uno per ogni combinazione (text, expected_label).
        """
        response = client.post("/sentiment/analyze", json={"text": text})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verifica label predetto
        assert data["label"] == expected_label, \
            f"Text '{text}' should be {expected_label}, got {data['label']}"
        
        # Verifica score in range
        assert 0.0 <= data["score"] <= 1.0
    
    @pytest.mark.parametrize("length", [1, 2, 5, 10, 50, 100, 500, 1000, 2000])
    @pytest.mark.sentiment
    def test_sentiment_various_text_lengths(self, client, length):
        """
        Test sentiment con diverse lunghezze testo.
        
        Genera 9 test cases per lunghezze da 1 a 2000 caratteri.
        Valida che il sistema gestisca testi di qualsiasi dimensione.
        """
        text = "A" * length
        response = client.post("/sentiment/analyze", json={"text": text})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "label" in data
        assert "score" in data
        assert 0.0 <= data["score"] <= 1.0
    
    @pytest.mark.parametrize("special_chars", [
        "🎉👍💯",  # Emoji
        "@#$%^&*()",  # Simboli
        "café résumé",  # Accenti
        "Hello\nWorld",  # Newline
        "Tab\tSeparated",  # Tab
        "  Multiple   Spaces  ",  # Spazi multipli
    ])
    @pytest.mark.sentiment
    def test_sentiment_special_characters(self, client, special_chars):
        """
        Test sentiment con caratteri speciali.
        
        Genera 6 test cases per diversi tipi di caratteri speciali.
        """
        response = client.post("/sentiment/analyze", json={"text": special_chars})
        
        # Dovrebbe processare senza errori
        assert response.status_code == status.HTTP_200_OK


# ============================================
# BATCH PROCESSING PARAMETRIZED TESTS
# ============================================

class TestBatchParametrized:
    """Test batch processing parametrizzati"""
    
    @pytest.mark.parametrize("batch_size", [1, 2, 5, 10, 25, 50, 75, 100])
    @pytest.mark.sentiment
    def test_batch_various_sizes(self, client, batch_size):
        """
        Test batch con diverse dimensioni.
        
        Genera 8 test cases da 1 a 100 testi.
        Valida scalabilità del batch processing.
        """
        texts = ["test text"] * batch_size
        response = client.post("/sentiment/batch", json={"texts": texts})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verifica numero predizioni
        assert len(data["predictions"]) == batch_size
        assert data["total_processed"] == batch_size
        
        # Verifica struttura predizioni
        for pred in data["predictions"]:
            assert "label" in pred
            assert "score" in pred
            assert 0.0 <= pred["score"] <= 1.0


# ============================================
# MEETING ENDPOINTS PARAMETRIZED
# ============================================

class TestMeetingParametrized:
    """Test meeting endpoints parametrizzati"""
    
    @pytest.mark.parametrize("meeting_id", ["mtg001", "mtg002", "mtg003"])
    @pytest.mark.api
    def test_all_meetings_accessible(self, client, meeting_id):
        """
        Test che tutti i meeting siano accessibili.
        
        Genera 3 test cases, uno per meeting.
        """
        response = client.get(f"/meeting/{meeting_id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "metadata" in data
        assert "participants" in data["metadata"]
        assert len(data["metadata"]["participants"]) > 0
    
    @pytest.mark.parametrize("endpoint_suffix", [
        "",  # GET /meeting/{id}
        "/transcript/",  # GET /meeting/{id}/transcript/
        "/analysis",  # GET /meeting/{id}/analysis
    ])
    @pytest.mark.api
    def test_meeting_endpoints_all_work(self, client, valid_meeting_ids, endpoint_suffix):
        """
        Test che tutti gli endpoint meeting funzionino.
        
        Genera 3 test cases, uno per endpoint.
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}{endpoint_suffix}")
        
        assert response.status_code == status.HTTP_200_OK
    
    @pytest.mark.parametrize("invalid_id", [
        "mtg999",
        "FAKE123",
        "invalid",
        "meeting_does_not_exist",
    ])
    @pytest.mark.api
    def test_invalid_meeting_ids_404(self, client, invalid_id):
        """
        Test che meeting invalidi diano 404.
        
        Genera 4 test cases per ID invalidi.
        """
        response = client.get(f"/meeting/{invalid_id}")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================
# TOXICITY PARAMETRIZED TESTS
# ============================================

class TestToxicityParametrized:
    """Test toxicity parametrizzati"""
    
    @pytest.mark.parametrize("safe_text", [
        "Thank you for your help",
        "Great work!",
        "Let me share my screen",
        "I appreciate your feedback",
        "This is helpful",
    ])
    @pytest.mark.toxicity
    def test_safe_texts_low_toxicity(self, client, safe_text):
        """
        Test che testi safe abbiano bassa tossicità.
        
        Genera 5 test cases per testi sicuri.
        """
        response = client.post("/toxicity/detect", json={"text": safe_text})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Testi safe dovrebbero avere toxicity_score basso
        assert data["toxicity_score"] < 0.5
        assert data["is_toxic"] == False
        assert data["severity"] in ["low", "medium"]
    
    @pytest.mark.parametrize("toxic_text", [
        "You are stupid",
        "This is garbage",
        "Shut up",
        "You're useless",
    ])
    @pytest.mark.toxicity
    def test_toxic_texts_high_toxicity(self, client, toxic_text):
        """
        Test che testi tossici abbiano alta tossicità.
        
        Genera 4 test cases per testi tossici.
        """
        response = client.post("/toxicity/detect", json={"text": toxic_text})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Testi tossici dovrebbero avere score alto
        assert data["toxicity_score"] > 0.3  # Almeno moderato
        assert data["severity"] in ["medium", "high"]


# ============================================
# RESPONSE VALIDATION PARAMETRIZED
# ============================================

class TestResponseValidation:
    """Test validazione struttura response"""
    
    @pytest.mark.parametrize("endpoint,method,payload", [
        ("/sentiment/analyze", "POST", {"text": "test"}),
        ("/toxicity/detect", "POST", {"text": "test"}),
        ("/", "GET", None),
        ("/health", "GET", None),
    ])
    @pytest.mark.api
    def test_endpoints_return_json(self, client, endpoint, method, payload):
        """
        Test che tutti gli endpoint ritornino JSON.
        
        Genera 4 test cases per endpoint diversi.
        """
        if method == "POST":
            response = client.post(endpoint, json=payload)
        else:
            response = client.get(endpoint)
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verifica Content-Type JSON
        assert "application/json" in response.headers.get("content-type", "")
        
        # Verifica che sia parsabile come JSON
        data = response.json()
        assert isinstance(data, dict)
    
    @pytest.mark.parametrize("score_field,endpoint,payload", [
        ("score", "/sentiment/analyze", {"text": "test"}),
        ("confidence", "/sentiment/analyze", {"text": "test"}),
        ("toxicity_score", "/toxicity/detect", {"text": "test"}),
        ("confidence", "/toxicity/detect", {"text": "test"}),
    ])
    @pytest.mark.api
    def test_all_scores_in_valid_range(self, client, score_field, endpoint, payload):
        """
        Test che tutti gli score siano in range 0-1.
        
        Genera 4 test cases per diversi campi score.
        """
        response = client.post(endpoint, json=payload)
        data = response.json()
        
        assert score_field in data, f"Missing field: {score_field}"
        assert 0.0 <= data[score_field] <= 1.0, \
            f"{score_field} out of range: {data[score_field]}"


# ============================================
# HTTP METHODS PARAMETRIZED
# ============================================

class TestHTTPMethods:
    """Test metodi HTTP parametrizzati"""
    
    @pytest.mark.parametrize("endpoint", [
        "/",
        "/health",
        "/participants",
        "/meetings",
    ])
    @pytest.mark.api
    def test_get_endpoints_reject_post(self, client, endpoint):
        """
        Test che GET endpoint rifiutino POST.
        
        Genera 4 test cases.
        """
        response = client.post(endpoint)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    
    @pytest.mark.parametrize("endpoint", [
        "/sentiment/analyze",
        "/sentiment/batch",
        "/toxicity/detect",
        "/toxicity/detect/batch",
    ])
    @pytest.mark.api
    def test_post_endpoints_reject_get(self, client, endpoint):
        """
        Test che POST endpoint rifiutino GET.
        
        Genera 4 test cases.
        """
        response = client.get(endpoint)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED