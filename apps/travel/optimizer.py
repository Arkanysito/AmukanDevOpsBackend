import logging
import math
import random
from datetime import datetime, time, timedelta
from collections import defaultdict
from django.db.models import Q
from django.utils import timezone

# Importaciones de modelos
from apps.location.models import Zone, Place
from apps.experiences.models import ActivityService, Event

# Importaciones locales
from . import constants
from . import data_provider
from . import optimization_core

logger = logging.getLogger(__name__)

class ItineraryOptimizer:
    
    def __init__(self, user, destination, start_date, end_date, budget, travelers, preferences=None):
        self.user = user
        self.destination = destination
        self.start_date = self._ensure_timezone_aware(start_date)
        self.end_date = self._ensure_timezone_aware(end_date)
        self.budget = budget
        self.travelers = travelers
        self.preferences = preferences or {}
        
        self.experiencias = self.preferences.get('experiencias', [])
        
        self.current_time = timezone.now()
        self.is_same_day = self.start_date.date() == self.end_date.date()
        
        if self.is_same_day:
            self.days = 1
            self.nights = 0
        else:
            date_diff = (self.end_date.date() - self.start_date.date()).days
            self.days = date_diff + 1
            self.nights = date_diff
            
        if self.end_date < self.start_date:
            raise ValueError("La fecha de fin no puede ser anterior a la fecha de inicio")
            
        self.zone = self._get_zone()
        
        self.performance_metrics = {
            'start_time': timezone.now(),
            'candidate_activities': 0,
            'selected_activities': 0,
            'budget_efficiency': 0,
            'time_efficiency': 0,
            'experiencias_used': self.experiencias,
        }
        
        # Inicializar caches
        self.__init_cache()

    def __init_cache(self):
        self._coordinates_cache = {}
        self._distance_cache = {}
        
    def _get_zone(self):
        """Busca la zona del destino"""
        return Zone.objects.filter(
            Q(name__icontains=self.destination) |
            Q(place__name__icontains=self.destination)
        ).first()
        
    def _ensure_timezone_aware(self, dt):
        """Asegura que un datetime sea timezone-aware usando Django"""
        if dt is None: return None
        if not timezone.is_aware(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
        
    def _calculate_distance(self, coord1, coord2):
        """Calcula distancia haversine (en km) CON CACHE"""
        if not coord1 or not coord2:
            return float('inf')
        
        cache_key = (coord1, coord2)
        if cache_key in self._distance_cache:
            return self._distance_cache[cache_key]
        
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = 6371 * c
        
        self._distance_cache[cache_key] = distance
        return distance
        
    def _get_coordinates(self, obj):
        """Obtiene coordenadas de un objeto CON CACHE"""
        cache_key = id(obj)
        if cache_key in self._coordinates_cache:
            return self._coordinates_cache[cache_key]
        
        coords = None
        if hasattr(obj, 'coordinates') and obj.coordinates:
            coords = (obj.coordinates.y, obj.coordinates.x)
        elif hasattr(obj, 'place_id') and hasattr(obj.place_id, 'coordinates') and obj.place_id.coordinates:
            coords = (obj.place_id.coordinates.y, obj.place_id.coordinates.x)
        
        self._coordinates_cache[cache_key] = coords
        return coords
    
    # --- Métodos de Lógica de Itinerario ---

    def _is_night_event(self, event_start, event_end):
        """
        Determina si un evento es nocturno.
        
        Criterios:
        - Empieza después de las 22:00 (10 PM)
        - O termina después de medianoche (cruza a día siguiente)
        - O empieza después de medianoche y antes de las 6 AM
        """
        start_hour = event_start.hour
        end_hour = event_end.hour
        
        # Evento que empieza de noche (22:00 - 23:59)
        if start_hour >= 22:
            return True
        
        # Evento que empieza en madrugada (00:00 - 05:59)
        if start_hour < 6:
            return True
        
        # Evento que cruza medianoche (ej: 23:00 a 02:00)
        # Si end_date es día siguiente y termina temprano
        if event_end.date() > event_start.date() and end_hour < 6:
            return True
        
        return False
    
    def _get_event_time_category(self, event_start, event_end):
        """
        Categoriza un evento según su horario.
        
        Returns:
            str: 'morning', 'lunch', 'afternoon', 'evening', 'night', 'late_night', 'multi_period'
        """
        start_hour = event_start.hour
        end_hour = event_end.hour
        
        # Calcular duración
        duration_hours = (event_end - event_start).total_seconds() / 3600
        
        # Evento que cruza medianoche
        if event_end.date() > event_start.date():
            if start_hour >= 22:
                return 'late_night'  # Evento nocturno largo
            else:
                return 'multi_period'  # Evento que cruza múltiples períodos
        
        # Eventos por horario de inicio
        if 9 <= start_hour < 12:
            return 'morning'
        elif 12 <= start_hour < 14:
            return 'lunch'
        elif 14 <= start_hour < 18:
            return 'afternoon'
        elif 18 <= start_hour < 22:
            return 'evening'
        elif 22 <= start_hour < 24:
            return 'night'
        elif 0 <= start_hour < 6:
            return 'late_night'
        else:
            return 'multi_period'
    
    def _calculate_accommodation_cost(self, place, strategy):
        """Calcula el costo de alojamiento basado en Place y estrategia"""
        base_price = float(place.average_price) if place.average_price else 50.0
        
        # Ajustar precio según estrategia
        strategy_multipliers = {
            'budget': 0.8,
            'balanced': 1.0,
            'premium': 1.5
        }
        
        multiplier = strategy_multipliers.get(strategy, 1.0)
        adjusted_price = base_price * multiplier
        
        # Calcular costo total por noches
        return adjusted_price * self.nights * self.travelers
    
    def _select_accommodation(self, strategy, accommodations):
        """Selecciona alojamiento DESDE PLACE - para same-day, no incluir alojamiento"""
        if self.is_same_day:
            return None  # No alojamiento para same-day
        
        if not accommodations:
            return None
        
        if strategy == 'budget':
            # Ordenar por precio más bajo
            return min(accommodations, key=lambda x: float(x.average_price) if x.average_price else float('inf'))
        elif strategy == 'premium':
            # Ordenar por rating más alto
            return max(accommodations, key=lambda x: float(x.rating) if x.rating else 0)
        else:
            # Balanced: mejor relación rating/precio
            best_value = None
            best_ratio = -1
            
            for acc in accommodations:
                if acc.average_price and acc.rating:
                    price = float(acc.average_price)
                    rating = float(acc.rating)
                    if price > 0:
                        ratio = rating / price
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
                    if current_hour < 11:
                        meal_types = ['breakfast', 'lunch', 'dinner']
                    elif current_hour < 15:
                        meal_types = ['lunch', 'dinner']
                    elif current_hour < 19:
                        meal_types = ['dinner']
                    else:
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
                else:
                    meal_types_to_include = ['dinner']
            
            for i, meal_type in enumerate(meal_types_to_include):
                restaurant_idx = (day * 3 + i) % len(selected_restaurants)
                restaurant = selected_restaurants[restaurant_idx]
                
                # Calcular costo BASADO EN average_price DE PLACE
                if hasattr(restaurant, 'average_price') and restaurant.average_price:
                    cost = float(restaurant.average_price) * self.travelers
                else:
                    cost = costs[meal_type] * self.travelers
                
                # Para same-day, ajustar la hora de la comida
                meal_time = day_date
                if self.is_same_day and meal_type == 'lunch' and current_hour < 12:
                    meal_time = meal_time.replace(hour=13, minute=0)
                elif self.is_same_day and meal_type == 'dinner' and current_hour < 18:
                    meal_time = meal_time.replace(hour=20, minute=0)
                
                meals.append({
                    'service': restaurant,
                    'type': 'dining',
                    'cost': cost,
                    'date': meal_time,
                    'meal_type': meal_type
                })
        
        return meals
    
    def _process_events(self, events, time_windows, activities_budget):
        """
        Procesa eventos incluyendo eventos nocturnos.
        
        Maneja correctamente eventos que cruzan medianoche
        """
        scheduled_events = []
        remaining_budget = activities_budget
        
        sorted_events = sorted(events, key=lambda x: x.start_date)
        
        for event in sorted_events:
            event_cost = float(event.price) * self.travelers
            
            if event_cost <= remaining_budget:
                event_start = self._ensure_timezone_aware(event.start_date)
                event_end = self._ensure_timezone_aware(event.end_date)
                event_duration = (event_end - event_start).total_seconds() / 3600
                
                # Verificar si el evento está dentro del rango (con tolerancia para eventos nocturnos)
                extended_end = self.end_date + timedelta(hours=6)
                
                if (event_start >= self.start_date and event_end <= extended_end):
                    is_night = self._is_night_event(event_start, event_end)
                    time_category = self._get_event_time_category(event_start, event_end)
                    
                    scheduled_events.append({
                        'service': event,
                        'type': 'event',
                        'cost': event_cost,
                        'date': event_start,
                        'start_time': event_start,
                        'end_time': event_end,
                        'duration_hours': event_duration,
                        'is_night_event': is_night,
                        'time_category': time_category,
                        'crosses_midnight': event_end.date() > event_start.date()
                    })
                    remaining_budget -= event_cost
        
        return scheduled_events, remaining_budget, set()
    
    def _hay_solapamiento(self, inicio1, fin1, inicio2, fin2):
        """Determina si dos intervalos de tiempo se solapan"""
        return max(inicio1, inicio2) < min(fin1, fin2)

    def _identificar_ventanas_ocupadas_por_eventos(self, scheduled_events, time_windows):
        used_windows = set()
        for event in scheduled_events:
            event_start = event['start_time']
            event_end = event['end_time']
            for i, (window_start, window_end) in enumerate(time_windows):
                if self._hay_solapamiento(event_start, event_end, window_start, window_end):
                    used_windows.add(i)
        return used_windows
    
    def _create_time_windows(self):
        """
        Crea ventanas de tiempo incluyendo horarios nocturnos.
        
        MEJORA: Ahora incluye:
        - Ventanas nocturnas (22:00 - 24:00)
        - Ventanas de madrugada (00:00 - 03:00) para eventos que cruzan medianoche
        """
        time_windows = []
        
        if self.is_same_day:
            # MISMO DÍA: Incluir ventanas nocturnas si aplica
            current_hour = self.current_time.hour
            day_date = self.current_time.date()
            end_hour = self.end_date.hour
            
            # Mañana (9-12)
            if current_hour < 12 and end_hour > 9:
                start_morning = max(self.current_time, timezone.make_aware(datetime.combine(day_date, time(9, 0))))
                end_morning = min(self.end_date, timezone.make_aware(datetime.combine(day_date, time(12, 0))))
                if start_morning < end_morning:
                    time_windows.append((start_morning, end_morning))
            
            # Almuerzo (12-14)
            if current_hour < 14 and end_hour > 12:
                start_lunch = max(self.current_time, timezone.make_aware(datetime.combine(day_date, time(12, 0))))
                end_lunch = min(self.end_date, timezone.make_aware(datetime.combine(day_date, time(14, 0))))
                if start_lunch < end_lunch:
                    time_windows.append((start_lunch, end_lunch))
            
            # Tarde (14-18)
            if current_hour < 18 and end_hour > 14:
                start_afternoon = max(self.current_time, timezone.make_aware(datetime.combine(day_date, time(14, 0))))
                end_afternoon = min(self.end_date, timezone.make_aware(datetime.combine(day_date, time(18, 0))))
                if start_afternoon < end_afternoon:
                    time_windows.append((start_afternoon, end_afternoon))
            
            # Noche temprana (19-22)
            if current_hour < 22 and end_hour > 19:
                start_evening = max(self.current_time, timezone.make_aware(datetime.combine(day_date, time(19, 0))))
                end_evening = min(self.end_date, timezone.make_aware(datetime.combine(day_date, time(22, 0))))
                if start_evening < end_evening:
                    time_windows.append((start_evening, end_evening))
            
            # Noche (22-24) - para eventos nocturnos
            if current_hour < 24 and end_hour >= 22:
                start_night = max(self.current_time, timezone.make_aware(datetime.combine(day_date, time(22, 0))))
                # Si el end_date cruza medianoche, extender hasta el día siguiente
                if self.end_date.date() > day_date:
                    end_night = self.end_date
                else:
                    end_night = timezone.make_aware(datetime.combine(day_date, time(23, 59)))
                
                if start_night < end_night:
                    time_windows.append((start_night, end_night))
            
            # Madrugada (00:00-03:00) - solo si el viaje cruza medianoche
            if self.end_date.date() > day_date or (current_hour >= 22 and end_hour < 6):
                next_day = day_date + timedelta(days=1)
                start_late_night = timezone.make_aware(datetime.combine(next_day, time(0, 0)))
                end_late_night = min(self.end_date, timezone.make_aware(datetime.combine(next_day, time(3, 0))))
                
                if start_late_night < end_late_night:
                    time_windows.append((start_late_night, end_late_night))
        
        else:
            # MÚLTIPLES DÍAS: Incluir ventanas nocturnas en cada día
            for day_offset in range(self.days):
                current_day = self.start_date + timedelta(days=day_offset)
                day_date = current_day.date()
                
                is_first_day = (day_offset == 0)
                is_last_day = (day_offset == self.days - 1)
                
                if is_first_day:
                    # Primer día: ajustar según hora de inicio
                    start_hour = self.start_date.hour
                    
                    if start_hour < 12:
                        time_windows.append((
                            self.start_date,
                            timezone.make_aware(datetime.combine(day_date, time(12, 0)))
                        ))
                    
                    if start_hour < 14:
                        start_lunch = max(self.start_date, timezone.make_aware(datetime.combine(day_date, time(12, 0))))
                        time_windows.append((
                            start_lunch,
                            timezone.make_aware(datetime.combine(day_date, time(14, 0)))
                        ))
                    
                    if start_hour < 18:
                        start_afternoon = max(self.start_date, timezone.make_aware(datetime.combine(day_date, time(14, 0))))
                        time_windows.append((
                            start_afternoon,
                            timezone.make_aware(datetime.combine(day_date, time(18, 0)))
                        ))
                    
                    if start_hour < 22:
                        start_evening = max(self.start_date, timezone.make_aware(datetime.combine(day_date, time(19, 0))))
                        time_windows.append((
                            start_evening,
                            timezone.make_aware(datetime.combine(day_date, time(22, 0)))
                        ))
                    
                    # NUEVA: Ventana nocturna primer día
                    if start_hour < 24:
                        start_night = max(self.start_date, timezone.make_aware(datetime.combine(day_date, time(22, 0))))
                        next_day = day_date + timedelta(days=1)
                        end_night = timezone.make_aware(datetime.combine(next_day, time(3, 0)))
                        time_windows.append((start_night, end_night))
                
                elif is_last_day:
                    # Último día: ajustar según hora de fin
                    end_hour = self.end_date.hour
                    
                    # Si el último día empieza en madrugada (continuación de evento nocturno)
                    if end_hour >= 0:
                        early_morning_start = timezone.make_aware(datetime.combine(day_date, time(0, 0)))
                        early_morning_end = min(self.end_date, timezone.make_aware(datetime.combine(day_date, time(6, 0))))
                        if early_morning_start < early_morning_end:
                            time_windows.append((early_morning_start, early_morning_end))
                    
                    if end_hour > 9:
                        time_windows.append((
                            timezone.make_aware(datetime.combine(day_date, time(9, 0))),
                            min(self.end_date, timezone.make_aware(datetime.combine(day_date, time(12, 0))))
                        ))
                    
                    if end_hour > 12:
                        time_windows.append((
                            timezone.make_aware(datetime.combine(day_date, time(12, 0))),
                            min(self.end_date, timezone.make_aware(datetime.combine(day_date, time(14, 0))))
                        ))
                    
                    if end_hour > 14:
                        time_windows.append((
                            timezone.make_aware(datetime.combine(day_date, time(14, 0))),
                            min(self.end_date, timezone.make_aware(datetime.combine(day_date, time(18, 0))))
                        ))
                    
                    if end_hour > 19:
                        time_windows.append((
                            timezone.make_aware(datetime.combine(day_date, time(19, 0))),
                            min(self.end_date, timezone.make_aware(datetime.combine(day_date, time(22, 0))))
                        ))
                    
                    # Ventana nocturna último día si aplica
                    if end_hour >= 22 or self.end_date.date() > day_date:
                        start_night = timezone.make_aware(datetime.combine(day_date, time(22, 0)))
                        end_night = self.end_date
                        if start_night < end_night:
                            time_windows.append((start_night, end_night))
                
                else:
                    # Días intermedios: ventanas completas incluidas nocturnas
                    windows = [
                        (timezone.make_aware(datetime.combine(day_date, time(9, 0))),
                         timezone.make_aware(datetime.combine(day_date, time(12, 0)))),
                        
                        (timezone.make_aware(datetime.combine(day_date, time(12, 0))),
                         timezone.make_aware(datetime.combine(day_date, time(14, 0)))),
                        
                        (timezone.make_aware(datetime.combine(day_date, time(14, 0))),
                         timezone.make_aware(datetime.combine(day_date, time(18, 0)))),
                        
                        (timezone.make_aware(datetime.combine(day_date, time(19, 0))),
                         timezone.make_aware(datetime.combine(day_date, time(22, 0)))),
                        
                        # Ventana nocturna (22:00 - 03:00 día siguiente)
                        (timezone.make_aware(datetime.combine(day_date, time(22, 0))),
                         timezone.make_aware(datetime.combine(day_date + timedelta(days=1), time(3, 0)))),
                    ]
                    time_windows.extend(windows)
        
        return time_windows
    
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
    
    def _generate_strategy_itinerary(self, strategy, accommodations, activities_with_scores, restaurants, events, time_windows):
        """
        Genera un itinerario para una estrategia específica, considerando tipo de usuario
        (Esta es la versión unificada de la función que tenías duplicada)
        """
        effective_strategy = strategy
        items = []
        total_cost = 0
        
        # 1. Seleccionar alojamiento
        if self.days > 1 and accommodations:
            acc = self._select_accommodation(effective_strategy, accommodations)
            if acc:
                acc_cost = self._calculate_accommodation_cost(acc, effective_strategy)
                items.append({
                    'service': acc, 'type': 'accommodation', 'cost': acc_cost,
                    'date': self.start_date, 'duration_days': self.nights
                })
                total_cost += acc_cost
                
        # 2. Planificar comidas
        meal_budget_ratio = constants.DEFAULT_MEAL_BUDGET_RATIO
        meal_budget = self.budget * meal_budget_ratio
        meal_plan = self._plan_meals(restaurants, effective_strategy, meal_budget)
        for meal in meal_plan:
            if total_cost + meal['cost'] <= self.budget:
                items.append(meal)
                total_cost += meal['cost']
                
        # 3. Presupuesto restante
        activities_events_budget = self.budget - total_cost
        
        # 4. Procesar Eventos (Prioritarios)
        scheduled_events, remaining_budget, _ = self._process_events(
            events, time_windows, activities_events_budget
        )
        for event in scheduled_events:
            items.append(event)
            total_cost += event['cost']
            
        # 5. Identificar ventanas ocupadas
        used_windows_for_events = self._identificar_ventanas_ocupadas_por_eventos(scheduled_events, time_windows)
        available_time_windows = [
            window for i, window in enumerate(time_windows)
            if i not in used_windows_for_events
        ]
        
        # 6. Resolver Problema de Orientación (El núcleo)
        selected_activities = optimization_core.solve_orienteeering_problem(
            self, # Pasa la instancia para acceder a caches y helpers
            activities_with_scores, 
            available_time_windows, 
            remaining_budget
        )
        
        # 7. Asignar actividades
        scheduled_activities = self._schedule_activities(selected_activities, available_time_windows)
        for activity in scheduled_activities:
            if total_cost + activity['cost'] <= self.budget:
                items.append(activity)
                total_cost += activity['cost']
                
        return {
            'items': items,
            'total_cost': total_cost,
            'strategy': effective_strategy,
            'original_strategy': strategy,
            'budget_utilization': total_cost / self.budget if self.budget > 0 else 0,
            'experiencias_applied': self.experiencias,
        }

    def generate_optimized_itineraries(self, max_itineraries=3):
        """
        Punto de entrada público para generar itinerarios optimizados
        """
        if not self.zone or self.days < 1:
            return []
        
        # 1. Obtener todos los candidatos usando el data_provider
        accommodations = data_provider.get_accommodations(self.user, self.zone, top_k=10)
        activities_with_scores = data_provider.get_activities_with_scores(
            self.user, self.zone, self.experiencias, top_k=50
        )
        restaurants = data_provider.get_restaurants(self.user, self.zone, top_k=20)
        events = data_provider.get_events(
            self.user, self.zone, self.start_date, self.end_date,
            self.is_same_day, self.current_time,
            self._is_night_event, self._ensure_timezone_aware, self._hay_solapamiento,
            top_k=15
        )
        time_windows = self._create_time_windows()
        
        self.performance_metrics['candidate_activities'] = len(activities_with_scores)
        
        # 2. Generar itinerarios
        itineraries = []
        strategies = ['budget', 'balanced', 'premium']
        
        for strategy in strategies[:max_itineraries]:
            itinerary = self._generate_strategy_itinerary(
                strategy, accommodations, activities_with_scores,
                restaurants, events, time_windows
            )
            if itinerary:
                itineraries.append(itinerary)
                
        # 3. Calcular métricas finales
        self.performance_metrics['end_time'] = timezone.now()
        self.performance_metrics['execution_time'] = (
            self.performance_metrics['end_time'] - self.performance_metrics['start_time']
        ).total_seconds()
        
        if itineraries:
            avg_budget_util = sum(it['budget_utilization'] for it in itineraries) / len(itineraries)
            self.performance_metrics['budget_efficiency'] = avg_budget_util
            
        return itineraries
    
    def get_optimization_report(self):
        """Retorna un reporte detallado de la optimización"""
        return {
            'metrics': self.performance_metrics,
            'summary': {
                'total_candidates': self.performance_metrics['candidate_activities'],
                'total_selected': self.performance_metrics['selected_activities'],
                'selection_rate': (
                    self.performance_metrics['selected_activities'] / 
                    self.performance_metrics['candidate_activities']
                    if self.performance_metrics['candidate_activities'] > 0 else 0
                ),
                'execution_time_ms': self.performance_metrics.get('execution_time', 0) * 1000
            }
        }
    
    
    
