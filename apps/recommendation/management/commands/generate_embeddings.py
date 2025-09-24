from itertools import chain
from django.core.management.base import BaseCommand
from apps.location.models import Place
from sentence_transformers import SentenceTransformer
from apps.experiences.models import AccommodationService, ActivityService, Event 

class Command(BaseCommand):
    help = "Genera embeddings para todos los Places"

    def handle(self, *args, **options):
        model = SentenceTransformer("all-MiniLM-L6-v2")
        for place in Place.objects.all():

            place_type = place.type
            if place_type == 'nan':
                place_type = ''
            text = f"{place.name}. {place_type}"
            emb = model.encode(text).tolist()
            place.embedding = emb
            place.save(update_fields=["embedding"])

        for service in chain(AccommodationService.objects.all(), ActivityService.objects.all(), Event.objects.all()):
            service_description = service.description
            if service_description == 'nan':
                service_description = ''
            text = f"{service.name}. {service_description}"
            emb = model.encode(text).tolist()
            service.embedding = emb
            service.save(update_fields=["embedding"])

        self.stdout.write(self.style.SUCCESS("Embeddings generados"))
