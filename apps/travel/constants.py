from apps.core.constants import PlaceType

# --- Estrategia y Perfil de Usuario ---
STRATEGY_ADJUSTMENTS_BY_USER_TYPE = {
    'mochilero': 'budget',
    'económico': 'budget',
    'turista': 'balanced',
    'premium': 'premium',
    'lujo': 'premium',
    'aventurero': 'balanced',
    'cultural': 'balanced',
    'familiar': 'balanced'
}

MEAL_BUDGET_RATIOS_BY_USER_TYPE = {
    'mochilero': 0.2,
    'económico': 0.25,
    'turista': 0.3,
    'premium': 0.35,
    'lujo': 0.4,
    'aventurero': 0.25,
    'cultural': 0.3,
    'familiar': 0.35
}

DEFAULT_MEAL_BUDGET_RATIO = 0.3

# --- Costos de Comida ---
MEAL_COSTS_BY_STRATEGY = {
    'budget': {'breakfast': 5, 'lunch': 10, 'dinner': 15},
    'balanced': {'breakfast': 8, 'lunch': 15, 'dinner': 25},
    'premium': {'breakfast': 15, 'lunch': 25, 'dinner': 40}
}

# --- Optimización ---
MAX_TRAVEL_TIME_MINUTES = 20 # Minutos máximo entre actividades

# --- Mapeo de Experiencias y Categorías ---
EXPERIENCIA_MATCH_BONUS = 1.3 # 30% de bonus

EXPERIENCIA_TO_CATEGORIES_MAP = {
    'Aventura': ['adventure', 'sports', 'outdoor', 'extreme', 'hiking', 'climbing'],
    'Cultura': ['cultural', 'museum', 'historical', 'art', 'heritage', 'architecture'],
    'Gastronomía': ['gastronomy', 'food', 'wine', 'culinary', 'cooking', 'tasting'],
    'Relax': ['relaxation', 'spa', 'wellness', 'leisure', 'yoga', 'meditation'],
    'Naturaleza': ['nature', 'ecotourism', 'wildlife', 'park', 'garden', 'beach'],
    'Urbano': ['urban', 'shopping', 'entertainment', 'city', 'nightlife', 'theater'],
    'Familiar': ['family', 'kids', 'amusement', 'educational', 'playground', 'zoo'],
    'Romántico': ['romantic', 'luxury', 'couples', 'intimate', 'scenic', 'viewpoint']
}

KEYWORD_MAPPING = {
    'aventura': 'adventure',
    'cultura': 'cultural',
    'gastronomía': 'gastronomy',
    'relax': 'relaxation',
    'naturaleza': 'nature',
    'urbano': 'urban',
    'familiar': 'family',
    'romántico': 'romantic'
}

# --- Tipos de Place (para data_provider) ---
ACCOMMODATION_TYPES = [
    PlaceType.HOTEL, PlaceType.HOSTEL, PlaceType.GUEST_HOUSE,
    PlaceType.RESORT, PlaceType.BED_BREAKFAST, PlaceType.MOTEL,
    PlaceType.CAMPSITE
]

RESTAURANT_TYPES = [
    PlaceType.RESTAURANT, PlaceType.CAFE, PlaceType.BAR, PlaceType.PUB,
    PlaceType.FAST_FOOD, PlaceType.ICE_CREAM
]