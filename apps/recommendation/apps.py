from django.apps import AppConfig


class RecommendationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.recommendation'
    verbose_name = 'Recommendation System'
    
    def ready(self):
        """
        Se ejecuta cuando Django inicia.
        Precarga el modelo de embeddings para evitar delay en la primera request.
        """
        # Solo ejecutar en el proceso principal (no en workers de autoreload)
        import sys
        if 'runserver' not in sys.argv and 'gunicorn' not in sys.argv[0]:
            return
        

