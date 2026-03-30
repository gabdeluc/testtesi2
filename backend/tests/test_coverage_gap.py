"""
test_coverage_gap.py — Test per colmare gap coverage.

Aggiornato per la piattaforma attuale:
  • userId (non participant_id)
  • participant_name (schema Arianna)
  • Aggiunto test whitespace validator
  • Aggiunto test toxic_ratio consistency
  • Rimosso riferimento a health score
"""
import pytest
from fastapi import status


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
        overrides = config_loader.get_generation_overrides()
        assert isinstance(overrides, dict)


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
            assert pred["label"] in ["positive", "neutral", "negative"]
            assert 0.0 <= pred["score"] <= 1.0
            assert pred["model_type"] == "sentiment"


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
        assert client.post("/sentiment/analyze", json={"text": 12345}).status_code    == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert client.post("/toxicity/detect",   json={"text": ["array"]}).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.api
    def test_whitespace_only_text_rejected(self, client):
        """Fix applicato: @validator con strip() rifiuta testi di soli spazi con 422."""
        assert client.post("/sentiment/analyze", json={"text": "   "}).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert client.post("/toxicity/detect",   json={"text": "   "}).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert client.post("/sentiment/analyze", json={"text": "\t\n"}).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestBranchCoverage:

    @pytest.mark.integration
    def test_transcript_filter_with_valid_participant(self, client, valid_meeting_ids, participant_ids):
        meeting_id       = valid_meeting_ids[0]
        participant_id   = list(participant_ids.keys())[0]
        participant_name = participant_ids[participant_id]
        response = client.get(f"/meeting/{meeting_id}/transcript", params={"userId": participant_id})
        assert response.status_code == status.HTTP_200_OK
        for entry in response.json()["transcript"]:
            assert entry["participant_name"] == participant_name

    @pytest.mark.integration
    def test_transcript_filter_with_invalid_participant(self, client, valid_meeting_ids):
        response = client.get(f"/meeting/{valid_meeting_ids[0]}/transcript", params={"userId": "INVALID_ID_999"})
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.integration
    def test_analysis_without_participant_filter(self, client, valid_meeting_ids):
        response = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["transcript"]) > 0

    @pytest.mark.integration
    def test_analysis_enriched_schema(self, client, valid_meeting_ids):
        """Schema Arianna + arricchimento sentiment/toxicity in ogni entry."""
        data = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        for entry in data["transcript"]:
            for field in ["conversation_turn", "participant_name", "transcribed_text", "created_at", "audio_duration_ms"]:
                assert field in entry, f"Campo Arianna mancante: {field}"
            for field in ["label", "score", "confidence", "polarity"]:
                assert field in entry["sentiment"], f"Campo sentiment mancante: {field}"
            for field in ["is_toxic", "toxicity_score", "severity", "confidence"]:
                assert field in entry["toxicity"], f"Campo toxicity mancante: {field}"


class TestToxicityMetricConsistency:

    @pytest.mark.integration
    def test_toxic_ratio_consistent_with_toxic_count(self, client, valid_meeting_ids):
        """Il gauge frontend usa toxic_ratio — deve essere coerente con toxic_count."""
        data  = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        stats = data["metadata"]["stats"]
        tox   = stats["toxicity"]
        total = stats["total_messages"]
        expected_ratio = tox["toxic_count"] / total if total > 0 else 0.0
        assert abs(tox["toxic_ratio"] - expected_ratio) < 0.001

    @pytest.mark.integration
    def test_zero_toxic_means_zero_gauge(self, client, sample_texts):
        """Con 0 messaggi tossici, toxic_ratio=0.0 → gauge mostra 0%."""
        response = client.post("/toxicity/detect/batch", json={"texts": sample_texts["safe"]})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        if data["toxic_count"] == 0:
            assert data["toxic_ratio"] == 0.0


class TestUtilityEndpointsCoverage:

    @pytest.mark.api
    def test_participants_endpoint(self, client):
        response = client.get("/participants")
        assert response.status_code == status.HTTP_200_OK
        for p in response.json()["participants"]:
            assert "id" in p and "name" in p

    @pytest.mark.api
    def test_meetings_list_endpoint(self, client):
        response = client.get("/meetings")
        assert response.status_code == status.HTTP_200_OK
        for m in response.json()["meetings"]:
            assert "id" in m and "date" in m
            assert "participants_count" in m and "messages_count" in m

    @pytest.mark.api
    def test_services_status_endpoint(self, client):
        response = client.get("/services/status")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for key in ["bert_sentiment", "bert_toxicity"]:
            assert "healthy" in data[key]
            assert "url"     in data[key]
            assert "port"    in data[key]

    @pytest.mark.api
    def test_config_debug_endpoint(self, client):
        response = client.get("/config")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for field in ["sample_phrases", "participants", "meetings", "generation"]:
            assert field in data

    @pytest.mark.api
    def test_health_endpoint_format(self, client):
        data = client.get("/health").json()
        assert data["status"]  == "healthy"
        assert data["service"] == "backend-gateway"
        assert "sentiment_mock" in data
        assert "toxicity_mock"  in data

    @pytest.mark.api
    def test_root_endpoint_format(self, client):
        data = client.get("/").json()
        assert data["status"]       == "ok"
        assert data["architecture"] == "microservices"
        assert "version"            in data