import logging
from django.core.management.base import BaseCommand
from apps.users.models import Interest

# Configurar un logger simple para este comando
logger = logging.getLogger(__name__)

# Lista de intereses optimizada para recomendaciones de viajes
INTERESTS_LIST = [
    # --- Naturaleza y Aire Libre ---
    "Hiking", "Trekking", "Playas", "Montañas", "Parques Nacionales", 
    "Observación de Vida Silvestre", "Observación de Aves", "Camping", 
    "Buceo", "Snorkel", "Surf", "Esquí", "Snowboard", "Jardines Botánicos", 
    "Lagos", "Ríos", "Cascadas", "Ciclismo de Montaña",

    # --- Cultura e Historia ---
    "Museos", "Galerías de Arte", "Sitios Históricos", "Ruinas Arqueológicas", 
    "Arquitectura", "Castillos", "Palacios", "Teatro", "Ópera", 
    "Música Clásica", "Cultura Local", "Sitios Religiosos", "Monumentos", "Bibliotecas",

    # --- Gastronomía y Vida Nocturna ---
    "Alta Cocina", "Gastronomía Local", "Comida Callejera", "Cafeterías", 
    "Cultura del Café", "Cata de Vinos", "Cervecerías Artesanales", 
    "Bares de Cócteles", "Vida Nocturna", "Discotecas", "Comida Vegana", "Mercados Gourmet",

    # --- Actividades y Aventura ---
    "Parques de Aventura", "Parques Temáticos", "Tirolesa (Zip-lining)", 
    "Escalada en Roca", "Kayak", "Canotaje", "Rafting", "Ciclismo Urbano", 
    "Golf", "Paseos a Caballo", "Vuelo en Globo Aerostático", "Parapente",

    # --- Relajación y Bienestar ---
    "Spas", "Retiros de Bienestar", "Yoga", "Meditación", "Aguas Termales", 
    "Tomar el Sol", "Resorts de Lujo", "Piscinas",

    # --- Compras y Entretenimiento ---
    "Centros Comerciales (Malls)", "Mercados Locales", "Artesanías", "Tiendas de Lujo", 
    "Tiendas de Ropa (Moda)", "Cines", "Conciertos", "Música en Vivo", "Festivales", "Deportes (Estadios)",

    # --- Temas Específicos/Nichos ---
    "Fotografía", "Viaje Sostenible", "Ecoturismo", "Actividades Familiares", 
    "Viaje Económico (Backpacking)", "Viaje de Lujo", "Voluntariado", "Vida Rural",
    "Tecnología", "Historia Militar"
]


class Command(BaseCommand):
    """
    Comando de Django para poblar la base de datos con una lista predefinida de intereses.
    
    Uso: python manage.py add_interests
    """
    help = 'Puebla la base de datos con intereses para el sistema de recomendaciones.'

    def handle(self, *args, **options):
        """
        Lógica principal del comando.
        """
        self.stdout.write(self.style.SUCCESS('Iniciando la carga de intereses...'))
        
        created_count = 0
        skipped_count = 0
        
        for interest_name in INTERESTS_LIST:
            # get_or_create previene duplicados.
            # Devuelve (objeto, created_boolean)
            try:
                obj, created = Interest.objects.get_or_create(name=interest_name)
                
                if created:
                    self.stdout.write(f'  [+] Creado: {obj.name}')
                    created_count += 1
                else:
                    skipped_count += 1
                    
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error al crear "{interest_name}": {e}'))
                logger.error(f'Error al crear "{interest_name}": {e}')

        # Mensaje de resumen
        if skipped_count > 0:
             self.stdout.write(f'\n  [=] Omitidos (ya existían): {skipped_count}')
       
        self.stdout.write(self.style.SUCCESS('\n--- Proceso Finalizado ---'))
        self.stdout.write(f'Intereses nuevos creados: {created_count}')
        
        try:
            total_interests = Interest.objects.count()
            self.stdout.write(f'Total de intereses en la BD: {total_interests}')
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'No se pudo contar el total de intereses: {e}'))