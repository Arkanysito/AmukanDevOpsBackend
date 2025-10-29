import numpy as np
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


def cosine_similarity_matrix(embeddings):
    """Calcula matriz de similitud coseno usando numpy"""
    if not embeddings:
        return np.array([])
    
    # Convertir a array numpy 2D
    emb_array = np.array(embeddings)
    
    # Normalizar vectores
    norms = np.linalg.norm(emb_array, axis=1, keepdims=True)
    norms[norms == 0] = 1  # Evitar división por cero
    normalized = emb_array / norms
    
    # Matriz de similitud = producto punto de vectores normalizados
    similarity_matrix = np.dot(normalized, normalized.T)
    
    return similarity_matrix

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
        # Calcular matriz de similitud coseno con numpy
        similarity_matrix = cosine_similarity_matrix(embeddings)
        
        # Diversidad = 1 - similitud promedio (excluyendo diagonal)
        n = len(similarity_matrix)
        
        # Obtener triángulo superior sin la diagonal
        upper_triangle = similarity_matrix[np.triu_indices(n, k=1)]
        
        if len(upper_triangle) == 0:
            return 0.0
        
        average_similarity = np.mean(upper_triangle)
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

def calculate_average_precision(recommended_items: List[Any], relevant_items: List[Any]) -> float:
    """
    Calcula Average Precision (AP) para una única lista de recomendaciones.
    AP recompensa encontrar items relevantes más arriba en la lista.
    """
    if not relevant_items or not recommended_items:
        return 0.0

    relevant_set = set(relevant_items)
    hits = 0
    sum_precisions = 0.0

    for k, item in enumerate(recommended_items):
        if item in relevant_set:
            hits += 1
            precision_at_k = hits / (k + 1)
            sum_precisions += precision_at_k

    if not relevant_set: # Evitar división por cero si no hay items relevantes
        return 0.0
        
    # Normalizar por el número total de items relevantes
    return sum_precisions / len(relevant_set)

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

        k_values = [5, 10, 20] # Valores de k
        metrics = {}
        all_ap_scores = [] # Para calcular MAP

        # Precision, Recall y AP por usuario
        for recs, truth in zip(all_recommendations, ground_truth):
            user_ap = calculate_average_precision(recs, truth)
            all_ap_scores.append(user_ap)

            for k in k_values:
                precision_key = f'precision@{k}'
                recall_key = f'recall@{k}'
                
                # Inicializar listas si no existen
                if precision_key not in metrics: metrics[precision_key] = []
                if recall_key not in metrics: metrics[recall_key] = []

                metrics[precision_key].append(calculate_precision_at_k(recs, truth, k))
                metrics[recall_key].append(calculate_recall_at_k(recs, truth, k))

        # Calcular promedios
        for k in k_values:
            metrics[f'precision@{k}'] = np.mean(metrics[f'precision@{k}'])
            metrics[f'recall@{k}'] = np.mean(metrics[f'recall@{k}'])

        # Mean Average Precision (MAP)
        metrics['map'] = np.mean(all_ap_scores)

        # Cobertura (sin cambios)
        metrics['coverage'] = calculate_coverage(all_recommendations, total_catalog_size)

        # Guardar en historial (sin cambios)
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