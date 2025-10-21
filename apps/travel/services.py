import logging
from .optimizer import ItineraryOptimizer
from .validation import ItineraryValidator, ItineraryComparator
from . import constants

logger = logging.getLogger(__name__)

# --- Funciones Helper para el servicio ---

def _map_experiencias_to_categories(experiencias):
    """Mapea experiencias a categorías de actividades"""
    categories = set()
    for experiencia in experiencias:
        if experiencia in constants.EXPERIENCIA_TO_CATEGORIES_MAP:
            categories.update(constants.EXPERIENCIA_TO_CATEGORIES_MAP[experiencia])
    return list(categories)


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

def generate_optimized_itineraries(request, destination, start_date, end_date,
                                   budget, travelers, preferences=None,
                                   experiencias=None,
                                   include_analytics=False):
    """
    Función principal para generar itinerarios optimizados con analytics opcionales
    """
    
    # 1. Integrar experiencias y tipo de usuario en las preferencias
    enhanced_preferences = preferences.copy() if preferences else {}
    
    if experiencias:
        enhanced_preferences['experiencias'] = experiencias
        enhanced_preferences['categories'] = _map_experiencias_to_categories(experiencias)
    
    # 2. Inicializar y ejecutar el optimizador
    try:
        optimizer = ItineraryOptimizer(
            user=request.user if request.user.is_authenticated else None,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            budget=budget,
            travelers=travelers,
        )
        
        itineraries = optimizer.generate_optimized_itineraries(max_itineraries=3)
        
    except Exception as e:
        logger.error(f"Error fatal durante la optimización del itinerario: {e}", exc_info=True)
        return {'error': str(e), 'itineraries': []}
    
    # 3. Validar itinerarios
    validated_itineraries = []
    for itinerary in itineraries:
        validation = ItineraryValidator.validate_itinerary(
            itinerary, budget, optimizer.days
        )
        itinerary['validation'] = validation
        validated_itineraries.append(itinerary)
        
    # 4. Comparar itinerarios
    comparison = ItineraryComparator.compare_itineraries(
        validated_itineraries,
        user_priorities=None
    )
    
    result = {
        'itineraries': validated_itineraries,
        'comparison': comparison,
        'best_itinerary_index': comparison[0]['index'] if comparison else None
    }
    
    # 5. Incluir analytics si se solicita
    if include_analytics:
        result['analytics'] = {
            'optimization_report': optimizer.get_optimization_report(),
            'budget_sensitivity': analyze_budget_sensitivity(optimizer),
            'user_profile_used': {
                'experiencias': experiencias,
            }
        }
    
    return result