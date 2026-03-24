"""
test_api_extended.py — Test completi endpoint FastAPI.

Fix applicati:
  • Campi schema Arianna: conversation_turn, participant_name,
    transcribed_text, created_at, audio_duration_ms
  • Query param: userId (non participant_id)
  • /toxicity/detect/batch alias aggiunto in main.py
  • GET / e /health formato corretto
  • /meetings restituisce participants_count e messages_count
"""

import pytest
from fastapi import status


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH & ROOT
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthEndpoints:

    @pytest.mark.smoke
    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "status"       in data
        assert data["status"] == "ok"
        assert "version"      in data
        assert "architecture" in data

    @pytest.mark.smoke
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"]  == "healthy"
        assert data["service"] == "backend-gateway"


# ─────────────────────────────────────────────────────────────────────────────
# MEETING ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

class TestMeetingEndpoints:

    @pytest.mark.api
    def test_get_meeting_success(self, client, valid_meeting_ids):
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "metadata" in data
        assert "participants" in data["metadata"]
        assert "date"         in data["metadata"]
        assert len(data["metadata"]["participants"]) == 3
        for p in data["metadata"]["participants"]:
            assert "id"   in p
            assert "name" in p

    @pytest.mark.api
    def test_get_meeting_not_found(self, client, invalid_meeting_ids):
        response = client.get(f"/meeting/{invalid_meeting_ids[0]}")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    @pytest.mark.api
    def test_get_transcript_full(self, client, valid_meeting_ids):
        """Verifica schema Arianna nel transcript."""
        response = client.get(f"/meeting/{valid_meeting_ids[0]}/transcript/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "transcript" in data
        assert "metadata"   in data
        assert data["metadata"]["language"] == "en"
        assert len(data["transcript"]) > 0
        for entry in data["transcript"]:
            assert "conversation_turn" in entry
            assert "participant_name"  in entry
            assert "transcribed_text"  in entry
            assert "created_at"        in entry
            assert "audio_duration_ms" in entry

    @pytest.mark.api
    def test_get_transcript_filtered(self, client, valid_meeting_ids, participant_ids):
        """Filtro per userId — schema Arianna."""
        meeting_id      = valid_meeting_ids[0]
        participant_id  = list(participant_ids.keys())[0]
        participant_name = participant_ids[participant_id]

        response = client.get(
            f"/meeting/{meeting_id}/transcript",
            params={"userId": participant_id},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "transcript" in data
        for entry in data["transcript"]:
            assert entry["participant_name"] == participant_name


# ─────────────────────────────────────────────────────────────────────────────
# SENTIMENT ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

class TestSentimentEndpoints:

    @pytest.mark.sentiment
    def test_analyze_sentiment_single_positive(self, client, sample_texts):
        text     = sample_texts["positive"][0]
        response = client.post("/sentiment/analyze", json={"text": text})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "label"      in data
        assert "score"      in data
        assert "confidence" in data
        assert "raw_output" in data
        assert "model_type" in data
        assert data["label"]      in ["positive", "neutral", "negative"]
        assert 0.0 <= data["score"]      <= 1.0
        assert 0.0 <= data["confidence"] <= 1.0
        assert data["model_type"] == "sentiment"

    @pytest.mark.sentiment
    def test_analyze_sentiment_single_negative(self, client, sample_texts):
        response = client.post("/sentiment/analyze", json={"text": sample_texts["negative"][0]})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["label"] in ["positive", "neutral", "negative"]
        assert 0.0 <= data["score"] <= 1.0

    @pytest.mark.sentiment
    def test_analyze_sentiment_batch(self, client, sample_texts):
        texts    = sample_texts["positive"][:3]
        response = client.post("/sentiment/batch", json={"texts": texts})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "predictions"        in data
        assert "total_processed"    in data
        assert "avg_score"          in data
        assert "label_distribution" in data
        assert len(data["predictions"])  == 3
        assert data["total_processed"]   == 3
        assert "positive" in data["label_distribution"]
        assert "neutral"  in data["label_distribution"]
        assert "negative" in data["label_distribution"]
        for pred in data["predictions"]:
            assert "label" in pred
            assert "score" in pred
            assert 0.0 <= pred["score"] <= 1.0

    @pytest.mark.sentiment
    def test_sentiment_empty_text_error(self, client):
        response = client.post("/sentiment/analyze", json={"text": ""})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.sentiment
    def test_sentiment_missing_text_error(self, client):
        response = client.post("/sentiment/analyze", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ─────────────────────────────────────────────────────────────────────────────
# TOXICITY DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestToxicityEndpoints:

    @pytest.mark.toxicity
    def test_detect_toxicity_safe(self, client, sample_texts):
        text     = sample_texts["safe"][0]
        response = client.post("/toxicity/detect", json={"text": text})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "is_toxic"       in data
        assert "toxicity_score" in data
        assert "severity"       in data
        assert "confidence"     in data
        assert "raw_output"     in data
        assert isinstance(data["is_toxic"], bool)
        assert 0.0 <= data["toxicity_score"] <= 1.0
        assert data["severity"] in ["low", "medium", "high"]
        assert 0.0 <= data["confidence"] <= 1.0
        assert data["is_toxic"]       == False
        assert data["toxicity_score"]  < 0.5
        assert data["severity"]       == "low"

    @pytest.mark.toxicity
    def test_detect_toxicity_toxic(self, client, sample_texts):
        text     = sample_texts["toxic"][0]
        response = client.post("/toxicity/detect", json={"text": text})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["toxicity_score"] >= 0.3
        assert data["severity"] in ["medium", "high"]

    @pytest.mark.toxicity
    def test_detect_toxicity_batch(self, client, sample_texts):
        texts    = sample_texts["safe"][:2] + sample_texts["toxic"][:2]
        response = client.post("/toxicity/detect/batch", json={"texts": texts})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "results"            in data
        assert "total_processed"    in data
        assert "toxic_count"        in data
        assert "toxic_ratio"        in data
        assert "avg_toxicity_score" in data
        assert len(data["results"])    == 4
        assert data["total_processed"] == 4
        assert data["toxic_count"]     >= 0
        assert 0.0 <= data["toxic_ratio"] <= 1.0
        for result in data["results"]:
            assert "is_toxic"       in result
            assert "toxicity_score" in result
            assert "severity"       in result

    @pytest.mark.toxicity
    def test_toxicity_empty_text_error(self, client):
        response = client.post("/toxicity/detect", json={"text": ""})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ─────────────────────────────────────────────────────────────────────────────
# UNIFIED ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

class TestUnifiedAnalysis:

    @pytest.mark.integration
    @pytest.mark.slow
    def test_meeting_analysis_complete(self, client, valid_meeting_ids):
        response = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "transcript" in data
        assert "metadata"   in data
        assert len(data["transcript"]) > 0

        for entry in data["transcript"]:
            assert "sentiment" in entry
            assert "label"      in entry["sentiment"]
            assert "score"      in entry["sentiment"]
            assert "confidence" in entry["sentiment"]
            assert "toxicity"   in entry
            assert "is_toxic"       in entry["toxicity"]
            assert "toxicity_score" in entry["toxicity"]
            assert "severity"       in entry["toxicity"]
            assert "confidence"     in entry["toxicity"]

        stats = data["metadata"]["stats"]
        assert "sentiment" in stats
        assert "distribution"    in stats["sentiment"]
        assert "average_score"   in stats["sentiment"]
        assert "positive_ratio"  in stats["sentiment"]
        assert "toxicity" in stats
        assert "toxic_count"            in stats["toxicity"]
        assert "toxic_ratio"            in stats["toxicity"]
        assert "average_toxicity_score" in stats["toxicity"]

    @pytest.mark.integration
    def test_meeting_analysis_filtered(self, client, valid_meeting_ids, participant_ids):
        meeting_id      = valid_meeting_ids[0]
        participant_id  = list(participant_ids.keys())[0]
        participant_name = participant_ids[participant_id]

        response = client.get(
            f"/meeting/{meeting_id}/analysis",
            params={"userId": participant_id},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for entry in data["transcript"]:
            assert entry["participant_name"] == participant_name


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

class TestUtilityEndpoints:

    @pytest.mark.api
    def test_get_participants(self, client):
        response = client.get("/participants")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "participants" in data
        assert len(data["participants"]) == 3
        for p in data["participants"]:
            assert "id"   in p
            assert "name" in p

    @pytest.mark.api
    def test_get_meetings_list(self, client):
        response = client.get("/meetings")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "meetings" in data
        assert len(data["meetings"]) >= 1
        for m in data["meetings"]:
            assert "id"                 in m
            assert "date"               in m
            assert "participants_count" in m
            assert "messages_count"     in m

    @pytest.mark.api
    def test_services_status(self, client):
        response = client.get("/services/status")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "bert_sentiment" in data
        assert "healthy" in data["bert_sentiment"]
        assert "url"     in data["bert_sentiment"]
        assert "bert_toxicity" in data
        assert "healthy" in data["bert_toxicity"]
        assert "url"     in data["bert_toxicity"]


# ─────────────────────────────────────────────────────────────────────────────
# ERROR HANDLING
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorHandling:

    @pytest.mark.api
    def test_invalid_endpoint(self, client):
        response = client.get("/invalid/endpoint")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.api
    def test_invalid_method(self, client):
        response = client.post("/health")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    @pytest.mark.api
    def test_malformed_json(self, client):
        response = client.post(
            "/sentiment/analyze",
            data="not a json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY