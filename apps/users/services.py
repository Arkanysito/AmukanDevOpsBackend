import logging
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

# Importaciones de modelos
from apps.tracking.models import Interaction
from apps.users.models import CustomUser, UserInterest, Interest, UserFavorite
from apps.core.constants import InteractionAction

# Importa los modelos de tus otras apps para que 'isinstance' funcione
from apps.experiences.models import ActivityService, Event, AccommodationService
from apps.location.models import Place

logger = logging.getLogger(__name__)

class UserProfileAnalyzer:
    """
    Analiza interacciones Y ESTADO ACTUAL (favoritos) 
    para actualizar el perfil del usuario.
    """
    
    def __init__(self, user: CustomUser):
        self.user = user
    
    def analyze_recent_interactions(self, days: int = 30):
        """
        Analiza interacciones recientes Y favoritos actuales para actualizar el perfil.
        """
        try:
            cutoff_date = timezone.now() - timedelta(days=days)
            
            # 1. Obtener interacciones "ruidosas" (búsquedas, guardados de itinerario)
            interactions = Interaction.objects.filter(
                user_id=self.user,
                interaction_date__gte=cutoff_date
            )
            
            search_interactions = interactions.filter(action=InteractionAction.SEARCH)
            save_interactions = interactions.filter(action=InteractionAction.SAVE_ITINERARY)
            
            # 2. Obtener el estado "estable" de los favoritos actuales
            current_favorites = UserFavorite.objects.filter(
                user_id=self.user
            ).select_related('content_type') # Optimización
            
            # 3. Actualizar intereses
            self._update_interests_from_data(
                search_interactions, 
                save_interactions,
                current_favorites  # <-- Pasamos la lista de favoritos
            )
            
            logger.info(f"✅ Perfil analizado para {self.user.email}")
            
        except Exception as e:
            logger.error(f"❌ Error analizando interacciones para {self.user.email}: {str(e)}", exc_info=True)

    def _update_interests_from_data(self, searches, saves, favorites):
        """Actualiza intereses basado en todas las fuentes de datos"""
        
        # Diccionario para acumular los pesos
        interest_weights = {} 
        
        # Procesar búsquedas (peso bajo: 0.1)
        for search in searches:
            metadata = search.metadata or {}
            search_params = metadata.get('search_parameters', {})
            preferences = search_params.get('preferences', {})
            self._extract_interests_from_preferences(preferences, interest_weights, weight=0.1)
        
        # Procesar guardados de itinerarios (peso alto: 0.3)
        for save in saves:
            metadata = save.metadata or {}
            user_preferences = metadata.get('user_preferences', {})
            service_dist = metadata.get('service_distribution', {})
            
            self._extract_interests_from_preferences(user_preferences, interest_weights, weight=0.3)
            self._extract_interests_from_services(service_dist, interest_weights, weight=0.2)
        
        # Procesar favoritos actuales (peso medio: 0.2)
        # Es estable porque es el estado final, no el "toggle"
        self._extract_interests_from_favorites_list(favorites, interest_weights, weight=0.2)
        
        # Aplicar cambios a la base de datos
        self._apply_interest_updates(interest_weights)

    def _extract_interests_from_favorites_list(self, favorites, interest_weights, weight):
        """
        Extrae intereses de la lista actual de objetos UserFavorite.
        """
        for fav in favorites:
            try:
                target = fav.target # Obtiene el objeto real (Place, Activity, etc.)
                if not target:
                    continue

                # Simulamos la lógica de 'service_dist'
                service_dist = {}
                if isinstance(target, (Place, Event)):
                    # Asumir que un Place/Event favorito es comida o cultura
                    service_dist['comida'] = {'count': 1}
                    service_dist['actividades'] = {'count': 1}
                elif isinstance(target, ActivityService):
                    service_dist['actividades'] = {'count': 1}
                elif isinstance(target, AccommodationService):
                    service_dist['hospedaje'] = {'count': 1}
                
                # Usamos la misma lógica de extracción que 'SAVE_ITINERARY'
                self._extract_interests_from_services(service_dist, interest_weights, weight)
                
            except Exception as e:
                logger.warning(f"No se pudo procesar el favorito {fav.object_id} para {self.user.email}: {e}")

    # --- Métodos Helper (Tus funciones originales) ---

    def _apply_interest_updates(self, interest_weights):
        """Aplica las actualizaciones de intereses a la base de datos"""
        if not interest_weights:
            return # No hay nada que actualizar

        for interest_name, weight_change in interest_weights.items():
            interest, created = Interest.objects.get_or_create(name=interest_name)
            
            # Ensure weight_change is Decimal for consistency
            decimal_weight_change = Decimal(str(weight_change))

            user_interest, created = UserInterest.objects.get_or_create(
                user_id=self.user,
                interest_id=interest,
                # Ensure the default is also Decimal and clamped
                defaults={'weight': min(decimal_weight_change, Decimal('1.0'))} 
            )
            
            if not created:
                # Actualizar peso existente (decay + boost)
                current_weight = user_interest.weight * Decimal('0.95') # Use Decimal for decay
                new_weight = min(current_weight + decimal_weight_change, Decimal('1.0')) # Clamp upper bound
                user_interest.weight = max(new_weight, Decimal('0.1')) # Clamp lower bound
                user_interest.save()

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
            'adventure': 'Aventura', 'cultural': 'Cultura', 
            'gastronomy': 'Gastronomía', 'relax': 'Relax',
            'luxury': 'Lujo', 'budget': 'Económico'
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