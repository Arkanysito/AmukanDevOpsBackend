# En serializers.py
from rest_framework import serializers
from apps.location.models import Place

class PlaceRecoSerializer(serializers.ModelSerializer):
    score = serializers.SerializerMethodField()
    type_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Place
        fields = [
            "place_id", 
            "name", 
            "type", 
            "type_display",
            "description", 
            "rating", 
            "score"
        ]
    
    def get_score(self, obj):
        # Obtener el score del contexto
        return self.context.get('score', 0.0)
    
    def get_type_display(self, obj):
        # Para mostrar el tipo de forma más legible
        return obj.get_type_display() if hasattr(obj, 'get_type_display') else obj.type