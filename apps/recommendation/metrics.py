"""
Módulo para calcular métricas de evaluación del sistema de recomendaciones
"""

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import time
from typing import List, Any, Callable


def calculate_precision_at_k(recommended_items: List[Any], relevant_items: List[Any], k: int) -> float:
    """
    Calcula Precision@k: proporción de items relevantes en los primeros k recomendados
    """
    if k <= 0 or not recommended_items:
        return 0.0
    
    top_k = recommended_items[:k]
    relevant_count = len(set(top_k) & set(relevant_items))
    
    return relevant_count / min(k, len(top_k))


def calculate_recall_at_k(recommended_items: List[Any], relevant_items: List[Any], k: int) -> float:
    """
    Calcula Recall@k: proporción de items relevantes recuperados en los primeros k
    """
    if not relevant_items or not recommended_items:
        return 0.0
    
    top_k = recommended_items[:k]
    relevant_count = len(set(top_k) & set(relevant_items))
    
    return relevant_count / len(relevant_items)


def calculate_coverage(all_recommendations: List[List[Any]], total_items: int) -> float:
    """
    Calcula cobertura: porcentaje de items únicos recomendados vs total disponible
    """
    if total_items <= 0:
        return 0.0
    
    unique_recommended = set()
    for user_recs in all_recommendations:
        unique_recommended.update(user_recs)
    
    return len(unique_recommended) / total_items


def calculate_diversity(services: List[Any]) -> float:
    """
    Calcula diversidad: grado de variación temática entre servicios recomendados
    """
    if len(services) <= 1:
        return 0.0
    
    # Extraer embeddings
    embeddings = []
    for service in services:
        if hasattr(service, 'embedding') and service.embedding is not None:
            emb = service.embedding
            if isinstance(emb, list):
                # Convertir lista a array numpy
                emb_array = np.array(emb, dtype=np.float32)
            else:
                emb_array = emb
            
            # Verificar que sea un array numpy válido
            if (isinstance(emb_array, np.ndarray) and 
                emb_array.size > 0 and 
                not np.any(np.isnan(emb_array))):
                embeddings.append(emb_array)
    
    if len(embeddings) <= 1:
        return 0.0
    
    try:
        # Calcular matriz de similitud coseno
        similarity_matrix = cosine_similarity(embeddings)
        
        # Diversidad = 1 - similitud promedio (excluyendo diagonal)
        n = len(similarity_matrix)
        total_similarity = 0
        count = 0
        
        for i in range(n):
            for j in range(i + 1, n):  # Solo pares únicos, excluir diagonal
                total_similarity += similarity_matrix[i][j]
                count += 1
        
        if count == 0:
            return 0.0
        
        average_similarity = total_similarity / count
        diversity = 1.0 - average_similarity
        
        return max(0.0, min(1.0, diversity))
        
    except Exception as e:
        print(f"⚠️ Error en cálculo de diversidad: {e}")
        return 0.0


def measure_response_time(recommendation_function: Callable) -> tuple:
    """
    Mide el tiempo de respuesta de una función de recomendación
    """
    start_time = time.time()
    result = recommendation_function()
    end_time = time.time()
    
    response_time = end_time - start_time
    return response_time, result


def calculate_conversion_rate(recommended_items: List[Any], interacted_items: List[Any]) -> float:
    """
    Calcula tasa de conversión simulada
    """
    if not recommended_items:
        return 0.0
    
    converted_count = len(set(recommended_items) & set(interacted_items))
    return converted_count / len(recommended_items)


class RecommendationMetrics:
    """Clase para calcular métricas completas del sistema de recomendaciones"""
    
    def __init__(self):
        self.metrics_history = []
    
    def evaluate_recommendations(self, all_recommendations: List[List[Any]], 
                               ground_truth: List[List[Any]], 
                               total_catalog_size: int) -> dict:
        """
        Evalúa recomendaciones usando múltiples métricas
        """
        if len(all_recommendations) != len(ground_truth):
            raise ValueError("all_recommendations y ground_truth deben tener la misma longitud")
        
        k_values = [1, 5, 10]  # Valores de k para Precision@k y Recall@k
        
        metrics = {}
        
        # Precision y Recall para diferentes k
        for k in k_values:
            precision_scores = []
            recall_scores = []
            
            for recs, truth in zip(all_recommendations, ground_truth):
                precision_scores.append(calculate_precision_at_k(recs, truth, k))
                recall_scores.append(calculate_recall_at_k(recs, truth, k))
            
            metrics[f'precision@{k}'] = np.mean(precision_scores)
            metrics[f'recall@{k}'] = np.mean(recall_scores)
        
        # Cobertura
        metrics['coverage'] = calculate_coverage(all_recommendations, total_catalog_size)
        
        # Guardar en historial
        self.metrics_history.append({
            'timestamp': time.time(),
            'metrics': metrics.copy()
        })
        
        return metrics
    
    def get_metrics_trend(self) -> dict:
        """Retorna la tendencia de las métricas a lo largo del tiempo"""
        if not self.metrics_history:
            return {}
        
        trend = {}
        latest = self.metrics_history[-1]['metrics']
        
        for metric_name in latest.keys():
            values = [entry['metrics'].get(metric_name, 0) for entry in self.metrics_history]
            trend[metric_name] = {
                'current': values[-1],
                'average': np.mean(values),
                'trend': 'improving' if len(values) > 1 and values[-1] > values[-2] else 'declining'
            }
        
        return trend