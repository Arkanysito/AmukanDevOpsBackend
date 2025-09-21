import random
import numpy as np
from datetime import datetime, time, timedelta
from django.db.models import Q
from django.utils import timezone
from collections import defaultdict
import math
from typing import List, Dict, Any, Tuple
from apps.location.models import Zone, Place
from apps.experiences.models import ActivityService, AccommodationService, Event
from apps.recommendation.services import recommend_places

class ItineraryOptimizer:
    def __init__(self, user, destination, start_date, end_date, budget, travelers, preferences=None):
        self.user = user
        self.destination = destination
        self.start_date = self._ensure_timezone_aware(start_date)
        self.end_date = self._ensure_timezone_aware(end_date)
        self.budget = budget
        self.travelers = travelers
        self.preferences = preferences or {}

        # Detectar si es same-day (mismo día)
        self.is_same_day = self.start_date.date() == self.end_date.date()
        self.current_time = timezone.now() if self.is_same_day else None
        
        self.days = max(1, (self.end_date - self.start_date).days)  # Mínimo 1 día
        self.zone = self._get_zone()
        self.time_slots_per_day = 4 
        
    def _get_zone(self):
        """Busca la zona del destino"""
        return Zone.objects.filter(
            Q(name__icontains=self.destination) |
            Q(place__name__icontains=self.destination)
        ).first()
    
    def _ensure_timezone_aware(self, dt):
        """Asegura que un datetime sea timezone-aware usando Django"""
        if dt is None:
            return None
        if not timezone.is_aware(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    
    def _calculate_distance(self, coord1, coord2):
        """Calcula distancia haversine entre dos coordenadas (en km)"""
        if not coord1 or not coord2:
            return float('inf')
            
        # Convertir a radianes
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
        
        # Fórmula haversine
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return 6371 * c  # Radio de la Tierra en km
    
    def _get_coordinates(self, obj):
        """Obtiene coordenadas de un objeto"""
        if hasattr(obj, 'coordinates') and obj.coordinates:
            return (obj.coordinates.y, obj.coordinates.x)
        elif hasattr(obj, 'place_id') and hasattr(obj.place_id, 'coordinates') and obj.place_id.coordinates:
            return (obj.place_id.coordinates.y, obj.place_id.coordinates.x)
        return None
    
    def _get_activities_with_scores(self, top_k=50):
        """Obtiene actividades con sus scores de recomendación"""
        try:
            activities = recommend_places(self.user, 'activity', self.zone, top_k=top_k)
            # Asegurar formato (servicio, score)
            if activities and isinstance(activities[0], tuple):
                return activities
            else:
                return [(act, 0.5) for act in activities]
        except:
            activities = ActivityService.objects.all()
            if self.zone:
                activities = activities.filter(place_id__zone_id=self.zone)
            return [(act, 0.5) for act in activities[:top_k]]
    
    def _get_accommodations(self, top_k=10):
        """Obtiene alojamientos"""
        try:
            accommodations = recommend_places(self.user, 'accommodation', self.zone, top_k=top_k)
            if accommodations and isinstance(accommodations[0], tuple):
                return [acc for acc, score in accommodations]
            return accommodations
        except:
            accommodations = AccommodationService.objects.all()
            if self.zone:
                accommodations = accommodations.filter(place_id__zone_id=self.zone)
            return list(accommodations[:top_k])
    
    def _get_restaurants(self, top_k=20):
        """Obtiene restaurantes"""
        try:
            restaurants = recommend_places(self.user, 'restaurant', self.zone, top_k=top_k)
            if restaurants and isinstance(restaurants[0], tuple):
                return [rest for rest, score in restaurants]
            return restaurants
        except:
            restaurants = Place.objects.filter(type__in=['restaurant', 'cafe', 'bar'])
            if self.zone:
                restaurants = restaurants.filter(zone_id=self.zone)
            return list(restaurants[:top_k])
    
    def _get_events(self, top_k=15):
        """Obtiene eventos dentro del rango de fechas con horarios flexibles"""
        try:
            events = recommend_places(self.user, 'event', self.zone, top_k=top_k)
            if events and isinstance(events[0], tuple):
                events = [event for event, score in events]
            
            filtered_events = []
            for event in events:
                event_start = self._ensure_timezone_aware(event.start_date)
                event_end = self._ensure_timezone_aware(event.end_date)
                
                # Para same-day: filtrar eventos que ya terminaron
                if self.is_same_day and self.current_time:
                    if event_end < self.current_time:
                        continue  # Saltar eventos que ya terminaron
                    # Para eventos en curso, ajustar el inicio al tiempo actual
                    if event_start < self.current_time < event_end:
                        event_start = self.current_time
                
                # Criterio flexible de solapamiento
                if self._hay_solapamiento(event_start, event_end, self.start_date, self.end_date):
                    filtered_events.append(event)
            
            return filtered_events[:top_k]
            
        except Exception as e:
            print(f"Error getting events: {e}")
            # Fallback con criterio flexible
            events = Event.objects.filter(
                Q(start_date__lte=self.end_date) & Q(end_date__gte=self.start_date)
            )
            
            # Filtrar por hora actual si es same-day
            if self.is_same_day and self.current_time:
                events = events.filter(end_date__gte=self.current_time)
            
            if self.zone:
                events = events.filter(place_id__zone_id=self.zone)
            return list(events[:top_k])
    
    def _process_events(self, events, time_windows, activities_budget):
        """Procesa eventos y los integra en la planificación"""
        scheduled_events = []
        remaining_budget = activities_budget
        
        # No usamos used_windows para eventos porque tienen horarios fijos
        sorted_events = sorted(events, key=lambda x: x.start_date)
        
        for event in sorted_events:
            event_cost = float(event.price) * self.travelers
            
            if event_cost <= remaining_budget:
                event_start = self._ensure_timezone_aware(event.start_date)
                event_end = self._ensure_timezone_aware(event.end_date)
                event_duration = (event_end - event_start).total_seconds() / 3600
                
                # Verificar si el evento ocurre durante el viaje (sin restricción de ventana)
                if (event_start >= self.start_date and event_end <= self.end_date):
                    scheduled_events.append({
                        'service': event,
                        'type': 'event',
                        'cost': event_cost,
                        'date': event_start,
                        'start_time': event_start,
                        'end_time': event_end,
                        'duration_hours': event_duration,
                        'es_fuera_de_horario': self._es_fuera_de_horario_normal(event_start, event_end)
                    })
                    remaining_budget -= event_cost
        
        return scheduled_events, remaining_budget, set()
    
    def _es_fuera_de_horario_normal(self, start_time, end_time):
        """Determina si un evento está fuera del horario normal (9-22)"""
        hora_inicio = start_time.hour
        hora_fin = end_time.hour
    
        # Considerar eventos que empiezan antes de las 9am o terminan después de las 10pm
        return hora_inicio < 9 or hora_fin > 22
    
    def _find_matching_time_window(self, event_start, event_end, time_windows, used_windows):
        """Encuentra la ventana de tiempo que coincide con un evento"""
        event_start = self._ensure_timezone_aware(event_start)
        event_end = self._ensure_timezone_aware(event_end)
        
        for i, (window_start, window_end) in enumerate(time_windows):
            if i not in used_windows:
                window_start = self._ensure_timezone_aware(window_start)
                window_end = self._ensure_timezone_aware(window_end)
                
                if (event_start >= window_start and event_end <= window_end):
                    return i
        return None
    
    def _create_time_windows(self):
        """Crea ventanas de tiempo para cada día"""
        time_windows = []
        
        if self.is_same_day and self.current_time:
            # Para same-day: crear ventanas desde la hora actual en adelante
            current_time = self.current_time
            current_hour = current_time.hour
            
            # Definir ventanas restantes del día
            day_date = current_time.date()
            
            # Mañana (si aún es temprano)
            if current_hour < 12:
                start_morning = max(current_time, timezone.make_aware(datetime.combine(day_date, time(9, 0))))
                time_windows.append((start_morning, timezone.make_aware(datetime.combine(day_date, time(12, 0)))))
            
            # Almuerzo (12-14)
            if current_hour < 14:
                start_lunch = max(current_time, timezone.make_aware(datetime.combine(day_date, time(12, 0))))
                time_windows.append((start_lunch, timezone.make_aware(datetime.combine(day_date, time(14, 0)))))
            
            # Tarde (14-18)
            if current_hour < 18:
                start_afternoon = max(current_time, timezone.make_aware(datetime.combine(day_date, time(14, 0))))
                time_windows.append((start_afternoon, timezone.make_aware(datetime.combine(day_date, time(18, 0)))))
            
            # Noche (19-22)
            if current_hour < 22:
                start_evening = max(current_time, timezone.make_aware(datetime.combine(day_date, time(19, 0))))
                time_windows.append((start_evening, timezone.make_aware(datetime.combine(day_date, time(22, 0)))))
            
            # Madrugada (22-24) - para eventos nocturnos
            if current_hour < 24:
                start_night = max(current_time, timezone.make_aware(datetime.combine(day_date, time(22, 0))))
                end_night = timezone.make_aware(datetime.combine(day_date + timedelta(days=1), time(2, 0)))  # Hasta las 2 AM
                time_windows.append((start_night, end_night))
                
        else:
            # Para múltiples días: ventanas normales
            for day in range(self.days):
                day_date = self.start_date + timedelta(days=day)
                day_date_date = day_date.date()
                
                windows = [
                    (timezone.make_aware(datetime.combine(day_date_date, time(9, 0))),
                    timezone.make_aware(datetime.combine(day_date_date, time(12, 0)))),
                    
                    (timezone.make_aware(datetime.combine(day_date_date, time(12, 0))),
                    timezone.make_aware(datetime.combine(day_date_date, time(14, 0)))),
                    
                    (timezone.make_aware(datetime.combine(day_date_date, time(14, 0))),
                    timezone.make_aware(datetime.combine(day_date_date, time(18, 0)))),
                    
                    (timezone.make_aware(datetime.combine(day_date_date, time(19, 0))),
                    timezone.make_aware(datetime.combine(day_date_date, time(22, 0)))),
                ]
                time_windows.extend(windows)
        
        return time_windows
    
    def solve_orienteeering_problem(self, activities, time_windows, budget_constraint):
        """
        Resuelve el Problema de Orientación para seleccionar actividades óptimas
        
        Args:
            activities: Lista de actividades con scores
            time_windows: Ventanas de tiempo disponibles
            budget_constraint: Presupuesto restante después de alojamiento/comidas
        
        Returns:
            Lista de actividades seleccionadas y sus asignaciones de tiempo
        """
        if not activities:
            return []
        
        # Preparar datos para el algoritmo
        n_activities = len(activities)
        # Matriz de scores (valor de cada actividad)
        scores = np.zeros(n_activities)
        activity_objects = []
        
        for i, (activity, score) in enumerate(activities):
            scores[i] = float(score) * 100  # Escalar para mejor optimización
            activity_objects.append(activity)
        
        # Matriz de distancias entre actividades
        distance_matrix = np.zeros((n_activities, n_activities))
        coordinates = [self._get_coordinates(act) for act in activity_objects]
        
        for i in range(n_activities):
            for j in range(n_activities):
                if i == j:
                    distance_matrix[i, j] = 0
                else:
                    distance_matrix[i, j] = self._calculate_distance(coordinates[i], coordinates[j])
        
        # Matriz de tiempos de viaje (asumir 20 km/h en ciudad)
        time_matrix = distance_matrix / 20 * 60  # Convertir a minutos
        
        # Tiempos de actividad (usar duration_minutes o valor por defecto)
        activity_durations = np.zeros(n_activities)
        for i, activity in enumerate(activity_objects):
            activity_durations[i] = getattr(activity, 'duration_minutes', 120)
        
        # Costos de actividades
        activity_costs = np.zeros(n_activities)
        for i, activity in enumerate(activity_objects):
            activity_costs[i] = float(activity.price) * self.travelers
        
        # Algoritmo greedy para el Problema de Orientación
        selected_activities = self._greedy_orienteeering(
            scores, time_matrix, activity_durations, activity_costs, 
            time_windows, budget_constraint, len(time_windows)
        )
        
        # Formatear resultado
        result = []
        for idx in selected_activities:
            activity = activity_objects[idx]
            result.append({
                'activity': activity,
                'score': scores[idx],
                'cost': activity_costs[idx],
                'duration': activity_durations[idx]
            })
        
        return result
    
    def _greedy_orienteeering(self, scores, time_matrix, durations, costs, 
                            time_windows, budget_constraint, max_activities):
        """
        Algoritmo greedy para el Problema de Orientación
        """
        n = len(scores)
        selected = []
        remaining_budget = budget_constraint
        remaining_time_windows = list(range(len(time_windows)))
        
        # Ordenar actividades por ratio score/(costo + tiempo)
        ratios = []
        for i in range(n):
            total_cost = costs[i] + 0.1  # Evitar división por cero
            time_value = durations[i] / 60  # Convertir a horas
            ratio = scores[i] / (total_cost + time_value)
            ratios.append((ratio, i))
        
        ratios.sort(reverse=True)
        
        # Seleccionar actividades greedy
        for ratio, idx in ratios:
            if costs[idx] <= remaining_budget and len(selected) < max_activities:
                # Verificar si cabe en alguna ventana de tiempo
                activity_duration = durations[idx] / 60  # Horas
                
                # Encontrar ventana de tiempo disponible
                time_window_idx = self._find_available_time_window(
                    selected, idx, time_matrix, durations, time_windows, remaining_time_windows
                )
                
                if time_window_idx is not None:
                    selected.append(idx)
                    remaining_budget -= costs[idx]
                    remaining_time_windows.remove(time_window_idx)
        
        return selected
    
    def _find_available_time_window(self, selected, new_idx, time_matrix, durations, 
                                  time_windows, available_windows):
        """
        Encuentra una ventana de tiempo disponible para una actividad
        """
        if not selected:
            return available_windows[0] if available_windows else None
        
        # Calcular tiempo de viaje desde la última actividad
        last_idx = selected[-1]
        travel_time = time_matrix[last_idx, new_idx] / 60  # Horas
        
        activity_duration = durations[new_idx] / 60  # Horas
        total_time_needed = travel_time + activity_duration
        
        for window_idx in available_windows:
            start_time, end_time = time_windows[window_idx]
            window_duration = (end_time - start_time).total_seconds() / 3600  # Horas
            
            if total_time_needed <= window_duration:
                return window_idx
        
        return None
    
    def generate_optimized_itineraries(self, max_itineraries=3):
        """
        Genera itinerarios optimizados usando el Problema de Orientación
        """
        if not self.zone or self.days < 1:
            return []
        
        # Obtener servicios
        accommodations = self._get_accommodations(10)
        activities_with_scores = self._get_activities_with_scores(50)
        restaurants = self._get_restaurants(20)
        events = self._get_events(10)
        time_windows = self._create_time_windows()
        
        itineraries = []
        strategies = ['budget', 'balanced', 'premium']
        
        for strategy in strategies[:max_itineraries]:
            itinerary = self._generate_strategy_itinerary(
                strategy, accommodations, activities_with_scores, 
                restaurants, events, time_windows
            )
            if itinerary:
                itineraries.append(itinerary)
        
        return itineraries
    
    def _generate_strategy_itinerary(self, strategy, accommodations, activities_with_scores, restaurants, events, time_windows): 
        """
        Genera un itinerario para una estrategia específica
        """
        items = []
        total_cost = 0
        
        # 1. Seleccionar alojamiento
        if self.days > 1 and accommodations:
            acc = self._select_accommodation(strategy, accommodations)
            if acc:
                acc_cost = float(acc.price) * (self.days - 1) * self.travelers
                items.append({
                    'service': acc,
                    'type': 'accommodation',
                    'cost': acc_cost,
                    'date': self.start_date,
                    'duration_days': self.days - 1
                })
                total_cost += acc_cost
        
        # 2. Planificar comidas
        meal_budget = self.budget * 0.3
        meal_plan = self._plan_meals(restaurants, strategy, meal_budget)
        for meal in meal_plan:
            if total_cost + meal['cost'] <= self.budget:
                items.append(meal)
                total_cost += meal['cost']
        
        # 3. Presupuesto restante para actividades y eventos
        activities_events_budget = self.budget - total_cost
        
        # 4. PRIMERO: Procesar eventos (sin restricción de ventanas)
        scheduled_events, remaining_budget, _ = self._process_events(
            events, time_windows, activities_events_budget
        )
        
        for event in scheduled_events:
            items.append(event)
            total_cost += event['cost']
        
        # 5. Identificar ventanas ocupadas por eventos
        used_windows_for_events = self._identificar_ventanas_ocupadas_por_eventos(scheduled_events, time_windows)
        
        # 6. LUEGO: Resolver Problema de Orientación para actividades
        available_time_windows = [
            window for i, window in enumerate(time_windows) 
            if i not in used_windows_for_events
        ]
        
        selected_activities = self.solve_orienteeering_problem(
            activities_with_scores, available_time_windows, remaining_budget
        )
        
        # 7. Asignar actividades a ventanas de tiempo disponibles
        scheduled_activities = self._schedule_activities(selected_activities, available_time_windows)
        
        for activity in scheduled_activities:
            if total_cost + activity['cost'] <= self.budget:
                items.append(activity)
                total_cost += activity['cost']
        
        return {
            'items': items,
            'total_cost': total_cost,
            'strategy': strategy,
            'budget_utilization': total_cost / self.budget if self.budget > 0 else 0
        }
    
    def _identificar_ventanas_ocupadas_por_eventos(self, scheduled_events, time_windows):
        """Identifica qué ventanas de tiempo están ocupadas por eventos"""
        used_windows = set()
        
        for event in scheduled_events:
            event_start = event['start_time']
            event_end = event['end_time']
            
            # Buscar ventanas que se solapan con el evento
            for i, (window_start, window_end) in enumerate(time_windows):
                if self._hay_solapamiento(event_start, event_end, window_start, window_end):
                    used_windows.add(i)
        
        return used_windows

    def _hay_solapamiento(self, inicio1, fin1, inicio2, fin2):
        """Determina si dos intervalos de tiempo se solapan"""
        return max(inicio1, inicio2) < min(fin1, fin2)
    
    def _select_accommodation(self, strategy, accommodations):
        """Selecciona alojamiento - para same-day, no incluir alojamiento"""
        if self.is_same_day:
            return None  # No alojamiento para same-day
        
        if not accommodations:
            return None
        
        if strategy == 'budget':
            return min(accommodations, key=lambda x: float(x.price))
        elif strategy == 'premium':
            return max(accommodations, key=lambda x: float(x.rating))
        else:
            best_value = None
            best_ratio = -1
            
            for acc in accommodations:
                if float(acc.price) > 0:
                    ratio = float(acc.rating) / float(acc.price)
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_value = acc
            
            return best_value or accommodations[0]
    
    def _plan_meals(self, restaurants, strategy, meal_budget):
        """Planifica comidas, ajustando para same-day según hora actual"""
        meals = []
        meal_costs = {
            'budget': {'breakfast': 5, 'lunch': 10, 'dinner': 15},
            'balanced': {'breakfast': 8, 'lunch': 15, 'dinner': 25},
            'premium': {'breakfast': 15, 'lunch': 25, 'dinner': 40}
        }
        
        costs = meal_costs[strategy]
        current_hour = self.current_time.hour if self.is_same_day and self.current_time else None
        
        if not restaurants:
            # Comidas genéricas - ajustar para same-day
            for day in range(self.days):
                day_date = self.start_date + timedelta(days=day)
                
                # Para same-day, solo incluir comidas futuras
                meal_types = []
                if not self.is_same_day or current_hour is None:
                    meal_types = ['breakfast', 'lunch', 'dinner']
                else:
                    if current_hour < 11:  # Antes de las 11AM: desayuno, almuerzo, cena
                        meal_types = ['breakfast', 'lunch', 'dinner']
                    elif current_hour < 15:  # 11AM-3PM: almuerzo, cena
                        meal_types = ['lunch', 'dinner']
                    elif current_hour < 19:  # 3PM-7PM: cena
                        meal_types = ['dinner']
                    else:  # Después de las 7PM: posible cena tardía o nada
                        meal_types = ['dinner'] if current_hour < 21 else []
                
                for meal_type in meal_types:
                    cost = costs[meal_type] * self.travelers
                    meals.append({
                        'service': None,
                        'type': 'dining',
                        'cost': cost,
                        'date': day_date,
                        'meal_type': meal_type
                    })
            return meals
        
        # Seleccionar restaurantes variados
        selected_restaurants = random.sample(restaurants, min(len(restaurants), self.days * 3))
        
        for day in range(self.days):
            day_date = self.start_date + timedelta(days=day)
            
            # Determinar qué comidas incluir basado en la hora actual
            meal_types_to_include = []
            if not self.is_same_day or current_hour is None:
                meal_types_to_include = ['breakfast', 'lunch', 'dinner']
            else:
                if current_hour < 11:
                    meal_types_to_include = ['breakfast', 'lunch', 'dinner']
                elif current_hour < 15:
                    meal_types_to_include = ['lunch', 'dinner']
                elif current_hour < 19:
                    meal_types_to_include = ['dinner']
                else:
                    meal_types_to_include = ['dinner'] if current_hour < 21 else []
            
            for i, meal_type in enumerate(meal_types_to_include):
                restaurant_idx = (day * 3 + i) % len(selected_restaurants)
                restaurant = selected_restaurants[restaurant_idx]
                
                # Calcular costo
                if hasattr(restaurant, 'average_price') and restaurant.average_price:
                    cost = float(restaurant.average_price) * self.travelers
                else:
                    cost = costs[meal_type] * self.travelers
                
                # Para same-day, ajustar la hora de la comida
                meal_time = day_date
                if self.is_same_day and meal_type == 'lunch' and current_hour < 12:
                    meal_time = meal_time.replace(hour=13, minute=0)  # Almuerzo a la 1PM
                elif self.is_same_day and meal_type == 'dinner' and current_hour < 18:
                    meal_time = meal_time.replace(hour=20, minute=0)  # Cena a las 8PM
                
                meals.append({
                    'service': restaurant,
                    'type': 'dining',
                    'cost': cost,
                    'date': meal_time,
                    'meal_type': meal_type
                })
        
        return meals
    
    def _schedule_activities(self, activities, time_windows):
        """Asigna actividades a ventanas de tiempo específicas"""
        scheduled = []
        used_windows = set()
        
        for activity_data in activities:
            activity = activity_data['activity']
            duration = activity_data['duration'] / 60  # Horas
            
            # Encontrar ventana disponible
            for i, (start_time, end_time) in enumerate(time_windows):
                if i not in used_windows:
                    window_duration = (end_time - start_time).total_seconds() / 3600
                    if duration <= window_duration:
                        scheduled.append({
                            'service': activity,
                            'type': 'activity',
                            'cost': activity_data['cost'],
                            'date': start_time,
                            'start_time': start_time,
                            'end_time': start_time + timedelta(hours=duration),
                            'duration_hours': duration
                        })
                        used_windows.add(i)
                        break
        
        return scheduled

# Función principal para uso en views
def generate_optimized_itineraries(request, destination, start_date, end_date, budget, travelers, preferences=None):
    """
    Función principal para generar itinerarios optimizados
    """
    optimizer = ItineraryOptimizer(
        user=request.user if request.user.is_authenticated else None,
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        budget=budget,
        travelers=travelers,
        preferences=preferences or {}
    )
    
    return optimizer.generate_optimized_itineraries(max_itineraries=3)