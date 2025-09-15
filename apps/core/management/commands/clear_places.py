# tu_app/management/commands/clear_places.py
from django.core.management.base import BaseCommand
from apps.location.models import Place

class Command(BaseCommand):
    help = 'Elimina todos los lugares de la base de datos'

    def handle(self, *args, **kwargs):
        count = Place.objects.count()
        Place.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'Se eliminaron {count} lugares.'))