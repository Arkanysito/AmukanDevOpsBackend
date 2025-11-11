# apps/recommendation/serializers.py
from rest_framework import serializers
from apps.location.models import Place
from apps.experiences.models import ActivityService, Event
from apps.core.s3_utils import build_public_url


def get_cover_image_url(self, obj):
    """Calcula y devuelve la URL pública de la imagen de portada."""
    if obj.cover_image:
        return build_public_url(obj.cover_image.bucket, obj.cover_image.object_key)
    return None

class PlaceRecoSerializer(serializers.ModelSerializer):
    score = serializers.SerializerMethodField()
    type_display = serializers.SerializerMethodField()
    coordinates = serializers.SerializerMethodField()
    average_price = serializers.SerializerMethodField()
    place_id = serializers.CharField(source='pk') 
    cover_image_url = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Place
        fields = [
            "place_id", 
            "name", 
            "type", 
            "type_display",
            "description", 
            "rating", 
            "score",
            "coordinates",
            "average_price",
            'cover_image_url',
            'organization_name',
        ]
    
    get_cover_image_url = get_cover_image_url
    
    def get_score(self, obj):
        return self.context.get('score', 0.0)
    
    def get_type_display(self, obj):
        return obj.get_type_display() if hasattr(obj, 'get_type_display') else obj.type

    def get_coordinates(self, obj):
        return obj.coordinates.wkt if obj.coordinates else None

    def get_average_price(self, obj):
        return obj.average_price

    def get_organization_name(self, obj):
        return obj.organization_id.name if obj.organization_id else None


class ActivityServiceRecoSerializer(serializers.ModelSerializer):
    score = serializers.SerializerMethodField()
    service_id = serializers.CharField(source='pk')
    name = serializers.CharField(source='place_id.name', read_only=True)
    description = serializers.CharField(source='place_id.description', read_only=True)
    coordinates = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ActivityService
        fields = [
            "service_id",
            "name",
            "description",
            "rating",
            "price",
            "coordinates",
            "score",
            'cover_image_url',
            'organization_name',
        ]

    get_cover_image_url = get_cover_image_url

    def get_score(self, obj):
        return self.context.get('score', 0.0)

    def get_coordinates(self, obj):
        if obj.place_id and obj.place_id.coordinates:
            return obj.place_id.coordinates.wkt
        return None

    def get_organization_name(self, obj):
        return obj.organization_id.name if obj.organization_id else None


class EventRecoSerializer(serializers.ModelSerializer):
    score = serializers.SerializerMethodField()
    event_id = serializers.CharField(source='pk')
    coordinates = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    organization_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Event
        fields = [
            "event_id",
            "name",
            "description",
            "rating",
            "price",
            "coordinates",
            "score",
            "start_date",
            "end_date",
            'cover_image_url',
            'organization_name',
        ]

    get_cover_image_url = get_cover_image_url    

    def get_score(self, obj):
        return self.context.get('score', 0.0)

    def get_coordinates(self, obj):
        if obj.place_id and obj.place_id.coordinates:
            return obj.place_id.coordinates.wkt
        return None

    def get_organization_name(self, obj):
        return obj.organization_id.name if obj.organization_id else None