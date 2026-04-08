"""
test_parametrized.py — Test data-driven con @pytest.mark.parametrize.

Fix applicati:
  • meeting_id → solo "mtg001"
  • params={"userId": ...} (non participant_id)
  • entry["participant_name"] (schema Arianna)
  • expected_label allineate al mock rule-based (_POS_KEYWORDS / _NEG_KEYWORDS)
  • Testi toxic aggiornati con parole nelle _TOX_KEYWORDS
"""

import pytest
from fastapi import status


# ─────────────────────────────────────────────────────────────────────────────
# SENTIMENT PARAMETRIZED
# ─────────────────────────────────────────────────────────────────────────────

class TestSentimentParametrized:

    @pytest.mark.parametrize("text,expected_label", [
        # Positive — keyword in _POS_KEYWORDS
        ("This is amazing!",              "positive"),
        ("Great work everyone!",          "positive"),
        ("I love this approach!",         "positive"),
        ("Excellent presentation!",       "positive"),
        ("Outstanding results!",          "positive"),   # "outstanding" in _POS_KEYWORDS
        # Neutral — nessuna keyword
        ("Let me share my screen",        "neutral"),
        ("Can everyone see this?",        "neutral"),
        ("The meeting starts at 3pm",     "neutral"),
        # Negative — keyword in _NEG_KEYWORDS
        ("This is terrible and wrong",    "negative"),
        ("I disagree with this approach", "negative"),   # "disagree" in _NEG_KEYWORDS
        ("This is wrong and bad",         "negative"),
    ])
    @pytest.mark.sentiment
    def test_sentiment_expected_labels(self, client, text, expected_label):
        response = client.post("/sentiment/analyze", json={"text": text})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["label"] == expected_label, \
            f"'{text}' expected {expected_label}, got {data['label']}"
        assert 0.0 <= data["score"] <= 1.0

    @pytest.mark.parametrize("length", [1, 2, 5, 10, 50, 100, 500, 1000, 2000])
    @pytest.mark.sentiment
    def test_sentiment_various_text_lengths(self, client, length):
        response = client.post("/sentiment/analyze", json={"text": "A" * length})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "label" in data
        assert 0.0 <= data["score"] <= 1.0

    @pytest.mark.parametrize("special_chars", [
        "🎉👍💯",
        "@#$%^&*()",
        "café résumé",
        "Hello\nWorld",
        "Tab\tSeparated",
        "  Multiple   Spaces  ",
    ])
    @pytest.mark.sentiment
    def test_sentiment_special_characters(self, client, special_chars):
        response = client.post("/sentiment/analyze", json={"text": special_chars})
        assert response.status_code == status.HTTP_200_OK


# ─────────────────────────────────────────────────────────────────────────────
# BATCH PROCESSING PARAMETRIZED
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchParametrized:

    @pytest.mark.parametrize("batch_size", [1, 2, 5, 10, 25, 50, 75, 100])
    @pytest.mark.sentiment
    def test_batch_various_sizes(self, client, batch_size):
        response = client.post("/sentiment/batch", json={"texts": ["test text"] * batch_size})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["predictions"])  == batch_size
        assert data["total_processed"]   == batch_size
        for pred in data["predictions"]:
            assert "label" in pred
            assert 0.0 <= pred["score"] <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# MEETING ENDPOINTS PARAMETRIZED
# ─────────────────────────────────────────────────────────────────────────────

