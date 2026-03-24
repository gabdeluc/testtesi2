"""
test_coverage_gap.py — Test per colmare gap coverage.

Fix applicati:
  • params={"userId": ...} (non participant_id)
  • entry["participant_name"] (non nickname)
  • /config e /services/status ora esistono in main.py
"""

import pytest
from fastapi import status


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG LOADER COVERAGE
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigLoaderCoverage:

    @pytest.mark.unit
    def test_config_loader_get_config_cached(self, client):
        from config.config_loader import config_loader
        config1 = config_loader.get_config()
        config2 = config_loader.get_config()
        assert config1 is config2

    @pytest.mark.unit
    def test_config_loader_all_getters(self, client):
        from config.config_loader import config_loader

        phrases = config_loader.get_sample_phrases()
        assert isinstance(phrases, list) and len(phrases) > 0

        participants = config_loader.get_participants()
        assert isinstance(participants, list) and len(participants) > 0

        meetings = config_loader.get_meetings()
        assert isinstance(meetings, list) and len(meetings) > 0

        gen_config = config_loader.get_generation_config()
        assert isinstance(gen_config, dict)
        assert "min_duration_seconds" in gen_config
        assert "max_pause_seconds"    in gen_config
        assert "chars_per_second"     in gen_config

        overrides = config_loader.get_generation_overrides()
        assert isinstance(overrides, dict)


# ─────────────────────────────────────────────────────────────────────────────
# PREDICTOR MODEL COVERAGE
# ─────────────────────────────────────────────────────────────────────────────

class TestPredictorModelCoverage:

    @pytest.mark.unit
    def test_sentiment_predictor_model_type(self):
        from models.predictor import SentimentPredictor
        import httpx
        predictor = SentimentPredictor("http://test:5001", httpx.AsyncClient())
        assert predictor.model_type == "sentiment"

    @pytest.mark.unit
    def test_toxicity_detector_severity_levels(self):
        from models.predictor import ToxicityDetector
        import httpx
        detector = ToxicityDetector("http://test:5003", httpx.AsyncClient())
        assert detector._get_severity(0.2).value == "low"
        assert detector._get_severity(0.5).value == "medium"
        assert detector._get_severity(0.8).value == "high"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_predictor_batch_normalize_all_results(self, client, sample_texts):
        response = client.post("/sentiment/batch", json={"texts": sample_texts["positive"][:3]})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for pred in data["predictions"]:
            assert "label"      in pred
            assert pred["label"] in ["positive", "neutral", "negative"]
            assert 0.0 <= pred["score"] <= 1.0
            assert "model_type" in pred
            assert pred["model_type"] == "sentiment"


# ─────────────────────────────────────────────────────────────────────────────
# ERROR PATH COVERAGE
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorPathCoverage:

    @pytest.mark.api
    def test_nonexistent_route_404(self, client):
        assert client.get("/this/route/does/not/exist").status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.api
    def test_invalid_json_body(self, client):
        response = client.post(
            "/sentiment/analyze",
            data="not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.api
    def test_missing_required_field(self, client):
        assert client.post("/sentiment/analyze", json={}).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert client.post("/toxicity/detect",   json={}).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.api
    def test_wrong_field_type(self, client):
        assert client.post("/sentiment/analyze", json={"text": 12345}).status_code   == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert client.post("/toxicity/detect",   json={"text": ["array"]}).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ─────────────────────────────────────────────────────────────────────────────
# BRANCH COVERAGE
# ─────────────────────────────────────────────────────────────────────────────

class TestBranchCoverage:

    @pytest.mark.integration
    def test_transcript_filter_with_valid_participant(self, client, valid_meeting_ids, participant_ids):
        meeting_id      = valid_meeting_ids[0]
        participant_id  = list(participant_ids.keys())[0]
        participant_name = participant_ids[participant_id]

        response = client.get(
            f"/meeting/{meeting_id}/transcript",
            params={"userId": participant_id},
        )
        assert response.status_code == status.HTTP_200_OK
        for entry in response.json()["transcript"]:
            assert entry["participant_name"] == participant_name

    @pytest.mark.integration
    def test_transcript_filter_with_invalid_participant(self, client, valid_meeting_ids):
        response = client.get(
            f"/meeting/{valid_meeting_ids[0]}/transcript",
            params={"userId": "INVALID_ID_999"},
        )
        # userId sconosciuto → ritorna transcript completo senza filtrare
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.integration
    def test_analysis_without_participant_filter(self, client, valid_meeting_ids):
        response = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["transcript"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY ENDPOINTS COVERAGE
# ─────────────────────────────────────────────────────────────────────────────

class TestUtilityEndpointsCoverage:

    @pytest.mark.api
    def test_participants_endpoint(self, client):
        response = client.get("/participants")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "participants" in data
        for p in data["participants"]:
            assert "id"   in p
            assert "name" in p

    @pytest.mark.api
    def test_meetings_list_endpoint(self, client):
        response = client.get("/meetings")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "meetings" in data
        for m in data["meetings"]:
            assert "id"                 in m
            assert "date"               in m
            assert "participants_count" in m
            assert "messages_count"     in m

    @pytest.mark.api
    def test_services_status_endpoint(self, client):
        response = client.get("/services/status")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for key in ["bert_sentiment", "bert_toxicity"]:
            assert key in data
            assert "healthy" in data[key]
            assert "url"     in data[key]
            assert "port"    in data[key]

    @pytest.mark.api
    def test_config_debug_endpoint(self, client):
        response = client.get("/config")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "sample_phrases" in data
        assert "participants"   in data
        assert "meetings"       in data
        assert "generation"     in data