from django.core.management.base import BaseCommand
from apps.recommendation.metrics_calculator import RecommendationMetricsCalculator
from apps.users.models import CustomUser
from apps.location.models import Zone

class Command(BaseCommand):
    help = 'Calcula métricas del sistema de recomendaciones'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--service-type',
            type=str,
            default='accommodation',
            help='Tipo de servicio (accommodation, activity, event, restaurant)'
        )
        parser.add_argument(
            '--zone',
            type=str,
            help='ID de la zona específica (UUID)'
        )
        parser.add_argument(
            '--users',
            type=int,
            default=10,
            help='Número de usuarios para evaluar'
        )
    
    def handle(self, *args, **options):
        calculator = RecommendationMetricsCalculator()
        
        # Obtener usuarios de prueba
        test_users = CustomUser.objects.all()[:options['users']]
        
        # Obtener zona si se especificó
        zone = None
        if options['zone']:
            try:
                # Para UUID, usamos zone_id
                zone = Zone.objects.get(zone_id=options['zone'])
            except Zone.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"⚠️  Zona {options['zone']} no encontrada, usando todas las zonas")
                )
        
        if not test_users:
            self.stdout.write(
                self.style.ERROR('❌ No hay usuarios para evaluar')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'🔍 Evaluando {len(test_users)} usuarios...')
        )
        
        # Calcular métricas
        metrics = calculator.calculate_all_metrics(
            test_users=test_users,
            service_type=options['service_type'],
            zone=zone
        )
        
        # Mostrar reporte
        calculator.print_metrics_report(metrics)
        
        self.stdout.write(
            self.style.SUCCESS('✅ Métricas calculadas exitosamente')
        )