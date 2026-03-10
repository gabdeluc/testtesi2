"""
test_statistics.py - Validazione Statistiche Aggregate

Test per validare correttezza matematica delle statistiche
calcolate dal backend. Assicura che medie, percentuali e
distribuzioni siano calcolate correttamente.

Total: 8 test di validazione statistica
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
        
        # Distribuzione sentiment
        sent_dist = stats["sentiment"]["distribution"]
        sum_categories = (
            sent_dist["positive"] + 
            sent_dist["neutral"] + 
            sent_dist["negative"]
        )
        
        assert sum_categories == total_messages, \
            f"Sentiment distribution sum {sum_categories} != total {total_messages}"
        
        # Ogni categoria deve essere >= 0
        assert sent_dist["positive"] >= 0
        assert sent_dist["neutral"] >= 0
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
        
        stats = data["metadata"]["stats"]
        total_messages = stats["total_messages"]
        
        sent_stats = stats["sentiment"]
        positive_count = sent_stats["distribution"]["positive"]
        reported_ratio = sent_stats["positive_ratio"]
        
        # Calcola ratio atteso
        if total_messages > 0:
            expected_ratio = positive_count / total_messages
        else:
            expected_ratio = 0.0
        
        # Verifica con tolleranza per arrotondamenti
        assert abs(reported_ratio - expected_ratio) < 0.001, \
            f"Positive ratio {reported_ratio} != expected {expected_ratio}"
        
        # Ratio deve essere in range [0, 1]
        assert 0.0 <= reported_ratio <= 1.0
    
    @pytest.mark.integration
    def test_average_sentiment_score_in_range(self, client, valid_meeting_ids):
        """
        Test che average_score sentiment sia valido.
        
        Valida:
        - 0.0 <= average_score <= 1.0
        - Score è media effettiva dei singoli messaggi
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/analysis")
        data = response.json()
        
        stats = data["metadata"]["stats"]
        avg_score = stats["sentiment"]["average_score"]
        
        # Verifica range
        assert 0.0 <= avg_score <= 1.0, \
            f"Average score {avg_score} out of range [0, 1]"
        
        # Calcola media manualmente dai messaggi
        transcript = data["transcript"]
        if len(transcript) > 0:
            manual_avg = sum(m["sentiment"]["score"] for m in transcript) / len(transcript)
            
            # Verifica con tolleranza
            assert abs(avg_score - manual_avg) < 0.001, \
                f"Reported avg {avg_score} != calculated {manual_avg}"
    
    @pytest.mark.integration
    def test_toxicity_counts_consistency(self, client, valid_meeting_ids):
        """
        Test consistenza conteggi toxicity.
        
        Valida:
        - toxic_count <= total_messages
        - toxic_count = numero messaggi con is_toxic=True
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/analysis")
        data = response.json()
        
        stats = data["metadata"]["stats"]
        total_messages = stats["total_messages"]
        
        tox_stats = stats["toxicity"]
        toxic_count = tox_stats["toxic_count"]
        
        # Toxic count <= totale
        assert toxic_count <= total_messages, \
            f"Toxic count {toxic_count} > total {total_messages}"
        
        # Conta manualmente messaggi tossici
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
        response = client.get(f"/meeting/{meeting_id}/analysis")
        data = response.json()
        
        stats = data["metadata"]["stats"]
        total_messages = stats["total_messages"]
        
        tox_stats = stats["toxicity"]
        toxic_count = tox_stats["toxic_count"]
        reported_ratio = tox_stats["toxic_ratio"]
        
        # Calcola ratio atteso
        if total_messages > 0:
            expected_ratio = toxic_count / total_messages
        else:
            expected_ratio = 0.0
        
        # Verifica con tolleranza
        assert abs(reported_ratio - expected_ratio) < 0.001, \
            f"Toxic ratio {reported_ratio} != expected {expected_ratio}"
        
        # Ratio deve essere in range [0, 1]
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
        response = client.get(f"/meeting/{meeting_id}/analysis")
        data = response.json()
        
        stats = data["metadata"]["stats"]
        total_messages = stats["total_messages"]
        
        sev_dist = stats["toxicity"]["severity_distribution"]
        sum_severities = sev_dist["low"] + sev_dist["medium"] + sev_dist["high"]
        
        assert sum_severities == total_messages, \
            f"Severity sum {sum_severities} != total {total_messages}"
        
        # Ogni severity >= 0
        assert sev_dist["low"] >= 0
        assert sev_dist["medium"] >= 0
        assert sev_dist["high"] >= 0
    
    @pytest.mark.integration
    def test_average_toxicity_score_in_range(self, client, valid_meeting_ids):
        """
        Test che average toxicity score sia valido.
        
        Valida:
        - 0.0 <= avg_toxicity_score <= 1.0
        - Score è media effettiva
        """
        meeting_id = valid_meeting_ids[0]
        response = client.get(f"/meeting/{meeting_id}/analysis")
        data = response.json()
        
        stats = data["metadata"]["stats"]
        avg_tox = stats["toxicity"]["average_toxicity_score"]
        
        # Verifica range
        assert 0.0 <= avg_tox <= 1.0, \
            f"Average toxicity {avg_tox} out of range [0, 1]"
        
        # Calcola media manualmente
        transcript = data["transcript"]
        if len(transcript) > 0:
            manual_avg = sum(m["toxicity"]["toxicity_score"] for m in transcript) / len(transcript)
            
            # Verifica con tolleranza
            assert abs(avg_tox - manual_avg) < 0.001, \
                f"Reported avg {avg_tox} != calculated {manual_avg}"
    
    @pytest.mark.integration
    def test_filtered_stats_consistency(self, client, valid_meeting_ids, participant_ids):
        """
        Test che statistiche filtrate siano consistenti.
        
        Valida che filtrando per partecipante:
        - Stats calcolate solo sui suoi messaggi
        - Conteggi <= meeting completo
        """
        meeting_id = valid_meeting_ids[0]
        participant_id = list(participant_ids.keys())[0]
        participant_name = participant_ids[participant_id]
        
        # Get filtered analysis
        response = client.get(
            f"/meeting/{meeting_id}/analysis",
            params={"participant_id": participant_id}
        )
        data = response.json()
        
        stats = data["metadata"]["stats"]
        transcript = data["transcript"]
        
        # Tutti messaggi devono essere del partecipante
        for entry in transcript:
            assert entry["nickname"] == participant_name
        
        # Total messages deve corrispondere
        assert stats["total_messages"] == len(transcript)
        
        # Sentiment distribution deve sommare a total
        sent_dist = stats["sentiment"]["distribution"]
        assert (sent_dist["positive"] + sent_dist["neutral"] + sent_dist["negative"]) == len(transcript)


# ============================================
# STATISTICAL EDGE CASES
# ============================================

class TestStatisticalEdgeCases:
    """Test casi limite statistici"""
    
    @pytest.mark.integration
    def test_stats_with_zero_messages_handled(self, client, valid_meeting_ids, participant_ids):
        """
        Test che statistiche con 0 messaggi non crashino.
        
        Scenario: Filtro per partecipante che non ha messaggi.
        """
        meeting_id = valid_meeting_ids[0]
        
        # Crea un participant_id fake che non ha messaggi
        fake_participant_id = "NONEXISTENT999"
        
        response = client.get(
            f"/meeting/{meeting_id}/analysis",
            params={"participant_id": fake_participant_id}
        )
        
        # Dovrebbe funzionare anche con 0 messaggi
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        stats = data["metadata"]["stats"]
        
        # Con 0 messaggi, gli average dovrebbero essere 0 o gestiti
        # (backend potrebbe gestirlo diversamente)
        assert stats["total_messages"] >= 0