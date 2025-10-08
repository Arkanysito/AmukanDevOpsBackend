from django.core.management.base import BaseCommand
from apps.users.models import CustomUser
from apps.recommendation.profile_analyzer import UserProfileAnalyzer

class Command(BaseCommand):
    help = 'Analiza interacciones y actualiza perfiles de usuarios'
    
    def handle(self, *args, **options):
        users = CustomUser.objects.filter(is_active=True)
        
        for user in users:
            analyzer = UserProfileAnalyzer(user)
            analyzer.analyze_recent_interactions(days=30)
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Perfiles actualizados para {users.count()} usuarios')
        )