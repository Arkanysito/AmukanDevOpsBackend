import random
import numpy as np
from datetime import datetime, time, timedelta
from django.db.models import Q
from django.utils import timezone
from collections import defaultdict
import math
from typing import List, Dict, Any, Tuple
from apps.location.models import Zone, Place
from apps.experiences.models import ActivityService, Event
from apps.recommendation.services import recommend_places
from apps.core.constants import PlaceType

class ItineraryOptimizer:
    def __init__(self, user, destination, start_date, end_date, budget, travelers, preferences=None):
        self.user = user
        self.destination = destination
        self.start_date = self._ensure_timezone_aware(start_date)
        self.end_date = self._ensure_timezone_aware(end_date)
        self.budget = budget
        self.travelers = travelers
        self.preferences = preferences or {}
        
        # Extraer experiencias y tipo de usuario específicamente
        self.experiencias = self.preferences.get('experiencias', [])
        self.tipo_usuario = self.preferences.get('tipo_usuario')
        
        # Detectar si es same-day (mismo día)
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
        self.time_slots_per_day = 4

        # Definir rangos de horarios incluidos nocturnos
        self.time_periods = {
            'morning': (9, 12),      # Mañana
            'lunch': (12, 14),       # Almuerzo
            'afternoon': (14, 18),   # Tarde
            'evening': (19, 22),     # Noche temprana
            'night': (22, 24),       # Noche
            'late_night': (0, 3)     # Madrugada (cruza medianoche)
        }

        # Sistema de métricas
        self.performance_metrics = {
            'start_time': timezone.now(),
            'candidate_activities': 0,
            'selected_activities': 0,
            'budget_efficiency': 0,
            'time_efficiency': 0,
            'experiencias_used': self.experiencias,
            'tipo_usuario': self.tipo_usuario
        }
        
    # Cache simple en memoria para coordenadas
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
        if dt is None:
            return None
        if not timezone.is_aware(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    
    def _calculate_distance(self, coord1, coord2):
        """Calcula distancia haversine entre dos coordenadas (en km) con cache"""
        if not coord1 or not coord2:
            return float('inf')
        
        # Cache de distancias
        cache_key = (coord1, coord2)
        if cache_key in getattr(self, '_distance_cache', {}):
            return self._distance_cache[cache_key]
        
        # Convertir a radianes
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
        
        # Fórmula haversine
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = 6371 * c
        
        if not hasattr(self, '_distance_cache'):
            self._distance_cache = {}
        self._distance_cache[cache_key] = distance
        
        return distance
    
    def _get_coordinates(self, obj):
        """Obtiene coordenadas de un objeto con cache"""
        cache_key = id(obj)
        if not hasattr(self, '_coordinates_cache'):
            self._coordinates_cache = {}
        
        if cache_key in self._coordinates_cache:
            return self._coordinates_cache[cache_key]
        
        coords = None
        if hasattr(obj, 'coordinates') and obj.coordinates:
            coords = (obj.coordinates.y, obj.coordinates.x)
        elif hasattr(obj, 'place_id') and hasattr(obj.place_id, 'coordinates') and obj.place_id.coordinates:
            coords = (obj.place_id.coordinates.y, obj.place_id.coordinates.x)
        
        self._coordinates_cache[cache_key] = coords
        return coords
    
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
    
    def _get_activities_with_scores(self, top_k=50):
        """Obtiene actividades con sus scores de recomendación, considerando experiencias"""
        try:
            activities = recommend_places(self.user, 'activity', self.zone, top_k=top_k)
            if activities and isinstance(activities[0], tuple):
                self.performance_metrics['candidate_activities'] = len(activities)
                
                # Ajustar scores basado en experiencias del usuario
                adjusted_activities = []
                for activity, score in activities:
                    adjusted_score = self._adjust_score_by_experiencias(activity, float(score))
                    adjusted_activities.append((activity, adjusted_score))
                
                return adjusted_activities
            else:
                activities_with_scores = []
                for act in activities:
                    adjusted_score = self._adjust_score_by_experiencias(act, 0.5)
                    activities_with_scores.append((act, adjusted_score))
                self.performance_metrics['candidate_activities'] = len(activities_with_scores)
                return activities_with_scores
        except:
            activities = ActivityService.objects.all()
            if self.zone:
                activities = activities.filter(place_id__zone_id=self.zone)
            
            # Aplicar ajuste por experiencias incluso en fallback
            result = []
            for act in activities[:top_k]:
                adjusted_score = self._adjust_score_by_experiencias(act, 0.5)
                result.append((act, adjusted_score))
            
            self.performance_metrics['candidate_activities'] = len(result)
            return result
    
    def _adjust_score_by_experiencias(self, activity, base_score):
        """
        Ajusta el score de una actividad basado en las experiencias seleccionadas
        """
        if not self.experiencias:
            return base_score
        
        adjusted_score = base_score
        activity_categories = self._get_activity_categories(activity)
        
        # Mapeo de experiencias a categorías de actividades
        experiencia_to_categories = {
            'Aventura': ['adventure', 'sports', 'outdoor', 'extreme', 'hiking', 'climbing'],
            'Cultura': ['cultural', 'museum', 'historical', 'art', 'heritage', 'architecture'],
            'Gastronomía': ['gastronomy', 'food', 'wine', 'culinary', 'cooking', 'tasting'],
            'Relax': ['relaxation', 'spa', 'wellness', 'leisure', 'yoga', 'meditation'],
            'Naturaleza': ['nature', 'ecotourism', 'wildlife', 'park', 'garden', 'beach'],
            'Urbano': ['urban', 'shopping', 'entertainment', 'city', 'nightlife', 'theater'],
            'Familiar': ['family', 'kids', 'amusement', 'educational', 'playground', 'zoo'],
            'Romántico': ['romantic', 'luxury', 'couples', 'intimate', 'scenic', 'viewpoint']
        }
        
        # Verificar coincidencia con experiencias
        for experiencia in self.experiencias:
            if experiencia in experiencia_to_categories:
                categories_for_experiencia = experiencia_to_categories[experiencia]
                # Si la actividad coincide con alguna categoría de la experiencia, aumentar score
                if any(cat in activity_categories for cat in categories_for_experiencia):
                    adjusted_score *= 1.3  # 30% de bonus por coincidencia
                    break  # Solo aplicar un bonus por actividad
        
        return min(adjusted_score, 1.0)  # Máximo 1.0
    
    def _get_activity_categories(self, activity):
        """
        Extrae categorías de una actividad para matching con experiencias
        """
        categories = []
        
        # Intentar obtener categorías de diferentes formas
        if hasattr(activity, 'category'):
            categories.append(activity.category.lower())
        
        if hasattr(activity, 'tags'):
            if isinstance(activity.tags, list):
                categories.extend([tag.lower() for tag in activity.tags])
            elif isinstance(activity.tags, str):
                categories.extend([tag.strip().lower() for tag in activity.tags.split(',')])
        
        if hasattr(activity, 'name'):
            name_lower = activity.name.lower()
            # Búsqueda de palabras clave en el nombre
            keyword_mapping = {
                'aventura': 'adventure',
                'cultura': 'cultural', 
                'gastronomía': 'gastronomy',
                'relax': 'relaxation',
                'naturaleza': 'nature',
                'urbano': 'urban',
                'familiar': 'family',
                'romántico': 'romantic'
            }
            
            for spanish, english in keyword_mapping.items():
                if spanish in name_lower:
                    categories.append(english)
        
        return categories
    
    def _generate_strategy_itinerary(self, strategy, accommodations, activities_with_scores, restaurants, events, time_windows):
        """
        Genera un itinerario para una estrategia específica, considerando tipo de usuario
        """
        # AJUSTAR ESTRATEGIA SEGÚN TIPO DE USUARIO
        effective_strategy = self._adjust_strategy_by_tipo_usuario(strategy)
        
        items = []
        total_cost = 0
        
        # 1. Seleccionar alojamiento (ajustado por tipo de usuario) - AHORA DESDE PLACE
        if self.days > 1 and accommodations:
            acc = self._select_accommodation(effective_strategy, accommodations)
            if acc:
                # CALCULAR COSTO BASADO EN average_price DE PLACE
                acc_cost = self._calculate_accommodation_cost(acc, effective_strategy)
                items.append({
                    'service': acc,
                    'type': 'accommodation',
                    'cost': acc_cost,
                    'date': self.start_date,
                    'duration_days': self.days - 1
                })
                total_cost += acc_cost
        
        # 2. Planificar comidas (ajustado por tipo de usuario)
        meal_budget = self.budget * self._get_meal_budget_ratio_by_tipo_usuario()
        meal_plan = self._plan_meals(restaurants, effective_strategy, meal_budget)
        for meal in meal_plan:
            if total_cost + meal['cost'] <= self.budget:
                items.append(meal)
                total_cost += meal['cost']
        
        # 3. Presupuesto restante para actividades y eventos
        activities_events_budget = self.budget - total_cost
        
        # 4. PRIMERO: Procesar eventos (priorizando eventos que coincidan con experiencias)
        scheduled_events, remaining_budget, _ = self._process_events(
            events, time_windows, activities_events_budget
        )
        
        for event in scheduled_events:
            items.append(event)
            total_cost += event['cost']
        
        # 5. Identificar ventanas ocupadas por eventos
        used_windows_for_events = self._identificar_ventanas_ocupadas_por_eventos(scheduled_events, time_windows)
        
        # 6. LUEGO: Resolver Problema de Orientación para actividades (con experiencias)
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
            'strategy': effective_strategy,
            'original_strategy': strategy,
            'budget_utilization': total_cost / self.budget if self.budget > 0 else 0,
            'experiencias_applied': self.experiencias,
            'tipo_usuario_used': self.tipo_usuario
        }
    
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
    
    def _adjust_strategy_by_tipo_usuario(self, original_strategy):
        """
        Ajusta la estrategia basada en el tipo de usuario
        """
        if not self.tipo_usuario:
            return original_strategy
        
        strategy_adjustments = {
            'mochilero': 'budget',
            'económico': 'budget', 
            'turista': 'balanced',
            'premium': 'premium',
            'lujo': 'premium',
            'aventurero': 'balanced',
            'cultural': 'balanced',
            'familiar': 'balanced'
        }
        
        return strategy_adjustments.get(self.tipo_usuario.lower(), original_strategy)
    
    def _get_meal_budget_ratio_by_tipo_usuario(self):
        """
        Define el ratio de presupuesto para comidas según tipo de usuario
        """
        if not self.tipo_usuario:
            return 0.3  # Default
        
        meal_ratios = {
            'mochilero': 0.2,
            'económico': 0.25,
            'turista': 0.3,
            'premium': 0.35,
            'lujo': 0.4,
            'aventurero': 0.25,
            'cultural': 0.3,
            'familiar': 0.35
        }
        
        return meal_ratios.get(self.tipo_usuario.lower(), 0.3)
    
    def _get_accommodations(self, top_k=10):
        """Obtiene alojamientos DESDE PLACE"""
        try:
            accommodations = recommend_places(self.user, 'accommodation', self.zone, top_k=top_k)
            if accommodations and isinstance(accommodations[0], tuple):
                return [acc for acc, score in accommodations]
            return accommodations
        except:
            #  Usar Place en lugar de AccommodationService
            accommodation_types = [
                PlaceType.HOTEL, PlaceType.HOSTEL, PlaceType.GUEST_HOUSE, 
                PlaceType.RESORT, PlaceType.BED_BREAKFAST, PlaceType.MOTEL, 
                PlaceType.CAMPSITE
            ]
            interesting_types = [pt.value for pt in accommodation_types]
            
            accommodations = Place.objects.filter(type__in=interesting_types)
            if self.zone:
                accommodations = accommodations.filter(zone_id=self.zone)
            return list(accommodations[:top_k])
    
    def _get_restaurants(self, top_k=20):
        """Obtiene restaurantes DESDE PLACE"""
        try:
            restaurants = recommend_places(self.user, 'restaurant', self.zone, top_k=top_k)
            if restaurants and isinstance(restaurants[0], tuple):
                return [rest for rest, score in restaurants]
            return restaurants
        except:
            # Usar Place directamente
            restaurant_types = [
                PlaceType.RESTAURANT, PlaceType.CAFE, PlaceType.BAR, PlaceType.PUB,
                PlaceType.FAST_FOOD, PlaceType.FOOD_COURT, PlaceType.ICE_CREAM
            ]
            interesting_types = [pt.value for pt in restaurant_types]
            
            restaurants = Place.objects.filter(type__in=interesting_types)
            if self.zone:
                restaurants = restaurants.filter(zone_id=self.zone)
            return list(restaurants[:top_k])
    
    def _get_events(self, top_k=15):
        """
        Obtiene eventos incluyendo eventos nocturnos.
        
        No filtra eventos nocturnos, los incluye con metadata especial
        """
        try:
            from apps.recommendation.services import recommend_places
            events = recommend_places(self.user, 'event', self.zone, top_k=top_k)
            if events and isinstance(events[0], tuple):
                events = [event for event, score in events]
            
            filtered_events = []
            night_events_count = 0
            
            for event in events:
                event_start = self._ensure_timezone_aware(event.start_date)
                event_end = self._ensure_timezone_aware(event.end_date)
                
                # Para mismo día: filtrar eventos que ya terminaron
                if self.is_same_day:
                    if event_end < self.current_time:
                        continue
                    
                    if event_start < self.current_time < event_end:
                        event_start = self.current_time
                    
                    if event_start.date() == self.start_date.date() or \
                       (event_end.date() == self.start_date.date() + timedelta(days=1) and event_end.hour < 6):
                        filtered_events.append(event)
                        
                        if self._is_night_event(event_start, event_end):
                            night_events_count += 1
                else:
                    # Para múltiples días: verificar solapamiento
                    # Extender búsqueda hasta el día siguiente temprano para eventos nocturnos
                    extended_end = self.end_date + timedelta(hours=6)
                    
                    if self._hay_solapamiento(event_start, event_end, self.start_date, extended_end):
                        filtered_events.append(event)
                        
                        if self._is_night_event(event_start, event_end):
                            night_events_count += 1
            
            return filtered_events[:top_k]
            
        except Exception as e:
            # Fallback con criterio flexible
            events = Event.objects.filter(
                Q(start_date__lte=self.end_date + timedelta(hours=6)) & 
                Q(end_date__gte=self.start_date)
            )
            
            # Filtrar por hora actual si es same-day
            if self.is_same_day:
                events = events.filter(end_date__gte=self.current_time)
            
            if self.zone:
                events = events.filter(place_id__zone_id=self.zone)
            return list(events[:top_k])
    
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
    
    # Algoritmo mejorado con diversidad geográfica
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
            # Ajuste dinámico de scores por preferencias
            adjusted_score = float(score) * 100
            
            # Bonus por coincidencia con preferencias del usuario
            if self.preferences:
                if hasattr(activity, 'category'):
                    pref_categories = self.preferences.get('categories', [])
                    if activity.category in pref_categories:
                        adjusted_score *= 1.3  # 30% bonus
                
                # Penalización por baja rating si el usuario valora calidad
                if self.preferences.get('prioritize_quality', False):
                    if hasattr(activity, 'rating') and activity.rating < 3.5:
                        adjusted_score *= 0.7
            
            scores[i] = adjusted_score
            activity_objects.append(activity)
        
        # Matriz de distancias entre actividades con cache
        distance_matrix = np.zeros((n_activities, n_activities))
        coordinates = [self._get_coordinates(act) for act in activity_objects]
        
        for i in range(n_activities):
            for j in range(i+1, n_activities):
                dist = self._calculate_distance(coordinates[i], coordinates[j])
                distance_matrix[i, j] = dist
                distance_matrix[j, i] = dist
        
        # Matriz de tiempos de viaje (asumir 20 km/h en ciudad)
        time_matrix = distance_matrix / 20 * 60 # Convertir a minutos
        
        activity_durations = np.zeros(n_activities)
        for i, activity in enumerate(activity_objects):
            activity_durations[i] = getattr(activity, 'duration_minutes', 120)
        
        # Costos de actividades
        activity_costs = np.zeros(n_activities)
        for i, activity in enumerate(activity_objects):
            activity_costs[i] = float(activity.price) * self.travelers
        
        # Algoritmo greedy para el Problema de Orientación mejorado con diversidad
        selected_activities = self._greedy_orienteeering_enhanced(
            scores, distance_matrix, time_matrix, activity_durations, 
            activity_costs, coordinates, time_windows, budget_constraint, 
            len(time_windows)
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
        
        self.performance_metrics['selected_activities'] = len(result)
        
        return result
    
    def _greedy_orienteeering_enhanced(self, scores, distance_matrix, time_matrix, 
                                      durations, costs, coordinates, time_windows, 
                                      budget_constraint, max_activities):
        """Algoritmo greedy mejorado con clustering geográfico"""
        n = len(scores)
        selected = []
        remaining_budget = budget_constraint
        remaining_time_windows = list(range(len(time_windows)))
        
        # Penalización por clustering excesivo
        geographic_clusters = self._simple_geographic_clustering(coordinates, n_clusters=3)
        cluster_counts = defaultdict(int)
        
        # Calcular ratios con penalización por distancia
        ratios = []
        for i in range(n):
            if costs[i] <= 0:
                continue
                
            # Ratio base: score / (costo + tiempo)
            total_cost = costs[i] + 0.1
            time_value = durations[i] / 60
            base_ratio = scores[i] / (total_cost + time_value)
            
            # Bonus por diversidad geográfica
            cluster_id = geographic_clusters[i]
            diversity_bonus = 1.0 / (1.0 + cluster_counts[cluster_id] * 0.2)
            
            final_ratio = base_ratio * diversity_bonus
            ratios.append((final_ratio, i, cluster_id))
        
        ratios.sort(reverse=True)
        
        # Selección greedy con límite de distancia
        MAX_TRAVEL_TIME = 45  # minutos máximo entre actividades
        
        for ratio, idx, cluster_id in ratios:
            if costs[idx] <= remaining_budget and len(selected) < max_activities:
                activity_duration = durations[idx] / 60
                
                # Verificar distancia si ya hay actividades seleccionadas
                if selected:
                    last_idx = selected[-1]
                    travel_time = time_matrix[last_idx, idx]
                    
                    # Saltar si está muy lejos
                    if travel_time > MAX_TRAVEL_TIME:
                        continue
                
                time_window_idx = self._find_available_time_window(
                    selected, idx, time_matrix, durations, time_windows, remaining_time_windows
                )
                
                if time_window_idx is not None:
                    selected.append(idx)
                    remaining_budget -= costs[idx]
                    remaining_time_windows.remove(time_window_idx)
                    cluster_counts[cluster_id] += 1
        
        return selected
    
    def _simple_geographic_clustering(self, coordinates, n_clusters=3):
        """Clustering geográfico simple usando k-means simplificado"""
        valid_coords = [(i, c) for i, c in enumerate(coordinates) if c is not None]
        
        if len(valid_coords) < n_clusters:
            return {i: 0 for i in range(len(coordinates))}
        
        # Inicializar centroides aleatoriamente
        random.shuffle(valid_coords)
        centroids = [coord for _, coord in valid_coords[:n_clusters]]
        
        # Asignación simple (sin iteración completa de k-means para eficiencia)
        clusters = {}
        for i, coord in enumerate(coordinates):
            if coord is None:
                clusters[i] = 0
                continue
            
            min_dist = float('inf')
            best_cluster = 0
            
            for c_idx, centroid in enumerate(centroids):
                dist = self._calculate_distance(coord, centroid)
                if dist < min_dist:
                    min_dist = dist
                    best_cluster = c_idx
            
            clusters[i] = best_cluster
        
        return clusters
    
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
        
        # Calcular métricas finales
        self.performance_metrics['end_time'] = timezone.now()
        self.performance_metrics['execution_time'] = (
            self.performance_metrics['end_time'] - self.performance_metrics['start_time']
        ).total_seconds()
        
        if itineraries:
            avg_budget_util = sum(it['budget_utilization'] for it in itineraries) / len(itineraries)
            self.performance_metrics['budget_efficiency'] = avg_budget_util
        
        return itineraries
    
    # Método para obtener logs de optimización
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
                acc_cost = 0
                if acc.average_price:
                    acc_cost = float(acc.average_price) * (self.days - 1) * self.travelers

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
        """
        Identifica ventanas ocupadas considerando eventos nocturnos.
        
        Maneja correctamente eventos que cruzan medianoche
        """
        used_windows = set()
        
        for event in scheduled_events:
            event_start = event['start_time']
            event_end = event['end_time']
            
            # Para eventos que cruzan medianoche, buscar en ambos días
            for i, (window_start, window_end) in enumerate(time_windows):
                if self._hay_solapamiento(event_start, event_end, window_start, window_end):
                    used_windows.add(i)
        
        return used_windows

    def _hay_solapamiento(self, inicio1, fin1, inicio2, fin2):
        """Determina si dos intervalos de tiempo se solapan"""
        return max(inicio1, inicio2) < min(fin1, fin2)
    
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


# Sistema de validación de itinerarios
class ItineraryValidator:
    """Valida la calidad y viabilidad de los itinerarios generados"""
    
    @staticmethod
    def validate_itinerary(itinerary, budget, days):
        """Valida un itinerario y retorna score de calidad"""
        validation_results = {
            'is_valid': True,
            'issues': [],
            'quality_score': 0,
            'metrics': {}
        }
        
        items = itinerary.get('items', [])
        total_cost = itinerary.get('total_cost', 0)
        
        # 1. Validar presupuesto
        if total_cost > budget:
            validation_results['is_valid'] = False
            validation_results['issues'].append('Budget exceeded')
        
        budget_usage = total_cost / budget if budget > 0 else 0
        validation_results['metrics']['budget_usage'] = budget_usage
        
        # 2. Validar distribución temporal
        activities_by_day = {}
        avg_activities = 0
        for item in items:
            if item['type'] in ['activity', 'event']:
                day = item['date'].date()
                activities_by_day[day] = activities_by_day.get(day, 0) + 1
        
        if activities_by_day:
            avg_activities = sum(activities_by_day.values()) / len(activities_by_day)
            validation_results['metrics']['avg_activities_per_day'] = avg_activities
            
            # Penalizar días vacíos o sobrecargados
            if avg_activities < 2:
                validation_results['issues'].append('Too few activities per day')
            elif avg_activities > 6:
                validation_results['issues'].append('Too many activities per day')
        
        # 3. Validar diversidad
        activity_types = [item['service'].__class__.__name__ for item in items if item.get('service')]
        diversity_score = len(set(activity_types)) / len(activity_types) if activity_types else 0
        validation_results['metrics']['diversity'] = diversity_score
        
        # 4. Calcular score de calidad (0-100)
        quality_score = 0
        
        # Budget efficiency (30 puntos)
        if 0.7 <= budget_usage <= 0.95:
            quality_score += 30
        elif 0.5 <= budget_usage < 0.7:
            quality_score += 20
        elif budget_usage > 0.95:
            quality_score += 25
        
        # Activities distribution (30 puntos)
        if 2 <= avg_activities <= 5:
            quality_score += 30
        elif 1 <= avg_activities < 2 or 5 < avg_activities <= 6:
            quality_score += 20
        
        # Diversity (20 puntos)
        quality_score += diversity_score * 20
        
        # Completeness (20 puntos)
        has_accommodation = any(item['type'] == 'accommodation' for item in items)
        has_dining = any(item['type'] == 'dining' for item in items)
        has_activities = any(item['type'] == 'activity' for item in items)
        
        completeness = sum([has_accommodation or days == 1, has_dining, has_activities])
        quality_score += (completeness / 3) * 20
        
        validation_results['quality_score'] = round(quality_score, 2)
        
        return validation_results


# Sistema de comparación de itinerarios
class ItineraryComparator:
    """Compara múltiples itinerarios y sugiere el mejor según criterios"""
    
    @staticmethod
    def compare_itineraries(itineraries, user_priorities=None):
        """
        Compara itinerarios y retorna ranking
        
        Args:
            itineraries: Lista de itinerarios
            user_priorities: Dict con pesos para criterios
                {'budget': 0.3, 'activities': 0.4, 'diversity': 0.3}
        """
        if not itineraries:
            return []
        
        # Prioridades por defecto
        priorities = user_priorities or {
            'budget_efficiency': 0.35,
            'activity_count': 0.25,
            'diversity': 0.20,
            'quality': 0.20
        }
        
        comparisons = []
        
        for idx, itinerary in enumerate(itineraries):
            items = itinerary.get('items', [])
            
            # Métricas
            activity_count = sum(1 for item in items if item['type'] in ['activity', 'event'])
            
            activity_types = [
                item['service'].__class__.__name__ 
                for item in items 
                if item.get('service')
            ]
            diversity = len(set(activity_types)) / len(activity_types) if activity_types else 0
            
            budget_util = itinerary.get('budget_utilization', 0)
            
            # Score compuesto
            score = (
                priorities['budget_efficiency'] * budget_util * 100 +
                priorities['activity_count'] * min(activity_count / 5, 1) * 100 +
                priorities['diversity'] * diversity * 100 +
                priorities['quality'] * 80  # Base quality score
            )
            
            comparisons.append({
                'index': idx,
                'strategy': itinerary.get('strategy', 'unknown'),
                'score': score,
                'metrics': {
                    'activity_count': activity_count,
                    'diversity': round(diversity, 2),
                    'budget_utilization': round(budget_util, 2),
                    'total_cost': itinerary.get('total_cost', 0)
                },
                'recommendation': ItineraryComparator._get_recommendation(
                    itinerary.get('strategy'), score
                )
            })
        
        # Ordenar por score
        comparisons.sort(key=lambda x: x['score'], reverse=True)
        
        return comparisons
    
    @staticmethod
    def _get_recommendation(strategy, score):
        """Genera recomendación textual"""
        if score >= 85:
            return f"Excelente opción {strategy}. Balance óptimo de todos los criterios."
        elif score >= 70:
            return f"Buena opción {strategy}. Cumple bien los objetivos principales."
        elif score >= 60:
            return f"Opción {strategy} aceptable. Algunos aspectos podrían mejorarse."
        else:
            return f"Opción {strategy} básica. Considera ajustar parámetros."


# MEJORA 11: Función helper para análisis de sensibilidad
def analyze_budget_sensitivity(optimizer, budget_variations=[0.8, 1.0, 1.2]):
    """
    Analiza cómo cambian los itinerarios con variaciones de presupuesto
    
    Args:
        optimizer: Instancia de ItineraryOptimizer
        budget_variations: Lista de multiplicadores de presupuesto
    
    Returns:
        Dict con análisis de sensibilidad
    """
    original_budget = optimizer.budget
    results = {}
    
    for multiplier in budget_variations:
        optimizer.budget = original_budget * multiplier
        itineraries = optimizer.generate_optimized_itineraries(max_itineraries=1)
        
        if itineraries:
            itinerary = itineraries[0]
            results[f'{int(multiplier*100)}%'] = {
                'budget': optimizer.budget,
                'total_cost': itinerary['total_cost'],
                'activity_count': sum(
                    1 for item in itinerary['items'] 
                    if item['type'] in ['activity', 'event']
                ),
                'utilization': itinerary['budget_utilization']
            }
    
    # Restaurar presupuesto original
    optimizer.budget = original_budget
    
    return results


# Función principal
def generate_optimized_itineraries(request, destination, start_date, end_date, 
                                  budget, travelers, preferences=None, 
                                  experiencias=None, tipo_usuario=None,
                                  include_analytics=False):
    """
    Función principal para generar itinerarios optimizados con analytics opcionales
    
    Args:
        request: HTTP request
        destination: Destino del viaje
        start_date: Fecha inicio
        end_date: Fecha fin
        budget: Presupuesto total
        travelers: Número de viajeros
        preferences: Preferencias del usuario (opcional)
        experiencias: Lista de experiencias seleccionadas (opcional)
        tipo_usuario: Tipo de usuario seleccionado (opcional)
        include_analytics: Si True, incluye reporte de optimización
    
    Returns:
        Dict con itinerarios y analytics opcionales
    """
    
    # INTEGRAR EXPERIENCIAS Y TIPO DE USUARIO EN LAS PREFERENCIAS
    enhanced_preferences = preferences.copy() if preferences else {}
    
    # Agregar experiencias a las preferencias
    if experiencias:
        enhanced_preferences['experiencias'] = experiencias
        # También mapear experiencias a categorías para el sistema de recomendación
        enhanced_preferences['categories'] = _map_experiencias_to_categories(experiencias)
    
    # Agregar tipo de usuario a las preferencias
    if tipo_usuario:
        enhanced_preferences['tipo_usuario'] = tipo_usuario
        # Ajustar estrategia basada en el tipo de usuario
        enhanced_preferences['strategy_weights'] = _get_strategy_weights_by_tipo_usuario(tipo_usuario)
    
    optimizer = ItineraryOptimizer(
        user=request.user if request.user.is_authenticated else None,
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        budget=budget,
        travelers=travelers,
        preferences=enhanced_preferences 
    )
    
    itineraries = optimizer.generate_optimized_itineraries(max_itineraries=3)
    
    # Validar itinerarios
    validated_itineraries = []
    for itinerary in itineraries:
        validation = ItineraryValidator.validate_itinerary(
            itinerary, budget, optimizer.days
        )
        itinerary['validation'] = validation
        validated_itineraries.append(itinerary)
    
    # Comparar itinerarios
    comparison = ItineraryComparator.compare_itineraries(
        validated_itineraries, 
        enhanced_preferences.get('priorities') 
    )
    
    result = {
        'itineraries': validated_itineraries,
        'comparison': comparison,
        'best_itinerary_index': comparison[0]['index'] if comparison else None
    }
    
    # Incluir analytics si se solicita
    if include_analytics:
        result['analytics'] = {
            'optimization_report': optimizer.get_optimization_report(),
            'budget_sensitivity': analyze_budget_sensitivity(optimizer),
            'user_profile_used': {
                'experiencias': experiencias,
                'tipo_usuario': tipo_usuario
            }
        }
    return result

# FUNCIONES AUXILIARES PARA MANEJAR EXPERIENCIAS Y TIPO DE USUARIO

def _map_experiencias_to_categories(experiencias):
    """
    Mapea experiencias a categorías de actividades para el sistema de recomendación
    """
    experiencia_to_categories = {
        'Aventura': ['adventure', 'sports', 'outdoor', 'extreme'],
        'Cultura': ['cultural', 'museum', 'historical', 'art'],
        'Gastronomía': ['gastronomy', 'food', 'wine', 'culinary'],
        'Relax': ['relaxation', 'spa', 'wellness', 'leisure'],
        'Naturaleza': ['nature', 'ecotourism', 'hiking', 'wildlife'],
        'Urbano': ['urban', 'shopping', 'entertainment', 'city'],
        'Familiar': ['family', 'kids', 'amusement', 'educational'],
        'Romántico': ['romantic', 'luxury', 'couples', 'intimate']
    }
    
    categories = set()
    for experiencia in experiencias:
        if experiencia in experiencia_to_categories:
            categories.update(experiencia_to_categories[experiencia])
    
    return list(categories)

def _get_strategy_weights_by_tipo_usuario(tipo_usuario):
    """
    Define pesos de estrategia basados en el tipo de usuario
    """
    strategy_weights = {
        'budget': 0.33,
        'balanced': 0.34,
        'premium': 0.33
    }
    
    # Ajustar pesos según el tipo de usuario
    tipo_usuario_weights = {
        'mochilero': {'budget': 0.6, 'balanced': 0.3, 'premium': 0.1},
        'económico': {'budget': 0.5, 'balanced': 0.4, 'premium': 0.1},
        'turista': {'budget': 0.3, 'balanced': 0.5, 'premium': 0.2},
        'premium': {'budget': 0.1, 'balanced': 0.3, 'premium': 0.6},
        'lujo': {'budget': 0.05, 'balanced': 0.25, 'premium': 0.7},
        'aventurero': {'budget': 0.4, 'balanced': 0.4, 'premium': 0.2},
        'cultural': {'budget': 0.3, 'balanced': 0.5, 'premium': 0.2},
        'familiar': {'budget': 0.2, 'balanced': 0.6, 'premium': 0.2}
    }
    
    return tipo_usuario_weights.get(tipo_usuario.lower() if tipo_usuario else '', strategy_weights)