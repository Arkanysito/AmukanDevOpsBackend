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
    current_duration = durations[new_idx] # Duración de la actividad actual en minutos

    # Si no hay duración válida, no puede caber en ninguna ventana
    if current_duration <= 0:
         # logger.debug(f"Actividad idx {new_idx} tiene duración inválida {current_duration}. No se encontrarán ventanas.")
         return []


    if not selected_indices:
        # Si es la primera actividad
        activity_duration_td = timedelta(minutes=current_duration)
        for window_idx in available_window_indices:
            start_time, end_time = time_windows[window_idx]
            # Verificar si la ventana es suficientemente larga
            if start_time + activity_duration_td <= end_time:
                activity_start_time = start_time
                activity_end_time = start_time + activity_duration_td
                valid_window_indices.append((window_idx, activity_start_time, activity_end_time))
        # logger.debug(f"Primer Actividad (idx {new_idx}, dur: {current_duration}m): Ventanas válidas encontradas: {len(valid_window_indices)}")
        return valid_window_indices

    # Si ya hay actividades seleccionadas
    last_idx = selected_indices[-1]
    travel_time_minutes = time_matrix[last_idx, new_idx]

    for window_idx in available_window_indices:
        window_start, window_end = time_windows[window_idx]

        # Calcular cuándo podría empezar la actividad como muy pronto
        earliest_possible_start = last_activity_end_time + timedelta(minutes=travel_time_minutes)

        # El inicio real debe ser DESPUÉS del viaje Y NO ANTES de que empiece la ventana
        potential_start_time = max(earliest_possible_start, window_start)

        potential_end_time = potential_start_time + timedelta(minutes=current_duration)

        # Verificar si la actividad (empezando en potential_start_time) cabe en la ventana [window_start, window_end]
        if potential_end_time <= window_end:
            valid_window_indices.append((window_idx, potential_start_time, potential_end_time))

    # logger.debug(f"Actividad (idx {new_idx}, dur: {current_duration}m) tras idx {last_idx} (viaje: {travel_time_minutes:.1f}m): Ventanas válidas encontradas: {len(valid_window_indices)}")
    return valid_window_indices


