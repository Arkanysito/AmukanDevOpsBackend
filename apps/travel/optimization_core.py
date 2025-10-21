import numpy as np
import random
from collections import defaultdict
from . import constants

def _find_available_time_window(selected, new_idx, time_matrix, durations,
                                time_windows, available_windows):
    """Encuentra una ventana de tiempo disponible para una actividad"""
    if not selected:
        return available_windows[0] if available_windows else None
    
    last_idx = selected[-1]
    travel_time_minutes = time_matrix[last_idx, new_idx]
    activity_duration_minutes = durations[new_idx]
    
    total_time_needed_hours = (travel_time_minutes + activity_duration_minutes) / 60
    
    for window_idx in available_windows:
        start_time, end_time = time_windows[window_idx]
        window_duration_hours = (end_time - start_time).total_seconds() / 3600
        
        if total_time_needed_hours <= window_duration_hours:
            return window_idx
            
    return None

def _simple_geographic_clustering(coordinates, distance_calculator, n_clusters=3):
    """Clustering geográfico simple usando k-means simplificado"""
    valid_coords = [(i, c) for i, c in enumerate(coordinates) if c is not None]
    
    if len(valid_coords) < n_clusters:
        return {i: 0 for i in range(len(coordinates))}
    
    random.shuffle(valid_coords)
    centroids = [coord for _, coord in valid_coords[:n_clusters]]
    
    clusters = {}
    for i, coord in enumerate(coordinates):
        if coord is None:
            clusters[i] = 0
            continue
        
        min_dist = float('inf')
        best_cluster = 0
        
        for c_idx, centroid in enumerate(centroids):
            dist = distance_calculator(coord, centroid) # Usa la función de distancia
            if dist < min_dist:
                min_dist = dist
                best_cluster = c_idx
                
        clusters[i] = best_cluster
        
    return clusters

def _greedy_orienteeering_enhanced(scores, distance_matrix, time_matrix,
                                   durations, costs, coordinates, time_windows,
                                   budget_constraint, max_activities, distance_calculator):
    """Algoritmo greedy mejorado con clustering geográfico"""
    n = len(scores)
    selected = []
    remaining_budget = budget_constraint
    remaining_time_windows = list(range(len(time_windows)))
    
    geographic_clusters = _simple_geographic_clustering(coordinates, distance_calculator, n_clusters=3)
    cluster_counts = defaultdict(int)
    
    ratios = []
    for i in range(n):
        total_cost = costs[i] + 0.1 # Evitar división por cero
        time_value = durations[i] / 60 # Costo en horas
        base_ratio = scores[i] / (total_cost + time_value)
        
        cluster_id = geographic_clusters[i]
        diversity_bonus = 1.0 / (1.0 + cluster_counts[cluster_id] * 0.2) # Penalización
        
        final_ratio = base_ratio * diversity_bonus
        ratios.append((final_ratio, i, cluster_id))
    
    ratios.sort(reverse=True)
    
    for ratio, idx, cluster_id in ratios:
        if costs[idx] <= remaining_budget and len(selected) < max_activities:
            
            # Verificar distancia si ya hay actividades seleccionadas
            if selected:
                last_idx = selected[-1]
                travel_time = time_matrix[last_idx, idx]
                
                if travel_time > constants.MAX_TRAVEL_TIME_MINUTES:
                    continue
            
            time_window_idx = _find_available_time_window(
                selected, idx, time_matrix, durations, time_windows, remaining_time_windows
            )
            
            if time_window_idx is not None:
                selected.append(idx)
                remaining_budget -= costs[idx]
                remaining_time_windows.remove(time_window_idx)
                cluster_counts[cluster_id] += 1
                
    return selected

def solve_orienteeering_problem(optimizer_instance, activities_with_scores, 
                                time_windows, budget_constraint):
    """
    Resuelve el Problema de Orientación.
    Esta función es el "núcleo" que prepara los datos para el algoritmo greedy.
    
    Args:
        optimizer_instance: La instancia de 'ItineraryOptimizer' para acceder a sus caches.
        activities_with_scores: Lista de tuplas (actividad, score)
        time_windows: Ventanas de tiempo disponibles
        budget_constraint: Presupuesto restante
    """
    if not activities_with_scores:
        return []

    activities = [(act, score) for act, score in activities_with_scores if act is not None]
    n_activities = len(activities)
    
    if n_activities == 0:
        return []
        
    scores = np.zeros(n_activities)
    activity_objects = []
    
    for i, (activity, score) in enumerate(activities):
        adjusted_score = float(score) * 100
        # (Aquí puedes añadir más lógica de 'preferences' si es necesario)
        scores[i] = adjusted_score
        activity_objects.append(activity)

    # Preparar matrices usando los métodos cacheados del optimizador
    distance_matrix = np.zeros((n_activities, n_activities))
    coordinates = [optimizer_instance._get_coordinates(act) for act in activity_objects]
    
    for i in range(n_activities):
        for j in range(i + 1, n_activities):
            dist = optimizer_instance._calculate_distance(coordinates[i], coordinates[j])
            distance_matrix[i, j] = dist
            distance_matrix[j, i] = dist
            
    time_matrix = distance_matrix / 20 * 60 # Asumir 20 km/h -> minutos
    
    activity_durations = np.zeros(n_activities)
    activity_costs = np.zeros(n_activities)
    
    for i, activity in enumerate(activity_objects):
        activity_durations[i] = getattr(activity, 'duration_minutes', 120)
        activity_costs[i] = float(activity.price) * optimizer_instance.travelers

    # Llamar al algoritmo greedy
    selected_indices = _greedy_orienteeering_enhanced(
        scores, distance_matrix, time_matrix, activity_durations,
        activity_costs, coordinates, time_windows, budget_constraint,
        len(time_windows), # max_activities = num de ventanas disponibles
        optimizer_instance._calculate_distance # Pasar la función de distancia
    )
    
    # Formatear resultado
    result = []
    for idx in selected_indices:
        activity = activity_objects[idx]
        result.append({
            'activity': activity,
            'score': scores[idx],
            'cost': activity_costs[idx],
            'duration': activity_durations[idx]
        })
    
    optimizer_instance.performance_metrics['selected_activities'] = len(result)
    return result