class TestMeetingParametrized:

    @pytest.mark.parametrize("meeting_id", ["mtg001"])
    @pytest.mark.api
    def test_all_meetings_accessible(self, client, meeting_id):
        response = client.get(f"/meeting/{meeting_id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "metadata" in data
        assert len(data["metadata"]["participants"]) > 0

    @pytest.mark.parametrize("endpoint_suffix", [
        "",
        "/transcript/",
        "/analysis",
    ])
    @pytest.mark.api
    def test_meeting_endpoints_all_work(self, client, valid_meeting_ids, endpoint_suffix):
        response = client.get(f"/meeting/{valid_meeting_ids[0]}{endpoint_suffix}")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.parametrize("invalid_id", [
        "mtg999", "FAKE123", "invalid", "meeting_does_not_exist",
    ])
    @pytest.mark.api
    def test_invalid_meeting_ids_404(self, client, invalid_id):
        assert client.get(f"/meeting/{invalid_id}").status_code == status.HTTP_404_NOT_FOUND


# ─────────────────────────────────────────────────────────────────────────────
# TOXICITY PARAMETRIZED
# ─────────────────────────────────────────────────────────────────────────────

class TestToxicityParametrized:

    @pytest.mark.parametrize("safe_text", [
        "Thank you for your help",
        "Great work!",
        "Let me share my screen",
        "I appreciate your feedback",
        "This is helpful",
    ])
    @pytest.mark.toxicity
    def test_safe_texts_low_toxicity(self, client, safe_text):
        response = client.post("/toxicity/detect", json={"text": safe_text})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["toxicity_score"] < 0.6
        assert data["is_toxic"]       == False
        assert data["severity"]       in ["low", "medium"]

    @pytest.mark.parametrize("toxic_text", [
        "You are stupid and useless",    # "stupid" + "useless" in _TOX_KEYWORDS → HIGH
        "This is garbage and crap",      # "garbage" + "crap" → HIGH
        "You are an idiot",              # "idiot" → MEDIUM/HIGH
        "Stop being so damn useless",    # "damn" + "useless" → HIGH
    ])
    @pytest.mark.toxicity
    def test_toxic_texts_high_toxicity(self, client, toxic_text):
        response = client.post("/toxicity/detect", json={"text": toxic_text})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["toxicity_score"] > 0.3
        assert data["severity"] in ["medium", "high"]


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE VALIDATION PARAMETRIZED
# ─────────────────────────────────────────────────────────────────────────────

class TestResponseValidation:

    @pytest.mark.parametrize("endpoint,method,payload", [
        ("/sentiment/analyze", "POST", {"text": "test"}),
        ("/toxicity/detect",   "POST", {"text": "test"}),
        ("/",                  "GET",  None),
        ("/health",            "GET",  None),
    ])
    @pytest.mark.api
    def test_endpoints_return_json(self, client, endpoint, method, payload):
        response = client.post(endpoint, json=payload) if method == "POST" else client.get(endpoint)
        assert response.status_code == status.HTTP_200_OK
        assert "application/json" in response.headers.get("content-type", "")
        assert isinstance(response.json(), dict)

    @pytest.mark.parametrize("score_field,endpoint,payload", [
        ("score",          "/sentiment/analyze", {"text": "test"}),
        ("confidence",     "/sentiment/analyze", {"text": "test"}),
        ("toxicity_score", "/toxicity/detect",   {"text": "test"}),
        ("confidence",     "/toxicity/detect",   {"text": "test"}),
    ])
    @pytest.mark.api
    def test_all_scores_in_valid_range(self, client, score_field, endpoint, payload):
        response = client.post(endpoint, json=payload)
        data = response.json()
        assert score_field in data, f"Missing field: {score_field}"
        assert 0.0 <= data[score_field] <= 1.0, \
            f"{score_field} out of range: {data[score_field]}"


# ─────────────────────────────────────────────────────────────────────────────
# HTTP METHODS PARAMETRIZED
# ─────────────────────────────────────────────────────────────────────────────

class TestHTTPMethods:

    @pytest.mark.parametrize("endpoint", ["/", "/health", "/participants", "/meetings"])
    @pytest.mark.api
    def test_get_endpoints_reject_post(self, client, endpoint):
        assert client.post(endpoint).status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    @pytest.mark.parametrize("endpoint", [
        "/sentiment/analyze",
        "/sentiment/batch",
        "/toxicity/detect",
        "/toxicity/detect/batch",
    ])
    @pytest.mark.api
    def test_post_endpoints_reject_get(self, client, endpoint):
        assert client.get(endpoint).status_code == status.HTTP_405_METHOD_NOT_ALLOWED