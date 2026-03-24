"""
test_integration.py — Test integrazione completi.

Fix applicati:
  • entry["nickname"] → entry["participant_name"]
  • params={"participant_id": ...} → params={"userId": ...}
  • 1 solo meeting (mtg001)
"""

import pytest
from fastapi import status


# ─────────────────────────────────────────────────────────────────────────────
# END-TO-END INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEndIntegration:

    @pytest.mark.integration
    @pytest.mark.slow
    def test_meeting_analysis_complete_flow(self, client, valid_meeting_ids):
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

    @pytest.mark.integration
    def test_sentiment_and_toxicity_consistency(self, client, valid_meeting_ids):
        response  = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis")
        data      = response.json()
        transcript = data["transcript"]
        stats      = data["metadata"]["stats"]

        assert len(transcript) == stats["total_messages"]

        sent_dist  = stats["sentiment"]["distribution"]
        total_sent = sent_dist["positive"] + sent_dist["neutral"] + sent_dist["negative"]
        assert total_sent == len(transcript)

        tox_stats = stats["toxicity"]
        assert tox_stats["toxic_count"] <= len(transcript)
        assert 0.0 <= tox_stats["toxic_ratio"] <= 1.0

    @pytest.mark.integration
    def test_filtered_analysis_maintains_integrity(self, client, valid_meeting_ids, participant_ids):
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
            assert "sentiment" in entry
            assert "toxicity"  in entry

        stats = data["metadata"]["stats"]
        assert stats["total_messages"] == len(data["transcript"])


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-SERVICE COMMUNICATION
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiServiceCommunication:

    @pytest.mark.integration
    def test_sentiment_service_integration(self, client, sample_texts):
        response = client.post("/sentiment/analyze", json={"text": sample_texts["positive"][0]})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "label" in data
        assert data["label"] in ["positive", "neutral", "negative"]
        assert 0.0 <= data["score"] <= 1.0
        assert data["model_type"] == "sentiment"

    @pytest.mark.integration
    def test_toxicity_service_integration(self, client, sample_texts):
        response = client.post("/toxicity/detect", json={"text": sample_texts["safe"][0]})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "is_toxic"       in data
        assert isinstance(data["is_toxic"], bool)
        assert 0.0 <= data["toxicity_score"] <= 1.0
        assert data["severity"] in ["low", "medium", "high"]

    @pytest.mark.integration
    @pytest.mark.slow
    def test_parallel_service_calls(self, client, valid_meeting_ids):
        response = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for entry in data["transcript"]:
            assert "sentiment" in entry
            assert "toxicity"  in entry
            assert entry["sentiment"]["label"] is not None
            assert entry["toxicity"]["is_toxic"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# DATA CONSISTENCY
# ─────────────────────────────────────────────────────────────────────────────

class TestDataConsistency:

    @pytest.mark.integration
    def test_transcript_entry_count_consistency(self, client, valid_meeting_ids):
        meeting_id = valid_meeting_ids[0]

        resp_t = client.get(f"/meeting/{meeting_id}/transcript/")
        resp_a = client.get(f"/meeting/{meeting_id}/analysis")

        count_transcript = len(resp_t.json()["transcript"])
        count_analysis   = len(resp_a.json()["transcript"])
        count_stats      = resp_a.json()["metadata"]["stats"]["total_messages"]

        assert count_transcript == count_analysis
        assert count_analysis   == count_stats

    @pytest.mark.integration
    def test_sentiment_score_distribution_valid(self, client, valid_meeting_ids):
        data   = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        stats  = data["metadata"]["stats"]
        dist   = stats["sentiment"]["distribution"]
        total  = stats["total_messages"]

        total_categorized = dist["positive"] + dist["neutral"] + dist["negative"]
        assert total_categorized == total

        expected_ratio = dist["positive"] / total
        assert abs(stats["sentiment"]["positive_ratio"] - expected_ratio) < 0.01
        assert 0.0 <= stats["sentiment"]["average_score"] <= 1.0

    @pytest.mark.integration
    def test_toxicity_counts_consistent(self, client, valid_meeting_ids):
        data      = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        stats     = data["metadata"]["stats"]
        tox_stats = stats["toxicity"]
        total     = stats["total_messages"]

        assert tox_stats["toxic_count"] <= total

        expected_ratio = tox_stats["toxic_count"] / total
        assert abs(tox_stats["toxic_ratio"] - expected_ratio) < 0.01

        sev = tox_stats["severity_distribution"]
        assert sev["low"] + sev["medium"] + sev["high"] == total


# ─────────────────────────────────────────────────────────────────────────────
# ERROR PROPAGATION
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorPropagation:

    @pytest.mark.integration
    def test_invalid_meeting_id_404(self, client, invalid_meeting_ids):
        meeting_id = invalid_meeting_ids[0]
        for endpoint in [
            f"/meeting/{meeting_id}",
            f"/meeting/{meeting_id}/transcript/",
            f"/meeting/{meeting_id}/analysis",
        ]:
            assert client.get(endpoint).status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.integration
    def test_invalid_text_sentiment_422(self, client):
        for text in ["", "   "]:
            resp = client.post("/sentiment/analyze", json={"text": text})
            assert resp.status_code in [
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ]

    @pytest.mark.integration
    def test_batch_size_limit_enforced(self, client):
        resp = client.post("/sentiment/batch", json={"texts": ["test"] * 101})
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ─────────────────────────────────────────────────────────────────────────────
# CONCURRENCY
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrency:

    @pytest.mark.integration
    @pytest.mark.slow
    def test_concurrent_sentiment_requests(self, client, sample_texts):
        import concurrent.futures
        text = sample_texts["positive"][0]

        def make_request():
            return client.post("/sentiment/analyze", json={"text": text})

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda _: make_request(), range(10)))

        for resp in results:
            assert resp.status_code == status.HTTP_200_OK