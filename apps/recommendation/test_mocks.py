import numpy as np
from unittest.mock import Mock, patch
from django.test import TestCase
from django.core.cache import cache

from apps.recommendation.metrics import (
    calculate_precision_at_k, calculate_coverage, calculate_diversity,
    measure_response_time, calculate_conversion_rate
)

class TestRecommendationMetrics(TestCase):
    """Tests de métricas que NO dependen de la base de datos"""
    
    def setUp(self):
        cache.clear()
    
    def tearDown(self):
        cache.clear()
    
    def test_precision_at_k(self):
        """Test de cálculo de Precision@k"""
        recommended = [1, 2, 3, 4, 5]
        relevant = [1, 3, 5, 7, 9]
        k = 3
        
        precision = calculate_precision_at_k(recommended, relevant, k)
        expected = 2.0 / 3.0
        self.assertAlmostEqual(precision, expected, places=2)
    
    def test_coverage(self):
        """Test de cálculo de cobertura"""
        all_recommendations = [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
        total_items = 10
        
        coverage = calculate_coverage(all_recommendations, total_items)
        expected = 0.4  # 4 únicos / 10 total
        self.assertEqual(coverage, expected)
    
    def test_diversity(self):
        """Test de cálculo de diversidad"""
        service1 = Mock()
        service1.embedding = np.array([1.0, 0.0, 0.0])
        
        service2 = Mock()
        service2.embedding = np.array([0.0, 1.0, 0.0])
        
        service3 = Mock()
        service3.embedding = np.array([0.0, 0.0, 1.0])
        
        services = [service1, service2, service3]
        diversity = calculate_diversity(services)
        
        self.assertGreater(diversity, 0.8)
        self.assertLessEqual(diversity, 1.0)
    
    def test_conversion_rate(self):
        """Test de tasa de conversión"""
        recommended = [1, 2, 3, 4, 5]
        interacted = [1, 3, 5, 7]
        conversion = calculate_conversion_rate(recommended, interacted)
        self.assertEqual(conversion, 0.6)
    
    def test_response_time(self):
        """Test de medición de tiempo de respuesta"""
        def mock_function():
            return "result"
        
        time_taken, result = measure_response_time(mock_function)
        self.assertEqual(result, "result")
        self.assertGreaterEqual(time_taken, 0)

class TestCacheFunctions(TestCase):
    """Tests de funciones de cache que NO dependen de DB"""
    
    def setUp(self):
        cache.clear()
    
    def test_cache_operations(self):
        """Test básico de operaciones de cache"""
        from apps.recommendation.services import get_user_vector_cache_key, invalidate_user_vector_cache
        
        user_id = 123
        cache_key = get_user_vector_cache_key(user_id)
        
        # Test set/get
        test_data = np.random.rand(384)
        cache.set(cache_key, test_data, 3600)
        cached_data = cache.get(cache_key)
        
        self.assertTrue(np.array_equal(cached_data, test_data))
        
        # Test invalidación
        invalidate_user_vector_cache(user_id)
        self.assertIsNone(cache.get(cache_key))