from .models import CustomUser
from rest_framework import serializers

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