def _simple_geographic_clustering(coordinates, distance_calculator, n_clusters=3):
    """Clustering geográfico simple usando k-means simplificado"""
    valid_coords = [(i, c) for i, c in enumerate(coordinates) if c is not None]

    # Evitar error si hay menos puntos que clusters deseados
    effective_n_clusters = min(n_clusters, len(valid_coords))
    if effective_n_clusters <= 0: # Si no hay coordenadas válidas
        return {i: 0 for i in range(len(coordinates))} # Asignar todos al cluster 0
    if effective_n_clusters == 1:
        return {i: 0 for i, c in enumerate(coordinates) if c is not None} # Asignar válidos al cluster 0

    random.shuffle(valid_coords)
    # Seleccionar centroides iniciales únicos
    centroid_indices = set()
    centroids = []
    for i, coord in valid_coords:
         is_unique = True
         # Simple check for very close initial centroids (optional)
         # for existing_centroid in centroids:
         #      if distance_calculator(coord, existing_centroid) < 0.1: # Threshold for "same" point
         #           is_unique = False
         #           break
         if is_unique:
              centroids.append(coord)
              centroid_indices.add(i)
              if len(centroids) == effective_n_clusters:
                   break

    # Asegurarse de tener la cantidad correcta de centroides (si hubo puntos muy juntos)
    while len(centroids) < effective_n_clusters and len(centroid_indices) < len(valid_coords):
         # Add the next available unique point
         next_point = next((c for i, c in valid_coords if i not in centroid_indices), None)
         if next_point:
              centroids.append(next_point)
              # Find the index corresponding to next_point to add to centroid_indices (less efficient but needed)
              for idx, c in valid_coords:
                   if c == next_point and idx not in centroid_indices:
                        centroid_indices.add(idx)
                        break
         else:
              break # No more unique points

    # Asignar clusters (simple assignment, no iterations needed for this basic version)
    clusters = {}
    for i, coord in enumerate(coordinates):
        if coord is None:
            clusters[i] = 0 # Asignar puntos sin coordenadas al cluster 0
            continue

        min_dist = float('inf')
        best_cluster = 0

        # Asignar al centroide más cercano
        for c_idx, centroid in enumerate(centroids):
            dist = distance_calculator(coord, centroid)
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
                                   exclude_activity_ids=None):
    """
    Algoritmo greedy mejorado con logging detallado y prioridad para Places.
    Incluye chequeo extra para evitar IndexError.
    """
    n = len(scores)
    selected_indices = []
    selected_details = [] # (idx, start_time, end_time)

    if exclude_activity_ids is None:
        exclude_activity_ids = set()

    remaining_budget = budget_constraint

    # --- Lógica de Balanceo de Días ---
    window_day_map = [tw[0].date() for tw in time_windows] if time_windows else [] # Handle empty time_windows
    day_activity_count = defaultdict(int)
    remaining_window_indices = set(range(len(time_windows)))

    # Asegurarse que distance_calculator es callable
    if not callable(distance_calculator):
         logger.error("Error crítico: distance_calculator no es una función callable.")
         # Decide how to handle: raise error or return empty?
         return [] # Return empty list


    geographic_clusters = _simple_geographic_clustering(coordinates, distance_calculator, n_clusters=3)
    cluster_counts = defaultdict(int)

    ratios = []
    #logger.debug(f"--- Calculando Ratios para {n} candidatos (Estrategia: {strategy}) ---")
    for i in range(n):

        activity = activity_objects[i]
        is_place = isinstance(activity, Place)
        activity_type = "Place" if is_place else "ActivityService"
        activity_name = getattr(activity, 'name', 'N/A')
        # Usar service_id adaptado (puede ser place_id o service_id real)
        activity_id = getattr(activity, 'service_id', None) # Default None if not adapted


        # --- Lógica de Estrategia y Diversidad ---
        base_score = scores[i] if i < len(scores) else 0 # Safety check

        # 1. Penalización por Diversidad
        is_penalized = False
        if activity_id and activity_id in exclude_activity_ids:
            base_score *= DIVERSITY_PENALTY
            is_penalized = True

        # 2. Bonus por Clustering (Diversidad geográfica)
        cluster_id = geographic_clusters.get(i, 0) # Use .get for safety
        diversity_bonus = 1.0 / (1.0 + cluster_counts.get(cluster_id, 0) * 0.2) # Use .get

        score_with_bonus = base_score * diversity_bonus

        # Boost para Places
        place_boost_applied = False
        if is_place:
            score_with_bonus *= PLACE_PRIORITY_BOOST
            place_boost_applied = True

        # 3. Ratio por Estrategia
        current_duration = durations[i] if i < len(durations) else DEFAULT_ACTIVITY_DURATION_MINUTES # Safety
        current_cost = costs[i] if i < len(costs) else 0 # Safety

        time_cost_hours = (current_duration / 60) + 0.1 # +0.1 para evitar división por cero
        money_cost = current_cost + 0.1

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

        if len(selected_indices) >= max_activities:
            # logger.debug("Límite de actividades alcanzado.")
            break

        if idx in processed_indices and rank > 0:
            continue
        processed_indices.add(idx)

        current_activity = activity_objects[idx]
        current_activity_type = "Place" if isinstance(current_activity, Place) else "ActivityService"
        current_activity_name = getattr(current_activity, 'name', 'N/A')
        current_cost = costs[idx]

        #logger.debug(f"\nEvaluando Rank {rank}: Idx {idx} [{current_activity_type}] '{current_activity_name}' (Ratio: {ratio:.4f}, Cost: ${current_cost:.2f})")

        # Chequeo de presupuesto
        if current_cost > remaining_budget:
            # logger.debug(f"  DESCARTADO: Costo (${current_cost:.2f}) excede presupuesto restante (${remaining_budget:.2f}).")
            continue

        # Verificar distancia
        travel_time = 0
        if selected_indices:
            last_idx = selected_indices[-1]
            travel_time = time_matrix[last_idx, idx]
            if travel_time > MAX_TRAVEL_TIME_MINUTES: # Use constant directly
                # logger.debug(f"  DESCARTADO: Tiempo de viaje ({travel_time:.1f} min) desde Idx {last_idx} excede el límite ({MAX_TRAVEL_TIME_MINUTES} min).")
                continue
            # else: logger.debug(f"  Tiempo de viaje desde Idx {last_idx}: {travel_time:.1f} min (OK).")
        # else: logger.debug("  Primer actividad, sin chequeo de viaje.")


        # --- Lógica de Balanceo de Días ---
        valid_windows = _find_valid_windows(
            selected_indices, idx, time_matrix, durations,
            time_windows, remaining_window_indices, last_activity_end_time
        )

        if not valid_windows:
            # logger.debug(f"  DESCARTADO (Rank {rank}, Idx {idx}): No se encontraron ventanas de tiempo válidas disponibles.")
            continue # Skip to the next candidate

        # logger.debug(f"  (Rank {rank}, Idx {idx}): Ventanas válidas encontradas: {len(valid_windows)}. Buscando la mejor por balanceo de días.")

        # Sort the valid windows found
        valid_windows_sorted = sorted(valid_windows, key=lambda w: day_activity_count[window_day_map[w[0]]])

        # *** ADDED SAFETY CHECK ***
        if not valid_windows_sorted: # Check if list is empty AFTER sorting
             logger.error(f"  ERROR INESPERADO (Rank {rank}, Idx {idx}, Name: {current_activity_name}): valid_windows_sorted está vacía DESPUÉS de check inicial y sort! valid_windows era: {valid_windows}. Skipping.")
             continue # Skip this candidate
        # *** END SAFETY CHECK ***

        try:
            best_window_idx, best_start_time, best_end_time = valid_windows_sorted[0]
        except IndexError:
             # This log should ideally never be reached now
             logger.error(f"  ERROR CRÍTICO (Rank {rank}, Idx {idx}, Name: {current_activity_name}): IndexError accessing valid_windows_sorted[0] despite checks! Lista: {valid_windows_sorted}. Skipping.")
             continue

        # Ensure index is valid before accessing window_day_map
        if best_window_idx >= len(window_day_map):
             logger.error(f"  ERROR ÍNDICE INVÁLIDO (Rank {rank}, Idx {idx}): best_window_idx={best_window_idx} fuera de rango para window_day_map (len={len(window_day_map)}). Skipping.")
             continue


        day_of_activity = window_day_map[best_window_idx]
        current_day_count = day_activity_count[day_of_activity]

        # logger.debug(f"  SELECCIONADO! Asignado a ventana {best_window_idx} ({best_start_time.strftime('%Y-%m-%d %H:%M')} - {best_end_time.strftime('%H:%M')}) en día {day_of_activity} (Actividades previas en día: {current_day_count}).")

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
        if cluster_id is not None:
             cluster_counts[cluster_id] += 1
        last_activity_end_time = best_end_time

        # logger.debug(f"  Presupuesto restante: ${remaining_budget:.2f}. Ventanas restantes: {len(remaining_window_indices)}.")

        # Check if max activities reached inside loop for cleaner exit
        if len(selected_indices) >= max_activities:
            # logger.debug("Límite de actividades alcanzado.")
            break


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
        #logger.debug("solve_orienteeering_problem: No activities with scores provided.")
        return []

    # Filter out None activities defensively
    valid_activities_scores = [(act, score) for act, score in activities_with_scores if act is not None]
    n_activities = len(valid_activities_scores)

    if n_activities == 0:
        #logger.debug("solve_orienteeering_problem: No valid activity objects after filtering.")
        return []

    # Prepare data arrays
    scores = np.zeros(n_activities)
    activity_objects = []
    activity_durations = np.zeros(n_activities)
    activity_costs = np.zeros(n_activities)
    coordinates = [] # Use list for coordinates initially

    # logger.debug(f"Preparing data for {n_activities} activities...")
    for i, (activity, score) in enumerate(valid_activities_scores):
        # Score adjustment
        adjusted_score = float(score) * 100 if score is not None else 50.0 # Assign fallback score if None
        scores[i] = adjusted_score
        activity_objects.append(activity)

        # Duration and Cost extraction (using adapted attributes from data_provider)
        current_duration = getattr(activity, 'duration_minutes', DEFAULT_ACTIVITY_DURATION_MINUTES)
        # Ensure duration is a number, default if not
        activity_durations[i] = float(current_duration) if current_duration is not None else DEFAULT_ACTIVITY_DURATION_MINUTES

        raw_price = getattr(activity, 'price', 0.0)
        # Ensure price is a number, default to 0.0 if None or invalid
        try:
             activity_costs[i] = float(raw_price or 0.0) * optimizer_instance.travelers
        except (ValueError, TypeError):
             logger.warning(f"Invalid price '{raw_price}' for activity '{getattr(activity, 'name', 'N/A')}', using 0.")
             activity_costs[i] = 0.0


        # Coordinates extraction
        coords = optimizer_instance._get_coordinates(activity) # Gets (lat, lon) tuple or None
        coordinates.append(coords) # Append tuple or None to the list

        # logger.debug(f"Idx {i}: Name='{getattr(activity, 'name', 'N/A')}', Score={scores[i]:.2f}, Dur={activity_durations[i]}, Cost={activity_costs[i]}, Coords={coords}")


    # Prepare distance and time matrices
    distance_matrix = np.full((n_activities, n_activities), float('inf')) # Initialize with infinity
    np.fill_diagonal(distance_matrix, 0) # Distance to self is 0

    for i in range(n_activities):
        for j in range(i + 1, n_activities):
            # Only calculate if both coordinates are valid
            if coordinates[i] is not None and coordinates[j] is not None:
                dist = optimizer_instance._calculate_distance(coordinates[i], coordinates[j])
                distance_matrix[i, j] = dist
                distance_matrix[j, i] = dist
            # else: logger.warning(f"Skipping distance calc between {i} and {j} due to missing coordinates.")


    time_matrix = np.where(distance_matrix == float('inf'), float('inf'), (distance_matrix / 10.0) * 60.0)
    np.fill_diagonal(time_matrix, 0)

    # Call the greedy algorithm
    max_activities_limit = min(len(time_windows), optimizer_instance.days * 5) if time_windows else 0 # Handle empty time_windows
    # logger.debug(f"Calling _greedy_orienteeering_enhanced with max_activities={max_activities_limit}, budget={budget_constraint}, strategy={strategy}")

    selected_activity_details = [] # Initialize
    if n_activities > 0 and max_activities_limit > 0 and time_windows:
        try:
            selected_activity_details = _greedy_orienteeering_enhanced(
                scores, distance_matrix, time_matrix, activity_durations,
                activity_costs, coordinates, time_windows, budget_constraint,
                max_activities_limit,
                optimizer_instance._calculate_distance,
                activity_objects,
                strategy=strategy,
                exclude_activity_ids=exclude_activity_ids
            )
        except Exception as e:
             logger.error(f"Error during _greedy_orienteeering_enhanced execution: {e}", exc_info=True)
             return []


    # Format the final result
    result = []
    if selected_activity_details:
        for details in selected_activity_details:
            idx = details['idx']
            if 0 <= idx < n_activities:
                activity = activity_objects[idx]
                result.append({
                    'activity': activity,
                    'score': scores[idx] / 100,
                    'cost': activity_costs[idx],
                    'duration': activity_durations[idx],
                    'start_time': details['start_time'],
                    'end_time': details['end_time']
                })
            else:
                 logger.error(f"Invalid index {idx} encountered in selected_activity_details.")


    optimizer_instance.performance_metrics['selected_activities'] = len(result)
    # logger.info(f"Orientation problem solved. Selected {len(result)} activities.")
    return result