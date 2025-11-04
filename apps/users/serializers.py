# apps/users/serializers.py

from rest_framework import serializers
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from .models import CustomUser, UserFavorite
from apps.organizations.models import OrganizationUser
from apps.core.constants import OrganizationCategory

ALL_CREATION_OPTIONS = [
    {
        "key": "event",
        "label": "Crear Evento",
        "link": "/crear-evento",
        "icon": "🎉",
    },
    {
        "key": "accommodation",
        "label": "Crear Alojamiento",
        "link": "/crear-servicio/accommodation",
        "icon": "🏨",
    },
    {
        "key": "activity",
        "label": "Crear Actividad",
        "link": "/crear-servicio/activity",
        "icon": "🎯",
    },
    {
        "key": "place",
        "label": "Crear Lugar",
        "link": "/crear-lugar",
        "icon": "📍",
    },
    {
        "key": "transport",
        "label": "Crear Transporte",
        "link": "/crear-servicio/transport",
        "icon": "🚗",
    },
]

def get_allowed_keys_for_category(category):
    if category == OrganizationCategory.ACCOMMODATION:
        return ["accommodation", "place", "event"]
    elif category == OrganizationCategory.EVENT_PRODUCTION:
        return ["event"]
    elif category == OrganizationCategory.GOVERNMENT:
        return ["activity", "place", "event"]
    elif category == OrganizationCategory.GASTRONOMY:
        return ["place", "event"]
    elif category == OrganizationCategory.TOURS_AND_ACTIVITIES:
        return ["activity", "event"]
    elif category == OrganizationCategory.TRANSPORT:
        return ["transport", "event"]
    elif category == OrganizationCategory.RETAIL:
        return ["place", "event"]
    else:
        return ["event"] if category else []


class UserSerializer(serializers.ModelSerializer):
    organization_category = serializers.SerializerMethodField()
    creation_permissions = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id", "username", "email", "password",
            "first_name", "last_name",
            "gender", "nationality", "language", "currency",
            "organization_category",
            "creation_permissions"
        ]
        extra_kwargs = {
            "password": {"write_only": True, "required": False}
        }

    def get_organization_category(self, user):
        """
        Lee la categoría desde la data precargada (prefetch_related)
        """
        org_user_set = user.organizationuser_set.all()
        if org_user_set:
            return org_user_set[0].organization_id.category
        return None

    def get_creation_permissions(self, user):
        """
        Lee la categoría del usuario (desde el prefetch) y devuelve
        la lista filtrada de opciones de creación.
        """
        category = None
        org_user_set = user.organizationuser_set.all()
        if org_user_set:
            category = org_user_set[0].organization_id.category
        
        elif not category and hasattr(user, 'id'):
             try:
                org_user = OrganizationUser.objects.select_related('organization_id').get(user_id=user)
                category = org_user.organization_id.category
             except OrganizationUser.DoesNotExist:
                pass 
        
        allowed_keys = get_allowed_keys_for_category(category)
        
        allowed_options = [
            option for option in ALL_CREATION_OPTIONS 
            if option["key"] in allowed_keys
        ]
        
        return allowed_options

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
    "activity": "experiences.ActivityService",
    "place": "location.Place",
    "event": "experiences.Event",
}

def resolve_content_type_for_target_type(target_type: str) -> ContentType:
    model_path = TARGET_TYPE_TO_MODEL_PATH.get(target_type)
    if not model_path:
        raise ValueError(f"target_type inválido: {target_type}. Opciones válidas: {list(TARGET_TYPE_TO_MODEL_PATH.keys())}")
    
    try:
        app_label, model_name = model_path.split(".")
        model_class = apps.get_model(app_label=app_label, model_name=model_name)
        if model_class is None:
            raise ValueError(f"Modelo no encontrado para {model_path}")
        return ContentType.objects.get_for_model(model_class)
    except LookupError as e:
        raise ValueError(f"Error al cargar el modelo {model_path}: {str(e)}")

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
        favorite, created = UserFavorite.objects.get_or_create(
            user_id=current_user,
            content_type=validated_data["content_type"],
            object_id=validated_data["object_id"],
        )
        return favorite