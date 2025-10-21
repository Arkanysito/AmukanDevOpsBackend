from django.core.management.base import BaseCommand
from django.db import models
from apps.users.models import CustomUser, UserInterest
from apps.recommendation.services import recommend_places, get_user_vector, get_optimized_services_queryset
from apps.location.models import Zone, Place
import numpy as np

class Command(BaseCommand):
    help = 'Debug detallado del sistema de recomendaciones'
    
    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='ID de usuario específico')
        parser.add_argument('--zone', type=str, help='ID de zona')
    
    def handle(self, *args, **options):
        user_id = options.get('user')
        zone_id = options.get('zone')
        
        # Usar el usuario con más intereses para debug
        if user_id:
            users = CustomUser.objects.filter(id=user_id)
        else:
            # Encontrar usuario con más intereses
            users = CustomUser.objects.annotate(
                interest_count=models.Count('userinterest')
            ).order_by('-interest_count')[:1]
        
        zone = None
        if zone_id:
            zone = Zone.objects.get(zone_id=zone_id)
        
        for user in users:
            self.debug_user_recommendations(user, zone)
    
    def debug_user_recommendations(self, user, zone):
        print(f"\n{'='*60}")
        print(f"🔍 DEBUG DETALLADO - Usuario: {user.id}")
        print(f"{'='*60}")
        
        # 1. VER INTERESES DEL USUARIO
        interests = UserInterest.objects.filter(user_id=user).select_related('interest_id')
        print(f"❤️  INTERESES DEL USUARIO ({interests.count()}):")
        for interest in interests:
            print(f"   - {interest.interest_id.name} (peso: {interest.weight:.2f})")
        
        # 2. VER VECTOR DE USUARIO
        user_vector = get_user_vector(user, use_cache=False)
        print(f"\n📊 VECTOR DE USUARIO:")
        print(f"   - Existe: {user_vector is not None}")
        if user_vector is not None:
            print(f"   - Dimensión: {user_vector.shape}")
            print(f"   - Norma: {np.linalg.norm(user_vector):.4f}")
            print(f"   - Valores sample: {user_vector[:5]}...")  # Primeros 5 valores
        
        # 3. VER SERVICIOS DISPONIBLES
        services = get_optimized_services_queryset('accommodation', zone)
        print(f"\n🏨 SERVICIOS DISPONIBLES EN ZONA: {services.count()}")
        
        # 4. VER RECOMENDACIONES CON DETALLE
        recommendations = recommend_places(user, 'accommodation', zone, top_k=10, use_cache=False)
        print(f"\n🎯 TOP 10 RECOMENDACIONES:")
        
        for i, (service, score) in enumerate(recommendations):
            service_id = getattr(service, 'place_id', 'Unknown')
            service_name = getattr(service, 'name', 'No name')
            service_type = getattr(service, 'type', 'No type')
            
            print(f"\n   {i+1}. {service_name}")
            print(f"      ID: {service_id}")
            print(f"      Tipo: {service_type}")
            print(f"      Score: {score:.4f}")
            
            # Ver embedding del servicio
            if hasattr(service, 'embedding') and service.embedding:
                try:
                    emb_array = np.array(service.embedding, dtype=np.float32)
                    print(f"      Embedding: dim={emb_array.shape}, norm={np.linalg.norm(emb_array):.4f}")
                    
                    # Calcular similitud manualmente si tenemos vector de usuario
                    if user_vector is not None and user_vector.size == emb_array.size:
                        similarity = np.dot(user_vector, emb_array) / (np.linalg.norm(user_vector) * np.linalg.norm(emb_array))
                        print(f"      Similitud manual: {similarity:.4f}")
                except Exception as e:
                    print(f"      Error con embedding: {e}")
            else:
                print(f"      ⚠️  SIN EMBEDDING - Probablemente recomendación por rating")
            
            # Ver rating si existe
            if hasattr(service, 'rating'):
                print(f"      Rating: {getattr(service, 'rating', 'N/A')}")
        
        # 5. VER SERVICIOS QUE DEBERÍA RECOMENDAR (por intereses)
        print(f"\n🔍 SERVICIOS QUE DEBERÍA RECOMENDAR (por intereses):")
        from django.db.models import Q
        
        recommended_services = []
        for interest in interests:
            interest_name = interest.interest_id.name.lower()
            weight = interest.weight
            
            # Buscar servicios que coincidan
            matching = Place.objects.filter(
                Q(name__icontains=interest_name) | 
                Q(type__icontains=interest_name) |
                Q(description__icontains=interest_name)
            ).exclude(embedding=None)[:3]
            
            for service in matching:
                service_id = getattr(service, 'place_id', 'Unknown')
                if service_id not in [s[0].place_id for s in recommendations if hasattr(s[0], 'place_id')]:
                    recommended_services.append((service, interest_name, weight))
        
        for service, interest, weight in recommended_services[:5]:  # Mostrar solo 5
            print(f"   - {service.name} (por interés: '{interest}', peso: {weight:.2f})")