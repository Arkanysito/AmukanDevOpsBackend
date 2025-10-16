from .models import CustomUser
from rest_framework import serializers
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from .models import UserFavorite

from .models import CustomUser
from rest_framework import serializers

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            "id", "username", "email", "password",
            "first_name", "last_name",
            "gender", "nationality", "language", "currency"
        ]
        extra_kwargs = {
            "password": {"write_only": True, "required": False}
        }

    def create(self, validated_data):
        # Remueve password para usar create_user
        password = validated_data.pop('password', None)
        user = CustomUser.objects.create_user(
            password=password,
            **validated_data
        )
        return user
    
    def update(self, instance, validated_data):
        # Remueve password si está presente
        password = validated_data.pop('password', None)
        
        # Actualiza campos normales
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Si hay password, la encripta
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance
    
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
        raise ValueError(f"target_type inválido: {target_type}")
    app_label, model_name = model_path.split(".")
    model_class = apps.get_model(app_label=app_label, model_name=model_name)
    if model_class is None:
        raise ValueError(f"Modelo no encontrado para {model_path}")
    return ContentType.objects.get_for_model(model_class)

class UserFavoriteSerializer(serializers.ModelSerializer):
    # Entrada
    target_type = serializers.ChoiceField(choices=list(TARGET_TYPE_TO_MODEL_PATH.keys()), write_only=True)
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
        ct = resolve_content_type_for_target_type(attrs["target_type"])
        model_cls = ct.model_class()

        if not model_cls.objects.filter(pk=attrs["target_id"]).exists():
            raise serializers.ValidationError({"target_id": "El objeto destino no existe."})

        attrs["content_type"] = ct
        attrs["object_id"] = attrs["target_id"]
        return attrs

    def create(self, validated_data):
        current_user = self.context["request"].user
        favorite, _ = UserFavorite.objects.get_or_create(
            user=current_user,
            content_type=validated_data["content_type"],
            object_id=validated_data["object_id"],
        )
        return favorite