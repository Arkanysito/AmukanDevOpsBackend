from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers
from .models import UserFavorite

# Ajusta si cambia la ubicación de tus modelos reales
TARGET_TYPE_TO_MODEL_PATH = {
    "accommodation": "experiences.AccommodationService",
    "transport": "experiences.TransportService",
    "activity": "experiences.ActivityService",
    "place": "location.Place",
    "event": "experiences.Event",
}

def resolve_content_type_for_target_type(target_type: str) -> ContentType:
    model_path = TARGET_TYPE_TO_MODEL_PATH.get(target_type)
    if not model_path:
        raise serializers.ValidationError({"target_type": "Tipo de favorito no permitido."})
    app_label, model_name = model_path.split(".")
    model_class = apps.get_model(app_label, model_name)
    if model_class is None:
        raise serializers.ValidationError({"target_type": "Modelo destino no encontrado."})
    return ContentType.objects.get_for_model(model_class, for_concrete_model=False)


class UserFavoriteSerializer(serializers.ModelSerializer):
    # Entrada del cliente (lo que llega desde el mini corazón)
    target_type = serializers.CharField(write_only=True)
    target_id = serializers.UUIDField(write_only=True)

    # Salida
    user_fav_id = serializers.UUIDField(read_only=True)
    target_display_label = serializers.SerializerMethodField()

    class Meta:
        model = UserFavorite
        fields = ["user_fav_id", "target_type", "target_id", "target_display_label"]

    def get_target_display_label(self, favorite: UserFavorite):
        obj = favorite.target
        if not obj:
            return None
        for attr in ("name", "title"):
            if hasattr(obj, attr):
                return getattr(obj, attr)
        return str(obj)

    def validate(self, attrs):
        target_type = attrs["target_type"]
        target_uuid = attrs["target_id"]

        ct = resolve_content_type_for_target_type(target_type)
        model_class = ct.model_class()

        # Asegurar que el objeto exista
        try:
            model_class.objects.get(pk=target_uuid)
        except model_class.DoesNotExist:
            raise serializers.ValidationError({"target_id": "El objeto destino no existe."})

        # Normalizamos para create() con los NOMBRES DE COLUMNA exactos del modelo
        attrs["content_type"] = ct
        attrs["object_id"] = target_uuid
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        favorite, _created = UserFavorite.objects.get_or_create(
            user=user,
            content_type=validated_data["content_type"],
            object_id=validated_data["object_id"],
        )
        return favorite