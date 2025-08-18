from .models import CustomUser
from rest_framework import serializers

class UserSerializer(serializers.ModelSerializer):
    nombreApellido = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = [
            "id", "username", "email", "password",
            "gender", "nationality", "language", "currency",
            "nombreApellido"
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def create(self, validated_data):
        full_name = validated_data.pop("nombreApellido", "")
        parts = full_name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        user = CustomUser.objects.create_user(
            first_name=first_name,
            last_name=last_name,
            **validated_data
        )
        return user