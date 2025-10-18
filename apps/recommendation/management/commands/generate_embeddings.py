from itertools import chain
from django.core.management.base import BaseCommand
from apps.location.models import Place
from apps.experiences.models import AccommodationService, ActivityService, Event
from apps.recommendation.services import encode_texts 

class Command(BaseCommand):
    help = "Genera embeddings para todos los Places"

    def handle(self, *args, **options):
        self.stdout.write("Generando embeddings con transformers...")
        
        # Procesar Places en lotes para mejor rendimiento
        places = Place.objects.all()
        self.stdout.write(f"Procesando {places.count()} places...")
        
        for place in places:
            place_type = place.type if place.type != 'nan' else ''
            description = place.description if place.description != 'nan' else ''
            text = f"{place.name}. {place_type}. {description}"
            
            emb = encode_texts(text)[0].tolist()  # [0] porque encode_texts retorna array 2D
            place.embedding = emb
            place.save(update_fields=["embedding"])
        
        # Procesar servicios
        services = list(chain(
            AccommodationService.objects.all(), 
            ActivityService.objects.all(), 
            Event.objects.all()
        ))
        
        self.stdout.write(f"Procesando {len(services)} servicios...")
        
        for service in services:
            service_description = service.description if service.description != 'nan' else ''
            text = f"{service.name}. {service_description}"
            
            emb = encode_texts(text)[0].tolist()
            service.embedding = emb
            service.save(update_fields=["embedding"])

        self.stdout.write(self.style.SUCCESS("Embeddings generados exitosamente"))