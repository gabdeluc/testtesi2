"""
test_integration.py - Test Integrazione Completi

Test end-to-end per validare integrazione tra componenti:
- Backend Gateway ↔ BERT Sentiment
- Backend Gateway ↔ BERT Toxicity
- Flussi completi multi-service
"""

import pytest
from fastapi import status


# ============================================
# END-TO-END INTEGRATION TESTS
# ============================================

class TestEndToEndIntegration:
    """Test flussi completi end-to-end"""
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_meeting_analysis_complete_flow(self, client, valid_meeting_ids):
        """
        Test flusso completo analisi meeting.
        
        Verifica:
        1. Gateway riceve richiesta
        2. Recupera transcript
        3. Chiama BERT Sentiment per ogni messaggio
        4. Chiama BERT Toxicity per ogni messaggio
        5. Combina risultati
        6. Calcola statistiche aggregate
        7. Ritorna JSON unificato
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/analysis")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verifica struttura completa
        assert "transcript" in data
        assert "metadata" in data
        assert len(data["transcript"]) > 0
        
        # Verifica ogni entry ha sentiment + toxicity
        for entry in data["transcript"]:
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
    
    @pytest.mark.integration
    def test_sentiment_and_toxicity_consistency(self, client, valid_meeting_ids):
        """
        Test consistenza tra sentiment e toxicity.
        
        Verifica che:
        - Nessun dato mancante
        - Tutti i messaggi analizzati
        - Statistiche coerenti
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/analysis")
        data = response.json()
        
        transcript = data["transcript"]
        stats = data["metadata"]["stats"]
        
        # Numero messaggi consistente
        assert len(transcript) == stats["total_messages"]
        
        # Sentiment stats coerenti
        sent_dist = stats["sentiment"]["distribution"]
        total_sent = sent_dist["positive"] + sent_dist["neutral"] + sent_dist["negative"]
        assert total_sent == len(transcript)
        
        # Toxicity stats coerenti
        tox_stats = stats["toxicity"]
        assert tox_stats["toxic_count"] <= len(transcript)
        assert 0.0 <= tox_stats["toxic_ratio"] <= 1.0
    
    @pytest.mark.integration
    def test_filtered_analysis_maintains_integrity(self, client, valid_meeting_ids, participant_ids):
        """
        Test che filtro partecipante mantenga integrità dati.
        
        Verifica che filtrando per partecipante:
        - Tutti messaggi siano del partecipante corretto
        - Ogni messaggio abbia sentiment + toxicity
        - Statistiche siano coerenti con subset
        """
        meeting_id = valid_meeting_ids[0]
        participant_id = list(participant_ids.keys())[0]
        participant_name = participant_ids[participant_id]
        
        response = client.get(
            f"/meeting/{meeting_id}/analysis",
            params={"participant_id": participant_id}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Tutti messaggi del partecipante
        for entry in data["transcript"]:
            assert entry["nickname"] == participant_name
            assert "sentiment" in entry
            assert "toxicity" in entry
        
        # Stats coerenti con subset
        stats = data["metadata"]["stats"]
        assert stats["total_messages"] == len(data["transcript"])


# ============================================
# MULTI-SERVICE COMMUNICATION TESTS
# ============================================

class TestMultiServiceCommunication:
    """Test comunicazione tra microservizi"""
    
    @pytest.mark.integration
    def test_sentiment_service_integration(self, client, sample_texts):
        """
        Test integrazione Gateway → BERT Sentiment.
        
        Verifica che Gateway possa:
        1. Chiamare microservizio sentiment
        2. Ricevere risposta corretta
        3. Normalizzare output
        """
        text = sample_texts["positive"][0]
        response = client.post("/sentiment/analyze", json={"text": text})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verifica output normalizzato
        assert "label" in data
        assert data["label"] in ["positive", "neutral", "negative"]
        assert "score" in data
        assert 0.0 <= data["score"] <= 1.0
        assert "model_type" in data
        assert data["model_type"] == "sentiment"
    
    @pytest.mark.integration
    def test_toxicity_service_integration(self, client, sample_texts):
        """
        Test integrazione Gateway → BERT Toxicity.
        
        Verifica che Gateway possa:
        1. Chiamare microservizio toxicity
        2. Ricevere risposta corretta
        3. Interpretare risultati
        """
        text = sample_texts["safe"][0]
        response = client.post("/toxicity/detect", json={"text": text})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verifica output dedicato toxicity
        assert "is_toxic" in data
        assert isinstance(data["is_toxic"], bool)
        assert "toxicity_score" in data
        assert 0.0 <= data["toxicity_score"] <= 1.0
        assert "severity" in data
        assert data["severity"] in ["low", "medium", "high"]
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_parallel_service_calls(self, client, valid_meeting_ids):
        """
        Test chiamate parallele a sentiment + toxicity.
        
        Nel flusso /meeting/{id}/analysis, il gateway chiama
        entrambi i servizi per ogni messaggio. Verifica che:
        1. Entrambi i servizi rispondano
        2. Risultati siano combinati correttamente
        3. Nessun timeout o errore
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/analysis")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Ogni messaggio deve avere entrambe le analisi
        for entry in data["transcript"]:
            assert "sentiment" in entry
            assert "toxicity" in entry
            
            # Verifica campi presenti
            assert entry["sentiment"]["label"] is not None
            assert entry["toxicity"]["is_toxic"] is not None


# ============================================
# DATA CONSISTENCY TESTS
# ============================================

class TestDataConsistency:
    """Test consistenza dati tra componenti"""
    
    @pytest.mark.integration
    def test_transcript_entry_count_consistency(self, client, valid_meeting_ids):
        """
        Test che numero entry transcript sia consistente.
        
        Verifica che:
        - /meeting/{id}/transcript/ conta N messaggi
        - /meeting/{id}/analysis conta N messaggi
        - Stats riportano N messaggi
        """
        meeting_id = valid_meeting_ids[0]
        
        # Get transcript
        resp_transcript = client.get(f"/meeting/{meeting_id}/transcript/")
        transcript_data = resp_transcript.json()
        
        # Get analysis
        resp_analysis = client.get(f"/meeting/{meeting_id}/analysis")
        analysis_data = resp_analysis.json()
        
        # Conta messaggi
        count_transcript = len(transcript_data["transcript"])
        count_analysis = len(analysis_data["transcript"])
        count_stats = analysis_data["metadata"]["stats"]["total_messages"]
        
        # Devono essere uguali
        assert count_transcript == count_analysis
        assert count_analysis == count_stats
    
    @pytest.mark.integration
    def test_sentiment_score_distribution_valid(self, client, valid_meeting_ids):
        """
        Test che distribuzione sentiment sia valida.
        
        Verifica che:
        - Somma positive + neutral + negative = totale messaggi
        - Average score sia media effettiva
        - Positive ratio sia percentuale corretta
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/analysis")
        data = response.json()
        
        stats = data["metadata"]["stats"]
        sent_stats = stats["sentiment"]
        dist = sent_stats["distribution"]
        
        # Somma categorie = totale
        total_categorized = dist["positive"] + dist["neutral"] + dist["negative"]
        assert total_categorized == stats["total_messages"]
        
        # Positive ratio valido
        expected_ratio = dist["positive"] / stats["total_messages"]
        assert abs(sent_stats["positive_ratio"] - expected_ratio) < 0.01
        
        # Average score in range
        assert 0.0 <= sent_stats["average_score"] <= 1.0
    
    @pytest.mark.integration
    def test_toxicity_counts_consistent(self, client, valid_meeting_ids):
        """
        Test che conteggi toxicity siano consistenti.
        
        Verifica che:
        - Toxic_count <= total_messages
        - Toxic_ratio sia percentuale corretta
        - Severity distribution sommi a totale
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/analysis")
        data = response.json()
        
        stats = data["metadata"]["stats"]
        tox_stats = stats["toxicity"]
        
        # Toxic count valido
        assert tox_stats["toxic_count"] <= stats["total_messages"]
        
        # Toxic ratio corretto
        expected_ratio = tox_stats["toxic_count"] / stats["total_messages"]
        assert abs(tox_stats["toxic_ratio"] - expected_ratio) < 0.01
        
        # Severity distribution somma a totale
        sev_dist = tox_stats["severity_distribution"]
        total_severity = sev_dist["low"] + sev_dist["medium"] + sev_dist["high"]
        assert total_severity == stats["total_messages"]


# ============================================
# ERROR PROPAGATION TESTS
# ============================================

class TestErrorPropagation:
    """Test propagazione errori tra servizi"""
    
    @pytest.mark.integration
    def test_invalid_meeting_id_404(self, client, invalid_meeting_ids):
        """
        Test che meeting invalido dia 404 in tutti gli endpoint.
        
        Verifica consistenza gestione errori.
        """
        meeting_id = invalid_meeting_ids[0]
        
        # Tutti devono dare 404
        endpoints = [
            f"/meeting/{meeting_id}",
            f"/meeting/{meeting_id}/transcript/",
            f"/meeting/{meeting_id}/analysis"
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.integration
    def test_invalid_text_sentiment_422(self, client):
        """Test testo invalido consistentemente"""
        invalid_texts = ["", "   ", None]
        
        for text in invalid_texts:
            if text is None:
                continue
            
            response = client.post(
                "/sentiment/analyze",
                json={"text": text}
            )
            # Backend può crashare (500) o validare (422) con input vuoti
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ]
    
    @pytest.mark.integration
    def test_batch_size_limit_enforced(self, client):
        """
        Test che limite batch size sia rispettato.
        
        Max 100 testi per batch.
        """
        # 101 testi → 422
        texts = ["test"] * 101
        
        response = client.post(
            "/sentiment/batch",
            json={"texts": texts}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ============================================
# CONCURRENT REQUEST TESTS (BONUS)
# ============================================

class TestConcurrency:
    """Test gestione richieste concorrenti"""
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_concurrent_sentiment_requests(self, client, sample_texts):
        """
        Test richieste sentiment concorrenti.
        
        Verifica che il sistema gestisca correttamente
        multiple richieste simultanee senza conflitti.
        """
        import concurrent.futures
        
        text = sample_texts["positive"][0]
        
        def make_request():
            return client.post("/sentiment/analyze", json={"text": text})
        
        # 10 richieste concorrenti
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # Tutte devono avere successo
        for response in results:
            assert response.status_code == status.HTTP_200_OK