import logging
from django.utils import timezone
from datetime import timedelta
from apps.tracking.models import Interaction
from apps.users.models import CustomUser, UserInterest, Interest
from apps.core.constants import InteractionAction

logger = logging.getLogger(__name__)

class UserProfileAnalyzer:
    """Analiza interacciones para actualizar el perfil del usuario"""
    
    def __init__(self, user):
        self.user = user
    
    def analyze_recent_interactions(self, days=30):
        """Analiza interacciones recientes para actualizar el perfil"""
        try:
            cutoff_date = timezone.now() - timedelta(days=days)
            
            interactions = Interaction.objects.filter(
                user_id=self.user,
                interaction_date__gte=cutoff_date
            ).order_by('interaction_date')
            
            # Agrupar interacciones por tipo
            search_interactions = interactions.filter(action=InteractionAction.SEARCH)
            save_interactions = interactions.filter(action=InteractionAction.SAVE_ITINERARY)
            view_interactions = interactions.filter(action=InteractionAction.VIEW)
            
            # Actualizar intereses basado en interacciones
            self._update_interests_from_interactions(
                search_interactions, 
                save_interactions, 
                view_interactions
            )
            
            logger.info(f"✅ Perfil analizado para {self.user.email}")
            
        except Exception as e:
            logger.error(f"❌ Error analizando interacciones: {str(e)}")
    
    def _update_interests_from_interactions(self, searches, saves, views):
        """Actualiza intereses basado en diferentes tipos de interacciones"""
        interest_weights = {}
        
        # Procesar búsquedas
        for search in searches:
            metadata = search.metadata or {}
            search_params = metadata.get('search_parameters', {})
            preferences = search_params.get('preferences', {})
            
            self._extract_interests_from_preferences(preferences, interest_weights, weight=0.1)
        
        # Procesar guardados (más peso)
        for save in saves:
            metadata = save.metadata or {}
            user_preferences = metadata.get('user_preferences', {})
            service_dist = metadata.get('service_distribution', {})
            
            self._extract_interests_from_preferences(user_preferences, interest_weights, weight=0.3)
            self._extract_interests_from_services(service_dist, interest_weights, weight=0.2)
        
        # Aplicar cambios a la base de datos
        self._apply_interest_updates(interest_weights)
    
    def _extract_interests_from_interactions(self, interactions, interest_weights):
        """Extrae intereses de todas las interacciones (incluyendo experiencias)"""
        for interaction in interactions:
            metadata = interaction.metadata or {}
            
            # Extraer de parámetros de búsqueda
            search_params = metadata.get('search_parameters', {})
            experiencias = search_params.get('experiencias', [])
            preferences = search_params.get('preferences', {})
            
            # Las experiencias tienen mayor peso en búsquedas
            self._extract_interests_from_experiencias(experiencias, interest_weights, weight=0.15)
            self._extract_interests_from_preferences(preferences, interest_weights, weight=0.1)
            
            # Extraer de itinerarios guardados
            user_preferences = metadata.get('user_preferences', {})
            experiencias_guardadas = metadata.get('experiencias_seleccionadas', [])
            service_dist = metadata.get('service_distribution', {})
            
            # Las experiencias en itinerarios guardados tienen aún más peso
            self._extract_interests_from_experiencias(experiencias_guardadas, interest_weights, weight=0.25)
            self._extract_interests_from_preferences(user_preferences, interest_weights, weight=0.2)
            self._extract_interests_from_services(service_dist, interest_weights, weight=0.15)
    
    def _extract_interests_from_experiencias(self, experiencias, interest_weights, weight=0.1):
        """Extrae intereses de las experiencias seleccionadas"""
        experiencia_to_interest = {
            'Aventura': ['Aventura', 'Naturaleza', 'Deportes', 'Extremo'],
            'Cultura': ['Cultura', 'Arte', 'Historia', 'Tradiciones'],
            'Gastronomía': ['Gastronomía', 'Local', 'Vinos', 'Culinario'],
            'Relax': ['Relax', 'Bienestar', 'Spa', 'Tranquilidad'],
            'Naturaleza': ['Naturaleza', 'Ecoturismo', 'Aire Libre', 'Aventura'],
            'Urbano': ['Ciudad', 'Compras', 'Entretenimiento', 'Moderno'],
            'Familiar': ['Familia', 'Niños', 'Diversión', 'Seguro'],
            'Romántico': ['Romántico', 'Lujo', 'Intimidad', 'Relax']
        }
        
        for experiencia in experiencias:
            if experiencia in experiencia_to_interest:
                for interest in experiencia_to_interest[experiencia]:
                    interest_weights[interest] = interest_weights.get(interest, 0) + weight
    
    def _extract_interests_from_preferences(self, preferences, interest_weights, weight=0.1):
        """Extrae intereses de las preferencias del usuario"""
        preference_to_interest = {
            'adventure': 'Aventura',
            'cultural': 'Cultura', 
            'gastronomy': 'Gastronomía',
            'relax': 'Relax',
            'luxury': 'Lujo',
            'budget': 'Económico'
        }
        
        for pref_key, interest_name in preference_to_interest.items():
            if preferences.get(pref_key, False):
                interest_weights[interest_name] = interest_weights.get(interest_name, 0) + weight
    
    def _extract_interests_from_services(self, service_dist, interest_weights, weight=0.1):
        """Extrae intereses de la distribución de servicios"""
        service_to_interest = {
            'actividades': ['Aventura', 'Cultura'],
            'eventos': ['Cultura', 'Música'],
            'hospedaje': ['Lujo', 'Relax'],
            'comida': ['Gastronomía'],
            'transporte': ['Aventura']
        }
        
        for service_type, distribution in service_dist.items():
            if service_type in service_to_interest and distribution.get('count', 0) > 0:
                for interest in service_to_interest[service_type]:
                    interest_weights[interest] = interest_weights.get(interest, 0) + weight
    
    def _apply_interest_updates(self, interest_weights):
        """Aplica las actualizaciones de intereses a la base de datos"""
        for interest_name, weight_change in interest_weights.items():
            interest, created = Interest.objects.get_or_create(name=interest_name)
            
            user_interest, created = UserInterest.objects.get_or_create(
                user_id=self.user,
                interest_id=interest,
                defaults={'weight': min(weight_change, 1.0)}
            )
            
            if not created:
                # Actualizar peso existente
                new_weight = min(user_interest.weight + weight_change, 1.0)
                user_interest.weight = max(new_weight, 0.1)  # Mínimo 0.1
                user_interest.save()

    