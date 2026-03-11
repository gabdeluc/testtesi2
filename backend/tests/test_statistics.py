"""
test_statistics.py - Validazione Statistiche Aggregate

Test per validare correttezza matematica delle statistiche
calcolate dal backend. Assicura che medie, percentuali e
distribuzioni siano calcolate correttamente.

Total: 9 test di validazione statistica
"""

import pytest
from fastapi import status


# ============================================
# STATISTICAL VALIDATION TESTS
# ============================================

class TestStatisticalValidation:
    """Test validazione matematica statistiche"""

    @pytest.mark.integration
    def test_sentiment_distribution_sums_to_total(self, client, valid_meeting_ids):
        """
        Test che distribuzione sentiment sommi al totale messaggi.

        Valida:
        - positive + neutral + negative = total_messages
        - Integrità matematica dei conteggi
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/analysis")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        stats = data["metadata"]["stats"]
        total_messages = stats["total_messages"]

        sent_dist = stats["sentiment"]["distribution"]
        sum_categories = (
            sent_dist["positive"] +
            sent_dist["neutral"] +
            sent_dist["negative"]
        )

        assert sum_categories == total_messages, \
            f"Sentiment distribution sum {sum_categories} != total {total_messages}"

        assert sent_dist["positive"] >= 0
        assert sent_dist["neutral"]  >= 0
        assert sent_dist["negative"] >= 0

    @pytest.mark.integration
    def test_positive_ratio_calculation_correct(self, client, valid_meeting_ids):
        """
        Test che positive_ratio sia calcolato correttamente.

        Valida:
        - positive_ratio = positive_count / total_messages
        - Precisione entro 0.001
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/analysis")
        data = response.json()

        stats         = data["metadata"]["stats"]
        total_messages = stats["total_messages"]
        sent_stats     = stats["sentiment"]
        positive_count = sent_stats["distribution"]["positive"]
        reported_ratio = sent_stats["positive_ratio"]

        if total_messages > 0:
            expected_ratio = positive_count / total_messages
        else:
            expected_ratio = 0.0

        assert abs(reported_ratio - expected_ratio) < 0.001, \
            f"Positive ratio {reported_ratio} != expected {expected_ratio}"

        assert 0.0 <= reported_ratio <= 1.0

    @pytest.mark.integration
    def test_average_sentiment_score_in_range(self, client, valid_meeting_ids):
        """
        Test che average_score sentiment (backward-compat) sia valido.

        Nota: average_score è la media grezza delle probabilità della classe
        vincente – non riflette la polarità. È mantenuto per compatibilità.
        Usare average_polarity per analisi accurate.

        Valida:
        - 0.0 <= average_score <= 1.0
        - Score è media effettiva dei singoli score
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/analysis")
        data = response.json()

        stats     = data["metadata"]["stats"]
        avg_score = stats["sentiment"]["average_score"]

        assert 0.0 <= avg_score <= 1.0, \
            f"Average score {avg_score} out of range [0, 1]"

        transcript = data["transcript"]
        if len(transcript) > 0:
            manual_avg = sum(m["sentiment"]["score"] for m in transcript) / len(transcript)
            assert abs(avg_score - manual_avg) < 0.001, \
                f"Reported avg {avg_score} != calculated {manual_avg}"

    # ──────────────────────────────────────────────────────────────────
    # NUOVO TEST  ▸  Validazione average_polarity
    # ──────────────────────────────────────────────────────────────────
    @pytest.mark.integration
    def test_average_polarity_range_and_formula(self, client, valid_meeting_ids):
        """
        Test che average_polarity sia nel range [-1, +1] e calcolata
        secondo la formula weighted-polarity corretta.

        Formula per ogni messaggio i:
            polarity_i = sign(label_i) × score_i × confidence_i

        dove:
            sign(positive)  = +1.0
            sign(neutral)   =  0.0
            sign(negative)  = -1.0

        Aggregazione:
            average_polarity = mean(polarity_i)   range [-1, +1]

        Motivazione accademica:
        - La media grezza degli score (average_score) è ambigua perché
          uno score 0.90 "positive" e uno score 0.90 "negative" hanno
          lo stesso valore numerico ma significato opposto.
        - La polarity risolve questa ambiguità assegnando segno al
          contributo di ogni messaggio e pesandolo per la confidence
          del modello: predizioni incerte pesano meno sull'aggregato.
        - Il risultato è una metrica su scala bipolare interpretabile:
            +1  →  meeting unanimemente positivo (alta confidence)
             0  →  neutro oppure positivi e negativi bilanciati
            -1  →  meeting unanimemente negativo (alta confidence)
        """
        meeting_id = valid_meeting_ids[0]
        response   = client.get(f"/meeting/{meeting_id}/analysis")
        data       = response.json()

        stats = data["metadata"]["stats"]
        assert "average_polarity" in stats["sentiment"], \
            "average_polarity mancante nelle stats sentiment"

        avg_polarity = stats["sentiment"]["average_polarity"]

        # Range [-1, +1]
        assert -1.0 <= avg_polarity <= 1.0, \
            f"average_polarity {avg_polarity} out of range [-1, +1]"

        # Verifica calcolo manuale dai messaggi del transcript
        transcript = data["transcript"]
        if len(transcript) == 0:
            return

        LABEL_SIGN = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}

        manual_polarity = sum(
            LABEL_SIGN[m["sentiment"]["label"]]
            * m["sentiment"]["score"]
            * m["sentiment"]["confidence"]
            for m in transcript
        ) / len(transcript)

        assert abs(avg_polarity - manual_polarity) < 0.001, \
            f"Reported polarity {avg_polarity} != manually calculated {manual_polarity:.4f}"

    @pytest.mark.integration
    def test_polarity_field_present_in_each_message(self, client, valid_meeting_ids):
        """
        Test che ogni messaggio del transcript esponga il campo 'polarity'.

        Il campo polarity per singolo messaggio è:
            polarity = sign(label) × score × confidence  ∈ [-1, +1]

        Permette analisi temporale della polarità messaggio per messaggio
        (es. per il Sentiment Timeline chart).
        """
        meeting_id = valid_meeting_ids[0]
        response   = client.get(f"/meeting/{meeting_id}/analysis")
        data       = response.json()

        transcript = data["transcript"]
        assert len(transcript) > 0

        LABEL_SIGN = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}

        for i, msg in enumerate(transcript):
            assert "polarity" in msg["sentiment"], \
                f"Campo 'polarity' mancante nel messaggio {i}"

            pol = msg["sentiment"]["polarity"]
            assert -1.0 <= pol <= 1.0, \
                f"Polarity {pol} del messaggio {i} fuori range [-1, +1]"

            # Verifica consistenza con label, score e confidence
            expected = round(
                LABEL_SIGN[msg["sentiment"]["label"]]
                * msg["sentiment"]["score"]
                * msg["sentiment"]["confidence"],
                4
            )
            assert abs(pol - expected) < 0.001, \
                f"Msg {i}: polarity {pol} != expected {expected}"

    # ──────────────────────────────────────────────────────────────────
    # Test esistenti toxicity (invariati)
    # ──────────────────────────────────────────────────────────────────
    @pytest.mark.integration
    def test_toxicity_counts_consistency(self, client, valid_meeting_ids):
        """
        Test consistenza conteggi toxicity.

        Valida:
        - toxic_count <= total_messages
        - toxic_count = numero messaggi con is_toxic=True
        """
        meeting_id = valid_meeting_ids[0]
        response   = client.get(f"/meeting/{meeting_id}/analysis")
        data       = response.json()

        stats         = data["metadata"]["stats"]
        total_messages = stats["total_messages"]
        tox_stats     = stats["toxicity"]
        toxic_count   = tox_stats["toxic_count"]

        assert toxic_count <= total_messages, \
            f"Toxic count {toxic_count} > total {total_messages}"

        transcript = data["transcript"]
        manual_toxic_count = sum(1 for m in transcript if m["toxicity"]["is_toxic"])

        assert toxic_count == manual_toxic_count, \
            f"Reported toxic count {toxic_count} != calculated {manual_toxic_count}"

    @pytest.mark.integration
    def test_toxic_ratio_calculation_correct(self, client, valid_meeting_ids):
        """
        Test che toxic_ratio sia calcolato correttamente.

        Valida:
        - toxic_ratio = toxic_count / total_messages
        - Precisione entro 0.001
        """
        meeting_id = valid_meeting_ids[0]
        response   = client.get(f"/meeting/{meeting_id}/analysis")
        data       = response.json()

        stats         = data["metadata"]["stats"]
        total_messages = stats["total_messages"]
        tox_stats     = stats["toxicity"]
        toxic_count   = tox_stats["toxic_count"]
        reported_ratio = tox_stats["toxic_ratio"]

        if total_messages > 0:
            expected_ratio = toxic_count / total_messages
        else:
            expected_ratio = 0.0

        assert abs(reported_ratio - expected_ratio) < 0.001, \
            f"Toxic ratio {reported_ratio} != expected {expected_ratio}"

        assert 0.0 <= reported_ratio <= 1.0

    @pytest.mark.integration
    def test_severity_distribution_sums_to_total(self, client, valid_meeting_ids):
        """
        Test che severity distribution sommi al totale.

        Valida:
        - low + medium + high = total_messages
        - Ogni severity >= 0
        """
        meeting_id = valid_meeting_ids[0]
        response   = client.get(f"/meeting/{meeting_id}/analysis")
        data       = response.json()

        stats         = data["metadata"]["stats"]
        total_messages = stats["total_messages"]
        sev_dist      = stats["toxicity"]["severity_distribution"]
        sum_severities = sev_dist["low"] + sev_dist["medium"] + sev_dist["high"]

        assert sum_severities == total_messages, \
            f"Severity sum {sum_severities} != total {total_messages}"

        assert sev_dist["low"]    >= 0
        assert sev_dist["medium"] >= 0
        assert sev_dist["high"]   >= 0

    @pytest.mark.integration
    def test_average_toxicity_score_in_range(self, client, valid_meeting_ids):
        """
        Test che average toxicity score sia valido.

        Valida:
        - 0.0 <= avg_toxicity_score <= 1.0
        - Score è media effettiva
        """
        meeting_id = valid_meeting_ids[0]
        response   = client.get(f"/meeting/{meeting_id}/analysis")
        data       = response.json()

        stats   = data["metadata"]["stats"]
        avg_tox = stats["toxicity"]["average_toxicity_score"]

        assert 0.0 <= avg_tox <= 1.0, \
            f"Average toxicity {avg_tox} out of range [0, 1]"

        transcript = data["transcript"]
        if len(transcript) > 0:
            manual_avg = sum(m["toxicity"]["toxicity_score"] for m in transcript) / len(transcript)
            assert abs(avg_tox - manual_avg) < 0.001, \
                f"Reported avg {avg_tox} != calculated {manual_avg}"