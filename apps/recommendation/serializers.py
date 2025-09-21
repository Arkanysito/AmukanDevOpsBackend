from rest_framework import serializers
from apps.location.models import Place

class PlaceRecoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Place
        fields = ["place_id", "name", "description", "rating"]
