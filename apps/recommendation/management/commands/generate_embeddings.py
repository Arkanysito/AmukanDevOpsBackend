from django.core.management.base import BaseCommand
from apps.location.models import Place
from sentence_transformers import SentenceTransformer

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
        self.stdout.write(self.style.SUCCESS("Embeddings generados"))
