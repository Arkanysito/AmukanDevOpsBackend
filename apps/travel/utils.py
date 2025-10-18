
def obtener_coordenadas_servicio(service_obj):
    """
    Función helper para obtener coordenadas de cualquier tipo de servicio
    """
    if not service_obj:
        return None
    
    try:
        # Para servicios con place_id (AccommodationService, ActivityService)
        if hasattr(service_obj, 'place_id') and service_obj.place_id:
            place = service_obj.place_id
            if hasattr(place, 'coordinates') and place.coordinates:
                return formatear_coordenadas(place.coordinates)
        
        # Para Place directamente
        elif hasattr(service_obj, 'coordinates') and service_obj.coordinates:
            return formatear_coordenadas(service_obj.coordinates)
        
        # Para Event
        elif hasattr(service_obj, 'place_id') and service_obj.place_id:
            place = service_obj.place_id
            if hasattr(place, 'coordinates') and place.coordinates:
                return formatear_coordenadas(place.coordinates)
                
    except Exception as e:
        print(f"Error obteniendo coordenadas: {e}")
    
    return None

def formatear_coordenadas(coordinates):
    """Formatea coordenadas para el frontend"""
    try:
        # Para Django GIS PointField
        if hasattr(coordinates, 'x') and hasattr(coordinates, 'y'):
            return {
                'lat': coordinates.y,
                'lng': coordinates.x
            }
        # Para string WKT
        elif hasattr(coordinates, 'wkt'):
            import re
            match = re.match(r'POINT\(([-\d.]+) ([-\d.]+)\)', coordinates.wkt)
            if match:
                lng, lat = match.groups()
                return {
                    'lat': float(lat),
                    'lng': float(lng)
                }
        # Si ya es un dict
        elif isinstance(coordinates, dict):
            return coordinates
            
    except Exception as e:
        print(f"Error formateando coordenadas: {e}")
    
    return None