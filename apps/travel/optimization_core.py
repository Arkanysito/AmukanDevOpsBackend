# apps/travel/optimization_core.py

import numpy as np
import random
from collections import defaultdict
from .constants import PLACE_PRIORITY_BOOST, DIVERSITY_PENALTY, MAX_TRAVEL_TIME_MINUTES, DEFAULT_ACTIVITY_DURATION_MINUTES
from datetime import timedelta
import logging
from apps.location.models import Place

logger = logging.getLogger(__name__)


def _find_valid_windows(selected_indices, new_idx, time_matrix, durations,
                        time_windows, available_window_indices, last_activity_end_time=None):
    """
    Encuentra TODAS las ventanas de tiempo disponibles para una actividad,
    considerando el tiempo de viaje desde la última actividad.
    """
    valid_window_indices = []

    if not selected_indices:
        # Si es la primera actividad, cualquier ventana que la soporte sirve
        activity_duration_hours = durations[new_idx] / 60
        for window_idx in available_window_indices:
            start_time, end_time = time_windows[window_idx]
            window_duration_hours = (end_time - start_time).total_seconds() / 3600
            if activity_duration_hours <= window_duration_hours:
                # Para la primera actividad, asumimos que empieza al inicio de la ventana
                activity_start_time = start_time
                activity_end_time = start_time + timedelta(minutes=durations[new_idx])
                valid_window_indices.append((window_idx, activity_start_time, activity_end_time))
        # logger.debug(f"Primer Actividad (idx {new_idx}): Ventanas válidas encontradas: {len(valid_window_indices)}")
        return valid_window_indices

    # Si ya hay actividades, calcular tiempo de viaje
    last_idx = selected_indices[-1]
    travel_time_minutes = time_matrix[last_idx, new_idx]
    activity_duration_minutes = durations[new_idx]

    total_time_needed_minutes = travel_time_minutes + activity_duration_minutes

    for window_idx in available_window_indices:
        window_start, window_end = time_windows[window_idx]

        # El inicio real de la actividad debe ser DESPUÉS de la última actividad + viaje
        # y DENTRO de la ventana
        potential_start_time = max(
            last_activity_end_time + timedelta(minutes=travel_time_minutes),
            window_start
        )

        potential_end_time = potential_start_time + timedelta(minutes=activity_duration_minutes)

        # Verificar si la actividad cabe en la ventana
        if potential_end_time <= window_end:
            valid_window_indices.append((window_idx, potential_start_time, potential_end_time))

    # logger.debug(f"Actividad (idx {new_idx}) tras idx {last_idx}: Ventanas válidas encontradas: {len(valid_window_indices)}")
    return valid_window_indices


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
                                   budget_constraint, max_activities, distance_calculator,
                                   activity_objects, # Necesario para IDs e info
                                   strategy='balanced',
                                   exclude_activity_ids=None): # Parámetro de diversidad
    """
    Algoritmo greedy mejorado con logging detallado y prioridad para Places.
    """
    n = len(scores)
    selected_indices = []
    selected_details = [] # (idx, start_time, end_time)

    if exclude_activity_ids is None:
        exclude_activity_ids = set()

    remaining_budget = budget_constraint

    # --- Lógica de Balanceo de Días ---
    window_day_map = [tw[0].date() for tw in time_windows]
    day_activity_count = defaultdict(int)
    remaining_window_indices = set(range(len(time_windows)))

    geographic_clusters = _simple_geographic_clustering(coordinates, distance_calculator, n_clusters=3)
    cluster_counts = defaultdict(int)
    
    ratios = []
    #logger.debug(f"--- Calculando Ratios para {n} candidatos (Estrategia: {strategy}) ---")
    for i in range(n):

        activity = activity_objects[i]
        is_place = isinstance(activity, Place)
        activity_type = "Place" if is_place else "ActivityService"
        activity_name = getattr(activity, 'name', 'N/A')
        activity_id = getattr(activity, 'service_id', 'N/A')

        # --- Lógica de Estrategia y Diversidad ---
        base_score = scores[i]

        # 1. Penalización por Diversidad
        is_penalized = False
        if activity_id and activity_id in exclude_activity_ids:
            base_score *= DIVERSITY_PENALTY
            is_penalized = True

        # 2. Bonus por Clustering (Diversidad geográfica)
        cluster_id = geographic_clusters[i]
        diversity_bonus = 1.0 / (1.0 + cluster_counts.get(cluster_id, 0) * 0.2)

        score_with_bonus = base_score * diversity_bonus

        # Boost para Places
        place_boost_applied = False
        if is_place:
            score_with_bonus *= PLACE_PRIORITY_BOOST
            place_boost_applied = True

        # 3. Ratio por Estrategia
        time_cost_hours = (durations[i] / 60) + 0.1 # +0.1 para evitar división por cero
        money_cost = costs[i] + 0.1

        final_ratio = 0
        try:
            if strategy == 'budget':
                final_ratio = score_with_bonus / (time_cost_hours * money_cost)
            elif strategy == 'premium':
                final_ratio = score_with_bonus / time_cost_hours
            else: # 'balanced'
                final_ratio = score_with_bonus / (time_cost_hours * (money_cost ** 0.5))
        except ZeroDivisionError:
            final_ratio = 0 # Evitar error si algo es 0
            logger.warning(f"División por cero al calcular ratio para {activity_name} (idx {i})")

        ratios.append((final_ratio, i, cluster_id))

        # Log de cálculo de ratio
        # logger.debug(f"Idx {i}: [{activity_type}] {activity_name} (ID:{activity_id}) | Score: {scores[i]:.2f} -> Base: {base_score:.2f} (Pen: {is_penalized}, Boost: {place_boost_applied}) -> FinalScore: {score_with_bonus:.2f} | Cost: ${costs[i]:.2f}, Dur: {durations[i]}min | Ratio ({strategy}): {final_ratio:.4f}")


    ratios.sort(key=lambda x: x[0], reverse=True)

    last_activity_end_time = None

    #logger.debug(f"--- Iniciando Selección (Max {max_activities}, Budget: ${remaining_budget:.2f}) ---")

    processed_indices = set() # Para evitar logs repetidos si un item falla varias veces

    for rank, (ratio, idx, cluster_id) in enumerate(ratios):

        #if len(selected_indices) >= max_activities:
            #logger.debug("Límite de actividades alcanzado.")
            #break

        if idx in processed_indices and rank > 0: # Solo loguear la primera vez que se evalúa
            continue

        processed_indices.add(idx)

        current_activity = activity_objects[idx]
        current_activity_type = "Place" if isinstance(current_activity, Place) else "ActivityService"
        current_activity_name = getattr(current_activity, 'name', 'N/A')
        current_cost = costs[idx]

        #logger.debug(f"\nEvaluando Rank {rank}: Idx {idx} [{current_activity_type}] '{current_activity_name}' (Ratio: {ratio:.4f}, Cost: ${current_cost:.2f})")

        # Chequeo de presupuesto
        #if current_cost > remaining_budget:
            #logger.debug(f"  DESCARTADO: Costo (${current_cost:.2f}) excede presupuesto restante (${remaining_budget:.2f}).")
            #continue

        # Verificar distancia si ya hay actividades seleccionadas
        travel_time = 0
        if selected_indices:
            last_idx = selected_indices[-1]
            travel_time = time_matrix[last_idx, idx]

            # Usar la constante global MAX_TRAVEL_TIME_MINUTES
            #if travel_time > MAX_TRAVEL_TIME_MINUTES:
                #logger.debug(f"  DESCARTADO: Tiempo de viaje ({travel_time:.1f} min) desde Idx {last_idx} excede el límite ({MAX_TRAVEL_TIME_MINUTES} min).")
                #continue
            #else:
                #logger.debug(f"  Tiempo de viaje desde Idx {last_idx}: {travel_time:.1f} min (OK).")
        #else:
             #logger.debug("  Primer actividad, sin chequeo de viaje.")


        # --- Lógica de Balanceo de Días ---
        valid_windows = _find_valid_windows(
            selected_indices, idx, time_matrix, durations,
            time_windows, remaining_window_indices, last_activity_end_time
        )

        #if not valid_windows:
            #logger.debug(f"  DESCARTADO: No se encontraron ventanas de tiempo válidas disponibles.")
            #continue
        #else:
            #logger.debug(f"  Ventanas válidas encontradas: {len(valid_windows)}. Buscando la mejor por balanceo de días.")

        # Encontrar la *mejor* ventana (la del día menos ocupado)
        valid_windows_sorted = sorted(valid_windows, key=lambda w: day_activity_count[window_day_map[w[0]]])
        best_window_idx, best_start_time, best_end_time = valid_windows_sorted[0]
        day_of_activity = window_day_map[best_window_idx]
        current_day_count = day_activity_count[day_of_activity]

        #logger.debug(f"  SELECCIONADO! Asignado a ventana {best_window_idx} ({best_start_time.strftime('%Y-%m-%d %H:%M')} - {best_end_time.strftime('%H:%M')}) en día {day_of_activity} (Actividades previas en día: {current_day_count}).")

        # Asignar la actividad
        selected_indices.append(idx)
        selected_details.append({
            'idx': idx,
            'start_time': best_start_time,
            'end_time': best_end_time
        })

        remaining_budget -= current_cost
        remaining_window_indices.remove(best_window_idx) # Marcar ventana como usada

        # Actualizar contadores
        day_activity_count[day_of_activity] += 1
        # Asegurar que cluster_id existe antes de incrementar
        if cluster_id is not None:
             cluster_counts[cluster_id] += 1
        last_activity_end_time = best_end_time

        #logger.debug(f"  Presupuesto restante: ${remaining_budget:.2f}. Ventanas restantes: {len(remaining_window_indices)}.")


    #logger.debug(f"--- Selección Finalizada: {len(selected_details)} actividades seleccionadas ---")
    return selected_details

