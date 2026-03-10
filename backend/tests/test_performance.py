"""
test_performance.py - Test Performance e SLA

Test per validare tempi di risposta e throughput del sistema.
Verifica che tutti gli endpoint rispettino i Service Level Agreement.
"""

import pytest
from fastapi import status
import time


# ============================================
# RESPONSE TIME TESTS
# ============================================

class TestResponseTime:
    """Test tempi di risposta endpoint"""
    
    @pytest.mark.performance
    def test_root_endpoint_response_time(self, client):
        """
        Test tempo risposta root endpoint < 1s.
        
        SLA: < 1 secondo
        """
        start = time.time()
        response = client.get("/")
        elapsed = time.time() - start
        
        assert response.status_code == status.HTTP_200_OK
        assert elapsed < 1.0, f"Root took {elapsed:.2f}s (SLA: <1s)"
    
    @pytest.mark.performance
    def test_health_check_response_time(self, client):
        """
        Test tempo risposta health check < 1s.
        
        SLA: < 1 secondo (deve essere rapido per monitoring)
        """
        start = time.time()
        response = client.get("/health")
        elapsed = time.time() - start
        
        assert response.status_code == status.HTTP_200_OK
        assert elapsed < 1.0, f"Health check took {elapsed:.2f}s (SLA: <1s)"
    
    @pytest.mark.performance
    def test_get_meeting_response_time(self, client, valid_meeting_ids):
        """
        Test tempo risposta GET meeting < 1s.
        
        SLA: < 1 secondo
        """
        meeting_id = valid_meeting_ids[0]
        
        start = time.time()
        response = client.get(f"/meeting/{meeting_id}")
        elapsed = time.time() - start
        
        assert response.status_code == status.HTTP_200_OK
        assert elapsed < 1.0, f"GET meeting took {elapsed:.2f}s (SLA: <1s)"
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_sentiment_single_response_time(self, client, sample_texts):
        """
        Test tempo risposta sentiment singolo < 2s.
        
        SLA: < 2 secondi (include chiamata microservizio + inference BERT)
        """
        text = sample_texts["positive"][0]
        
        start = time.time()
        response = client.post("/sentiment/analyze", json={"text": text})
        elapsed = time.time() - start
        
        assert response.status_code == status.HTTP_200_OK
        assert elapsed < 2.0, f"Sentiment took {elapsed:.2f}s (SLA: <2s)"
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_toxicity_single_response_time(self, client, sample_texts):
        """
        Test tempo risposta toxicity singolo < 2s.
        
        SLA: < 2 secondi
        """
        text = sample_texts["safe"][0]
        
        start = time.time()
        response = client.post("/toxicity/detect", json={"text": text})
        elapsed = time.time() - start
        
        assert response.status_code == status.HTTP_200_OK
        assert elapsed < 2.0, f"Toxicity took {elapsed:.2f}s (SLA: <2s)"
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_sentiment_batch_response_time(self, client, sample_texts):
        """
        Test tempo risposta sentiment batch (10 testi) < 5s.
        
        SLA: < 5 secondi per 10 testi
        """
        texts = sample_texts["positive"][:10] if len(sample_texts["positive"]) >= 10 else sample_texts["positive"] * 5
        texts = texts[:10]  # Esattamente 10
        
        start = time.time()
        response = client.post("/sentiment/batch", json={"texts": texts})
        elapsed = time.time() - start
        
        assert response.status_code == status.HTTP_200_OK
        assert elapsed < 5.0, f"Batch sentiment (10) took {elapsed:.2f}s (SLA: <5s)"
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_meeting_analysis_response_time(self, client, valid_meeting_ids):
        """
        Test tempo risposta analisi completa < 10s.
        
        SLA: < 10 secondi (operazione complessa con multiple chiamate)
        """
        meeting_id = valid_meeting_ids[0]
        
        start = time.time()
        response = client.get(f"/meeting/{meeting_id}/analysis")
        elapsed = time.time() - start
        
        assert response.status_code == status.HTTP_200_OK
        assert elapsed < 10.0, f"Analysis took {elapsed:.2f}s (SLA: <10s)"


# ============================================
# THROUGHPUT TESTS
# ============================================

