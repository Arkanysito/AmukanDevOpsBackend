import numpy as np
from unittest.mock import Mock, patch
from django.test import TestCase
from django.core.cache import cache
from apps.recommendation.services import (
    ModelSingleton, get_sentence_transformer, get_user_vector,
    recommend_places, get_service_embeddings_batch, 
    get_fallback_services, recommend_places_batch, RecommendationCacheMonitor,
    get_user_vector_cache_key, invalidate_user_vector_cache,
    get_recommendations_cache_key
)

# Importa las métricas desde el archivo separado
from apps.recommendation.metrics import (
    calculate_precision_at_k, calculate_coverage, calculate_diversity,
    measure_response_time, calculate_conversion_rate
)


class TestRecommendationSystem(TestCase):
    """Test suite para el sistema de recomendaciones"""

    def setUp(self):
        """Configuración inicial para todos los tests"""
        self.user = Mock()
        self.user.id = 1
        self.user.username = "test_user"
        
        self.zone = Mock()
        self.zone.zone_id = 1
        self.zone.name = "Test Zone"
        
        # Limpiar cache antes de cada test
        cache.clear()
        
        # Mock del modelo SentenceTransformer
        self.mock_model = Mock()
        self.mock_model.encode.return_value = np.random.rand(384).astype(np.float32)

    def tearDown(self):
        """Limpieza después de cada test"""
        cache.clear()

    # ============================================================================
    # Tests Básicos del Sistema
    # ============================================================================
    
    def test_model_singleton_returns_same_instance(self):
        """Test que verifica que ModelSingleton retorna la misma instancia"""
        singleton1 = ModelSingleton()
        singleton2 = ModelSingleton()
        self.assertIs(singleton1, singleton2)
    
    def test_user_vector_cache_key_generation(self):
        """Test de generación de claves de cache para vectores de usuario"""
        user_id = 123
        expected_key = f"user_vector_{user_id}"
        cache_key = get_user_vector_cache_key(user_id)
        self.assertEqual(cache_key, expected_key)
    
    def test_invalidate_user_vector_cache(self):
        """Test de invalidación de cache de vectores de usuario"""
        user_id = 123
        cache_key = get_user_vector_cache_key(user_id)
        
        # Guardar algo en cache
        test_vector = np.random.rand(384).astype(np.float32)
        cache.set(cache_key, test_vector, timeout=3600)
        
        # Verificar que está en cache
        self.assertIsNotNone(cache.get(cache_key))
        
        # Invalidar cache
        invalidate_user_vector_cache(user_id)
        
        # Verificar que ya no está en cache
        self.assertIsNone(cache.get(cache_key))

    # ============================================================================
    # Tests de Procesamiento de Embeddings
    # ============================================================================
    
    def test_get_service_embeddings_batch(self):
        """Test de procesamiento batch de embeddings de servicios"""
        # Crear servicios mock con embeddings
        service1 = Mock()
        service1.service_id = 1
        service1.embedding = np.random.rand(384).tolist()
        
        service2 = Mock()
        service2.service_id = 2
        service2.embedding = np.random.rand(384).tolist()
        
        service3 = Mock()  # Servicio sin embedding
        service3.service_id = 3
        service3.embedding = None
        
        services = [service1, service2, service3]
        
        embeddings_map = get_service_embeddings_batch(services)
        
        # Verificar resultados
        self.assertIn(1, embeddings_map)
        self.assertIn(2, embeddings_map)
        self.assertNotIn(3, embeddings_map)
        self.assertEqual(len(embeddings_map), 2)
        
        # Verificar que los embeddings son arrays numpy
        self.assertIsInstance(embeddings_map[1], np.ndarray)
        self.assertIsInstance(embeddings_map[2], np.ndarray)

    # ============================================================================
    # Tests de Métricas de Evaluación
    # ============================================================================
    
    def test_precision_at_k(self):
        """Test de cálculo de Precision@k"""
        recommended_items = [1, 2, 3, 4, 5]  # IDs de items recomendados
        relevant_items = [1, 3, 5, 7, 9]     # IDs de items relevantes
        k = 3
        
        precision = calculate_precision_at_k(recommended_items, relevant_items, k)
        
        # Entre los primeros 3 recomendados [1,2,3], los relevantes son [1,3]
        # Precision@3 = 2/3 ≈ 0.666
        expected_precision = 2.0 / 3.0
        self.assertAlmostEqual(precision, expected_precision, places=2)
    
    def test_coverage(self):
        """Test de cálculo de cobertura"""
        all_recommendations = [[1, 2, 3], [2, 3, 4], [3, 4, 5]]  # Recomendaciones para 3 usuarios
        total_items = 10  # Total de items en el catálogo
        
        coverage = calculate_coverage(all_recommendations, total_items)
        
        # Items únicos recomendados: {1,2,3,4,5} = 5 items
        # Cobertura = 5/10 = 0.5
        expected_coverage = 5.0 / 10.0
        self.assertAlmostEqual(coverage, expected_coverage, places=2)
    
    def test_diversity(self):
        """Test de cálculo de diversidad"""
        # Mock de servicios con embeddings
        service1 = Mock()
        service1.embedding = np.array([1.0, 0.0, 0.0])  # Vector unitario
        
        service2 = Mock()
        service2.embedding = np.array([0.0, 1.0, 0.0])  # Vector ortogonal
        
        service3 = Mock()
        service3.embedding = np.array([0.0, 0.0, 1.0])  # Vector ortogonal
        
        services = [service1, service2, service3]
        
        diversity = calculate_diversity(services)
        
        # Para vectores ortogonales, la diversidad debería ser alta
        self.assertGreater(diversity, 0.8)
        self.assertLessEqual(diversity, 1.0)

    # ============================================================================
    # Tests de Rendimiento
    # ============================================================================
    
    def test_response_time(self):
        """Test de tiempo de respuesta"""
        # Función mock para test
        def mock_recommendation_function():
            import time
            time.sleep(0.01)  # Simular procesamiento rápido
            return ["item1", "item2", "item3"]
        
        response_time, result = measure_response_time(mock_recommendation_function)
        
        # Verificar que se retorna el resultado correcto
        self.assertEqual(result, ["item1", "item2", "item3"])
        
        # Verificar que el tiempo de respuesta es razonable
        self.assertGreaterEqual(response_time, 0.01)
        self.assertLess(response_time, 1.0)

    # ============================================================================
    # Tests de Recomendaciones Principales - VERSIÓN CORREGIDA
    # ============================================================================

    @patch('apps.recommendation.services.get_user_vector')
    @patch('apps.recommendation.services.get_optimized_services_queryset')
    @patch('apps.recommendation.services.get_fallback_services')  # ¡NUEVO: Mock del fallback!
    def test_recommend_places_with_user_vector(self, mock_fallback, mock_get_services, mock_get_user_vector):
        """Test de recomendaciones con vector de usuario disponible"""
        # Mock del vector de usuario
        user_vector = np.random.rand(384).astype(np.float32)
        mock_get_user_vector.return_value = user_vector
        
        # Mock de servicios
        mock_service1 = Mock()
        mock_service1.service_id = 1
        mock_service1.embedding = np.random.rand(384).tolist()
        mock_service1.rating = 4.5
        
        mock_service2 = Mock()
        mock_service2.service_id = 2
        mock_service2.embedding = np.random.rand(384).tolist()
        mock_service2.rating = 4.2
        
        mock_services = Mock()
        mock_services.count.return_value = 2
        mock_services.__iter__ = Mock(return_value=iter([mock_service1, mock_service2]))
        
        mock_get_services.return_value = mock_services
        
        # Mock del fallback para evitar queries de DB
        mock_fallback.return_value = []
        
        recommendations = recommend_places(
            user=self.user,
            service_type='accommodation',
            zone=self.zone,
            top_k=5,
            use_cache=False
        )
        
        # Verificar resultados
        self.assertEqual(len(recommendations), 2)
        self.assertIsInstance(recommendations[0], tuple)
        self.assertIsInstance(recommendations[0][0], Mock)
        self.assertIsInstance(recommendations[0][1], float)
        
        # Verificar que los scores están en orden descendente
        scores = [score for _, score in recommendations]
        self.assertEqual(scores, sorted(scores, reverse=True))

    @patch('apps.recommendation.services.get_user_vector')
    @patch('apps.recommendation.services.get_fallback_services')
    def test_recommend_places_fallback(self, mock_fallback, mock_get_user_vector):
        """Test de recomendaciones con fallback (sin vector de usuario)"""
        # Mock de vector de usuario no disponible
        mock_get_user_vector.return_value = None
        
        # Mock de servicios de fallback
        mock_fallback_services = [Mock(), Mock(), Mock()]
        mock_fallback.return_value = mock_fallback_services
        
        recommendations = recommend_places(
            user=self.user,
            service_type='activity',
            zone=self.zone,
            top_k=5,
            use_cache=False
        )
        
        # Verificar que se usó el fallback
        mock_fallback.assert_called_once_with('activity', self.zone, 5)
        
        # Verificar resultados de fallback
        self.assertEqual(len(recommendations), 3)
        self.assertEqual(recommendations[0][1], 0.5)  # Score por defecto

    # ============================================================================
    # Tests de Cache de Recomendaciones
    # ============================================================================
    
    def test_recommendations_cache_key(self):
        """Test de generación de claves de cache para recomendaciones"""
        user_id = 123
        service_type = "accommodation"
        zone_id = 456
        top_k = 10
        
        cache_key = get_recommendations_cache_key(user_id, service_type, zone_id, top_k)
        
        expected_key = f"recommendations_{user_id}_{service_type}_{zone_id}_{top_k}"
        self.assertEqual(cache_key, expected_key)

    # ============================================================================
    # Tests de Monitor de Cache
    # ============================================================================
    
    def test_cache_monitor(self):
        """Test del monitor de cache"""
        # Probar get_cache_stats
        stats = RecommendationCacheMonitor.get_cache_stats()
        self.assertIsInstance(stats, dict)
        
        # Probar clear_all_recommendation_caches
        result = RecommendationCacheMonitor.clear_all_recommendation_caches()
        self.assertIsInstance(result, dict)
        self.assertIn('cleared_patterns', result)

    # ============================================================================
    # Tests de Edge Cases - VERSIÓN CORREGIDA
    # ============================================================================

    @patch('apps.recommendation.services.get_fallback_services')  # ¡Mock agregado!
    def test_recommend_places_no_user(self, mock_fallback):
        """Test de recomendaciones sin usuario"""
        # Mock del fallback para evitar queries de DB
        mock_fallback.return_value = []
        
        recommendations = recommend_places(
            user=None,
            service_type='accommodation',
            zone=self.zone,
            top_k=5,
            use_cache=False
        )
        
        # Debería retornar una lista (posiblemente vacía o con fallback)
        self.assertIsInstance(recommendations, list)

    @patch('apps.recommendation.services.get_fallback_services')  # ¡Mock agregado!
    def test_recommend_places_invalid_service_type(self, mock_fallback):
        """Test de recomendaciones con tipo de servicio inválido"""
        # Mock del fallback para evitar queries de DB
        mock_fallback.return_value = []
        
        recommendations = recommend_places(
            user=self.user,
            service_type='invalid_type',
            zone=self.zone,
            top_k=5,
            use_cache=False
        )
        
        # Debería retornar una lista vacía
        self.assertEqual(recommendations, [])

    @patch('apps.recommendation.services.get_user_vector')
    @patch('apps.recommendation.services.get_fallback_services')
    def test_recommend_places_exception_handling(self, mock_fallback, mock_get_user_vector):
        """Test de manejo de excepciones en recomendaciones"""
        # Mock que lanza excepción
        mock_get_user_vector.side_effect = Exception("Test error")
        
        # Mock del fallback
        mock_fallback.return_value = [Mock(), Mock()]
        
        # Debería manejar la excepción y retornar fallback
        recommendations = recommend_places(
            user=self.user,
            service_type='accommodation',
            zone=self.zone,
            top_k=5,
            use_cache=False
        )
        
        # Debería retornar una lista (fallback)
        self.assertIsInstance(recommendations, list)
        self.assertEqual(len(recommendations), 2)

    # ============================================================================
    # Tests de Recomendaciones en Batch - VERSIÓN CORREGIDA
    # ============================================================================

    @patch('apps.recommendation.services.get_user_vector')
    @patch('apps.recommendation.services.get_optimized_services_queryset')
    @patch('apps.recommendation.services.get_fallback_services')
    @patch('apps.recommendation.services.get_service_embeddings_batch')
    @patch('apps.recommendation.services.cache') 
    def test_recommend_places_batch_fixed(self, mock_cache, mock_embeddings_batch, mock_fallback, mock_get_services, mock_get_user_vector):
        """Test de recomendaciones en batch - VERSIÓN CORREGIDA"""
        # Crear usuarios mock
        user1 = Mock()
        user1.id = 1
        user2 = Mock()
        user2.id = 2
        users = [user1, user2]
        
        # Mock de vectores de usuario
        user1_vector = np.random.rand(384).astype(np.float32)
        user2_vector = np.random.rand(384).astype(np.float32)
        
        def user_vector_side_effect(user, use_cache=True):
            if user.id == 1:
                return user1_vector
            elif user.id == 2:
                return user2_vector
            return None
        
        mock_get_user_vector.side_effect = user_vector_side_effect
        
        # Mock de servicios
        mock_service1 = Mock()
        mock_service1.service_id = 1
        mock_service1.embedding = np.random.rand(384).tolist()
        
        mock_service2 = Mock()
        mock_service2.service_id = 2
        mock_service2.embedding = np.random.rand(384).tolist()
        
        # Retornar lista simple
        mock_get_services.return_value = [mock_service1, mock_service2]
        
        # Mock de embeddings
        mock_embeddings_batch.return_value = {
            1: np.array(mock_service1.embedding),
            2: np.array(mock_service2.embedding)
        }
        
        # Mock del fallback
        mock_fallback.return_value = []
        
        # Mock del cache para evitar problemas de serialización
        mock_cache.set = Mock()
        mock_cache.get = Mock(return_value=None)
        
        results = recommend_places_batch(
            users=users,
            service_type='accommodation',
            zone=self.zone,
            top_k=5
        )
        
        # Verificar resultados
        self.assertIn(1, results)
        self.assertIn(2, results)
        self.assertEqual(len(results[1]), 2)
        self.assertEqual(len(results[2]), 2)
        
        # Verificar que se intentó guardar en cache
        self.assertTrue(mock_cache.set.called)

class TestRecommendationMetrics(TestCase):
    """Tests adicionales para métricas específicas"""
    
    def test_conversion_rate(self):
        """Test de cálculo de tasa de conversión"""
        recommended = [1, 2, 3, 4, 5]
        interacted = [1, 3, 5, 7]
        conversion = calculate_conversion_rate(recommended, interacted)
        self.assertEqual(conversion, 0.6)  # 3 de 5 convertidos
    
    def test_empty_recommendations(self):
        """Test con recomendaciones vacías"""
        precision = calculate_precision_at_k([], [1, 2, 3], 3)
        self.assertEqual(precision, 0.0)
        
        coverage = calculate_coverage([], 10)
        self.assertEqual(coverage, 0.0)
        
        diversity = calculate_diversity([])
        self.assertEqual(diversity, 0.0)