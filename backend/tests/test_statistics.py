"""
test_statistics.py — Validazione statistiche aggregate.

Aggiornato per la piattaforma attuale:
  • Gauge usa toxic_ratio (non average_toxicity_score)
  • Frontend usa Sentiment Polarity Index (pos-neg)/total
  • test_severity_and_toxic_count_independent verifica la distinzione
    tra messaggi tossici (soglia 0.6) e severity (score grezzo)
"""
import pytest
from fastapi import status


class TestStatisticalValidation:

    @pytest.mark.integration
    def test_sentiment_distribution_sums_to_total(self, client, valid_meeting_ids):
        data  = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        stats = data["metadata"]["stats"]
        total = stats["total_messages"]
        dist  = stats["sentiment"]["distribution"]
        assert dist["positive"] + dist["neutral"] + dist["negative"] == total

    @pytest.mark.integration
    def test_positive_ratio_calculation_correct(self, client, valid_meeting_ids):
        data  = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        stats = data["metadata"]["stats"]
        total = stats["total_messages"]
        pos   = stats["sentiment"]["distribution"]["positive"]
        ratio = stats["sentiment"]["positive_ratio"]
        expected = pos / total if total > 0 else 0.0
        assert abs(ratio - expected) < 0.001
        assert 0.0 <= ratio <= 1.0

    @pytest.mark.integration
    def test_average_sentiment_score_in_range(self, client, valid_meeting_ids):
        data      = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        avg_score = data["metadata"]["stats"]["sentiment"]["average_score"]
        assert 0.0 <= avg_score <= 1.0
        transcript = data["transcript"]
        if transcript:
            manual = sum(m["sentiment"]["score"] for m in transcript) / len(transcript)
            assert abs(avg_score - manual) < 0.001

    @pytest.mark.integration
    def test_average_polarity_range_and_formula(self, client, valid_meeting_ids):
        data  = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        stats = data["metadata"]["stats"]
        assert "average_polarity" in stats["sentiment"]
        avg_polarity = stats["sentiment"]["average_polarity"]
        assert -1.0 <= avg_polarity <= 1.0
        transcript = data["transcript"]
        if not transcript:
            return
        SIGN = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
        manual = sum(
            SIGN[m["sentiment"]["label"]] * m["sentiment"]["score"] * m["sentiment"]["confidence"]
            for m in transcript
        ) / len(transcript)
        assert abs(avg_polarity - manual) < 0.001

    @pytest.mark.integration
    def test_frontend_polarity_index_formula(self, client, valid_meeting_ids):
        """Formula (pos-neg)/total usata dal frontend — Sentiment Polarity Index (Liu 2012)."""
        data  = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        dist  = data["metadata"]["stats"]["sentiment"]["distribution"]
        total = data["metadata"]["stats"]["total_messages"]
        if total == 0:
            return
        polarity = (dist["positive"] - dist["negative"]) / total
        assert -1.0 <= polarity <= 1.0

    @pytest.mark.integration
    def test_polarity_field_present_in_each_message(self, client, valid_meeting_ids):
        data       = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        transcript = data["transcript"]
        assert len(transcript) > 0
        SIGN = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
        for i, msg in enumerate(transcript):
            assert "polarity" in msg["sentiment"], f"polarity mancante al messaggio {i}"
            pol = msg["sentiment"]["polarity"]
            assert -1.0 <= pol <= 1.0
            expected = round(
                SIGN[msg["sentiment"]["label"]] * msg["sentiment"]["score"] * msg["sentiment"]["confidence"], 4
            )
            assert abs(pol - expected) < 0.001

    @pytest.mark.integration
    def test_toxicity_counts_consistency(self, client, valid_meeting_ids):
        data       = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        stats      = data["metadata"]["stats"]
        transcript = data["transcript"]
        tox        = stats["toxicity"]
        assert tox["toxic_count"] <= stats["total_messages"]
        manual = sum(1 for m in transcript if m["toxicity"]["is_toxic"])
        assert tox["toxic_count"] == manual

    @pytest.mark.integration
    def test_toxic_ratio_calculation_correct(self, client, valid_meeting_ids):
        data  = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        stats = data["metadata"]["stats"]
        total = stats["total_messages"]
        tox   = stats["toxicity"]
        expected = tox["toxic_count"] / total if total > 0 else 0.0
        assert abs(tox["toxic_ratio"] - expected) < 0.001
        assert 0.0 <= tox["toxic_ratio"] <= 1.0

    @pytest.mark.integration
    def test_severity_distribution_sums_to_total(self, client, valid_meeting_ids):
        data  = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        stats = data["metadata"]["stats"]
        total = stats["total_messages"]
        sev   = stats["toxicity"]["severity_distribution"]
        assert sev["low"] + sev["medium"] + sev["high"] == total
        assert all(v >= 0 for v in sev.values())

    @pytest.mark.integration
    def test_toxic_ratio_zero_when_no_toxic_messages(self, client, valid_meeting_ids):
        """
        Con 0 messaggi tossici (score > TOXICITY_THRESHOLD=0.6), toxic_ratio deve essere 0.0.
        """
        data = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        tox  = data["metadata"]["stats"]["toxicity"]
        if tox["toxic_count"] == 0:
            assert tox["toxic_ratio"] == 0.0

    @pytest.mark.integration
    def test_severity_independent_from_toxic_threshold(self, client, valid_meeting_ids):
        """
        Severity e is_toxic sono metriche indipendenti:
        severity descrive lo score grezzo su TUTTI i messaggi,
        is_toxic indica solo i messaggi sopra soglia 0.6 (TOXICITY_THRESHOLD).
        Un meeting con 0 tossici può avere messaggi in severity LOW/MEDIUM.
        """
        data       = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        stats      = data["metadata"]["stats"]
        tox        = stats["toxicity"]
        total      = stats["total_messages"]
        sev        = tox["severity_distribution"]

        # Severity copre tutti i messaggi
        assert sev["low"] + sev["medium"] + sev["high"] == total

        # toxic_count copre solo quelli sopra soglia 0.6 (TOXICITY_THRESHOLD)
        assert tox["toxic_count"] <= total

        # I due contatori non devono necessariamente coincidere
        # (questa è la distinzione chiave spiegata nella tesi §3.3)

    @pytest.mark.integration
    def test_average_toxicity_score_in_range(self, client, valid_meeting_ids):
        data       = client.get(f"/meeting/{valid_meeting_ids[0]}/analysis").json()
        avg_tox    = data["metadata"]["stats"]["toxicity"]["average_toxicity_score"]
        transcript = data["transcript"]
        assert 0.0 <= avg_tox <= 1.0
        if transcript:
            manual = sum(m["toxicity"]["toxicity_score"] for m in transcript) / len(transcript)
            assert abs(avg_tox - manual) < 0.001