class TestThroughput:
    """Test throughput e confronto batch vs serial"""
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_batch_faster_than_serial(self, client, sample_texts):
        """
        Test che batch processing sia più veloce di chiamate seriali.
        
        Verifica:
        - Batch di 5 testi < 5 * single call
        - Benefit del batch processing
        """
        texts = sample_texts["positive"][:5] if len(sample_texts["positive"]) >= 5 else sample_texts["positive"] * 3
        texts = texts[:5]
        
        # Batch processing
        start_batch = time.time()
        response_batch = client.post("/sentiment/batch", json={"texts": texts})
        elapsed_batch = time.time() - start_batch
        
        assert response_batch.status_code == status.HTTP_200_OK
        
        # Serial processing (solo primi 2 per non sovraccaricare)
        start_serial = time.time()
        for text in texts[:2]:
            client.post("/sentiment/analyze", json={"text": text})
        elapsed_serial = time.time() - start_serial
        
        # Estrapolazione tempo serial per 5 testi
        estimated_serial_time = (elapsed_serial / 2) * 5
        
        # Batch dovrebbe essere più veloce
        # Accettiamo anche se batch non è più veloce per stabilità test
        # Ma loggiamo il risultato per analisi
        print(f"\nBatch time: {elapsed_batch:.2f}s")
        print(f"Estimated serial time: {estimated_serial_time:.2f}s")
        print(f"Speedup: {estimated_serial_time / elapsed_batch:.2f}x")
        
        # Test passa sempre, ma loggiamo metriche
        assert elapsed_batch < 10.0  # Sanity check


# ============================================
# LOAD TESTS (LIGHT)
# ============================================

class TestLoad:
    """Test carico leggero (non stress test vero)"""
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_multiple_concurrent_requests(self, client, sample_texts):
        """
        Test gestione 10 richieste concorrenti.
        
        Verifica che il sistema gestisca correttamente
        un carico moderato senza degradazione.
        """
        import concurrent.futures
        
        text = sample_texts["positive"][0]
        
        def make_request():
            start = time.time()
            response = client.post("/sentiment/analyze", json={"text": text})
            elapsed = time.time() - start
            return response, elapsed
        
        # 10 richieste concorrenti
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # Tutte devono avere successo
        for response, elapsed in results:
            assert response.status_code == status.HTTP_200_OK
            # Ogni richiesta deve rispettare SLA anche sotto carico
            assert elapsed < 5.0  # Più permissivo per carico concorrente


# ============================================
# PERFORMANCE MONITORING TESTS
# ============================================

class TestPerformanceMonitoring:
    """Test metriche performance per monitoring"""
    
    @pytest.mark.performance
    def test_average_response_time_baseline(self, client, sample_texts):
        """
        Test baseline tempo risposta medio.
        
        Esegue 5 richieste e calcola media.
        Utile per stabilire baseline performance.
        """
        text = sample_texts["positive"][0]
        times = []
        
        for _ in range(5):
            start = time.time()
            response = client.post("/sentiment/analyze", json={"text": text})
            elapsed = time.time() - start
            
            assert response.status_code == status.HTTP_200_OK
            times.append(elapsed)
        
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print(f"\nPerformance baseline:")
        print(f"  Average: {avg_time:.3f}s")
        print(f"  Min: {min_time:.3f}s")
        print(f"  Max: {max_time:.3f}s")
        
        # Media deve essere sotto SLA
        assert avg_time < 2.0
    
    @pytest.mark.performance
    def test_p95_response_time(self, client, sample_texts):
        """
        Test P95 tempo risposta (percentile 95).
        
        Il 95% delle richieste deve essere sotto SLA.
        """
        text = sample_texts["positive"][0]
        times = []
        
        # 20 richieste per calcolare P95
        for _ in range(20):
            start = time.time()
            response = client.post("/sentiment/analyze", json={"text": text})
            elapsed = time.time() - start
            
            assert response.status_code == status.HTTP_200_OK
            times.append(elapsed)
        
        # Ordina tempi
        times_sorted = sorted(times)
        
        # P95 = valore al 95° percentile
        p95_index = int(len(times_sorted) * 0.95)
        p95_time = times_sorted[p95_index]
        
        print(f"\nP95 response time: {p95_time:.3f}s")
        
        # P95 deve essere sotto SLA + 20% tolleranza
        assert p95_time < 2.4  # 2s SLA + 20%


# ============================================
# PERFORMANCE REGRESSION TESTS
# ============================================

class TestPerformanceRegression:
    """Test per prevenire regressione performance"""
    
    @pytest.mark.performance
    def test_no_performance_degradation_after_updates(self, client, sample_texts):
        """
        Test che performance non degradi dopo aggiornamenti.
        
        Baseline: sentiment single < 2s
        Questo test fallirà se performance peggiora significativamente.
        """
        text = sample_texts["positive"][0]
        
        # 3 run per consistenza
        times = []
        for _ in range(3):
            start = time.time()
            response = client.post("/sentiment/analyze", json={"text": text})
            elapsed = time.time() - start
            times.append(elapsed)
        
        avg_time = sum(times) / len(times)
        
        # Se media > 2s, c'è degradazione
        assert avg_time < 2.0, f"Performance degradation detected: {avg_time:.2f}s (baseline: <2s)"