def solve_orienteeering_problem(optimizer_instance, activities_with_scores,
                                time_windows, budget_constraint,
                                strategy='balanced', # Nuevo
                                exclude_activity_ids=None): # Nuevo
    """
    Resuelve el Problema de Orientación.
    Esta función es el "núcleo" que prepara los datos para el algoritmo greedy.

    Args:
        optimizer_instance: La instancia de 'ItineraryOptimizer' para acceder a sus caches.
        activities_with_scores: Lista de tuplas (actividad, score)
        time_windows: Ventanas de tiempo disponibles
        budget_constraint: Presupuesto restante
        strategy: 'budget', 'balanced', o 'premium'
        exclude_activity_ids: Set de IDs a penalizar
    """
    if not activities_with_scores:
        #logger.debug("solve_orienteeering_problem: No hay actividades con scores para procesar.")
        return []

    activities = [(act, score) for act, score in activities_with_scores if act is not None]
    n_activities = len(activities)

    if n_activities == 0:
        #logger.debug("solve_orienteeering_problem: No hay objetos de actividad válidos tras filtrar Nones.")
        return []

    scores = np.zeros(n_activities)
    activity_objects = []

    # logger.debug(f"Preparando datos para {n_activities} actividades...")
    for i, (activity, score) in enumerate(activities):
        adjusted_score = float(score) * 100 if score is not None else 50.0 # Score fallback si es None
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

    time_matrix = distance_matrix / 10 * 60 # Asumir 10 km/h -> minutos

    activity_durations = np.zeros(n_activities)
    activity_costs = np.zeros(n_activities)

    for i, activity in enumerate(activity_objects):
        # Usar getattr seguro para duración y precio (adaptados en data_provider)
        # Usar las constantes para defaults
        activity_durations[i] = getattr(activity, 'duration_minutes', DEFAULT_ACTIVITY_DURATION_MINUTES)
        # Asegurar que el precio sea float, default a 0.0 si no existe o es None
        raw_price = getattr(activity, 'price', 0.0)
        activity_costs[i] = float(raw_price or 0.0) * optimizer_instance.travelers

        # logger.debug(f"Idx {i}: Dur={activity_durations[i]}, Cost={activity_costs[i]}")


    # Llamar al algoritmo greedy
    max_activities_limit = min(len(time_windows), optimizer_instance.days * 5)
    logger.debug(f"Llamando a _greedy_orienteeering_enhanced con max_activities={max_activities_limit}, budget={budget_constraint}, strategy={strategy}")

    selected_activity_details = _greedy_orienteeering_enhanced(
        scores, distance_matrix, time_matrix, activity_durations,
        activity_costs, coordinates, time_windows, budget_constraint,
        max_activities_limit,
        optimizer_instance._calculate_distance,
        activity_objects,
        strategy=strategy,
        exclude_activity_ids=exclude_activity_ids # Pasar IDs a excluir
    )

    # Formatear resultado
    result = []
    for details in selected_activity_details:
        idx = details['idx']
        activity = activity_objects[idx]
        result.append({
            'activity': activity,
            'score': scores[idx] / 100, # Revertir la multiplicación por 100
            'cost': activity_costs[idx],
            'duration': activity_durations[idx],
            'start_time': details['start_time'], # Agregar tiempos asignados
            'end_time': details['end_time']
        })

    # Actualizar métrica global (se hace aquí porque ahora tenemos el count final)
    optimizer_instance.performance_metrics['selected_activities'] = len(result)
    #logger.info(f"Problema de Orientación resuelto. Seleccionadas {len(result)} actividades.")
    return result